import asyncio
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from contextlib import asynccontextmanager

from simulation import BuildingSimulation
from mcp_server import MCPServer
from ai_agent import AIAgent

# Define global simulation components
sim = BuildingSimulation()
mcp = MCPServer(sim)
agent = AIAgent(mcp)

sim_running = True
simulation_task = None

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                # Handle dead connections silently
                pass

manager = ConnectionManager()

async def run_simulation_loop():
    """Background task running the simulation clock and AI control loops."""
    global sim_running
    while True:
        try:
            if sim_running:
                # 1. AI Decision Cycle
                if sim.ai_enabled:
                    loop = asyncio.get_running_loop()
                    # Run AI queries in thread executor to keep websocket loop non-blocking
                    await loop.run_in_executor(None, agent.run_control_cycle)
                
                # 2. Advance simulation physics by 1 hour
                active, baseline = sim.step()
                
                # 3. Broadcast state to clients
                payload = {
                    "type": "sim_update",
                    "data": {
                        "active": active,
                        "baseline": baseline,
                        "ai_enabled": sim.ai_enabled,
                        "thoughts": sim.ai_thought_log,
                        "cumulative_cost": round(sim.cumulative_cost, 2),
                        "cumulative_carbon": round(sim.cumulative_carbon, 2),
                        "baseline_cumulative_cost": round(sim.baseline_cumulative_cost, 2),
                        "baseline_cumulative_carbon": round(sim.baseline_cumulative_carbon, 2)
                    }
                }
                await manager.broadcast(json.dumps(payload))
                
            await asyncio.sleep(2.0)  # 2 seconds = 1 simulated hour
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Simulation loop error: {e}")
            await asyncio.sleep(2.0)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global simulation_task
    # Startup: spawn background simulator loop
    simulation_task = asyncio.create_task(run_simulation_loop())
    yield
    # Shutdown: cancel task
    if simulation_task:
        simulation_task.cancel()

app = FastAPI(lifespan=lifespan)

# Allow CORS for local frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Schemas
class ToggleAIRequest(BaseModel):
    enabled: bool

class ManualSetpointRequest(BaseModel):
    zone_id: str
    cooling_setpoint: float
    heating_setpoint: float
    light_dim_level: float
    airflow_rate: float

class ScenarioRequest(BaseModel):
    scenario: str

@app.get("/api/state")
def get_state():
    """Retrieve full building status."""
    hour = sim.simulation_hour % 24
    outdoor = sim.get_weather(hour)
    
    zones_data = {}
    for zid, z in sim.zones.items():
        zones_data[zid] = {
            "name": z.name,
            "temperature": round(z.temp, 2),
            "cooling_setpoint": z.cooling_setpoint,
            "heating_setpoint": z.heating_setpoint,
            "light_dim_level": z.light_dim_level,
            "airflow_rate": z.airflow_rate,
            "pmv": round(z.pmv, 3),
            "ppd": round(z.ppd, 1),
            "hvac_power_kw": round((z.hvac_cooling_power + z.hvac_heating_power) / 1000.0, 3),
            "light_power_kw": round(z.lighting_power / 1000.0, 3)
        }
        
    return {
        "simulation_hour": sim.simulation_hour,
        "hour_of_day": hour,
        "active_scenario": sim.active_scenario,
        "outdoor_temp": outdoor["outdoor_temp"],
        "outdoor_humidity": outdoor["humidity"],
        "solar_rad": outdoor["solar_rad"],
        "electricity_price": sim.get_electricity_price(hour),
        "grid_carbon": sim.get_grid_carbon(hour),
        "occupancy_factor": round(sim.get_occupancy(hour), 2),
        "ai_enabled": sim.ai_enabled,
        "zones": zones_data,
        "cumulative_cost": round(sim.cumulative_cost, 2),
        "cumulative_carbon": round(sim.cumulative_carbon, 2),
        "baseline_cumulative_cost": round(sim.baseline_cumulative_cost, 2),
        "baseline_cumulative_carbon": round(sim.baseline_cumulative_carbon, 2),
        "savings_cost": round(sim.baseline_cumulative_cost - sim.cumulative_cost, 2),
        "savings_carbon": round(sim.baseline_cumulative_carbon - sim.cumulative_carbon, 2)
    }

@app.post("/api/toggle_ai")
def toggle_ai(data: ToggleAIRequest):
    sim.ai_enabled = data.enabled
    mode_str = "AI Optimization Enabled" if sim.ai_enabled else "AI Optimization Disabled (Manual Mode)"
    sim.add_ai_thought(mode_str)
    return {"status": "success", "ai_enabled": sim.ai_enabled}

@app.post("/api/manual_setpoint")
def manual_setpoint(data: ManualSetpointRequest):
    """Allows user overrides. Forces AI optimization off."""
    if data.zone_id not in sim.zones:
        raise HTTPException(status_code=404, detail="Zone not found")
        
    if data.cooling_setpoint <= data.heating_setpoint:
        raise HTTPException(status_code=400, detail="Cooling setpoint must exceed heating setpoint")
        
    # Disable AI
    sim.ai_enabled = False
    
    zone = sim.zones[data.zone_id]
    zone.cooling_setpoint = round(data.cooling_setpoint, 2)
    zone.heating_setpoint = round(data.heating_setpoint, 2)
    zone.light_dim_level = max(0.0, min(1.0, round(data.light_dim_level, 2)))
    zone.airflow_rate = max(0.05, min(1.5, round(data.airflow_rate, 2)))
    
    msg = f"Manual override in {zone.name}: Cooling={zone.cooling_setpoint}°C, Heating={zone.heating_setpoint}°C, Lights={int(zone.light_dim_level*100)}%"
    sim.add_ai_thought(msg)
    return {"status": "success", "message": msg, "ai_enabled": sim.ai_enabled}

@app.post("/api/scenario")
def change_scenario(data: ScenarioRequest):
    success = sim.set_scenarios(data.scenario)
    if not success:
        raise HTTPException(status_code=400, detail="Invalid scenario name")
    sim.add_ai_thought(f"Injected Scenario: {data.scenario.replace('_', ' ').title()}")
    return {"status": "success", "scenario": sim.active_scenario}

@app.post("/api/reset")
def reset_simulation():
    sim.set_scenarios(sim.active_scenario)
    sim.add_ai_thought("Simulation variables reset.")
    return {"status": "success"}

@app.get("/api/history")
def get_history():
    return {
        "active": sim.history,
        "baseline": sim.baseline_history
    }

@app.get("/api/thoughts")
def get_thoughts():
    return {"thoughts": sim.ai_thought_log}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, listen for any messages from client (not strictly required)
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)

if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False)

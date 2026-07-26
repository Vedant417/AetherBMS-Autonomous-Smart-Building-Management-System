import sys
import json
import asyncio
from simulation import BuildingSimulation

class MCPServer:
    def __init__(self, sim_instance: BuildingSimulation):
        self.sim = sim_instance
        self.tools = {
            "get_building_state": {
                "name": "get_building_state",
                "description": "Get current indoor/outdoor temperatures, occupant levels, energy consumption, tariffs, carbon intensity, and Fanger PMV comfort indices for all zones.",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
            "get_forecast": {
                "name": "get_forecast",
                "description": "Get a 24-hour forecast of outdoor temperature, solar radiation, occupancy levels, electricity tariffs, and grid carbon intensity.",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
            "set_zone_setpoints": {
                "name": "set_zone_setpoints",
                "description": "Modify the HVAC heating and cooling setpoints and ventilation airflow rate for a specific zone. Comfortable PMV ranges (-0.5 to +0.5) are usually achieved with setpoints around 20°C - 24°C.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "zone_id": {
                            "type": "string",
                            "enum": ["Zone_A_Executive", "Zone_B_Workspace", "Zone_C_DataRoom"],
                            "description": "The unique identifier of the target zone."
                        },
                        "cooling_setpoint": {
                            "type": "number",
                            "description": "Cooling thermostat setpoint in °C. The cooling HVAC activates if temp rises above this."
                        },
                        "heating_setpoint": {
                            "type": "number",
                            "description": "Heating thermostat setpoint in °C. The heating HVAC activates if temp drops below this."
                        },
                        "airflow_rate": {
                            "type": "number",
                            "minimum": 0.05,
                            "maximum": 1.5,
                            "description": "Ventilation airflow rate in m^3/s. Higher rates improve indoor air quality but increase energy cost if outdoor temp is extreme."
                        }
                    },
                    "required": ["zone_id", "cooling_setpoint", "heating_setpoint"]
                }
            },
            "optimize_lights": {
                "name": "optimize_lights",
                "description": "Set the lighting dimming levels in a zone. Dimming saves direct lighting power and reduces heat load in the zone.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "zone_id": {
                            "type": "string",
                            "enum": ["Zone_A_Executive", "Zone_B_Workspace", "Zone_C_DataRoom"],
                            "description": "The unique identifier of the target zone."
                        },
                        "light_dim_level": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                            "description": "Lighting dim level. 0.0 is fully dimmed (off), 1.0 is maximum brightness."
                        }
                    },
                    "required": ["zone_id", "light_dim_level"]
                }
            }
        }

    def execute_tool(self, name, arguments):
        """Executes a tool call locally against the building simulation instance."""
        try:
            if name == "get_building_state":
                hour = self.sim.simulation_hour % 24
                outdoor = self.sim.get_weather(hour)
                price = self.sim.get_electricity_price(hour)
                carbon = self.sim.get_grid_carbon(hour)
                
                zones_data = {}
                for zid, z in self.sim.zones.items():
                    zones_data[zid] = {
                        "name": z.name,
                        "temperature": round(z.temp, 2),
                        "cooling_setpoint": z.cooling_setpoint,
                        "heating_setpoint": z.heating_setpoint,
                        "light_dim_level": z.light_dim_level,
                        "airflow_rate": z.airflow_rate,
                        "pmv_comfort": round(z.pmv, 3),
                        "ppd_dissatisfied_pct": round(z.ppd, 1),
                        "hvac_cooling_w": round(z.hvac_cooling_power, 1),
                        "hvac_heating_w": round(z.hvac_heating_power, 1),
                        "lighting_w": round(z.lighting_power, 1),
                        "equipment_w": z.base_equipment_load
                    }
                
                return {
                    "simulation_hour": self.sim.simulation_hour,
                    "hour_of_day": hour,
                    "active_scenario": self.sim.active_scenario,
                    "outdoor_temp": outdoor["outdoor_temp"],
                    "outdoor_humidity": outdoor["humidity"],
                    "solar_rad": outdoor["solar_rad"],
                    "electricity_price_per_kwh": price,
                    "grid_carbon_kg_per_kwh": carbon,
                    "occupancy_factor": self.sim.get_occupancy(hour),
                    "zones": zones_data,
                    "cumulative_cost": round(self.sim.cumulative_cost, 2),
                    "cumulative_carbon": round(self.sim.cumulative_carbon, 2)
                }
                
            elif name == "get_forecast":
                forecast = []
                current_hour = self.sim.simulation_hour
                for h in range(1, 25):  # 24 hours lookahead
                    target_sim_hour = current_hour + h
                    hour_of_day = target_sim_hour % 24
                    outdoor = self.sim.get_weather(hour_of_day)
                    price = self.sim.get_electricity_price(hour_of_day)
                    carbon = self.sim.get_grid_carbon(hour_of_day)
                    occ = self.sim.get_occupancy(hour_of_day)
                    
                    forecast.append({
                        "hours_ahead": h,
                        "hour_of_day": hour_of_day,
                        "outdoor_temp": outdoor["outdoor_temp"],
                        "solar_rad": outdoor["solar_rad"],
                        "electricity_price_per_kwh": price,
                        "grid_carbon_kg_per_kwh": carbon,
                        "occupancy_factor": round(occ, 2)
                    })
                return {"forecast": forecast}
                
            elif name == "set_zone_setpoints":
                zid = arguments.get("zone_id")
                t_cool = arguments.get("cooling_setpoint")
                t_heat = arguments.get("heating_setpoint")
                flow = arguments.get("airflow_rate")
                
                if zid not in self.sim.zones:
                    return {"error": f"Zone '{zid}' not found."}
                
                zone = self.sim.zones[zid]
                
                # Validation: Cooling setpoint must be higher than heating setpoint
                if t_cool <= t_heat:
                    return {"error": "Cooling setpoint must be strictly greater than heating setpoint to prevent HVAC short-cycling."}
                    
                zone.cooling_setpoint = round(float(t_cool), 2)
                zone.heating_setpoint = round(float(t_heat), 2)
                if flow is not None:
                    zone.airflow_rate = max(0.05, min(1.5, round(float(flow), 2)))
                    
                msg = f"Setpoints updated for {zone.name}: Cooling={zone.cooling_setpoint}°C, Heating={zone.heating_setpoint}°C, Flow={zone.airflow_rate}m³/s"
                self.sim.add_ai_thought(msg)
                return {"status": "success", "message": msg}
                
            elif name == "optimize_lights":
                zid = arguments.get("zone_id")
                dim = arguments.get("light_dim_level")
                
                if zid not in self.sim.zones:
                    return {"error": f"Zone '{zid}' not found."}
                
                zone = self.sim.zones[zid]
                zone.light_dim_level = max(0.0, min(1.0, round(float(dim), 2)))
                
                msg = f"Lighting optimized for {zone.name}: Dimming={int(zone.light_dim_level * 100)}%"
                self.sim.add_ai_thought(msg)
                return {"status": "success", "message": msg}
                
            else:
                return {"error": f"Tool '{name}' not found."}
                
        except Exception as e:
            return {"error": str(e)}

    async def handle_stdio(self):
        """MCP standard JSON-RPC 2.0 stdio server interface."""
        sys.stderr.write("AetherBMS MCP stdio server started...\n")
        sys.stderr.flush()
        
        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)
        
        while True:
            line_bytes = await reader.readline()
            if not line_bytes:
                break
            
            line = line_bytes.decode('utf-8').strip()
            if not line:
                continue
                
            try:
                request = json.loads(line)
                req_id = request.get("id")
                method = request.get("method")
                
                if method == "tools/list":
                    response = {
                        "jsonrpc": "2.0",
                        "result": {
                            "tools": list(self.tools.values())
                        },
                        "id": req_id
                    }
                elif method == "tools/call":
                    params = request.get("params", {})
                    tool_name = params.get("name")
                    args = params.get("arguments", {})
                    
                    result = self.execute_tool(tool_name, args)
                    
                    response = {
                        "jsonrpc": "2.0",
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": json.dumps(result)
                                }
                            ]
                        },
                        "id": req_id
                    }
                elif method == "initialize":
                    response = {
                        "jsonrpc": "2.0",
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {
                                "tools": {}
                            },
                            "serverInfo": {
                                "name": "aether-bms-server",
                                "version": "1.0.0"
                            }
                        },
                        "id": req_id
                    }
                else:
                    response = {
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32601,
                            "message": f"Method {method} not found"
                        },
                        "id": req_id
                    }
                    
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
                
            except Exception as e:
                err_res = {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32603,
                        "message": str(e)
                    },
                    "id": None
                }
                sys.stdout.write(json.dumps(err_res) + "\n")
                sys.stdout.flush()

if __name__ == "__main__":
    # If run directly as a script, start the stdio server loop
    sim = BuildingSimulation()
    server = MCPServer(sim)
    asyncio.run(server.handle_stdio())

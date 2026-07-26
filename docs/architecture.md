# AetherBMS Architecture & Integration Documentation

AetherBMS (Autonomous Energy-Thermal Hybrid Efficient Real-time Building Management System) is an intelligent, closed-loop control system that optimizes commercial building energy draw and indoor carbon footprints while safeguarding occupant comfort. 

---

## 1. System Architecture

AetherBMS is structured as an event-driven, decoupled network of modules. Telemetry frames flow from the physical/simulated environment up to the AI client and are visualized live on a React dashboard.

```
       +---------------------------------------------+
       |             React Web Dashboard             |
       +---------------------------------------------+
                              ^
                              | (WebSockets & REST API)
                              v
       +---------------------------------------------+
       |             FastAPI Web Server              |
       +---------------------------------------------+
                              ^
                              | (Direct Memory Object Link)
                              v
+------------+        +------------------------------+
|  AI Agent  | <====> |  Physics Building Simulator  |
| (MCP Client)        +------------------------------+
+------------+                       ^
      ^                              | (MCP API Tools)
      | (JSON-RPC)                   v
      |               +------------------------------+
      +-------------> |          MCP Server          |
                      +------------------------------+
```

### Module Descriptions
1. **Building Physics Engine (`simulation.py`)**: Simulates thermodynamic heat transfer differential equations across three distinct thermal zones. It accounts for solar load, ventilation conduction, internal equipment gains, and Fanger's Predicted Mean Vote (PMV) comfort model.
2. **Model Context Protocol (MCP) Server (`mcp_server.py`)**: Implements the open standard protocol for tools calling via JSON-RPC 2.0. It exposes interfaces allowing the AI Agent to inspect telemetry, retrieve 24-hour weather/occupancy forecasts, and adjust HVAC/lighting operating parameters.
3. **AI Autonomous Agent (`ai_agent.py`)**: Acts as the MCP Client. Every simulated hour, it collects building metrics, targets optimization goals, and queries Groq API (via REST API using Llama 3.3) for tool invocation decisions. If offline or no key is provided, it falls back to a high-fidelity local MPC rule-based optimizer.
4. **FastAPI Web Server (`server.py`)**: Exposes REST endpoints to toggle modes, inject scenarios (Heatwaves, Storms, Carbon Peaks), and runs a WebSocket server (`/ws`) that broadcasts building states every 2 seconds (1 simulated hour per 2 seconds).
5. **Vite React Dashboard**: Built with Recharts and Tailwind CSS, featuring glassmorphic designs, zone indicators that reflect live indoor comfort, and a scrolling viewport displaying the AI's real-time thought trace.

---

## 2. Dynamic Thermodynamic Physics Model

The core thermodynamics loop computes temperature transitions using a multi-zone thermal resistance-capacitance (RC) formulation:

$$C_i \frac{dT_i}{dt} = Q_{\text{hvac},i} + Q_{\text{solar},i} + Q_{\text{internal},i} + U_i A_i (T_{\text{ext}} - T_i) + \dot{m}_i C_p (T_{\text{ext}} - T_i)$$

Where:
* $T_i$ = Dry-bulb temperature of zone $i$ (°C)
* $C_i$ = Effective thermal capacitance of zone $i$ (kJ/K)
* $Q_{\text{hvac},i}$ = Sensible heating or cooling power added by the HVAC system (W)
* $Q_{\text{solar},i}$ = Solar radiation heat gain transmitted through windows (W)
* $Q_{\text{internal},i}$ = Internal sensible heat gains (occupants + lighting + computers) (W)
* $U_i A_i$ = Envelope heat transmission coefficient and surface area (W/K)
* $\dot{m}_i C_p$ = Ventilation mass flow rate and air heat capacity (W/K)

### Occupant Thermal Comfort (Fanger's PMV Index)
Fanger's PMV model estimates thermal sensation on a scale from -3 (Too Cold) to +3 (Too Hot) using:

$$\text{PMV} = [0.303 e^{-0.036 M} + 0.028] \cdot (M - W - H_L)$$

Where $M$ is metabolic rate, $W$ is external work, and $H_L$ is dry and latent heat loss from the body (depending on clothing CLO, relative humidity, air temp, and local air velocity).
* Target comfort threshold: **$\text{PMV} \in [-0.5, +0.5]$** (ISO 7730 Comfort Category A/B).

---

## 3. Model Context Protocol (MCP) Compliance

The MCP Server implements the standard tool schema via stdin/stdout JSON-RPC 2.0 communication:

### Exposed Tools
* **`get_building_state`**: Retrieves real-time dry-bulb temp, HVAC cooling/heating draw, current utility price ($/kWh), carbon intensity (kg CO₂/kWh), and PMV comforts for all zones.
* **`get_forecast`**: Provides a 24-hour lookahead table of ambient outdoor temperatures, occupant occupancy factors, and time-of-use (TOU) electricity pricing.
* **`set_zone_setpoints`**: Updates cooling threshold, heating threshold, and ventilation rate ($m^3/s$) per zone.
* **`optimize_lights`**: Dims zone illumination down to daylight-harvesting levels ($0.0$ to $1.0$).

---

## 4. Real EnergyPlus Integration Strategy

To deploy AetherBMS in a production facility using EnergyPlus instead of the virtual simulator, follow this integration path:

```
+------------+       +---------------+       +------------------+
|  AI Agent  | <===> |  MCP Server   | <===> |  PyEp / PyFMI    |
| (MCP Client)       | (Python App)  |       | (Co-Sim Adapter) |
+------------+       +---------------+       +------------------+
                                                      ^
                                                      | (Actuate/Read)
                                                      v
                                             +------------------+
                                             |   EnergyPlus     |
                                             | (Building Model) |
                                             +------------------+
```

1. **FMU Co-Simulation**: Convert the building IDF model (`office_building.idf`) into a Functional Mock-up Unit (FMU) using the `EnergyPlusToFMU` compiler.
2. **Python Link (`pyfmi`)**: Replace the virtual `simulation.py` state references inside `mcp_server.py` with a PyFMI wrapper. PyFMI loads the `.fmu` container, drives the co-simulation clock, and updates variables dynamically.
3. **EnergyPlus API (v23+)**: Alternatively, load the EnergyPlus shared library directly via Python's standard `pyenergyplus` package. Register callbacks on target simulation time-steps to execute setpoints dynamically via our MCP tools.

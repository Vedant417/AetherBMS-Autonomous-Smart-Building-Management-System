# AetherBMS: Autonomous Smart Building Management System

AetherBMS (Autonomous Energy-Thermal Hybrid Efficient Real-time Building Management System) is an intelligent, closed-loop control system that optimizes commercial building energy draw and indoor carbon footprints while safeguarding occupant comfort. 

The system utilizes the Model Context Protocol (MCP) to bridge the physical/simulated thermodynamic building dynamics with a cognitive AI agent (powered by Llama 3.3 or local MPC rules) that evaluates real-time telemetry and makes setpoint adjustments. Telemetry and agent thoughts are streamed live to a premium glassmorphic React dashboard.

This project includes:
* **FastAPI Web Server**: Drives WebSocket telemetry streaming and scenario injection.
* **Building Physics Engine**: Custom 3-zone thermodynamic simulator modeling thermal capacity, solar load, and comfort indices.
* **Model Context Protocol (MCP) Server**: Implements JSON-RPC 2.0 tool execution over stdio.
* **AI Autonomous Agent**: An MCP client querying LLM endpoints to perform closed-loop load shifting and comfort tracking.
* **Vite React Dashboard**: Premium visual UI built with Recharts, Tailwind CSS, and custom glassmorphism components.
* **EnergyPlus Building Model**: Ready-to-deploy `.idf` model skeleton matching the simulated building configuration.

---

## 📂 Project Structure

```text
Autonomous Smart Building/
│
├── backend/
│   ├── ai_agent.py         (AI MCP Client / Groq Orchestration / Local MPC Fallback)
│   ├── mcp_server.py       (MCP JSON-RPC Server exposing building tools)
│   ├── server.py           (FastAPI Web Server / WebSocket Broadcast Gateway)
│   ├── simulation.py       (3-Zone Thermodynamic Simulator & PMV Index Engine)
│   ├── requirements.txt    (Backend Python Dependencies)
│   └── .env                (Environment Variables & API Keys)
│
├── building_models/
│   └── office_building.idf (EnergyPlus Model Skeleton for 3-Zone setup)
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx         (Vite React Web Dashboard & WS Client)
│   │   ├── index.css       (Global Styles & Tailwind Directives)
│   │   └── main.jsx        (Application Entrypoint)
│   ├── tailwind.config.js  (Tailwind Configuration)
│   ├── vite.config.js      (Vite Dev Server Configuration)
│   └── package.json        (Frontend Dependencies)
│
├── docs/
│   └── architecture.md     (Detailed System Architecture & Physics Specifications)
│
└── README.md               (Project Overview & Setup Documentation)
```

---

## ✨ Features

* **Closed-Loop AI Control**: The AI Agent functions as an MCP client. Every simulated hour, it gets building states, evaluates them, and invokes MCP tools (`set_zone_setpoints`, `optimize_lights`) to update active thermodynamic parameters.
* **MCP Stdio Server Compliance**: Exposes standard schemas via JSON-RPC 2.0. Can easily connect to any standard MCP host.
* **Multi-Zone Physics Simulation**: Models complex thermal resistance-capacitance (RC) equations across 3 zones (Executive Suite, Workspace, and Server Room) accounting for:
  - Envelope wall heat transmission (conduction)
  - Ventilation mass air flow
  - Solar radiation gains (directional East/West tracking)
  - Internal occupancy and equipment heat loads (e.g. constant 12kW Server Room load)
* **Occupant Comfort (Fanger's PMV Model)**: Continuously evaluates Predicted Mean Vote (PMV) and Predicted Percentage of Dissatisfied (PPD) comfort metrics to keep zones inside target comfort ranges ($-0.5$ to $+0.5$).
* **Dynamic Grid Load-Shifting**: Utilizes 24-hour lookahead forecasts of outdoor temperature, occupancy density, electricity prices, and grid carbon intensity to:
  - Pre-cool or pre-heat zones before high price periods.
  - Relax thermal setpoints (load-shedding) during grid strain.
* **Aesthetic Live Dashboard**: Responsive, glassmorphic UI displaying:
  - Live temperature meters and thermal comfort indices.
  - Dynamic graphs showing Active (AI-controlled) vs. Baseline (static schedule) cost and carbon savings.
  - Real-time AI thought-log displaying the agent's analytical decision flow.
* **Local Fallback Controller**: Automatically shifts to a local high-fidelity Model Predictive Control (MPC) rule-based optimizer if Groq API keys are not supplied, ensuring uninterrupted local operation.

---

## 🛠️ Technologies Used

### Backend
* **Python 3.11** - Core server logic and thermodynamic physics model.
* **FastAPI & Uvicorn** - High-performance ASGI web server and WebSocket broker.
* **Model Context Protocol (MCP)** - Open-source standard client/server protocol.
* **Groq API / Llama 3.3** - Remote AI orchestration and model reasoning.
* **NumPy** - Fast array-based mathematical operations.

### Frontend
* **React 18 (Vite)** - Fast Single Page Application framework.
* **Tailwind CSS** - Glassmorphism, grid systems, and layout design.
* **Recharts** - Responsive charts representing live building telemetry.
* **Lucide React** - High-quality vector icons.

---

## 💻 System Requirements

* **Python 3.10 - 3.12** (Recommended: `3.11`)
* **Node.js v18+**
* **Windows / macOS / Linux**

---

## 🚀 Setup & Installation

### 1. Clone the Repository
```bash
git clone https://github.com/YOUR_USERNAME/Autonomous-Smart-Building
cd "Autonomous Smart Building"
```

### 2. Backend Setup
The backend requires a Python environment. It is highly recommended to use a virtual environment.

```bash
cd backend
# Create virtual environment
python -m venv venv

# Activate on Windows:
.\venv\Scripts\activate
# Activate on Mac/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration
Create or modify the `.env` file inside the `backend/` directory:
```env
GROQ_API_KEY=your_groq_api_key_here
```
> **Note**: If `GROQ_API_KEY` is empty or missing, the system will fall back to the **Local Smart Optimizer** automatically.

### 4. Run the Backend Web Server
In the active virtual environment under the `backend/` directory, launch the FastAPI server:
```bash
python server.py
```
The console will log that the server is running on [http://127.0.0.1:8000](http://127.0.0.1:8000).

### 5. Frontend Setup & Run
Open a new terminal window, navigate to the `frontend/` directory, install dependencies, and start the Vite dev server:
```bash
cd frontend
npm install
npm run dev
```
The dashboard will launch locally and be available at: [http://localhost:5173](http://localhost:5173).

---

## 🧠 Closed-Loop Control Architecture

```text
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

1. **Infiltration & External Loads**: The physics engine in `simulation.py` runs thermodynamic updates using current weather (sinusoidal temperature shifts, solar radiation) and internal gains (occupants, devices, lighting heat).
2. **Telemetry Broadcast**: FastAPI reads variables, updates cumulative metrics (AI vs Baseline), and sends state updates to the React client via WebSockets.
3. **AI Evaluation**: Every simulated hour, if AI is enabled, the AI Agent (`ai_agent.py`) fetches data via the MCP Server tools, weighs optimization metrics, and computes optimized setpoint offsets.
4. **Control Ingestion**: Updates are written back into the simulation object via standard MCP schema calls, modifying setpoints for the next hour step.

---

## 📊 Thermodynamic Formulation

The core thermodynamics loop computes temperature updates using a multi-zone thermal resistance-capacitance (RC) formulation:

$$C_i \frac{dT_i}{dt} = Q_{\text{hvac},i} + Q_{\text{solar},i} + Q_{\text{internal},i} + U_i A_i (T_{\text{ext}} - T_i) + \dot{m}_i C_p (T_{\text{ext}} - T_i)$$

Where:
* $T_i$ = Indoor dry-bulb temperature of zone $i$ (°C)
* $C_i$ = Effective thermal capacitance of zone $i$ (kJ/K)
* $Q_{\text{hvac},i}$ = Sensible heating/cooling power added by HVAC (W)
* $Q_{\text{solar},i}$ = Solar radiation heat gain through windows (W)
* $Q_{\text{internal},i}$ = Internal heat gains (occupants, lighting, servers) (W)
* $U_i A_i$ = Wall heat transmission coefficient and surface area (W/K)
* $\dot{m}_i C_p$ = Ventilation mass flow rate and air heat capacity (W/K)

---

## 🔧 Troubleshooting

* **WebSocket Disconnected**: Check that your FastAPI server is running on port 8000. If port 8000 is occupied, update the port in `backend/server.py` and the `WS_URL` / `API_BASE` constants in `frontend/src/App.jsx`.
* **CORS Blockage**: FastAPI has CORS middleware configured to allow origins of `*` by default. Ensure your browser is not running security extensions that strip CORS headers.
* **LLM Fails to Generate Tools**: Check that your `.env` contains a valid Groq API Key and you are not exceeding your rate limits. Monitor the console standard error to view JSON-RPC tool calls.

---

## 📝 License
This project is licensed under the MIT License - see the LICENSE details for research and education purposes. Developed as a Capstone for Smart Building Automation and Cognitive Control Systems.

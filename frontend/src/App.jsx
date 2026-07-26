import React, { useState, useEffect, useRef } from 'react';
import { 
  Activity, 
  Cpu, 
  Settings, 
  Sun, 
  Wind, 
  Zap, 
  ShieldAlert, 
  CloudSun, 
  TrendingDown, 
  Leaf, 
  RefreshCw, 
  Clock, 
  CheckCircle2, 
  Thermometer, 
  Maximize2,
  Lock,
  UserCheck
} from 'lucide-react';
import { 
  ResponsiveContainer, 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  Tooltip, 
  Legend, 
  LineChart, 
  Line,
  CartesianGrid
} from 'recharts';

export default function App() {
  const [state, setState] = useState(null);
  const [history, setHistory] = useState({ active: [], baseline: [] });
  const [thoughts, setThoughts] = useState([]);
  const [selectedZone, setSelectedZone] = useState('Zone_B_Workspace');
  const [aiEnabled, setAiEnabled] = useState(false);
  const [scenario, setScenario] = useState('summer_heatwave');
  const [wsStatus, setWsStatus] = useState('connecting');
  
  // Manual Control states
  const [coolingSetpoint, setCoolingSetpoint] = useState(24);
  const [heatingSetpoint, setHeatingSetpoint] = useState(20);
  const [airflowRate, setAirflowRate] = useState(0.2);
  const [lightDimLevel, setLightDimLevel] = useState(1.0);

  const thoughtsEndRef = useRef(null);
  const socketRef = useRef(null);
  const lastSyncedZoneRef = useRef(null);
  const wasAiEnabledRef = useRef(false);

  const API_BASE = 'http://127.0.0.1:8000';
  const WS_URL = 'ws://127.0.0.1:8000/ws';

  // Fetch initial REST data
  const fetchData = async () => {
    try {
      const stateRes = await fetch(`${API_BASE}/api/state`);
      const stateData = await stateRes.json();
      setState(stateData);
      setAiEnabled(stateData.ai_enabled);
      setScenario(stateData.active_scenario);

      const histRes = await fetch(`${API_BASE}/api/history`);
      const histData = await histRes.json();
      setHistory(histData);

      const thoughtRes = await fetch(`${API_BASE}/api/thoughts`);
      const thoughtData = await thoughtRes.json();
      setThoughts(thoughtData.thoughts);
      
      // Update local sliders to match loaded state
      if (stateData.zones && stateData.zones[selectedZone]) {
        const zone = stateData.zones[selectedZone];
        setCoolingSetpoint(zone.cooling_setpoint);
        setHeatingSetpoint(zone.heating_setpoint);
        setAirflowRate(zone.airflow_rate);
        setLightDimLevel(zone.light_dim_level);
      }
    } catch (err) {
      console.error("Error loading server data:", err);
    }
  };

  // Setup WebSocket connection for live telemetry stream
  useEffect(() => {
    fetchData();

    const connectWS = () => {
      setWsStatus('connecting');
      const ws = new WebSocket(WS_URL);
      socketRef.current = ws;

      ws.onopen = () => {
        setWsStatus('connected');
      };

      ws.onmessage = (event) => {
        const payload = JSON.parse(event.data);
        if (payload.type === 'sim_update') {
          const update = payload.data;
          
          // Update state
          setState(prev => {
            if (!prev) return null;
            const hour = update.active.hour % 24;
            const zonesData = {};
            
            // Map flat active zones back to state shape
            for (const zid in update.active.zones) {
              const activeZ = update.active.zones[zid];
              zonesData[zid] = {
                name: prev.zones[zid]?.name || zid,
                temperature: activeZ.temp,
                cooling_setpoint: activeZ.cooling_setpoint,
                heating_setpoint: activeZ.heating_setpoint,
                light_dim_level: activeZ.light_dim_level,
                airflow_rate: activeZ.airflow_rate,
                pmv: activeZ.pmv,
                ppd: activeZ.ppd,
                hvac_power_kw: activeZ.hvac_power_kw,
                light_power_kw: activeZ.light_power_kw
              };
            }

            return {
              ...prev,
              simulation_hour: update.active.hour,
              hour_of_day: hour,
              outdoor_temp: update.active.outdoor_temp,
              outdoor_humidity: update.active.humidity,
              solar_rad: update.active.solar_rad,
              electricity_price: update.active.price,
              grid_carbon: update.active.carbon_intensity,
              occupancy_factor: update.active.occupancy,
              cumulative_cost: update.cumulative_cost,
              cumulative_carbon: update.cumulative_carbon,
              baseline_cumulative_cost: update.baseline_cumulative_cost,
              baseline_cumulative_carbon: update.baseline_cumulative_carbon,
              savings_cost: roundNum(update.baseline_cumulative_cost - update.cumulative_cost, 2),
              savings_carbon: roundNum(update.baseline_cumulative_carbon - update.cumulative_carbon, 2),
              zones: zonesData
            };
          });

          // Append to history for charts
          setHistory(prev => {
            const activeHist = [...prev.active, update.active];
            const baselineHist = [...prev.baseline, update.baseline];
            // Keep last 48 steps for graph performance
            if (activeHist.length > 48) activeHist.shift();
            if (baselineHist.length > 48) baselineHist.shift();
            return { active: activeHist, baseline: baselineHist };
          });

          // Update thoughts
          setThoughts(update.thoughts);
        }
      };

      ws.onclose = () => {
        setWsStatus('disconnected');
        // Reconnect after 3 seconds
        setTimeout(() => connectWS(), 3000);
      };

      ws.onerror = () => {
        setWsStatus('error');
        ws.close();
      };
    };

    connectWS();

    return () => {
      if (socketRef.current) socketRef.current.close();
    };
  }, []);

  // Sync state values to sliders selectively to prevent overwrite glitch
  useEffect(() => {
    if (!state?.zones?.[selectedZone]) return;
    const zone = state.zones[selectedZone];

    const zoneChanged = lastSyncedZoneRef.current !== selectedZone;
    const aiToggled = aiEnabled !== wasAiEnabledRef.current;
    const isInitial = lastSyncedZoneRef.current === null;
    const isReset = state.simulation_hour === 0;

    if (zoneChanged || aiEnabled || aiToggled || isInitial || isReset) {
      setCoolingSetpoint(zone.cooling_setpoint);
      setHeatingSetpoint(zone.heating_setpoint);
      setAirflowRate(zone.airflow_rate);
      setLightDimLevel(zone.light_dim_level);
      
      lastSyncedZoneRef.current = selectedZone;
      wasAiEnabledRef.current = aiEnabled;
    }
  }, [selectedZone, state, aiEnabled]);

  // Scroll to bottom of thoughts
  // useEffect(() => {
  //   thoughtsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  // }, [thoughts]);

  const roundNum = (val, dec) => {
    return Math.round(val * Math.pow(10, dec)) / Math.pow(10, dec);
  };

  const handleToggleAI = async (val) => {
    setAiEnabled(val);
    try {
      await fetch(`${API_BASE}/api/toggle_ai`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: val })
      });
    } catch (err) {
      console.error(err);
    }
  };

  const handleScenarioChange = async (scenName) => {
    setScenario(scenName);
    try {
      const res = await fetch(`${API_BASE}/api/scenario`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario: scenName })
      });
      const data = await res.json();
      fetchData(); // reload simulation history & thoughts
    } catch (err) {
      console.error(err);
    }
  };

  const handleReset = async () => {
    try {
      await fetch(`${API_BASE}/api/reset`, { method: 'POST' });
      fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  const handleApplyManualSettings = async () => {
    try {
      setAiEnabled(false);
      const res = await fetch(`${API_BASE}/api/manual_setpoint`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          zone_id: selectedZone,
          cooling_setpoint: parseFloat(coolingSetpoint),
          heating_setpoint: parseFloat(heatingSetpoint),
          light_dim_level: parseFloat(lightDimLevel),
          airflow_rate: parseFloat(airflowRate)
        })
      });
      const data = await res.json();
      setState(prev => ({ ...prev, ai_enabled: false }));
    } catch (err) {
      console.error(err);
    }
  };

  // Helper: comfort color mapping
  const getComfortStatus = (pmv) => {
    if (Math.abs(pmv) <= 0.5) return { label: 'Optimal', color: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20', bg: 'bg-emerald-500/5', dot: 'bg-emerald-400' };
    if (Math.abs(pmv) <= 1.0) return { label: 'Acceptable', color: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20', bg: 'bg-cyan-500/5', dot: 'bg-cyan-400' };
    if (pmv > 1.0) return { label: 'Warm (Too Hot)', color: 'text-orange-400 bg-orange-500/10 border-orange-500/20', bg: 'bg-orange-500/5', dot: 'bg-orange-400' };
    return { label: 'Cool (Too Cold)', color: 'text-sky-400 bg-sky-500/10 border-sky-500/20', bg: 'bg-sky-500/5', dot: 'bg-sky-400' };
  };

  // Prepare chart data format
  const chartData = history.active.map((step, idx) => {
    const baselineStep = history.baseline[idx] || {};
    return {
      hour: step.hour,
      hourOfDay: `${step.hour_of_day}:00`,
      outdoor: step.outdoor_temp,
      zone_a: step.zones?.Zone_A_Executive?.temp || 0,
      zone_b: step.zones?.Zone_B_Workspace?.temp || 0,
      zone_c: step.zones?.Zone_C_DataRoom?.temp || 0,
      totalPower: step.total_power_kw,
      baselinePower: baselineStep.total_power_kw || 0,
      cost: step.cumulative_cost,
      baselineCost: baselineStep.cumulative_cost || 0,
      carbon: step.cumulative_carbon,
      baselineCarbon: baselineStep.cumulative_carbon || 0
    };
  });

  return (
    <div className="bg-grid-pattern min-h-screen">
      
      {/* Top Floating Header */}
      <header className="glass-panel sticky top-0 z-50 border-b px-6 py-4 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="relative flex items-center justify-center w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 shadow-[0_0_15px_rgba(16,185,129,0.2)]">
            <Cpu className="w-5 h-5 animate-pulse" />
          </div>
          <div>
            <h1 className="font-extrabold text-xl tracking-tight bg-gradient-to-r from-white via-gray-200 to-gray-400 bg-clip-text text-transparent">AETHER<span className="text-emerald-400">//</span>BMS</h1>
            <p className="text-xs text-gray-400 font-medium">Model Context Protocol Autonomic System</p>
          </div>
        </div>

        {/* Live Simulation Clock */}
        {state && (
          <div className="flex items-center gap-6 text-sm font-medium text-gray-300">
            <div className="flex items-center gap-2 bg-white/5 border border-white/10 px-3 py-1.5 rounded-lg">
              <Clock className="w-4 h-4 text-emerald-400" />
              <span>Sim Hour: <span className="font-bold text-white">{state.hour_of_day}:00</span></span>
            </div>
            <div className="flex items-center gap-2 bg-white/5 border border-white/10 px-3 py-1.5 rounded-lg">
              <CloudSun className="w-4 h-4 text-sky-400" />
              <span>Scenario: <span className="font-bold text-white capitalize">{state.active_scenario.replace('_', ' ')}</span></span>
            </div>
          </div>
        )}

        {/* Controls and Autonomy Toggles */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 bg-white/5 border border-white/10 p-1 rounded-lg">
            <button
              onClick={() => handleScenarioChange('summer_heatwave')}
              className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${scenario === 'summer_heatwave' ? 'bg-orange-500/20 text-orange-400 border border-orange-500/30' : 'text-gray-400 hover:text-gray-200'}`}
            >
              Heatwave
            </button>
            <button
              onClick={() => handleScenarioChange('winter_storm')}
              className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${scenario === 'winter_storm' ? 'bg-sky-500/20 text-sky-400 border border-sky-500/30' : 'text-gray-400 hover:text-gray-200'}`}
            >
              Winter
            </button>
            <button
              onClick={() => handleScenarioChange('shoulder_day')}
              className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${scenario === 'shoulder_day' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'text-gray-400 hover:text-gray-200'}`}
            >
              Mild
            </button>
            <button
              onClick={() => handleScenarioChange('carbon_crisis')}
              className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${scenario === 'carbon_crisis' ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30' : 'text-gray-400 hover:text-gray-200'}`}
            >
              Grid Peak
            </button>
          </div>

          <div className="h-6 w-px bg-white/10" />

          {/* AI Autonomous Activation Switch */}
          <div className="flex items-center gap-3">
            <span className="text-xs font-semibold tracking-wider uppercase text-gray-400">AI Autonomy</span>
            <button
              onClick={() => handleToggleAI(!aiEnabled)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-all duration-300 ${aiEnabled ? 'bg-emerald-500' : 'bg-gray-700'}`}
            >
              <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-all duration-300 ${aiEnabled ? 'translate-x-6' : 'translate-x-1'}`} />
            </button>
          </div>

          <button
            onClick={handleReset}
            title="Reset Simulation"
            className="p-2 hover:bg-white/5 border border-transparent hover:border-white/10 text-gray-400 hover:text-white rounded-lg transition-all"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </header>

      {/* Main Container */}
      <main className="max-w-[1700px] mx-auto p-6 space-y-6">
        
        {/* Telemetry Strip */}
        <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          
          {/* Card 1: Cost Savings */}
          <div className="glass-panel relative overflow-hidden rounded-2xl p-5 flex items-center justify-between border-l-4 border-l-emerald-500">
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-1">Financial Optimizations</p>
              <h2 className="text-3xl font-extrabold text-white">${state ? state.cumulative_cost : '0.00'}</h2>
              <div className="flex items-center gap-1 text-emerald-400 text-xs font-semibold mt-2">
                <TrendingDown className="w-3.5 h-3.5" />
                <span>Saved {state ? roundNum((state.baseline_cumulative_cost - state.cumulative_cost), 2) : '0'} ($) vs baseline</span>
              </div>
            </div>
            <div className="p-3 bg-emerald-500/10 text-emerald-400 rounded-xl">
              <Zap className="w-6 h-6" />
            </div>
          </div>

          {/* Card 2: Carbon Reduction */}
          <div className="glass-panel relative overflow-hidden rounded-2xl p-5 flex items-center justify-between border-l-4 border-l-cyan-500">
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-1">Carbon Reduction</p>
              <h2 className="text-3xl font-extrabold text-white">{state ? state.cumulative_carbon : '0.00'} kg</h2>
              <div className="flex items-center gap-1 text-cyan-400 text-xs font-semibold mt-2">
                <Leaf className="w-3.5 h-3.5" />
                <span>Reduced {state ? roundNum(state.baseline_cumulative_carbon - state.cumulative_carbon, 2) : '0'} kg CO₂</span>
              </div>
            </div>
            <div className="p-3 bg-cyan-500/10 text-cyan-400 rounded-xl">
              <Leaf className="w-6 h-6" />
            </div>
          </div>

          {/* Card 3: Power Usage */}
          <div className="glass-panel relative overflow-hidden rounded-2xl p-5 border-l-4 border-l-orange-500">
            <div className="flex items-center justify-between mb-3">
              <div>
                <p className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-1">Dynamic Electrical Grid Load</p>
                <h2 className="text-3xl font-extrabold text-white">{state ? roundNum(Object.values(state.zones).reduce((acc, z) => acc + z.hvac_power_kw + z.light_power_kw, 0) + 12.0, 1) : '0.0'} kW</h2>
              </div>
              <div className="text-orange-400 text-xs font-bold bg-orange-500/10 px-2 py-1 rounded-md">
                Tariff: ${state ? state.electricity_price : '0.00'}/kWh
              </div>
            </div>
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs text-gray-400">
                <span>Optimized Grid Draw</span>
                <span>Baseline: {state ? roundNum(chartData[chartData.length - 1]?.baselinePower || 0, 1) : '0'} kW</span>
              </div>
              <div className="w-full h-2 bg-white/5 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-orange-500 rounded-full transition-all duration-500" 
                  style={{ width: `${state ? Math.min(100, (Object.values(state.zones).reduce((acc, z) => acc + z.hvac_power_kw + z.light_power_kw, 0) / (chartData[chartData.length - 1]?.baselinePower || 100)) * 100) : 0}%` }}
                />
              </div>
            </div>
          </div>

          {/* Card 4: Weather Conditions */}
          <div className="glass-panel relative overflow-hidden rounded-2xl p-5 flex items-center justify-between border-l-4 border-l-sky-500">
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-1">Ambient Weather</p>
              <h2 className="text-3xl font-extrabold text-white">{state ? state.outdoor_temp : '0'} °C</h2>
              <p className="text-xs text-gray-400 mt-2">
                Sun Solar: <span className="text-white font-semibold">{state ? state.solar_rad : '0'} W/m²</span> | RH: <span className="text-white font-semibold">{state ? state.outdoor_humidity : '0'}%</span>
              </p>
            </div>
            <div className="p-3 bg-sky-500/10 text-sky-400 rounded-xl">
              <CloudSun className="w-6 h-6" />
            </div>
          </div>

        </section>

        {/* 3 Column Grid */}
        <section className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
          
          {/* Column 1: Interactive Isometric Floor Plan (5 cols) */}
          <div className="glass-panel rounded-2xl p-6 lg:col-span-5 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between border-b border-white/5 pb-4 mb-6">
                <div>
                  <h3 className="font-extrabold text-lg text-white">Smart Building Layout</h3>
                  <p className="text-xs text-gray-400">Click a zone to adjust operating parameters</p>
                </div>
                <div className="flex items-center gap-1.5 text-xs text-emerald-400 font-semibold bg-emerald-500/10 px-2 py-1 rounded-md">
                  <Activity className="w-3.5 h-3.5" />
                  <span>Interactive Real-time Model</span>
                </div>
              </div>

              {/* Floor Plan Display Matrix */}
              <div className="space-y-4">
                {state && Object.entries(state.zones).map(([key, zone]) => {
                  const comfort = getComfortStatus(zone.pmv);
                  const isSelected = selectedZone === key;
                  
                  return (
                    <div 
                      key={key}
                      onClick={() => setSelectedZone(key)}
                      className={`cursor-pointer group flex flex-col p-4 rounded-xl border transition-all ${isSelected ? 'bg-white/10 border-white/20 shadow-lg' : 'bg-white/5 border-white/5 hover:border-white/10'}`}
                    >
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-3">
                          <div className={`w-3 h-3 rounded-full ${isSelected ? 'bg-emerald-400' : 'bg-gray-400'} group-hover:scale-125 transition-transform`} />
                          <h4 className="font-extrabold text-sm text-white group-hover:text-emerald-400 transition-colors">{zone.name.split(' - ')[0]}</h4>
                        </div>
                        <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${comfort.color}`}>
                          {comfort.label}
                        </span>
                      </div>

                      <div className="grid grid-cols-3 gap-4 text-center mt-1">
                        
                        {/* Temperature status block */}
                        <div className="flex flex-col items-center justify-center p-2 rounded-lg bg-black/20">
                          <Thermometer className="w-4 h-4 text-gray-400 mb-1" />
                          <span className="text-xs text-gray-400">Temp</span>
                          <span className="text-sm font-bold text-white mt-0.5">{zone.temperature} °C</span>
                        </div>

                        {/* HVAC Airflow block */}
                        <div className="flex flex-col items-center justify-center p-2 rounded-lg bg-black/20">
                          <Wind className={`w-4 h-4 text-gray-400 mb-1 ${zone.airflow_rate > 0.05 ? 'animate-spin-medium' : ''}`} />
                          <span className="text-xs text-gray-400">Airflow</span>
                          <span className="text-sm font-bold text-white mt-0.5">{zone.airflow_rate} m³/s</span>
                        </div>

                        {/* Comfort metric block */}
                        <div className="flex flex-col items-center justify-center p-2 rounded-lg bg-black/20">
                          <Activity className="w-4 h-4 text-gray-400 mb-1" />
                          <span className="text-xs text-gray-400">PMV</span>
                          <span className="text-sm font-bold text-white mt-0.5">{zone.pmv}</span>
                        </div>

                      </div>

                      {/* Lighting Level Bar */}
                      <div className="mt-3 space-y-1">
                        <div className="flex justify-between text-[11px] text-gray-400">
                          <span>Lighting Power Dimmer</span>
                          <span>{Math.round(zone.light_dim_level * 100)}%</span>
                        </div>
                        <div className="w-full h-1.5 bg-black/30 rounded-full overflow-hidden">
                          <div 
                            className="h-full bg-amber-400 rounded-full transition-all duration-300"
                            style={{ width: `${zone.light_dim_level * 100}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
            
            {/* System Status info */}
            <div className="mt-4 pt-4 border-t border-white/5 flex items-center justify-between text-xs text-gray-500">
              <span className="flex items-center gap-1.5">
                <span className={`w-2 h-2 rounded-full ${wsStatus === 'connected' ? 'bg-emerald-400 pulse-green' : 'bg-red-500'}`} />
                WebSocket Link: {wsStatus}
              </span>
              <span>Building: Denver Medium Office</span>
            </div>
          </div>

          {/* Column 2: Parameters Panel & Adjustments (4 cols) */}
          <div className="glass-panel rounded-2xl p-6 lg:col-span-4 flex flex-col justify-between">
            {state && state.zones[selectedZone] ? (
              <div className="space-y-6">
                <div className="border-b border-white/5 pb-4">
                  <h3 className="font-extrabold text-lg text-white">Zone Optimizer</h3>
                  <p className="text-xs text-gray-400">Configure parameters for <span className="text-emerald-400 font-semibold">{state.zones[selectedZone].name.split(' - ')[0]}</span></p>
                </div>

                {/* Lock Overlay indicating autonomous LLM control is running */}
                {aiEnabled ? (
                  <div className="relative flex flex-col items-center justify-center p-6 bg-emerald-500/5 border border-emerald-500/10 rounded-xl text-center space-y-3">
                    <div className="p-3 bg-emerald-500/10 text-emerald-400 rounded-full shadow-[0_0_15px_rgba(16,185,129,0.1)]">
                      <UserCheck className="w-6 h-6 animate-pulse" />
                    </div>
                    <div>
                      <h4 className="font-bold text-white text-sm">AI Agent Optimization Active</h4>
                      <p className="text-xs text-gray-400 mt-1 max-w-xs leading-relaxed">Gemini is dynamically modifying temperatures and dimmers to optimize financial cost and comfort limits.</p>
                    </div>
                    <button
                      onClick={() => handleToggleAI(false)}
                      className="px-4 py-1.5 bg-white/5 border border-white/10 hover:bg-white/10 text-xs font-bold text-white rounded-lg transition-all"
                    >
                      Disable AI & Override Manually
                    </button>
                  </div>
                ) : (
                  <div className="space-y-5">
                    
                    {/* Cooling thermostat slider */}
                    <div className="space-y-2">
                      <div className="flex justify-between text-sm font-semibold">
                        <span className="text-gray-300">Cooling HVAC Setpoint</span>
                        <span className="text-emerald-400 font-bold">{coolingSetpoint} °C</span>
                      </div>
                      <input 
                        type="range" 
                        min="21" 
                        max="30" 
                        step="0.5"
                        value={coolingSetpoint}
                        onChange={(e) => setCoolingSetpoint(parseFloat(e.target.value))}
                        className="w-full accent-emerald-500 h-1.5 bg-black/40 rounded-lg cursor-pointer"
                      />
                      <p className="text-[11px] text-gray-500">HVAC cooling activates if indoor temp rises above this threshold.</p>
                    </div>

                    {/* Heating thermostat slider */}
                    <div className="space-y-2">
                      <div className="flex justify-between text-sm font-semibold">
                        <span className="text-gray-300">Heating HVAC Setpoint</span>
                        <span className="text-sky-400 font-bold">{heatingSetpoint} °C</span>
                      </div>
                      <input 
                        type="range" 
                        min="14" 
                        max="21.5" 
                        step="0.5"
                        value={heatingSetpoint}
                        onChange={(e) => setHeatingSetpoint(parseFloat(e.target.value))}
                        className="w-full accent-sky-500 h-1.5 bg-black/40 rounded-lg cursor-pointer"
                      />
                      <p className="text-[11px] text-gray-500">HVAC heating activates if indoor temp drops below this threshold.</p>
                    </div>

                    {/* Ventilation air damper rate slider */}
                    <div className="space-y-2">
                      <div className="flex justify-between text-sm font-semibold">
                        <span className="text-gray-300">Ventilation Flow Rate</span>
                        <span className="text-cyan-400 font-bold">{airflowRate} m³/s</span>
                      </div>
                      <input 
                        type="range" 
                        min="0.05" 
                        max="1.2" 
                        step="0.05"
                        value={airflowRate}
                        onChange={(e) => setAirflowRate(parseFloat(e.target.value))}
                        className="w-full accent-cyan-500 h-1.5 bg-black/40 rounded-lg cursor-pointer"
                      />
                      <p className="text-[11px] text-gray-500">Volume flow rate of fresh air. Higher rates increase outdoor thermal exchange load.</p>
                    </div>

                    {/* Light dim level slider */}
                    <div className="space-y-2">
                      <div className="flex justify-between text-sm font-semibold">
                        <span className="text-gray-300">Daylighting Dimming Level</span>
                        <span className="text-amber-400 font-bold">{Math.round(lightDimLevel * 100)}%</span>
                      </div>
                      <input 
                        type="range" 
                        min="0" 
                        max="1" 
                        step="0.05"
                        value={lightDimLevel}
                        onChange={(e) => setLightDimLevel(parseFloat(e.target.value))}
                        className="w-full accent-amber-500 h-1.5 bg-black/40 rounded-lg cursor-pointer"
                      />
                      <p className="text-[11px] text-gray-500">Control dimming output. Lowering values saves direct electricity draw.</p>
                    </div>

                    <button
                      onClick={handleApplyManualSettings}
                      className="w-full py-2.5 mt-2 bg-emerald-500 hover:bg-emerald-600 active:scale-95 text-sm font-bold text-black rounded-xl transition-all shadow-[0_0_15px_rgba(16,185,129,0.15)]"
                    >
                      Apply Manual Overrides
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-20 text-gray-500">Loading optimizer modules...</div>
            )}
            
            {/* Legend block */}
            <div className="mt-6 pt-4 border-t border-white/5 space-y-2 text-xs">
              <span className="font-bold text-gray-400 block uppercase tracking-wider text-[10px]">Guidelines for efficiency</span>
              <div className="flex items-center justify-between text-gray-500">
                <span>Minimum Zone C threshold:</span>
                <span className="font-semibold text-white">23.0 °C max</span>
              </div>
              <div className="flex items-center justify-between text-gray-500">
                <span>Healthy PMV comfort bounds:</span>
                <span className="font-semibold text-emerald-400">[-0.5 to +0.5]</span>
              </div>
            </div>
          </div>

          {/* Column 3: AI Mind & Thought Feed (3 cols) */}
          <div className="glass-panel rounded-2xl p-6 lg:col-span-3 flex flex-col justify-between">
            <div className="flex flex-col h-full">
              <div className="flex items-center gap-2.5 border-b border-white/5 pb-4 mb-4">
                <div className="p-1.5 bg-emerald-500/10 text-emerald-400 rounded-lg">
                  <Activity className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="font-extrabold text-sm text-white">AI Closed-Loop Telemetry</h3>
                  <p className="text-[11px] text-gray-500">Decisions, thought traces, and action logs</p>
                </div>
              </div>

              {/* Terminal Logs View */}
              <div className="flex-1 min-h-[300px] max-h-[380px] overflow-y-auto pr-1 space-y-3 font-mono text-xs text-gray-400">
                {thoughts.length === 0 ? (
                  <div className="text-center py-20 text-gray-600 italic">No cycles run yet. Enable AI Autonomy to initialize loops.</div>
                ) : (
                  thoughts.map((log, idx) => {
                    const isSystem = log.message.includes('AI Optimization') || log.message.includes('Simulation variables') || log.message.includes('Scenario');
                    const isManual = log.message.includes('Manual override');
                    
                    let prefixColor = 'text-emerald-400';
                    if (isSystem) prefixColor = 'text-purple-400';
                    if (isManual) prefixColor = 'text-orange-400';
                    
                    return (
                      <div key={idx} className="p-2 bg-black/35 rounded border border-white/5 space-y-1">
                        <div className="flex justify-between items-center text-[10px] text-gray-500 border-b border-white/5 pb-1">
                          <span>{log.sim_hour}</span>
                          <span>{log.timestamp}</span>
                        </div>
                        <p className="leading-relaxed break-words">
                          <span className={`${prefixColor} font-bold mr-1.5`}>&gt;</span>
                          {log.message}
                        </p>
                      </div>
                    );
                  })
                )}
                <div ref={thoughtsEndRef} />
              </div>
            </div>
          </div>

        </section>

        {/* Real-time Visualization Charts */}
        <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          
          {/* Temperature visualizer */}
          <div className="glass-panel rounded-2xl p-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="font-extrabold text-lg text-white">Dynamic Zone Temperatures</h3>
                <p className="text-xs text-gray-400">Outdoor vs actual indoor zones temperatures (°C)</p>
              </div>
              <span className="p-2 bg-white/5 border border-white/10 rounded-lg text-gray-400"><Thermometer className="w-4 h-4" /></span>
            </div>
            <div className="h-[300px]">
              {chartData.length === 0 ? (
                <div className="w-full h-full flex items-center justify-center text-gray-600 italic">Simulating starting conditions...</div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData}>
                    <defs>
                      <linearGradient id="colorOutdoor" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#ef4444" stopOpacity={0.05}/>
                        <stop offset="95%" stopColor="#ef4444" stopOpacity={0}/>
                      </linearGradient>
                      <linearGradient id="colorZoneB" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#10b981" stopOpacity={0.15}/>
                        <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" />
                    <XAxis dataKey="hourOfDay" stroke="rgba(255,255,255,0.4)" fontSize={11} />
                    <YAxis stroke="rgba(255,255,255,0.4)" fontSize={11} domain={['dataMin - 3', 'dataMax + 3']} />
                    <Tooltip contentStyle={{ backgroundColor: 'rgba(10,12,22,0.9)', borderColor: 'rgba(255,255,255,0.08)' }} />
                    <Legend wrapperStyle={{ fontSize: 12, paddingTop: 10 }} />
                    <Area name="Outdoor Ambient" type="monotone" dataKey="outdoor" stroke="#ef4444" fillOpacity={1} fill="url(#colorOutdoor)" strokeWidth={1.5} />
                    <Area name="Zone B Workspace" type="monotone" dataKey="zone_b" stroke="#10b981" fillOpacity={1} fill="url(#colorZoneB)" strokeWidth={2.5} />
                    <Line name="Zone A Executive" type="monotone" dataKey="zone_a" stroke="#3b82f6" strokeWidth={1.5} dot={false} />
                    <Line name="Zone C Server Room" type="monotone" dataKey="zone_c" stroke="#a855f7" strokeWidth={1.5} dot={false} />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          {/* Energy cost visualizer comparison */}
          <div className="glass-panel rounded-2xl p-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="font-extrabold text-lg text-white">Cumulative Utility Cost Savings</h3>
                <p className="text-xs text-gray-400">Baseline fixed setpoints vs AI Optimizer ($)</p>
              </div>
              <span className="p-2 bg-white/5 border border-white/10 rounded-lg text-gray-400"><Zap className="w-4 h-4" /></span>
            </div>
            <div className="h-[300px]">
              {chartData.length === 0 ? (
                <div className="w-full h-full flex items-center justify-center text-gray-600 italic">Simulating starting conditions...</div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" />
                    <XAxis dataKey="hourOfDay" stroke="rgba(255,255,255,0.4)" fontSize={11} />
                    <YAxis stroke="rgba(255,255,255,0.4)" fontSize={11} />
                    <Tooltip contentStyle={{ backgroundColor: 'rgba(10,12,22,0.9)', borderColor: 'rgba(255,255,255,0.08)' }} />
                    <Legend wrapperStyle={{ fontSize: 12, paddingTop: 10 }} />
                    <Line name="Baseline Run" type="monotone" dataKey="baselineCost" stroke="#ef4444" strokeWidth={1.5} dot={false} strokeDasharray="4 4" />
                    <Line name="AetherBMS Optimized" type="monotone" dataKey="cost" stroke="#10b981" strokeWidth={3} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

        </section>

      </main>
    </div>
  );
}

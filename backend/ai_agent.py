import os
import json
import requests
import dotenv
from mcp_server import MCPServer

# Load environment variables
dotenv.load_dotenv(override=True)
print("=" * 50)
print("Groq Key Loaded :", os.getenv("GROQ_API_KEY")[:8] + "..." if os.getenv("GROQ_API_KEY") else "None")
print("=" * 50)

class AIAgent:
    def __init__(self, mcp_server: MCPServer):
        self.mcp = mcp_server
        self.api_key = os.getenv("GROQ_API_KEY")
        self.api_url = "https://api.groq.com/openai/v1/chat/completions"
        self.model = "llama-3.3-70b-versatile"
        
    def query_groq(self, system_instruction, prompt):
        """Sends prompt and tool schema to the Groq REST API (OpenAI compatible)."""
        if not self.api_key:
            return None, None, "NO_API_KEY"
            
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        # Build tool definitions mapping MCP tools to OpenAI/Groq function declarations
        tools_def = [
            {
                "type": "function",
                "function": {
                    "name": "set_zone_setpoints",
                    "description": "Modify the HVAC heating and cooling setpoints and ventilation airflow rate for a zone.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "zone_id": {
                                "type": "string",
                                "description": "The unique identifier of the zone. Options: Zone_A_Executive, Zone_B_Workspace, Zone_C_DataRoom"
                            },
                            "cooling_setpoint": {
                                "type": "number",
                                "description": "Thermostat cooling setpoint in °C. Typically between 22°C and 26°C."
                            },
                            "heating_setpoint": {
                                "type": "number",
                                "description": "Thermostat heating setpoint in °C. Typically between 18°C and 21°C."
                            },
                            "airflow_rate": {
                                "type": "number",
                                "description": "Ventilation airflow rate in m^3/s. Usually between 0.1 and 1.0."
                            }
                        },
                        "required": ["zone_id", "cooling_setpoint", "heating_setpoint"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "optimize_lights",
                    "description": "Optimize the lighting dimming levels in a zone.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "zone_id": {
                                "type": "string",
                                "description": "The unique identifier of the zone. Options: Zone_A_Executive, Zone_B_Workspace, Zone_C_DataRoom"
                            },
                            "light_dim_level": {
                                "type": "number",
                                "description": "Dimming factor between 0.0 (off) and 1.0 (maximum brightness)."
                            }
                        },
                        "required": ["zone_id", "light_dim_level"]
                    }
                }
            }
        ]
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            "tools": tools_def,
            "tool_choice": "auto"
        }
        
        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=12,
            )

            print("=" * 80)
            print("GROQ API STATUS :", response.status_code)
            print(response.text)
            print("=" * 80)
            if response.status_code == 200:
                res_data = response.json()
                choices = res_data.get("choices", [])
                if choices:
                    message = choices[0].get("message", {})
                    content = message.get("content") or ""
                    tool_calls = message.get("tool_calls") or []
                    return content, tool_calls, "OK"
            return None, None, f"API Error {response.status_code}: {response.text}"
        except Exception as e:
            return None, None, f"Connection error: {str(e)}"

    def local_smart_optimizer(self, state, forecast):
        """
        Fallback controller that mimics LLM tool execution using MPC principles.
        Operates on physics formulas and rules to yield optimal tool calls.
        """
        hour = state["hour_of_day"]
        scen = state["active_scenario"]
        outdoor_temp = state["outdoor_temp"]
        solar_rad = state["solar_rad"]
        tariff = state["electricity_price_per_kwh"]
        carbon = state["grid_carbon_kg_per_kwh"]
        occ_factor = state["occupancy_factor"]
        
        tool_calls = []
        thoughts = []
        
        # 1. Server room optimization (Zone C)
        # Needs to stay cool under heavy 12 kW internal load.
        # Heating is not needed. Cooling setpoint should be kept low.
        z_c = state["zones"]["Zone_C_DataRoom"]
        if z_c["temperature"] > 21.5:
            tool_calls.append({
                "name": "set_zone_setpoints",
                "args": {
                    "zone_id": "Zone_C_DataRoom",
                    "cooling_setpoint": 20.0,
                    "heating_setpoint": 15.0,
                    "airflow_rate": 0.4
                }
            })
            thoughts.append("Data center temperature high. Setting aggressive cooling (20°C) with high ventilation (0.4m³/s) to prevent equipment thermal throttling.")
        else:
            # Server is fine, set a standard cooling point to conserve energy
            tool_calls.append({
                "name": "set_zone_setpoints",
                "args": {
                    "zone_id": "Zone_C_DataRoom",
                    "cooling_setpoint": 22.0,
                    "heating_setpoint": 15.0,
                    "airflow_rate": 0.2
                }
            })
            thoughts.append("Data center thermal profile stable. Maintaining server cooling at 22°C to conserve fan energy.")

        # 2. Zone A (Executive) & Zone B (Workspace) Optimization
        # Analyze upcoming tariff peak
        peak_hours_ahead = [f["hours_ahead"] for f in forecast["forecast"] if f["electricity_price_per_kwh"] >= 0.45]
        next_peak_in = peak_hours_ahead[0] if peak_hours_ahead else 99
        
        # Carbon intensity
        carbon_is_high = carbon > 0.40
        
        # --- Zone A (East Suite - Morning Sun) ---
        z_a = state["zones"]["Zone_A_Executive"]
        # Daylighting dimming check
        if solar_rad > 300 and 6 <= hour <= 12:
            # Morning solar is high. East suite gets good light.
            dim_level = 0.35
            thoughts.append("Morning daylight harvesting in Zone A. Dimming lights to 35% based on solar radiation ({} W/m²).".format(solar_rad))
            tool_calls.append({
                "name": "optimize_lights",
                "args": {"zone_id": "Zone_A_Executive", "light_dim_level": dim_level}
            })
        elif occ_factor < 0.1:
            # Unoccupied
            tool_calls.append({
                "name": "optimize_lights",
                "args": {"zone_id": "Zone_A_Executive", "light_dim_level": 0.0}
            })
            thoughts.append("Zone A unoccupied. Shutting down office illumination.")
        else:
            # Standard occupied lighting
            tool_calls.append({
                "name": "optimize_lights",
                "args": {"zone_id": "Zone_A_Executive", "light_dim_level": 1.0}
            })
            
        # Thermal setpoint logic
        if occ_factor < 0.05:
            # Night/Unoccupied setback
            tool_calls.append({
                "name": "set_zone_setpoints",
                "args": {
                    "zone_id": "Zone_A_Executive",
                    "cooling_setpoint": 28.0,
                    "heating_setpoint": 15.0,
                    "airflow_rate": 0.05
                }
            })
            thoughts.append("Night setback active for Zone A. Relaxing HVAC limits to [15°C, 28°C] to eliminate standby heating/cooling.")
        else:
            # Occupied
            if scen == "summer_heatwave":
                # Pre-cooling strategy if peak is coming
                if next_peak_in <= 2:
                    tool_calls.append({
                        "name": "set_zone_setpoints",
                        "args": {
                            "zone_id": "Zone_A_Executive",
                            "cooling_setpoint": 21.0,
                            "heating_setpoint": 18.0,
                            "airflow_rate": 0.35
                        }
                    })
                    thoughts.append("Pre-cooling Zone A in anticipation of grid tariff peak in {} hours. Pulling temp down to 21°C.".format(next_peak_in))
                elif tariff >= 0.45:
                    # Peak pricing: load shed. Allow temp to drift up slightly
                    tool_calls.append({
                        "name": "set_zone_setpoints",
                        "args": {
                            "zone_id": "Zone_A_Executive",
                            "cooling_setpoint": 25.5,
                            "heating_setpoint": 18.0,
                            "airflow_rate": 0.15
                        }
                    })
                    thoughts.append("Peak electricity price tariff active ($0.45/kWh). Performing load shedding in Zone A. Raising cooling setpoint to 25.5°C.")
                else:
                    # Normal cooling
                    tool_calls.append({
                        "name": "set_zone_setpoints",
                        "args": {
                            "zone_id": "Zone_A_Executive",
                            "cooling_setpoint": 23.5,
                            "heating_setpoint": 20.0,
                            "airflow_rate": 0.2
                        }
                    })
                    thoughts.append("Standard warm weather occupancy. Adjusting HVAC bounds in Zone A to [20.0°C, 23.5°C] to maintain PMV near comfort neutral.")
            elif scen == "winter_storm":
                if tariff >= 0.45:
                    # Heat shed
                    tool_calls.append({
                        "name": "set_zone_setpoints",
                        "args": {
                            "zone_id": "Zone_A_Executive",
                            "cooling_setpoint": 24.0,
                            "heating_setpoint": 18.5,
                            "airflow_rate": 0.15
                        }
                    })
                    thoughts.append("Peak electricity tariff. Shedding heating load in Zone A by lowering heating setpoint to 18.5°C.")
                else:
                    # Standard heating
                    tool_calls.append({
                        "name": "set_zone_setpoints",
                        "args": {
                            "zone_id": "Zone_A_Executive",
                            "cooling_setpoint": 24.0,
                            "heating_setpoint": 20.5,
                            "airflow_rate": 0.2
                        }
                    })
                    thoughts.append("Sub-zero winter conditions outside. Heating Zone A to comfortable 20.5°C.")
            else: # Free cooling / Shoulder day
                # Nice weather outside, economizer mode
                if 17.0 <= outdoor_temp <= 22.0:
                    tool_calls.append({
                        "name": "set_zone_setpoints",
                        "args": {
                            "zone_id": "Zone_A_Executive",
                            "cooling_setpoint": 23.0,
                            "heating_setpoint": 19.5,
                            "airflow_rate": 0.5  # High airflow for economizer ventilation
                        }
                    })
                    thoughts.append("Outdoor temp is pleasant ({}°C). Activating economizer natural ventilation in Zone A. Increasing outdoor air intake to 0.5m³/s.".format(outdoor_temp))
                else:
                    tool_calls.append({
                        "name": "set_zone_setpoints",
                        "args": {
                            "zone_id": "Zone_A_Executive",
                            "cooling_setpoint": 23.0,
                            "heating_setpoint": 20.0,
                            "airflow_rate": 0.2
                        }
                    })

        # --- Zone B (Open Workspace - West Side Sun Afternoon) ---
        z_b = state["zones"]["Zone_B_Workspace"]
        if solar_rad > 300 and 13 <= hour <= 18:
            # Afternoon solar is high on West side.
            dim_level = 0.40
            thoughts.append("West solar radiation high. Daylight harvesting dimming Zone B lighting to 40% (Solar: {} W/m²).".format(solar_rad))
            tool_calls.append({
                "name": "optimize_lights",
                "args": {"zone_id": "Zone_B_Workspace", "light_dim_level": dim_level}
            })
        elif occ_factor < 0.1:
            tool_calls.append({
                "name": "optimize_lights",
                "args": {"zone_id": "Zone_B_Workspace", "light_dim_level": 0.0}
            })
            thoughts.append("Zone B unoccupied. Powering off lighting fixtures.")
        else:
            tool_calls.append({
                "name": "optimize_lights",
                "args": {"zone_id": "Zone_B_Workspace", "light_dim_level": 1.0}
            })
            
        # Thermal setpoint logic
        if occ_factor < 0.05:
            tool_calls.append({
                "name": "set_zone_setpoints",
                "args": {
                    "zone_id": "Zone_B_Workspace",
                    "cooling_setpoint": 28.0,
                    "heating_setpoint": 15.0,
                    "airflow_rate": 0.05
                }
            })
            thoughts.append("Zone B in unoccupied state. Activating thermal setback.")
        else:
            if scen == "summer_heatwave":
                if next_peak_in <= 2:
                    tool_calls.append({
                        "name": "set_zone_setpoints",
                        "args": {
                            "zone_id": "Zone_B_Workspace",
                            "cooling_setpoint": 21.0,
                            "heating_setpoint": 18.0,
                            "airflow_rate": 0.4
                        }
                    })
                    thoughts.append("Shifting load. Pre-cooling open workspace Zone B to 21°C ahead of the evening peak tariff.")
                elif tariff >= 0.45:
                    tool_calls.append({
                        "name": "set_zone_setpoints",
                        "args": {
                            "zone_id": "Zone_B_Workspace",
                            "cooling_setpoint": 25.0,
                            "heating_setpoint": 18.0,
                            "airflow_rate": 0.15
                        }
                    })
                    thoughts.append("High price peak active. Discharging thermal mass in Zone B. Raising cooling setpoint to 25.0°C.")
                else:
                    # Normal cooling
                    tool_calls.append({
                        "name": "set_zone_setpoints",
                        "args": {
                            "zone_id": "Zone_B_Workspace",
                            "cooling_setpoint": 23.5,
                            "heating_setpoint": 20.0,
                            "airflow_rate": 0.25
                        }
                    })
                    thoughts.append("Dynamic comfort control. Setting HVAC in Zone B to [20.0°C, 23.5°C] with standard airflow.")
            elif scen == "winter_storm":
                if tariff >= 0.45:
                    tool_calls.append({
                        "name": "set_zone_setpoints",
                        "args": {
                            "zone_id": "Zone_B_Workspace",
                            "cooling_setpoint": 23.5,
                            "heating_setpoint": 18.0,
                            "airflow_rate": 0.15
                        }
                    })
                    thoughts.append("Peak tariff active. Thermostat setback applied to Zone B heating (18.0°C).")
                else:
                    tool_calls.append({
                        "name": "set_zone_setpoints",
                        "args": {
                            "zone_id": "Zone_B_Workspace",
                            "cooling_setpoint": 23.5,
                            "heating_setpoint": 20.0,
                            "airflow_rate": 0.25
                        }
                    })
                    thoughts.append("High heating load. Elevating Zone B heating to 20.0°C for occupant comfort.")
            else: # Free cooling / Shoulder day
                if 17.0 <= outdoor_temp <= 22.0:
                    tool_calls.append({
                        "name": "set_zone_setpoints",
                        "args": {
                            "zone_id": "Zone_B_Workspace",
                            "cooling_setpoint": 23.0,
                            "heating_setpoint": 19.5,
                            "airflow_rate": 0.6  # High ventilation
                        }
                    })
                    thoughts.append("Outside air quality and temperature ({}°C) perfect. Enabling natural economizer venting in Zone B (0.6m³/s) to bypass cooling compressors.".format(outdoor_temp))
                else:
                    tool_calls.append({
                        "name": "set_zone_setpoints",
                        "args": {
                            "zone_id": "Zone_B_Workspace",
                            "cooling_setpoint": 23.0,
                            "heating_setpoint": 20.0,
                            "airflow_rate": 0.25
                        }
                    })
                    
        # If carbon intensity is extremely high, adjust setpoints to prioritize carbon reduction
        if carbon_is_high and tariff < 0.45:
            # If not already load-shedding due to price, shed slightly due to carbon
            for call in tool_calls:
                if call["name"] == "set_zone_setpoints" and call["args"]["zone_id"] in ["Zone_A_Executive", "Zone_B_Workspace"]:
                    if scen == "summer_heatwave" and call["args"]["cooling_setpoint"] < 24.5:
                        call["args"]["cooling_setpoint"] = 24.5
                        thoughts.append(f"Grid carbon intensity is high ({carbon} kg CO2/kWh). Prioritizing emissions reduction: Relaxing cooling setpoint in {call['args']['zone_id']} to 24.5°C.")
                    elif scen == "winter_storm" and call["args"]["heating_setpoint"] > 19.5:
                        call["args"]["heating_setpoint"] = 19.5
                        thoughts.append(f"High carbon intensity ({carbon} kg CO2/kWh). Prioritizing emissions reduction: Lowering heating setpoint in {call['args']['zone_id']} to 19.5°C.")

        return tool_calls, thoughts

    def run_control_cycle(self):
        """Runs one full closed-loop control iteration."""
        # 1. Fetch current building state and forecast via MCP tools
        state = self.mcp.execute_tool("get_building_state", {})
        forecast = self.mcp.execute_tool("get_forecast", {})
        
        if "error" in state or "error" in forecast:
            msg = f"Failed to get building telemetry: {state.get('error') or forecast.get('error')}"
            self.mcp.sim.add_ai_thought(msg)
            return
            
        tool_calls = []
        thoughts = []
        used_groq = False
        
        # 2. Query Groq if API key is present
        if self.api_key:
            sys_instruction = (
                "You are AetherBMS, the central AI agent for an autonomous Building Management System.\n"
                "Your objective is to minimize HVAC and lighting energy cost and carbon footprint while keeping indoor occupants highly comfortable.\n"
                "Constraints:\n"
                "- Keep occupant Predicted Mean Vote (PMV) thermal comfort index strictly between -0.5 and +0.5 during occupied hours (occupancy > 0.05), and between -1.0 and +1.0 during standby hours.\n"
                "- The server room (Zone_C_DataRoom) has no occupants but has a constant equipment load of 12kW and must be kept below 23°C to prevent equipment failure. Do not heat this zone.\n"
                "- For Zone_A_Executive and Zone_B_Workspace, dim lighting to save energy when solar radiation is high (daylight harvesting) and switch off lights (0.0) when occupied factor is zero.\n"
                "- Utilize electricity pricing and carbon intensity forecasts to perform load shifting (e.g. pre-cool/pre-heat before peak pricing/carbon hours, and relax setpoints during peak hours)."
            )
            
            # Construct JSON state prompt for Groq
            prompt = (
                f"CURRENT STATE telemetry:\n{json.dumps(state, indent=2)}\n\n"
                f"24-HOUR FORECAST data:\n{json.dumps(forecast, indent=2)}\n\n"
                "Please analyze this data, explain your optimization reasoning in detail, and call the necessary tools (set_zone_setpoints, optimize_lights) to apply your decisions. For each zone, you should make at least one tool call to optimize its setpoints and lights."
            )
            
            content, g_tool_calls, status = self.query_groq(sys_instruction, prompt)
            
            if status == "OK" and (content or g_tool_calls):
                used_groq = True
                if content and content.strip():
                    self.mcp.sim.add_ai_thought("[Groq Reasoning] " + content.strip())
                    
                # Process any tool calls returned by Groq
                if g_tool_calls:
                    for call in g_tool_calls:
                        func = call.get("function", {})
                        name = func.get("name")
                        try:
                            args = json.loads(func.get("arguments", "{}"))
                            tool_calls.append({
                                "name": name,
                                "args": args
                            })
                        except Exception as e:
                            self.mcp.sim.add_ai_thought(f"Failed to parse Groq tool arguments for {name}: {e}")
            else:
                self.mcp.sim.add_ai_thought(f"Groq API failure ({status}). Rolling back to Local Smart Optimizer.")
                
        # 3. Fallback to Local Smart Controller if Groq is not set up or fails
        if not used_groq:
            tool_calls, thoughts = self.local_smart_optimizer(state, forecast)
            for t in thoughts:
                self.mcp.sim.add_ai_thought("[Local Autonomous Thought] " + t)
                
        # 4. Execute all tool calls against the MCP Server
        for call in tool_calls:
            name = call["name"]
            args = call["args"]
            res = self.mcp.execute_tool(name, args)
            if "error" in res:
                self.mcp.sim.add_ai_thought(f"AI command error on {name}: {res['error']}")
            else:
                # Log success message
                pass
                
if __name__ == "__main__":
    from simulation import BuildingSimulation
    sim = BuildingSimulation()
    server = MCPServer(sim)
    agent = AIAgent(server)
    print("Testing AI Agent loop in fallback mode...")
    agent.run_control_cycle()
    print("AI thought log:")
    for thought in sim.ai_thought_log:
        print(f"[{thought['timestamp']}] {thought['message']}")

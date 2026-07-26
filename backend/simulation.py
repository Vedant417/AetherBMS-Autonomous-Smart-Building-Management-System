import math
import random
import time

class Zone:
    def __init__(self, name, volume, thermal_capacitance, wall_area, u_value, peak_occupants, base_equipment_load, has_solar=True, solar_direction="east"):
        self.name = name
        self.volume = volume  # m^3
        self.C = thermal_capacitance  # kJ/K (thermal capacitance)
        self.A = wall_area  # m^2 (envelope area exposed to outside)
        self.U = u_value  # W/m^2-K (envelope heat transfer coefficient)
        self.peak_occupants = peak_occupants
        self.base_equipment_load = base_equipment_load  # W
        self.has_solar = has_solar
        self.solar_direction = solar_direction
        
        # State variables
        self.temp = 22.0  # °C
        self.cooling_setpoint = 24.0  # °C
        self.heating_setpoint = 20.0  # °C
        self.light_dim_level = 1.0  # 0.0 (off) to 1.0 (fully on)
        self.airflow_rate = 0.2  # m^3/s (ventilation rate)
        
        # Diagnostics
        self.hvac_cooling_power = 0.0  # W
        self.hvac_heating_power = 0.0  # W
        self.lighting_power = 0.0  # W
        self.pmv = 0.0
        self.ppd = 0.0

    def compute_pmv_fanger(self, rh=50.0):
        """
        Calculates Fanger's PMV (Predicted Mean Vote) and PPD (Predicted Percentage of Dissatisfied).
        Standard office conditions: MET = 1.2 (sedentary office work), CLO = 0.65 (summer dress/light trousers).
        Air velocity = 0.1 m/s (standard indoor ventilation).
        """
        ta = self.temp  # Air temp
        tr = ta  # Assume Mean Radiant Temp ≈ Air Temp for simplicity
        vel = 0.1  # m/s
        met = 1.2
        clo = 0.65
        
        # Vapor pressure (kPa)
        pa = (rh / 100.0) * 0.133322 * math.exp(18.6686 - 4062.13 / (ta + 235.0))
        
        icl = 0.155 * clo
        fcl = 1.0 + 0.2 * clo if clo < 0.5 else 1.05 + 0.1 * clo
        
        # Heat transfer coefficient by natural convection
        hcf = 12.1 * math.sqrt(vel)
        taa = ta + 273.15
        tra = tr + 273.15
        
        # Solve for clothing surface temp (tcl) iteratively
        tcl = taa + (35.5 - ta) / (3.5 * (6.45 * icl + .1))
        for _ in range(5):
            hcc = 2.38 * (abs(tcl - taa) ** 0.25)
            hc = hcc if hcc > hcf else hcf
            tcl = 35.7 - 0.028 * (met * 58.15) - icl * (
                3.96e-8 * fcl * (tcl**4 - tra**4) + fcl * hc * (tcl - taa)
            )
        
        # Heat loss components
        mw = met * 58.15  # W/m2
        hl1 = 3.05e-3 * (5733 - 6.99 * mw - pa * 1000)  # Skin diff diffusion
        hl2 = 0.42 * (mw - 58.15) if mw > 58.15 else 0.0  # Sweat
        hl3 = 1.7e-5 * met * (5867 - pa * 1000)  # Respiration latent
        hl4 = 0.0014 * met * (34 - ta)  # Respiration dry
        hl5 = 3.96e-8 * fcl * (tcl**4 - tra**4)  # Radiation
        hl6 = fcl * hc * (tcl - taa)  # Convection
        
        # Thermal sensation transfer coefficient
        ts = 0.303 * math.exp(-0.036 * met)
        pmv = ts * (mw - hl1 - hl2 - hl3 - hl4 - hl5 - hl6)
        
        # Limit PMV to standard [-3, +3] range
        self.pmv = max(-3.0, min(3.0, pmv))
        
        # PPD calculation
        ppd = 100.0 - 95.0 * math.exp(-0.03353 * (self.pmv**4) - 0.2179 * (self.pmv**2))
        self.ppd = max(5.0, min(99.0, ppd))
        return self.pmv, self.ppd


class BuildingSimulation:
    def __init__(self):
        # 3 Zones
        self.zones = {
            "Zone_A_Executive": Zone(
                name="Zone A - Executive Suite (East)",
                volume=300.0,
                thermal_capacitance=12000.0, # kJ/K
                wall_area=80.0,
                u_value=0.35, # Good insulation
                peak_occupants=8,
                base_equipment_load=800.0, # W
                has_solar=True,
                solar_direction="east"
            ),
            "Zone_B_Workspace": Zone(
                name="Zone B - Open Workspace (West)",
                volume=900.0,
                thermal_capacitance=36000.0,
                wall_area=220.0,
                u_value=0.45,
                peak_occupants=35,
                base_equipment_load=4500.0,
                has_solar=True,
                solar_direction="west"
            ),
            "Zone_C_DataRoom": Zone(
                name="Zone C - Data Server Room (Core)",
                volume=200.0,
                thermal_capacitance=9000.0,
                wall_area=40.0,
                u_value=0.15, # Interior insulated walls
                peak_occupants=0, # No occupants
                base_equipment_load=12000.0, # Constant 12 kW server load
                has_solar=False
            )
        }
        
        # Global states
        self.simulation_hour = 0
        self.day_of_year = 200  # Summer day (July 19)
        self.active_scenario = "summer_heatwave"
        self.ai_enabled = False
        
        # Historical metrics tracker
        self.history = []
        self.baseline_history = []
        
        # Cumulative scores
        self.cumulative_cost = 0.0
        self.cumulative_carbon = 0.0
        self.baseline_cumulative_cost = 0.0
        self.baseline_cumulative_carbon = 0.0
        
        self.ai_thought_log = []
        
        # Constants
        self.COP_base = 3.5  # HVAC cooling base COP
        self.COP_heating_base = 3.0  # HVAC heating COP
        
    def get_weather(self, hour, scenario=None):
        """Generates dynamic weather based on scenario and hour of day."""
        scen = scenario or self.active_scenario
        
        # Base sinusoidal temp wave
        if scen == "summer_heatwave":
            mean_temp = 30.0
            range_temp = 10.0
            peak_hour = 15.0
            humidity = 45.0 + 15.0 * math.sin((hour - 6.0) * math.pi / 12.0)
            solar_peak = 900.0  # W/m^2
        elif scen == "winter_storm":
            mean_temp = -1.0
            range_temp = 6.0
            peak_hour = 14.0
            humidity = 70.0 + 10.0 * math.sin((hour - 12.0) * math.pi / 12.0)
            solar_peak = 250.0
        elif scen == "carbon_crisis":
            mean_temp = 22.0
            range_temp = 7.0
            peak_hour = 15.0
            humidity = 50.0
            solar_peak = 650.0
        else:  # shoulder_day (Spring/Autumn)
            mean_temp = 16.0
            range_temp = 6.0
            peak_hour = 14.0
            humidity = 55.0
            solar_peak = 550.0
            
        outdoor_temp = mean_temp + range_temp * math.cos((hour - peak_hour) * math.pi / 12.0)
        
        # Solar radiation model
        solar_rad = 0.0
        if 6.0 <= hour <= 18.0:
            solar_rad = solar_peak * math.sin((hour - 6.0) * math.pi / 12.0)
            
        return {
            "outdoor_temp": round(outdoor_temp, 2),
            "solar_rad": round(solar_rad, 2),
            "humidity": round(humidity, 2)
        }

    def get_occupancy(self, hour):
        """Generates occupancy density based on typical office hours."""
        if 8.0 <= hour <= 12.0:
            # Morning buildup
            factor = (hour - 8.0) / 4.0
        elif 12.0 <= hour <= 13.5:
            # Lunch dip
            factor = 0.4
        elif 13.5 <= hour <= 17.0:
            # Afternoon peak
            factor = 1.0
        elif 17.0 <= hour <= 20.0:
            # Evening departure
            factor = 1.0 - (hour - 17.0) / 3.0
        else:
            # Night
            factor = 0.02  # Minimal cleaning/security staff
            
        return max(0.0, min(1.0, factor))

    def get_electricity_price(self, hour):
        """Time-of-Use pricing ($/kWh)"""
        # Peak: 14:00 - 20:00 (0.45 $/kWh)
        # Mid-peak: 08:00-14:00, 20:00-22:00 (0.22 $/kWh)
        # Off-peak: 22:00 - 08:00 (0.09 $/kWh)
        if 14.0 <= hour < 20.0:
            return 0.45
        elif (8.0 <= hour < 14.0) or (20.0 <= hour < 22.0):
            return 0.22
        else:
            return 0.09

    def get_grid_carbon(self, hour, scenario=None):
        """Grid carbon intensity in kg CO2 per kWh."""
        # Carbon intensity peaks in evening when solar is low and gas turbines ramp up.
        # It is lowest in midday when solar generation is high.
        scen = scenario or self.active_scenario
        base_intensity = 0.35  # kg CO2/kWh
        
        if scen == "carbon_crisis":
            # Grid failure or coal backup activated
            base_intensity = 0.65
            
        # Sinusoidal variation: peak carbon at 19:00, lowest at 12:00
        variation = 0.15 * math.sin((hour - 13.0) * math.pi / 6.0)
        return round(max(0.1, base_intensity + variation), 3)

    def calculate_zone_physics(self, zone, outdoor, hour, time_step_hours=1.0):
        """
        Physics-based thermal dynamics: calculates HVAC load, temperatures, and power.
        """
        # 1. Internal gains
        occ_factor = self.get_occupancy(hour)
        occupants = zone.peak_occupants * occ_factor
        q_people = occupants * 115.0  # 115W sensible heat per person
        
        # Base equipment heat + lighting heat
        # 100% lights = 12 W per m2. Lights dimming converts power to heat
        q_lights = zone.light_dim_level * (zone.volume * 0.04 * 12.0)  # approx lighting heat gain
        q_equipment = zone.base_equipment_load
        
        q_internal = q_people + q_lights + q_equipment  # Watts
        
        # 2. Solar gains (if zone has solar exposure)
        q_solar = 0.0
        if zone.has_solar and outdoor["solar_rad"] > 0:
            # Solar gain depends on orientation and solar radiation
            if zone.solar_direction == "east" and hour < 13.0:
                q_solar = outdoor["solar_rad"] * 15.0 * math.cos((hour - 9.0) * math.pi / 8.0)
            elif zone.solar_direction == "west" and hour >= 11.0:
                q_solar = outdoor["solar_rad"] * 25.0 * math.cos((hour - 16.0) * math.pi / 8.0)
        q_solar = max(0.0, q_solar)
        
        # 3. Envelope heat transfer (Conduction)
        # Q_envelope = U * A * (T_ext - T_indoor)
        q_envelope = zone.U * zone.A * (outdoor["outdoor_temp"] - zone.temp)  # Watts
        
        # 4. Infiltration/Ventilation heat gain
        # Air density = 1.2 kg/m^3, Specific heat of air = 1005 J/kg-K
        # Q_vent = m_dot * Cp * (T_ext - T_indoor)
        m_dot = zone.airflow_rate * 1.2  # kg/s
        q_vent = m_dot * 1005.0 * (outdoor["outdoor_temp"] - zone.temp)  # Watts
        
        # Net passive heat load in Watts (Joules/sec)
        q_passive = q_internal + q_solar + q_envelope + q_vent
        
        # 5. HVAC Heat Extraction / Injection
        # HVAC system tries to maintain temperature within [heating_setpoint, cooling_setpoint]
        q_hvac_needed = 0.0
        
        # Thermal dynamics update without HVAC
        temp_no_hvac = zone.temp + (q_passive * 3600.0 * time_step_hours) / (zone.C * 1000.0) # kJ to J
        
        if temp_no_hvac > zone.cooling_setpoint:
            # Cooling needed
            cooling_cap = zone.volume * 45.0  # W (cooling capacity limit)
            target_heat_removal = (temp_no_hvac - zone.cooling_setpoint) * zone.C * 1000.0 / (3600.0 * time_step_hours)
            q_hvac_needed = -min(target_heat_removal, cooling_cap)  # Negative is cooling
        elif temp_no_hvac < zone.heating_setpoint:
            # Heating needed
            heating_cap = zone.volume * 35.0  # W (heating capacity limit)
            target_heat_addition = (zone.heating_setpoint - temp_no_hvac) * zone.C * 1000.0 / (3600.0 * time_step_hours)
            q_hvac_needed = min(target_heat_addition, heating_cap)
            
        # 6. Actual Temperature update
        q_net = q_passive + q_hvac_needed
        zone.temp = zone.temp + (q_net * 3600.0 * time_step_hours) / (zone.C * 1000.0)
        
        # 7. Energy Consumption
        # Cooling Power = Q_cool / COP
        # Heating Power = Q_heat / COP_heating
        if q_hvac_needed < 0:
            # COP decreases with higher outdoor temperatures
            cop = self.COP_base - 0.04 * max(0, outdoor["outdoor_temp"] - 25)
            zone.hvac_cooling_power = abs(q_hvac_needed)
            zone.hvac_heating_power = 0.0
            hvac_electric_w = abs(q_hvac_needed) / max(1.5, cop)
        elif q_hvac_needed > 0:
            # COP decreases with lower outdoor temperatures
            cop = self.COP_heating_base - 0.03 * max(0, 7.0 - outdoor["outdoor_temp"])
            zone.hvac_cooling_power = 0.0
            zone.hvac_heating_power = q_hvac_needed
            hvac_electric_w = q_hvac_needed / max(1.2, cop)
        else:
            zone.hvac_cooling_power = 0.0
            zone.hvac_heating_power = 0.0
            hvac_electric_w = 0.0
            
        # Lighting electrical power
        # Base lighting power is 10 W per m^2
        floor_area = zone.volume / 3.0  # assume 3m height
        zone.lighting_power = zone.light_dim_level * floor_area * 10.0
        
        # PMV Update
        zone.compute_pmv_fanger(rh=outdoor["humidity"])
        
        return hvac_electric_w, zone.lighting_power

    def step(self):
        """Advances the simulation by 1 simulation hour."""
        hour = self.simulation_hour % 24
        outdoor = self.get_weather(hour)
        price = self.get_electricity_price(hour)
        carbon_intensity = self.get_grid_carbon(hour)
        
        # Calculate active control run (this could be AI-driven or manually set)
        total_hvac_w = 0.0
        total_light_w = 0.0
        
        for name, zone in self.zones.items():
            hvac_w, light_w = self.calculate_zone_physics(zone, outdoor, hour)
            total_hvac_w += hvac_w
            total_light_w += light_w
            
        # Server equipment power is always active (Zone C)
        server_w = self.zones["Zone_C_DataRoom"].base_equipment_load
        total_power_kw = (total_hvac_w + total_light_w + server_w) / 1000.0
        
        step_cost = total_power_kw * price
        step_carbon = total_power_kw * carbon_intensity
        
        self.cumulative_cost += step_cost
        self.cumulative_carbon += step_carbon
        
        # Log active run history
        active_snapshot = {
            "hour": self.simulation_hour,
            "hour_of_day": hour,
            "outdoor_temp": outdoor["outdoor_temp"],
            "solar_rad": outdoor["solar_rad"],
            "humidity": outdoor["humidity"],
            "price": price,
            "carbon_intensity": carbon_intensity,
            "occupancy": self.get_occupancy(hour),
            "zones": {
                name: {
                    "temp": round(z.temp, 2),
                    "cooling_setpoint": z.cooling_setpoint,
                    "heating_setpoint": z.heating_setpoint,
                    "light_dim_level": round(z.light_dim_level, 2),
                    "airflow_rate": z.airflow_rate,
                    "pmv": round(z.pmv, 3),
                    "ppd": round(z.ppd, 1),
                    "hvac_power_kw": round((z.hvac_cooling_power + z.hvac_heating_power) / 1000.0, 3),
                    "light_power_kw": round(z.lighting_power / 1000.0, 3)
                }
                for name, z in self.zones.items()
            },
            "total_power_kw": round(total_power_kw, 2),
            "step_cost": round(step_cost, 4),
            "step_carbon": round(step_carbon, 4),
            "cumulative_cost": round(self.cumulative_cost, 2),
            "cumulative_carbon": round(self.cumulative_carbon, 2)
        }
        self.history.append(active_snapshot)
        
        # Calculate Baseline run parallelly for savings comparison
        # Baseline uses static schedules: Cooling = 22.0°C, Heating = 20.0°C.
        # Lights: 100% on during day (8 to 18), off at night (10% stand-by)
        baseline_total_hvac_w = 0.0
        baseline_total_light_w = 0.0
        
        # We simulate baseline state inside local variables to avoid messing with current state
        # Create a mock of zones with baseline rules
        for name, zone in self.zones.items():
            # Create a clone representation for the baseline run
            # To make calculations exact, we keep tracking a parallel baseline temperature
            if not hasattr(self, 'baseline_temps'):
                self.baseline_temps = {n: 22.0 for n in self.zones}
                
            base_z = Zone(
                name=zone.name,
                volume=zone.volume,
                thermal_capacitance=zone.C,
                wall_area=zone.A,
                u_value=zone.U,
                peak_occupants=zone.peak_occupants,
                base_equipment_load=zone.base_equipment_load,
                has_solar=zone.has_solar,
                solar_direction=zone.solar_direction
            )
            base_z.temp = self.baseline_temps[name]
            base_z.cooling_setpoint = 22.0 # Fixed comfortable cooling setpoint
            base_z.heating_setpoint = 20.0 # Fixed heating setpoint
            
            # Static lights schedule
            if 8.0 <= hour <= 18.0:
                base_z.light_dim_level = 1.0
            else:
                base_z.light_dim_level = 0.1 # Night standby
                
            # Physics call
            b_hvac_w, b_light_w = self.calculate_zone_physics(base_z, outdoor, hour)
            self.baseline_temps[name] = base_z.temp
            
            baseline_total_hvac_w += b_hvac_w
            baseline_total_light_w += b_light_w
            
        baseline_power_kw = (baseline_total_hvac_w + baseline_total_light_w + server_w) / 1000.0
        baseline_step_cost = baseline_power_kw * price
        baseline_step_carbon = baseline_power_kw * carbon_intensity
        
        self.baseline_cumulative_cost += baseline_step_cost
        self.baseline_cumulative_carbon += baseline_step_carbon
        
        baseline_snapshot = {
            "hour": self.simulation_hour,
            "total_power_kw": round(baseline_power_kw, 2),
            "cumulative_cost": round(self.baseline_cumulative_cost, 2),
            "cumulative_carbon": round(self.baseline_cumulative_carbon, 2)
        }
        self.baseline_history.append(baseline_snapshot)
        
        # Increment hour
        self.simulation_hour += 1
        
        return active_snapshot, baseline_snapshot

    def set_scenarios(self, scenario_name):
        if scenario_name in ["summer_heatwave", "winter_storm", "shoulder_day", "carbon_crisis"]:
            self.active_scenario = scenario_name
            # Reset thermal states to clean starting points for new scenarios
            self.simulation_hour = 0
            self.cumulative_cost = 0.0
            self.cumulative_carbon = 0.0
            self.baseline_cumulative_cost = 0.0
            self.baseline_cumulative_carbon = 0.0
            self.history.clear()
            self.baseline_history.clear()
            self.ai_thought_log.clear()
            
            # Initial states
            if scenario_name == "winter_storm":
                init_temp = 12.0
            else:
                init_temp = 24.0
                
            self.baseline_temps = {n: init_temp for n in self.zones}
            for z in self.zones.values():
                z.temp = init_temp
                if scenario_name == "winter_storm":
                    z.cooling_setpoint = 22.0
                    z.heating_setpoint = 18.0
                else:
                    z.cooling_setpoint = 24.0
                    z.heating_setpoint = 20.0
                z.light_dim_level = 1.0
                
            return True
        return False
        
    def add_ai_thought(self, message):
        timestamp = time.strftime("%H:%M:%S")
        sim_hour_str = f"Hour {self.simulation_hour % 24}:00"
        self.ai_thought_log.append({
            "timestamp": timestamp,
            "sim_hour": sim_hour_str,
            "message": message
        })
        # Cap thoughts list
        if len(self.ai_thought_log) > 50:
            self.ai_thought_log.pop(0)

# Local unit test
if __name__ == "__main__":
    sim = BuildingSimulation()
    print("Testing Building Physics Simulator...")
    # Step through 24 hours of summer heatwave
    for i in range(24):
        active, baseline = sim.step()
        print(f"Hour {active['hour_of_day']:02d}: Outdoor: {active['outdoor_temp']}°C | Power: {active['total_power_kw']}kW | Baseline Power: {baseline['total_power_kw']}kW")
    print("Test Complete. Cost saved: $", round(sim.baseline_cumulative_cost - sim.cumulative_cost, 2))

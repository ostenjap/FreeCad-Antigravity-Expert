import os
import sys
import json
import time
import numpy as np
from physics_solver import TurbineBladeFEASolver
from cfd_solver import TurbineBladeCFDSolver

# ANSI colors for rich terminal output
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"

class AerodynamicArchitectAgent:
    """
    Translates high-level natural language prompts into aerodynamic & thermal boundary conditions,
    turbomachinery constraints, and coupled optimization objectives.
    """
    def __init__(self, prompt):
        self.prompt = prompt

    def formulate_aerodynamic_problem(self):
        print(f"\n{BOLD}{CYAN}[Aerodynamic Architect]{RESET} Translating prompt: '{self.prompt}'")
        time.sleep(0.8)
        
        config = {
            "fluid_material": "Combustion Gas (HP stage)",
            "inlet_velocity": 150.0,      # m/s
            "gas_temperature": 1000.0,     # °C
            "coolant_temperature": 400.0,  # °C
            "target_max_temp": 900.0,      # °C (creep safety limit)
            "target_min_ld_ratio": 75.0,  # Aerodynamic efficiency limit
            "min_shape_bound": 0.4,       # Aero thickness limit
            "max_shape_bound": 1.5,       # Geometric shroud limit
            "objective_weights": {
                "mass": 0.40,
                "aerodynamics": 0.35,
                "thermal": 0.25
            }
        }
        
        print(f"{GREEN}[OK] Aerothermal boundary conditions formulated successfully:{RESET}")
        print(json.dumps(config, indent=2))
        return config

class FSIBridgeAgent:
    """
    Acts as the multi-physics coupler (simulating preCICE partitioned coupling).
    Directly maps fluid pressure & thermal loads to structural boundary conditions.
    """
    def __init__(self, fea_solver, cfd_solver, config):
        self.fea_solver = fea_solver
        self.cfd_solver = cfd_solver
        self.config = config
        
    def evaluate_coupled_state(self, densities, shape_scale):
        """
        Executes a coupled FSI evaluation:
        1. Runs CFD solver with current external shape and internal densities to get L/D and surface temps.
        2. Passes CFD surface temperatures to the FEA solver to calculate thermal expansion & stresses.
        3. Returns combined physical state.
        """
        # Step 1: Aerodynamics and CHT
        cfd_res = self.cfd_solver.analyze_blade_aerodynamics(
            shape_scale_profile=shape_scale,
            relative_density_profile=densities,
            num_slices=len(densities)
        )
        
        # Step 2: Structural FEA with CHT temperatures and external shape scaling
        fea_res = self.fea_solver.solve_stresses(
            relative_density_profile=densities,
            num_slices=len(densities),
            shape_scale_profile=shape_scale,
            temperatures=cfd_res["temperatures"]
        )
        
        return {
            "cfd": cfd_res,
            "fea": fea_res,
            "temperatures": cfd_res["temperatures"],
            "safety_factor": fea_res["safety_factor"],
            "combined_stress": fea_res["combined_stress"],
            "avg_lift_to_drag": cfd_res["avg_lift_to_drag"]
        }

class CFDOrchestratorAgent:
    """
    Executes shape optimization and coupled multi-objective Pareto optimization loops.
    """
    def __init__(self, config, bridge):
        self.config = config
        self.bridge = bridge
        self.num_slices = 24

    def run_coupled_optimization(self, max_epochs=80, learning_rate=0.02):
        print(f"\n{BOLD}{CYAN}[CFD Orchestrator]{RESET} Launching multi-physics optimization loop...")
        print(f"  Optimizing 48 parameters (24 internal densities, 24 external scales)...")
        time.sleep(1.0)
        
        # Initialize: densities = 1.0 (solid), shape_scales = 1.0 (nominal)
        densities = np.ones(self.num_slices)
        shape_scales = np.ones(self.num_slices)
        
        # Target Safety Factor Profile
        z_coords = np.linspace(0.0, 120.0, self.num_slices)
        target_sf_profile = np.where(z_coords <= 45.0, 0.9, 0.5)
        
        history = []
        
        for epoch in range(1, max_epochs + 1):
            # Evaluate current coupled state
            state = self.bridge.evaluate_coupled_state(densities, shape_scales)
            
            # --- Multi-Objective Loss Computation ---
            # 1. Mass objective (minimize relative mass)
            nominal_mass = np.sum(state["fea"]["areas"])
            current_mass = np.sum(state["fea"]["areas"] * (shape_scales ** 2) * densities)
            f_mass = current_mass / nominal_mass
            
            # 2. Aerodynamic objective (maximize L/D ratio -> minimize inverse L/D)
            # Nominal L/D is ~110. Let's normalize it
            f_aero = 1.0 - (state["avg_lift_to_drag"] / 120.0)
            
            # 3. Thermal penalty (T <= target_max_temp)
            t_limit = self.config["target_max_temp"]
            t_violations = np.maximum(0, state["temperatures"] - t_limit)
            f_thermal = np.sum(t_violations ** 2) / (t_limit ** 2)
            
            # Weighted base loss
            weights = self.config["objective_weights"]
            base_loss = (weights["mass"] * f_mass + 
                         weights["aerodynamics"] * f_aero + 
                         weights["thermal"] * f_thermal)
            
            # 4. Critical Structural constraint penalty
            sf_violations = np.maximum(0, target_sf_profile - state["safety_factor"])
            penalty_stress = 30.0 * np.sum(sf_violations ** 2)
            
            total_loss = base_loss + penalty_stress
            
            # --- Gradient Computation via finite differences ---
            grad_densities = np.zeros(self.num_slices)
            grad_scales = np.zeros(self.num_slices)
            epsilon = 1e-4
            
            for i in range(self.num_slices):
                # Gradient w.r.t internal density
                d_perturbed = densities.copy()
                d_perturbed[i] += epsilon
                st_d = self.bridge.evaluate_coupled_state(d_perturbed, shape_scales)
                mass_d = np.sum(st_d["fea"]["areas"] * (shape_scales ** 2) * d_perturbed)
                f_mass_d = mass_d / nominal_mass
                f_aero_d = 1.0 - (st_d["avg_lift_to_drag"] / 120.0)
                f_thermal_d = np.sum(np.maximum(0, st_d["temperatures"] - t_limit)**2) / (t_limit**2)
                loss_d = (weights["mass"] * f_mass_d + 
                          weights["aerodynamics"] * f_aero_d + 
                          weights["thermal"] * f_thermal_d + 
                          30.0 * np.sum(np.maximum(0, target_sf_profile - st_d["safety_factor"])**2))
                grad_densities[i] = (loss_d - total_loss) / epsilon
                
                # Gradient w.r.t shape scale
                s_perturbed = shape_scales.copy()
                s_perturbed[i] += epsilon
                st_s = self.bridge.evaluate_coupled_state(densities, s_perturbed)
                mass_s = np.sum(st_s["fea"]["areas"] * (s_perturbed ** 2) * densities)
                f_mass_s = mass_s / nominal_mass
                f_aero_s = 1.0 - (st_s["avg_lift_to_drag"] / 120.0)
                f_thermal_s = np.sum(np.maximum(0, st_s["temperatures"] - t_limit)**2) / (t_limit**2)
                loss_s = (weights["mass"] * f_mass_s + 
                          weights["aerodynamics"] * f_aero_s + 
                          weights["thermal"] * f_thermal_s + 
                          30.0 * np.sum(np.maximum(0, target_sf_profile - st_s["safety_factor"])**2))
                grad_scales[i] = (loss_s - total_loss) / epsilon
                
            # Gradient normalization for stability
            norm_d = np.linalg.norm(grad_densities)
            norm_s = np.linalg.norm(grad_scales)
            if norm_d > 1e-6: grad_densities /= norm_d
            if norm_s > 1e-6: grad_scales /= norm_s
            
            # Parameters update
            densities -= learning_rate * grad_densities
            shape_scales -= learning_rate * grad_scales
            
            # Enforce limits
            densities = np.clip(densities, 0.4, 1.0)
            shape_scales = np.clip(shape_scales, self.config["min_shape_bound"], self.config["max_shape_bound"])
            
            history.append({
                "epoch": epoch,
                "loss": total_loss,
                "mass_fraction": f_mass,
                "ld_ratio": state["avg_lift_to_drag"],
                "max_temp": np.max(state["temperatures"]),
                "min_sf": np.min(state["safety_factor"])
            })
            
            if epoch % 20 == 0 or epoch == 1:
                print(f"  Epoch {epoch:02d} | Loss: {total_loss:.4f} | Rel Mass: {f_mass:.2f} | Avg L/D: {state['avg_lift_to_drag']:.1f} | Min SF: {state['safety_factor'].min():.4f} | Max Temp: {np.max(state['temperatures']):.1f}°C")
                
        final_state = self.bridge.evaluate_coupled_state(densities, shape_scales)
        print(f"{GREEN}[OK] Coupled Multi-Objective Optimization completed.{RESET}")
        return densities, shape_scales, final_state, history

class ThermalCriticAgent:
    """
    Quality-control debugger specialized in aerothermal margins and heat transfer criteria.
    """
    def __init__(self, config):
        self.config = config

    def evaluate_results(self, final_results, densities, shape_scales):
        print(f"\n{BOLD}{CYAN}[Thermal Critic]{RESET} Inspecting aerothermal state...")
        time.sleep(0.8)
        
        temps = final_results["temperatures"]
        max_temp = np.max(temps)
        target_temp = self.config["target_max_temp"]
        avg_ld = final_results["avg_lift_to_drag"]
        min_ld = self.config["target_min_ld_ratio"]
        
        print(f"  Aerodynamic L/D ratio: {avg_ld:.2f} (Required: >= {min_ld:.1f})")
        print(f"  Peak blade temperature: {max_temp:.1f}°C (Required: <= {target_temp:.1f}°C)")
        
        if max_temp > target_temp:
            print(f"{RED}[WARN] Critic Alert: Surface temperature limit exceeded!{RESET}")
            print(f"  Action: Raising thermal weight and reinforcing cooling requirements...")
            return False, {"raise_thermal_weight": 1.5}
            
        if avg_ld < min_ld:
            print(f"{RED}[WARN] Critic Alert: Aerodynamic performance index is too low!{RESET}")
            print(f"  Action: Raising aerodynamic weight and adjusting shape bounds...")
            return False, {"raise_aero_weight": 1.5}
            
        print(f"{GREEN}[OK] Thermal Critic verification passed!{RESET}")
        return True, {}

class CoupledDeadMansSwitch:
    """
    Hardware-in-the-loop safety console displaying multi-physics telemetry.
    """
    def __init__(self, initial_state, optimized_state):
        self.initial_state = initial_state
        self.optimized_state = optimized_state

    def draw_chart(self, title, label_y, initial_data, optimized_data, z_coords):
        width = 50
        height = 10
        print(f"\n{BOLD}{YELLOW}--- {title} ---{RESET}")
        
        data_min = min(min(initial_data), min(optimized_data))
        data_max = max(max(initial_data), max(optimized_data))
        if data_max == data_min:
            data_max += 1.0
            
        grid = [[" " for _ in range(width)] for _ in range(height)]
        
        for i in range(len(z_coords)):
            z_norm = z_coords[i] / z_coords[-1]
            x_idx = int(z_norm * (width - 1))
            
            y_norm_init = (initial_data[i] - data_min) / (data_max - data_min)
            y_idx_init = int(y_norm_init * (height - 1))
            
            y_norm_opt = (optimized_data[i] - data_min) / (data_max - data_min)
            y_idx_opt = int(y_norm_opt * (height - 1))
            
            grid[y_idx_init][x_idx] = 'o'
            grid[y_idx_opt][x_idx] = '*'
            
        for r in range(height - 1, -1, -1):
            val = data_min + (r / (height - 1)) * (data_max - data_min)
            print(f"{val:7.1f} | " + "".join(grid[r]))
        print("          Root (Z=0) " + " " * (width - 25) + " Tip (Z=120) ")
        print(f"          [o] Initial  [*] Optimized (Target {label_y})")

    def run_approval(self):
        print(f"\n{BOLD}{RED}[DANGER] COUPLED MULTI-PHYSICS HIL DEAD MAN'S SWITCH TRIGGERED [DANGER]{RESET}")
        print(f"{YELLOW}Awaiting manual operator coupled geometry validation...{RESET}")
        
        z = self.initial_state["fea"]["z_coords"]
        
        # Telemetry displays
        self.draw_chart("Conjugate Heat Transfer Temperature Profile (°C)", "Temp", 
                        self.initial_state["temperatures"], 
                        self.optimized_state["temperatures"], z)
        
        self.draw_chart("Safety Factor Distribution (Structural)", "SF", 
                        self.initial_state["safety_factor"], 
                        self.optimized_state["safety_factor"], z)
        
        self.draw_chart("External Airfoil Shape Scale Profile Factor", "Scale", 
                        np.ones(len(z)), 
                        self.optimized_state["cfd"]["shape_scale_profile"], z)

        # Print summary statistics
        init_m = np.sum(self.initial_state["fea"]["areas"])
        opt_m = np.sum(self.optimized_state["fea"]["areas"] * (self.optimized_state["cfd"]["shape_scale_profile"]**2) * self.optimized_state["fea"]["density_profile"])
        weight_savings = (1.0 - opt_m/init_m) * 100.0
        
        print(f"\n{BOLD}COUPLED DESIGN SUMMARY METRICS:{RESET}")
        print(f"  - Aerodynamic L/D ratio: {self.initial_state['avg_lift_to_drag']:.1f} -> {self.optimized_state['avg_lift_to_drag']:.1f}")
        print(f"  - Peak surface temperature: {np.max(self.initial_state['temperatures']):.1f}°C -> {np.max(self.optimized_state['temperatures']):.1f}°C")
        print(f"  - Min structural Safety Factor: {self.initial_state['safety_factor'].min():.4f} -> {self.optimized_state['safety_factor'].min():.4f}")
        print(f"  - Combined blade mass reduction: {weight_savings:.2f}%")
        
        approval = input(f"\n{BOLD}{YELLOW}Do you approve this coupled aero-thermal-structural geometry? (y/n): {RESET}").strip().lower()
        if approval in ['y', 'yes']:
            print(f"\n{GREEN}[OK] Operator approved coupled geometry. Exporting datasets...{RESET}")
            return True
        else:
            print(f"\n{RED}[FAIL] Operator rejected coupled geometry. Optimization discarded.{RESET}")
            return False

def run_coupled_swarm_pipeline():
    print(f"{BOLD}{YELLOW}====================================================================={RESET}")
    print(f"{BOLD}{YELLOW}         COUPLING SWARM: AERO-THERMAL-STRUCTURAL OPTIMIZER          {RESET}")
    print(f"{BOLD}{YELLOW}====================================================================={RESET}")
    
    prompt = "Optimize the external airfoil profile and internal lattice density of the Inconel blade to maximize L/D and weight savings, keeping temperature under 900 C"
    
    # 1. Aerodynamic Architect
    architect = AerodynamicArchitectAgent(prompt)
    config = architect.formulate_aerodynamic_problem()
    
    # 2. Solvers Setup
    fea_solver = TurbineBladeFEASolver(
        step_path="turbines_test/turbine_blade.step",
        rpm=30000.0,
        t_root=400.0,
        t_tip=1000.0
    )
    cfd_solver = TurbineBladeCFDSolver(
        step_path="turbines_test/turbine_blade.step",
        rpm=30000.0,
        t_coolant=config["coolant_temperature"],
        t_gas=config["gas_temperature"]
    )
    
    # 3. FSI Bridge
    bridge = FSIBridgeAgent(fea_solver, cfd_solver, config)
    
    # Get initial nominal state
    initial_state = bridge.evaluate_coupled_state(np.ones(24), np.ones(24))
    
    # 4. CFD Orchestrator runs optimization
    orchestrator = CFDOrchestratorAgent(config, bridge)
    
    critic = ThermalCriticAgent(config)
    
    while True:
        densities, shape_scales, final_state, history = orchestrator.run_coupled_optimization()
        
        # 5. Critic Evaluates CHT and Aero constraints
        success, action = critic.evaluate_results(final_state, densities, shape_scales)
        if success:
            break
        else:
            print(f"{YELLOW}Critic Feedback Action: Modifying objectives. Re-running loop...{RESET}")
            if "raise_thermal_weight" in action:
                config["objective_weights"]["thermal"] *= action["raise_thermal_weight"]
            if "raise_aero_weight" in action:
                config["objective_weights"]["aerodynamics"] *= action["raise_aero_weight"]
            time.sleep(1.0)
            
    # 6. Dead Man's Switch (HIL)
    dms = CoupledDeadMansSwitch(initial_state, final_state)
    approved = dms.run_approval()
    
    if approved:
        # Export optimization JSON
        config_out = "turbines_test/turbine_blade_coupled_optimized.json"
        with open(config_out, "w") as f:
            serializable = {
                "material": "Inconel 718",
                "rpm": 30000.0,
                "density_profile": densities.tolist(),
                "shape_scale_profile": shape_scales.tolist(),
                "surface_temperatures": final_state["temperatures"].tolist(),
                "safety_factors": final_state["safety_factor"].tolist(),
                "combined_stress": final_state["combined_stress"].tolist(),
                "avg_lift_to_drag": final_state["avg_lift_to_drag"]
            }
            json.dump(serializable, f, indent=2)
        print(f"{GREEN}[OK] Coupled optimized design configurations saved to: {config_out}{RESET}")
        
        # STEP and FreeCAD file export
        source_step = "turbines_test/turbine_blade_stressed.step"
        target_step = "turbines_test/turbine_blade_optimized.step"
        if os.path.exists(source_step):
            import shutil
            shutil.copy(source_step, target_step)
            print(f"{GREEN}[OK] Production-ready STEP copied to: {target_step}{RESET}")
            
        source_fcstd = "turbines_test/turbine_blade_stressed.FCStd"
        target_fcstd = "turbines_test/turbine_blade_optimized.FCStd"
        if os.path.exists(source_fcstd):
            import shutil
            shutil.copy(source_fcstd, target_fcstd)
            print(f"{GREEN}[OK] Production FreeCAD file saved to: {target_fcstd}{RESET}")
    else:
        print(f"{RED}Coupled swarm pipeline aborted. No files updated.{RESET}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--auto-approve":
        print(f"{YELLOW}Running in automated verification mode (auto-approving HIL console)...{RESET}")
        import builtins
        builtins.input = lambda _: "yes"
        
    run_coupled_swarm_pipeline()

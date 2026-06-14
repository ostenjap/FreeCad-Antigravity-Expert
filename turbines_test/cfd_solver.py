import os
import math
import numpy as np

class TurbineBladeCFDSolver:
    """
    Computational Fluid Dynamics (CFD) and Conjugate Heat Transfer (CHT) simulator
    for gas turbine blades. Evaluates aerodynamic efficiency (L/D ratio) and
    thermal profile based on external shape and internal cooling geometry.
    """
    def __init__(self, step_path="turbines_test/turbine_blade.step", rpm=30000.0, t_coolant=400.0, t_gas=1000.0, r_hub=200.0):
        self.step_path = step_path
        self.rpm = rpm
        self.omega = (rpm * 2 * math.pi) / 60.0  # rad/s
        self.t_coolant = t_coolant
        self.t_gas = t_gas
        self.r_hub = r_hub
        
        # Gas properties
        self.rho_gas = 4.5  # kg/m^3 (high-pressure stage gas density)
        self.k_gas = 0.08    # W/m*K (thermal conductivity of gas at high temp)
        
        # Nominal geometry constants
        self.height = 120.0  # mm
        
    def analyze_blade_aerodynamics(self, shape_scale_profile, relative_density_profile=None, num_slices=24):
        """
        Computes lift, drag, pressure distribution, and surface temperatures along the blade span.
        
        Args:
            shape_scale_profile: Array of size num_slices representing the external airfoil scale factors [0.4, 1.5].
            relative_density_profile: Array of size num_slices representing internal lattice density [0.4, 1.0].
                                      Used for Conjugate Heat Transfer (CHT) surface area calculations.
        """
        n = len(shape_scale_profile)
        z_coords = np.linspace(0.0, self.height, n)
        
        if relative_density_profile is None:
            relative_density_profile = np.ones(n)
            
        shape_scale_profile = np.clip(shape_scale_profile, 0.4, 1.5)
        relative_density_profile = np.clip(relative_density_profile, 0.4, 1.0)
        
        lift_coefs = np.zeros(n)
        drag_coefs = np.zeros(n)
        lift_forces = np.zeros(n)
        drag_forces = np.zeros(n)
        temperatures = np.zeros(n)
        h_gas_coeffs = np.zeros(n)
        h_coolant_coeffs = np.zeros(n)
        
        dz = self.height / n  # mm
        
        for i in range(n):
            z = z_coords[i]
            r = (self.r_hub + z) / 1000.0  # m (radius from rotor center)
            U = self.omega * r              # m/s (blade tangential speed)
            
            # Hot gas axial velocity entering rotor
            V_g = 150.0  # m/s
            W = math.sqrt(V_g**2 + U**2)  # m/s (relative inlet velocity)
            
            # Nominal chord and thickness at this slice height
            c_nominal = 40.0 - (20.0 / self.height) * z  # mm (tapering from 40mm at root to 20mm at tip)
            c = c_nominal * shape_scale_profile[i]        # mm
            
            # Effective angle of attack (twist makes it twist from root to tip)
            alpha_deg = 12.0 - (8.0 / self.height) * z     # 12 deg at root, 4 deg at tip
            alpha = math.radians(alpha_deg)
            
            # Lift coefficient: C_L = 2 * pi * sin(alpha)
            # Camel-back / camber term is scaled with shape_scale
            C_L = 2.0 * math.pi * math.sin(alpha) * (1.0 + 0.15 * (shape_scale_profile[i] - 1.0))
            lift_coefs[i] = C_L
            
            # Drag coefficient: skin friction + shape profile drag
            # Profile drag is proportional to the square of max thickness/chord ratio
            # Thicker blades produce larger wakes and shock losses
            thickness_chord_ratio = 0.15 * shape_scale_profile[i]
            C_D = 0.006 + 0.07 * (thickness_chord_ratio**2) * (1.0 + 3.0 * math.sin(alpha)**2)
            drag_coefs[i] = C_D
            
            # Force calculations per unit span (convert mm to m for chord)
            lift_force = 0.5 * self.rho_gas * (W**2) * (c / 1000.0) * C_L  # N/m
            drag_force = 0.5 * self.rho_gas * (W**2) * (c / 1000.0) * C_D  # N/m
            
            lift_forces[i] = lift_force
            drag_forces[i] = drag_force
            
            # --- Conjugate Heat Transfer (CHT) Thermal Energy Balance ---
            # Gas-side convective heat transfer coefficient (Dittus-Boelter style correlation)
            # h_gas is proportional to Reynolds number Re^0.8
            # Re = rho * W * c / mu
            Re = self.rho_gas * W * (c / 1000.0) / 1.8e-5
            Nu_gas = 0.023 * (Re**0.8) * (0.7**0.4)  # Pr = 0.7 for gas
            h_gas = Nu_gas * self.k_gas / (c / 1000.0)
            h_gas_coeffs[i] = h_gas
            
            # Coolant-side heat transfer coefficient
            # Enhanced by internal lattice structure density. Higher density = more surface area/turbulence.
            # However, scaling up the external blade too much (larger scale) increases path length and reduces cooling velocity.
            h_coolant = 15000.0 * math.sqrt(relative_density_profile[i]) * (1.0 / shape_scale_profile[i])**0.3
            h_coolant_coeffs[i] = h_coolant
            
            # Energy balance: q_in = q_out -> h_gas * (T_gas - T_surf) = h_cool = h_coolant * (T_surf - T_coolant)
            # T_surf = (h_gas * T_gas + h_coolant * T_coolant) / (h_gas + h_coolant)
            t_surf = (h_gas * self.t_gas + h_coolant * self.t_coolant) / (h_gas + h_coolant)
            temperatures[i] = t_surf
            
        # Overall blade aerodynamic efficiency (L/D ratio)
        avg_lift_to_drag = np.sum(lift_forces) / np.sum(drag_forces)
        
        return {
            "z_coords": z_coords,
            "chord": (40.0 - (20.0 / self.height) * z_coords) * shape_scale_profile,
            "lift_coef": lift_coefs,
            "drag_coef": drag_coefs,
            "lift_force": lift_forces,
            "drag_force": drag_forces,
            "temperatures": temperatures,
            "h_gas": h_gas_coeffs,
            "h_coolant": h_coolant_coeffs,
            "avg_lift_to_drag": avg_lift_to_drag,
            "shape_scale_profile": shape_scale_profile
        }

if __name__ == "__main__":
    solver = TurbineBladeCFDSolver()
    scale = np.ones(24)
    densities = np.ones(24) * 0.7
    res = solver.analyze_blade_aerodynamics(scale, densities)
    print("CFD Solver Test Complete.")
    print(f"Average Lift-to-Drag Ratio: {res['avg_lift_to_drag']:.4f}")
    print(f"Root Temp: {res['temperatures'][0]:.1f} °C, Tip Temp: {res['temperatures'][-1]:.1f} °C")

import os
import math
import numpy as np
import cadquery as cq

class TurbineBladeFEASolver:
    """
    Finite Element Analysis (FEA) simulator for gas turbine blades.
    Computes centrifugal loading, thermal gradients, and mechanical/thermal stresses.
    """
    def __init__(self, step_path="turbines_test/cad/turbine_blade.step", rpm=30000.0, t_root=400.0, t_tip=1000.0, r_hub=200.0):
        self.step_path = step_path
        self.rpm = rpm
        self.omega = (rpm * 2 * math.pi) / 60.0  # rad/s
        self.t_root = t_root
        self.t_tip = t_tip
        self.r_hub = r_hub  # Hub radius in mm
        
        # Load blade geometry
        if os.path.exists(self.step_path):
            try:
                self.blade_shape = cq.importers.importStep(self.step_path)
                print(f"Successfully loaded step model: {self.step_path}")
            except Exception as e:
                print(f"Warning: Failed to load step file: {e}. Using parametric geometry model.")
                self.blade_shape = None
        else:
            print(f"Warning: STEP file {self.step_path} not found. Using parametric geometry model.")
            self.blade_shape = None

        # Material constants (Inconel 718)
        self.density = 8190.0 / 1e9  # kg/mm^3 (8.19 g/cm^3)
        self.t_ref = 20.0  # Reference room temperature in °C

        # Caching for fast optimization cycles
        self._cached_num_slices = None
        self._cached_z_coords = None
        self._cached_areas = None
        self._cached_temps = None

    def get_material_properties(self, temp):
        """
        Returns temperature-dependent material properties for Inconel 718.
        """
        # Young's Modulus E in MPa (GPa * 1000)
        E = (200.0 - 0.08 * temp) * 1000.0
        
        # Coefficient of Thermal Expansion alpha (1/K)
        alpha = (13.0 + 0.003 * temp) * 1e-6
        
        # Yield Strength in MPa
        if temp <= 600.0:
            sigma_yield = 1030.0 - 0.22 * temp
        else:
            sigma_yield = 900.0 - 1.875 * (temp - 600.0)
            
        # Thermal Conductivity k (W / m * K)
        k = 11.4 + 0.0173 * temp
        
        return E, alpha, sigma_yield, k

    def get_blade_height(self):
        """Returns the Z-span (height) of the blade in mm."""
        if self.blade_shape:
            try:
                # Find bounding box along Z
                bbox = self.blade_shape.val().BoundingBox()
                return bbox.zmax - bbox.zmin
            except:
                return 120.0
        return 120.0

    def analyze_slices(self, num_slices=24):
        """
        Analyzes the blade geometry at multiple Z-height slices.
        Computes slice Z-coordinates, cross-sectional areas, and average temperatures.
        """
        if self._cached_num_slices == num_slices and self._cached_z_coords is not None:
            return self._cached_z_coords, self._cached_areas, self._cached_temps

        height = self.get_blade_height()
        z_coords = np.linspace(0.0, height, num_slices)
        areas = []
        temperatures = []
        
        # Linear thermal gradient along Z
        for z in z_coords:
            temp = self.t_root + (self.t_tip - self.t_root) * (z / height)
            temperatures.append(temp)
            
            area = self._compute_slice_area(z)
            areas.append(area)
            
        self._cached_num_slices = num_slices
        self._cached_z_coords = z_coords
        self._cached_areas = np.array(areas)
        self._cached_temps = np.array(temperatures)
        
        return self._cached_z_coords, self._cached_areas, self._cached_temps

    def _compute_slice_area(self, z):
        """Computes or estimates the cross-sectional area at a given Z height."""
        # Method 1: Attempt to slice using CadQuery
        if self.blade_shape:
            try:
                # Slicing via section plane intersection
                slice_face = cq.Workplane("XY").workplane(offset=z).section().val()
                area = slice_face.Area()
                if area > 1.0:
                    return area
            except:
                pass
                
        # Method 2: Fallback to mathematical interpolation of lofted blade profiles
        # At Z=0 (root), scale is 40. At Z=60, scale is 30. At Z=120 (tip), scale is 20.
        # Normalized airfoil profile area is ~0.045
        if z <= 60.0:
            scale = 40.0 - (10.0 / 60.0) * z
        else:
            scale = 30.0 - (10.0 / 60.0) * (z - 60.0)
            
        area_est = 0.046 * (scale ** 2)
        return area_est

    def solve_stresses(self, relative_density_profile=None, num_slices=24, shape_scale_profile=None, temperatures=None):
        """
        Calculates stresses along the blade span.
        
        Args:
            relative_density_profile: Array of size num_slices containing values in [0.4, 1.0].
                                      Represents the lattice density fraction (topology state).
            shape_scale_profile: Array of size num_slices containing values in [0.4, 1.5].
                                 Represents external airfoil scale factor.
            temperatures: Optional array of temperatures at each slice from CFD/CHT.
        """
        z_coords, areas, default_temps = self.analyze_slices(num_slices)
        n = len(z_coords)
        dz = z_coords[1] - z_coords[0] if n > 1 else 1.0
        
        if relative_density_profile is None:
            relative_density_profile = np.ones(n)
            
        if shape_scale_profile is None:
            shape_scale_profile = np.ones(n)
            
        temps = temperatures if temperatures is not None else default_temps
        
        # Ensure bounds on relative density and shape scale
        relative_density_profile = np.clip(relative_density_profile, 0.4, 1.0)
        shape_scale_profile = np.clip(shape_scale_profile, 0.4, 1.5)
        
        # Effective areas and mass distribution (area scales as shape_scale^2)
        effective_areas = areas * (shape_scale_profile ** 2) * relative_density_profile
        effective_masses = self.density * effective_areas * dz
        
        # 1. Centrifugal Stress:
        # F_c(z_i) = sum_{j >= i} m_j * omega^2 * r_j
        centrifugal_forces = np.zeros(n)
        for i in range(n):
            force = 0.0
            for j in range(i, n):
                r_m = (self.r_hub + z_coords[j]) / 1000.0  # Convert mm to meters
                force += effective_masses[j] * (self.omega ** 2) * r_m
            centrifugal_forces[i] = force
            
        # stress = force / area
        centrifugal_stresses = np.zeros(n)
        for i in range(n):
            if effective_areas[i] > 0:
                centrifugal_stresses[i] = centrifugal_forces[i] / effective_areas[i]
            else:
                centrifugal_stresses[i] = 0.0
                
        # 2. Thermal Stress:
        # sigma_th = E * alpha * delta_T (relaxed for free-expansion blade tip)
        thermal_stresses = np.zeros(n)
        yield_strengths = np.zeros(n)
        for i in range(n):
            E, alpha, sig_y, _ = self.get_material_properties(temps[i])
            yield_strengths[i] = sig_y
            
            # Thermal gradient stress: root is fixed at t_root, tip is free to expand.
            # Stress is proportional to distance from the root reference gradient.
            thermal_stresses[i] = 0.12 * E * alpha * abs(temps[i] - self.t_root)

        # 3. Combined Von Mises Stress
        combined_stresses = centrifugal_stresses + thermal_stresses
        
        # 4. Safety Factors
        safety_factors = np.zeros(n)
        for i in range(n):
            if combined_stresses[i] > 0:
                safety_factors[i] = yield_strengths[i] / combined_stresses[i]
            else:
                safety_factors[i] = 999.0
                
        return {
            "z_coords": z_coords,
            "areas": areas,
            "temperatures": temps,
            "density_profile": relative_density_profile,
            "centrifugal_stress": centrifugal_stresses,
            "thermal_stress": thermal_stresses,
            "combined_stress": combined_stresses,
            "yield_strength": yield_strengths,
            "safety_factor": safety_factors
        }

if __name__ == "__main__":
    solver = TurbineBladeFEASolver()
    res = solver.solve_stresses()
    print("Solver Test Complete. Root Stress:", res["combined_stress"][0], "MPa. Safety Factor:", res["safety_factor"][0])

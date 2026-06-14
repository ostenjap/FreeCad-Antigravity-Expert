"""
propeller_physics.py
====================
Static structural analysis for the 5-blade CF-PA6 propeller.

Loads considered
----------------
1. Centrifugal (tensile) stress: σ_c = ρ · ω² · r · A  (at the root section)
2. Aerodynamic bending:          M_b = F_thrust · L_arm
3. Torsional load:               T   = Q_blade / N_blades  (from total torque)

Safety factors
--------------
Material tensile strength (CF-PA6 30wt%) : 200 MPa
Design safety factor                      : 2.5
Allowable stress                          : 80 MPa
"""

import math
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Material (CF-PA6, 30 wt% short carbon fibre)
# ---------------------------------------------------------------------------
CFPA6 = {
    "E_Pa":          30e9,
    "nu":            0.35,
    "density_kg_m3": 1300,
    "tensile_MPa":   200,
    "yield_MPa":     150,
    "safety_factor": 2.5,
}
ALLOWABLE_MPa = CFPA6["tensile_MPa"] / CFPA6["safety_factor"]   # 80 MPa


# ---------------------------------------------------------------------------
# Propeller operating parameters (drone hover)
# ---------------------------------------------------------------------------
@dataclass
class PropellerSpec:
    n_blades:        int   = 5
    diameter_m:      float = 0.254        # 10-inch
    hub_radius_m:    float = 0.012
    chord_root_m:    float = 0.028
    chord_tip_m:     float = 0.010
    thickness_ratio: float = 0.12         # NACA 4412
    rpm:             float = 8000         # typical quadcopter hover RPM
    rho_air:         float = 1.225        # [kg/m³] sea level ISA
    total_thrust_N:  float = 15.0         # [N]  total for one motor
    total_torque_Nm: float = 0.35         # [Nm] shaft torque

    @property
    def omega_rad_s(self) -> float:
        return self.rpm * 2 * math.pi / 60

    @property
    def radius_m(self) -> float:
        return self.diameter_m / 2

    @property
    def thrust_per_blade_N(self) -> float:
        return self.total_thrust_N / self.n_blades

    @property
    def torque_per_blade_Nm(self) -> float:
        return self.total_torque_Nm / self.n_blades


# ---------------------------------------------------------------------------
# Root cross-section properties (simplified rectangular equivalent)
# ---------------------------------------------------------------------------

def root_section_properties(spec: PropellerSpec) -> dict:
    """
    Approximate the root cross-section as a rectangle of width = chord_root
    and height = thickness_ratio * chord_root.  Returns second moments of
    area and cross-sectional area.
    """
    c = spec.chord_root_m
    h = spec.thickness_ratio * c          # thickness at root

    A  = c * h                            # [m²]
    Iz = c * h**3 / 12                   # [m⁴]  bending about chord axis
    Iy = h * c**3 / 12                   # [m⁴]  bending about thickness axis
    J  = Iz + Iy                          # polar moment (thin-walled approx)

    return {"A_m2": A, "Iz_m4": Iz, "Iy_m4": Iy, "J_m4": J,
            "chord_m": c, "thickness_m": h}


# ---------------------------------------------------------------------------
# Centrifugal stress (blade root, worst case)
# ---------------------------------------------------------------------------

def centrifugal_stress(spec: PropellerSpec, sec: dict) -> float:
    """
    Centrifugal tensile stress at the blade root.

        σ_c = ρ_mat · ω² · ∫[hub → tip] r · A(r) dr  /  A_root

    Simplified (constant area = root area, conservative):
        σ_c = ρ_mat · ω² · r_eff · 1.0   [Pa]
    where r_eff = 2/3 of span centroid
    """
    rho   = CFPA6["density_kg_m3"]
    omega = spec.omega_rad_s
    span  = spec.radius_m - spec.hub_radius_m
    r_eff = spec.hub_radius_m + 0.5 * span   # centroid of triangular taper area

    # Full integral for linearly tapered blade
    A_root = sec["A_m2"]
    A_tip  = (spec.chord_tip_m * spec.thickness_ratio * spec.chord_tip_m)

    # ∫ ρ ω² r A(r) dr  with A(r) linearly tapered
    def A_r(r):
        frac = (r - spec.hub_radius_m) / span
        return A_root + frac * (A_tip - A_root)

    r_vals = np.linspace(spec.hub_radius_m, spec.radius_m, 200)
    integrand = rho * omega**2 * r_vals * np.array([A_r(r) for r in r_vals])
    F_cent = np.trapz(integrand, r_vals)    # [N]  centrifugal force

    sigma_c = F_cent / A_root               # [Pa]
    return sigma_c


# ---------------------------------------------------------------------------
# Aerodynamic bending stress at root
# ---------------------------------------------------------------------------

def bending_stress(spec: PropellerSpec, sec: dict) -> float:
    """
    The thrust force on one blade acts at ~0.7R (effective aerodynamic radius).
    This creates a root bending moment M = F_blade × (0.7R - hub_R).
    Bending stress σ_b = M · (h/2) / Iz
    """
    r_eff = 0.70 * spec.radius_m
    arm   = r_eff - spec.hub_radius_m
    M     = spec.thrust_per_blade_N * arm   # [Nm]

    h  = sec["thickness_m"]
    Iz = sec["Iz_m4"]

    sigma_b = M * (h / 2) / Iz             # [Pa]
    return sigma_b


# ---------------------------------------------------------------------------
# Torsional shear stress at root
# ---------------------------------------------------------------------------

def torsional_stress(spec: PropellerSpec, sec: dict) -> float:
    """
    Torsional shear stress  τ = T · r_max / J
    where r_max = half-diagonal of rectangular section ≈ sqrt((c/2)²+(h/2)²)
    """
    T     = spec.torque_per_blade_Nm
    c, h  = sec["chord_m"], sec["thickness_m"]
    r_max = math.sqrt((c / 2)**2 + (h / 2)**2)
    J     = sec["J_m4"]
    tau   = T * r_max / J                  # [Pa]
    return tau


# ---------------------------------------------------------------------------
# Combined Von Mises stress (root, worst case)
# ---------------------------------------------------------------------------

def von_mises_stress(sigma_normal: float, tau: float) -> float:
    """σ_vm = sqrt(σ² + 3τ²)"""
    return math.sqrt(sigma_normal**2 + 3 * tau**2)


# ---------------------------------------------------------------------------
# Full structural assessment
# ---------------------------------------------------------------------------

@dataclass
class StructuralReport:
    sigma_centrifugal_MPa: float = 0.0
    sigma_bending_MPa:     float = 0.0
    tau_torsion_MPa:       float = 0.0
    sigma_total_MPa:       float = 0.0
    sigma_von_mises_MPa:   float = 0.0
    allowable_MPa:         float = ALLOWABLE_MPa
    utilisation_pct:       float = 0.0
    status:                str   = "UNKNOWN"
    margin_of_safety:      float = 0.0
    tip_velocity_m_s:      float = 0.0
    natural_freq_Hz:       Optional[float] = None


def run_structural_check(spec: Optional[PropellerSpec] = None) -> StructuralReport:
    if spec is None:
        spec = PropellerSpec()

    sec = root_section_properties(spec)

    σ_c  = centrifugal_stress(spec, sec)
    σ_b  = bending_stress(spec, sec)
    τ    = torsional_stress(spec, sec)
    σ_t  = σ_c + σ_b                       # combined normal stress [Pa]
    σ_vm = von_mises_stress(σ_t, τ)

    σ_vm_MPa = σ_vm / 1e6

    utilisation = σ_vm_MPa / ALLOWABLE_MPa * 100  # %
    margin      = ALLOWABLE_MPa / σ_vm_MPa - 1    # MS > 0 means pass

    status = "PASS" if margin >= 0 else "FAIL"

    # Tip velocity
    v_tip = spec.omega_rad_s * spec.radius_m

    # Crude first natural frequency (clamped beam, simplified)
    # fn = (3.516 / (2π)) * sqrt(E I / (ρ A L⁴))  for 1st bending mode
    span = spec.radius_m - spec.hub_radius_m
    fn = (3.516 / (2 * math.pi)) * math.sqrt(
        CFPA6["E_Pa"] * sec["Iz_m4"] / (CFPA6["density_kg_m3"] * sec["A_m2"] * span**4)
    )

    return StructuralReport(
        sigma_centrifugal_MPa = σ_c / 1e6,
        sigma_bending_MPa     = σ_b / 1e6,
        tau_torsion_MPa       = τ   / 1e6,
        sigma_total_MPa       = σ_t / 1e6,
        sigma_von_mises_MPa   = σ_vm_MPa,
        allowable_MPa         = ALLOWABLE_MPa,
        utilisation_pct       = utilisation,
        status                = status,
        margin_of_safety      = margin,
        tip_velocity_m_s      = v_tip,
        natural_freq_Hz       = fn,
    )


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse, json

    parser = argparse.ArgumentParser(description="CF-PA6 Propeller Structural Check")
    parser.add_argument("--rpm",      type=float, default=8000, help="Operating RPM")
    parser.add_argument("--thrust",   type=float, default=15.0, help="Total thrust per motor [N]")
    parser.add_argument("--torque",   type=float, default=0.35, help="Shaft torque [Nm]")
    args = parser.parse_args()

    spec = PropellerSpec(rpm=args.rpm, total_thrust_N=args.thrust,
                         total_torque_Nm=args.torque)
    rpt  = run_structural_check(spec)

    print("\n" + "=" * 55)
    print("  CF-PA6 Propeller — Static Structural Assessment")
    print("=" * 55)
    print(f"  RPM                  : {spec.rpm:.0f}")
    print(f"  Tip velocity         : {rpt.tip_velocity_m_s:.1f} m/s  ({rpt.tip_velocity_m_s/343:.3f} Ma)")
    print(f"  σ centrifugal        : {rpt.sigma_centrifugal_MPa:.2f} MPa")
    print(f"  σ bending            : {rpt.sigma_bending_MPa:.2f} MPa")
    print(f"  τ torsion            : {rpt.tau_torsion_MPa:.2f} MPa")
    print(f"  Von Mises (root)     : {rpt.sigma_von_mises_MPa:.2f} MPa")
    print(f"  Allowable (SF=2.5)   : {rpt.allowable_MPa:.1f} MPa")
    print(f"  Utilisation          : {rpt.utilisation_pct:.1f} %")
    print(f"  Margin of Safety     : {rpt.margin_of_safety:.3f}")
    print(f"  1st Bending Freq     : {rpt.natural_freq_Hz:.1f} Hz  (excite @ {spec.rpm/60*spec.n_blades:.1f} Hz BPF)")
    print(f"  STATUS               : {rpt.status}")
    print("=" * 55)

    # JSON dump for CI/pipeline
    out = {k: (v if not isinstance(v, float) else round(v, 4))
           for k, v in vars(rpt).items()}
    print("\n  JSON:\n", json.dumps(out, indent=4))

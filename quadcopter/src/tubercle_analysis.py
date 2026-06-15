"""
tubercle_analysis.py
====================
Acoustic & aerodynamic benefit model for humpback-whale tubercles
on the quadcopter propeller leading edge.

Physical basis
--------------
Tubercles on the leading edge of a lifting surface (flipper/blade) act as
passive flow control devices.  The sinusoidal peaks and troughs modify the
span-wise vorticity distribution, producing these measurable effects:

1. STALL DELAY (+10–15% AoA before stall) — Fish & Battle 1995, Miklosovic 2004
2. LIFT INCREASE (~5% in post-stall regime) — van Nierop 2008
3. DRAG REDUCTION (~7–32% at high AoA) — Johari et al. 2007
4. ACOUSTIC REDUCTION (~3–6 dB BPF tone, ~2–4 dB broadband)
   — Skillen et al. 2015; Chong et al. 2022

This module implements simplified analytical models for each benefit:

    a) Stall-angle shift:    ΔαS = f(A/λ)
    b) Lift coefficient mod: CL_tb = CL_clean × (1 + k_L × sin(2πr/λ))
    c) Drag coefficient mod: CD_tb = CD_clean × (1 - k_D × (A/λ))
    d) Acoustic tone level:  SPL_tb = SPL_clean - ΔdB(A/c, V_tip)
"""

import math
import numpy as np
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Tubercle geometry (must match generate_propeller.py)
# ---------------------------------------------------------------------------
A_tubercle   = 0.003          # [m]  amplitude (half peak-to-valley)
lambda_tb    = 0.040          # [m]  wavelength
AR_tubercle  = A_tubercle / lambda_tb   # amplitude-to-wavelength ratio ≈ 0.075


# ---------------------------------------------------------------------------
# Empirical coefficients (fit to published data: Johari 2007, Miklosovic 2004)
# ---------------------------------------------------------------------------
K_STALL_DELAY = 3.8     # deg/unit  Δα_stall per unit A/λ
K_LIFT        = 0.045   # fractional lift gain in post-stall (linear approx)
K_DRAG        = 0.22    # fractional drag reduction at moderate AoA
K_ACOUSTIC    = 6.0     # dB reduction per unit A/c  (Chong et al.)


# ---------------------------------------------------------------------------
# Propeller-specific inputs
# ---------------------------------------------------------------------------
@dataclass
class PropellerAero:
    rpm:          float = 8000
    diameter_m:   float = 0.254
    n_blades:     int   = 5
    chord_eff_m:  float = 0.018     # effective chord at 0.7R
    CL_clean:     float = 0.85      # design lift coeff (NACA 4412 at ~6° AoA)
    CD_clean:     float = 0.015     # design drag coeff
    rho_air:      float = 1.225     # [kg/m³]
    # Tubercle geometry — defaults preserve the historical module constants so
    # the existing CLI and prior results are unchanged.  The optimizer overrides
    # these per candidate design.
    tubercle_amp_m: float = A_tubercle    # [m] amplitude (half peak-to-valley)
    tubercle_wl_m:  float = lambda_tb     # [m] wavelength

    @property
    def omega(self) -> float:
        return self.rpm * 2 * math.pi / 60

    @property
    def v_tip(self) -> float:
        return self.omega * self.diameter_m / 2

    @property
    def v_eff(self) -> float:
        """Effective velocity at 0.7R station."""
        return self.omega * 0.70 * self.diameter_m / 2

    @property
    def AR_tb(self) -> float:
        """Amplitude-to-wavelength ratio for this design (0 if no tubercles)."""
        if self.tubercle_wl_m <= 0:
            return 0.0
        return self.tubercle_amp_m / self.tubercle_wl_m


# ---------------------------------------------------------------------------
# Analysis models
# ---------------------------------------------------------------------------

def stall_delay_deg(AR: float = AR_tubercle) -> float:
    """
    Stall angle improvement (degrees) due to tubercles.
    ΔαS ≈ K_STALL_DELAY × (A / λ)
    """
    return K_STALL_DELAY * AR


def lift_mod(aero: PropellerAero, in_post_stall: bool = False) -> dict:
    """
    CL modification.  Pre-stall: ~neutral (small gain).
    Post-stall: meaningful gain that sustains hover during gusts.
    """
    CL_tb = aero.CL_clean * (1 + K_LIFT * aero.AR_tb * (1.5 if in_post_stall else 0.2))
    delta  = CL_tb - aero.CL_clean
    return {"CL_clean": aero.CL_clean, "CL_tubercle": round(CL_tb, 4),
            "delta_CL": round(delta, 4), "gain_pct": round(delta / aero.CL_clean * 100, 2)}


def drag_mod(aero: PropellerAero) -> dict:
    """
    CD reduction at operating AoA due to span-wise vortex pinning.
    CD_tb = CD_clean × (1 - K_DRAG × (A/λ))
    """
    CD_tb  = aero.CD_clean * (1 - K_DRAG * aero.AR_tb)
    L_D_clean  = aero.CL_clean / aero.CD_clean
    L_D_tb     = aero.CL_clean / CD_tb        # CL unchanged pre-stall
    return {
        "CD_clean":     aero.CD_clean,
        "CD_tubercle":  round(CD_tb, 5),
        "delta_CD":     round(aero.CD_clean - CD_tb, 5),
        "reduction_pct":round(K_DRAG * aero.AR_tb * 100, 2),
        "LD_clean":     round(L_D_clean, 2),
        "LD_tubercle":  round(L_D_tb, 2),
    }


def acoustic_benefit(aero: PropellerAero) -> dict:
    """
    Acoustic noise reduction model.

    BPF (blade-passage frequency): f_BPF = (RPM/60) × N_blades

    Two mechanisms:
    1. Reduced loading noise (from smoother spanwise loading distribution)
       ΔSPL_loading ≈ K_ACOUSTIC × (A / c_eff)           [dB]
    2. Reduced vortex-shedding tone at trailing edge
       ΔSPL_TE ≈ 0.5 × ΔSPL_loading                      [dB, conservative]

    Reference: Chong, T.P. et al. 2022, Acta Acustica
    """
    A_over_c = aero.tubercle_amp_m / aero.chord_eff_m
    ΔSPL_loading = K_ACOUSTIC * A_over_c
    ΔSPL_TE      = 0.5 * ΔSPL_loading

    BPF_Hz = (aero.rpm / 60) * aero.n_blades

    return {
        "BPF_Hz":              round(BPF_Hz, 1),
        "A_over_c":            round(A_over_c, 4),
        "ΔSPL_loading_dB":     round(ΔSPL_loading, 2),
        "ΔSPL_trailing_edge_dB": round(ΔSPL_TE, 2),
        "total_noise_reduction_dB": round(ΔSPL_loading + ΔSPL_TE, 2),
        "note": "Estimate based on Chong et al. 2022 empirical correlation"
    }


def efficiency_gain(aero: PropellerAero) -> dict:
    """
    Estimated figure of merit (FM) improvement from tubercles.
    FM_tb / FM_clean ≈ (CL_tb^1.5 / CD_tb) / (CL_clean^1.5 / CD_clean)
    """
    dr   = drag_mod(aero)
    lr   = lift_mod(aero)
    CL_clean = aero.CL_clean
    CD_clean = aero.CD_clean
    CL_tb    = lr["CL_tubercle"]
    CD_tb    = dr["CD_tubercle"]

    FM_clean = CL_clean**1.5 / CD_clean
    FM_tb    = CL_tb**1.5    / CD_tb
    gain     = (FM_tb / FM_clean - 1) * 100

    return {
        "FM_clean":    round(FM_clean, 4),
        "FM_tubercle": round(FM_tb,    4),
        "FM_gain_pct": round(gain,     2),
    }


# ---------------------------------------------------------------------------
# Full report
# ---------------------------------------------------------------------------

def full_report(aero: PropellerAero | None = None) -> dict:
    if aero is None:
        aero = PropellerAero()

    return {
        "operating_point": {
            "rpm":        aero.rpm,
            "tip_speed_m_s":  round(aero.v_tip, 2),
            "mach_tip":       round(aero.v_tip / 343, 4),
        },
        "tubercle_geometry": {
            "amplitude_mm":    aero.tubercle_amp_m * 1000,
            "wavelength_mm":   aero.tubercle_wl_m  * 1000,
            "A_over_lambda":   round(aero.AR_tb, 4),
        },
        "stall_delay_deg":   round(stall_delay_deg(aero.AR_tb), 2),
        "lift":              lift_mod(aero, in_post_stall=False),
        "lift_post_stall":   lift_mod(aero, in_post_stall=True),
        "drag":              drag_mod(aero),
        "acoustic":          acoustic_benefit(aero),
        "efficiency":        efficiency_gain(aero),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json, argparse

    parser = argparse.ArgumentParser(description="Tubercle aeroacoustic analysis")
    parser.add_argument("--rpm",    type=float, default=8000)
    parser.add_argument("--n",      type=int,   default=5,    help="Number of blades")
    args = parser.parse_args()

    aero = PropellerAero(rpm=args.rpm, n_blades=args.n)
    rpt  = full_report(aero)

    print("\n" + "=" * 60)
    print("  Tubercle Aeroacoustic Benefit Summary")
    print("=" * 60)

    op = rpt["operating_point"]
    print(f"\n  Operating Point")
    print(f"    RPM          : {op['rpm']:.0f}")
    print(f"    Tip speed    : {op['tip_speed_m_s']:.1f} m/s  (Ma = {op['mach_tip']:.3f})")

    tg = rpt["tubercle_geometry"]
    print(f"\n  Tubercle Geometry")
    print(f"    Amplitude    : {tg['amplitude_mm']:.1f} mm")
    print(f"    Wavelength   : {tg['wavelength_mm']:.1f} mm")
    print(f"    A/λ ratio    : {tg['A_over_lambda']:.4f}")

    print(f"\n  Stall Delay   : +{rpt['stall_delay_deg']:.2f}° AoA")

    d = rpt["drag"]
    print(f"\n  Drag Reduction")
    print(f"    CD clean     : {d['CD_clean']:.5f}")
    print(f"    CD w/tubercle: {d['CD_tubercle']:.5f}  ({d['reduction_pct']:.1f}% reduction)")
    print(f"    L/D clean    : {d['LD_clean']:.1f}")
    print(f"    L/D tubercle : {d['LD_tubercle']:.1f}")

    ac = rpt["acoustic"]
    print(f"\n  Acoustic Benefit")
    print(f"    BPF          : {ac['BPF_Hz']:.0f} Hz")
    print(f"    Loading noise: -{ac['ΔSPL_loading_dB']:.2f} dB")
    print(f"    TE noise     : -{ac['ΔSPL_trailing_edge_dB']:.2f} dB")
    print(f"    Total ΔdB    : -{ac['total_noise_reduction_dB']:.2f} dB")

    eff = rpt["efficiency"]
    print(f"\n  Figure of Merit")
    print(f"    FM clean     : {eff['FM_clean']:.4f}")
    print(f"    FM tubercle  : {eff['FM_tubercle']:.4f}")
    print(f"    Gain         : +{eff['FM_gain_pct']:.2f}%")
    print("=" * 60)

    print("\n  Full JSON report:")
    print(json.dumps(rpt, indent=2))

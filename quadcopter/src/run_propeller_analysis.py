"""
run_propeller_analysis.py
=========================
Master runner: generates the STEP/STL geometry (if CadQuery is available)
and runs both structural + tubercle aeroacoustic analyses.

Usage
-----
    # Full run (generate geometry + analyse)
    python quadcopter/src/run_propeller_analysis.py

    # Analysis only (no CadQuery geometry generation)
    python quadcopter/src/run_propeller_analysis.py --no-cad

    # Custom RPM
    python quadcopter/src/run_propeller_analysis.py --rpm 10000 --thrust 20
"""

import argparse
import json
import sys
import pathlib
import datetime
import traceback

# ---------------------------------------------------------------------------
# Resolve project root so we can import siblings
# ---------------------------------------------------------------------------
ROOT = pathlib.Path(__file__).resolve().parents[2]   # CAD-Expert/
sys.path.insert(0, str(ROOT / "quadcopter" / "src"))

from propeller_physics  import PropellerSpec, run_structural_check
from tubercle_analysis  import PropellerAero, full_report as tubercle_report

OUT_CAD  = ROOT / "quadcopter" / "cad"
OUT_DATA = ROOT / "quadcopter" / "data"


# ---------------------------------------------------------------------------
def banner(title: str):
    w = 62
    print("\n" + "-" * w)
    print(f"  {title}")
    print("-" * w)


def run(rpm: float, thrust: float, torque: float, generate_cad: bool):

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    # ── STRUCTURAL CHECK ──────────────────────────────────────────────────
    banner("Structural Analysis  (CF-PA6 30wt%  |  5 blades  |  NACA 4412)")

    spec = PropellerSpec(rpm=rpm, total_thrust_N=thrust, total_torque_Nm=torque)
    srpt = run_structural_check(spec)

    print(f"  RPM                 : {spec.rpm:.0f}")
    print(f"  Tip velocity        : {srpt.tip_velocity_m_s:.1f} m/s  "
          f"(Ma = {srpt.tip_velocity_m_s/343:.4f})")
    print(f"  σ centrifugal       : {srpt.sigma_centrifugal_MPa:8.3f} MPa")
    print(f"  σ bending           : {srpt.sigma_bending_MPa:8.3f} MPa")
    print(f"  τ torsion           : {srpt.tau_torsion_MPa:8.3f} MPa")
    print(f"  Von Mises (root)    : {srpt.sigma_von_mises_MPa:8.3f} MPa")
    print(f"  Allowable  (SF=2.5) : {srpt.allowable_MPa:8.1f} MPa")
    print(f"  Utilisation         : {srpt.utilisation_pct:8.1f} %")
    print(f"  Margin of Safety    : {srpt.margin_of_safety:8.3f}")
    print(f"  1st Bending Mode    : {srpt.natural_freq_Hz:8.1f} Hz")
    bpf = rpm / 60 * spec.n_blades
    print(f"  Blade-Pass Freq     : {bpf:8.1f} Hz  "
          f"({'RESONANCE RISK ⚠' if abs(srpt.natural_freq_Hz - bpf) < 20 else 'OK — no resonance'})")
    print(f"\n  ► STATUS            : {srpt.status}")

    # ── AEROACOUSTIC / TUBERCLE CHECK ─────────────────────────────────────
    banner("Tubercle Aeroacoustic Analysis")

    aero = PropellerAero(rpm=rpm, n_blades=spec.n_blades)
    trpt = tubercle_report(aero)

    op = trpt["operating_point"]
    d  = trpt["drag"]
    ac = trpt["acoustic"]
    ef = trpt["efficiency"]

    print(f"  Tip speed           : {op['tip_speed_m_s']:.1f} m/s")
    print(f"  Stall delay         : +{trpt['stall_delay_deg']:.2f}°")
    print(f"  CD reduction        : {d['reduction_pct']:.1f}%  "
          f"({d['CD_clean']:.5f} → {d['CD_tubercle']:.5f})")
    print(f"  L/D improvement     : {d['LD_clean']:.1f} → {d['LD_tubercle']:.1f}")
    print(f"  BPF noise reduction : -{ac['ΔSPL_loading_dB']:.2f} dB  "
          f"(BPF = {ac['BPF_Hz']:.0f} Hz)")
    print(f"  TE vortex noise     : -{ac['ΔSPL_trailing_edge_dB']:.2f} dB")
    print(f"  Total ΔdB           : -{ac['total_noise_reduction_dB']:.2f} dB")
    print(f"  Figure of Merit Δ   : +{ef['FM_gain_pct']:.2f}%")

    # ── CAD GENERATION ───────────────────────────────────────────────────
    cad_paths = None
    if generate_cad:
        banner("CAD Geometry Generation  (CadQuery)")
        try:
            from generate_propeller import build_propeller, export_all, compute_mass_properties
            prop = build_propeller()
            mass = compute_mass_properties(prop)
            print(f"  Estimated volume    : {mass['volume_cm3']} cm³")
            print(f"  Estimated mass      : {mass['mass_g']} g")
            OUT_CAD.mkdir(parents=True, exist_ok=True)
            cad_paths = export_all(prop, OUT_CAD)
            print(f"  STEP                : {cad_paths['step']}")
            print(f"  STL                 : {cad_paths['stl']}")
        except ImportError as e:
            print(f"  ⚠  CadQuery not installed — skipping CAD export. ({e})")
        except Exception as e:
            print(f"  ✗  CAD generation failed: {e}")
            traceback.print_exc()

    # ── COMBINED JSON REPORT ─────────────────────────────────────────────
    banner("Saving Combined Report")

    def _round(v):
        return round(v, 4) if isinstance(v, float) else v

    combined = {
        "generated_at": datetime.datetime.now().isoformat(),
        "config": {
            "n_blades":       spec.n_blades,
            "diameter_mm":    spec.diameter_m * 1000,
            "rpm":            rpm,
            "thrust_N":       thrust,
            "torque_Nm":      torque,
        },
        "structural": {k: _round(v) for k, v in vars(srpt).items()},
        "aeroacoustic": trpt,
        "cad_files":  cad_paths or "not generated",
    }

    OUT_DATA.mkdir(parents=True, exist_ok=True)
    rpt_path = OUT_DATA / "propeller_analysis.json"
    with open(rpt_path, "w") as f:
        json.dump(combined, f, indent=2)
    print(f"  Report saved → {rpt_path}")

    banner("Complete")
    print(f"  Structural status  : {srpt.status}")
    print(f"  Acoustic benefit   : -{ac['total_noise_reduction_dB']:.1f} dB")
    print(f"  FM gain            : +{ef['FM_gain_pct']:.1f}%\n")

    return combined


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Propeller full analysis pipeline")
    parser.add_argument("--rpm",     type=float, default=8000)
    parser.add_argument("--thrust",  type=float, default=15.0, help="Total thrust [N]")
    parser.add_argument("--torque",  type=float, default=0.35, help="Shaft torque [Nm]")
    parser.add_argument("--no-cad",  action="store_true",      help="Skip CadQuery geometry")
    args = parser.parse_args()

    run(rpm=args.rpm,
        thrust=args.thrust,
        torque=args.torque,
        generate_cad=not args.no_cad)

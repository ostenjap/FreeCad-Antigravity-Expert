"""
cfd_verify.py
=============
High-fidelity verification stage of the hybrid optimization: take the top Pareto
designs from the autoresearch run and re-score them with OpenFOAM (the real
truth), then re-rank by CFD Figure of Merit.

For each design it:
  1. builds the CadQuery geometry (build_propeller(design)),
  2. writes a self-contained OpenFOAM case (setup_openfoam_case.main) with the
     MRF omega set from the design RPM,
  3. runs the case (run_cfd.sh) IF an OpenFOAM toolchain is detected,
  4. parses postProcessing/forces -> thrust (total_z) and torque (moment_z),
     and computes FM = T^1.5 / (sqrt(2*rho*A) * P).

OpenFOAM is gated: if no solver is found on PATH (or via WSL/Docker), the cases
are still prepared and clear run instructions are printed — nothing fails.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]      # quadcopter/
sys.path.insert(0, str(ROOT / "src"))

from optimization.design import Design                  # noqa: E402
from optimization.evaluate import OBJECTIVES            # noqa: E402

RHO_AIR = 1.225
CASES_ROOT = ROOT / "cfd" / "optim_cases"
PARETO_JSON = ROOT / "data" / "optimization" / "pareto_front.json"


# ---------------------------------------------------------------------------
# OpenFOAM toolchain detection (PATH, then WSL, then Docker)
# ---------------------------------------------------------------------------
def detect_openfoam() -> dict | None:
    if shutil.which("simpleFoam"):
        return {"kind": "native", "prefix": []}
    if shutil.which("wsl"):
        try:
            r = subprocess.run(["wsl", "bash", "-lc", "command -v simpleFoam"],
                               capture_output=True, text=True, timeout=20)
            if r.returncode == 0 and r.stdout.strip():
                return {"kind": "wsl", "prefix": ["wsl", "bash", "-lc"]}
        except Exception:
            pass
    # Docker image (openfoam/openfoam*-paraview*) — only report, do not auto-pull
    if shutil.which("docker"):
        return {"kind": "docker-available", "prefix": None}
    return None


# ---------------------------------------------------------------------------
# Case preparation + result parsing
# ---------------------------------------------------------------------------
def prepare_case(design: Design, case_dir: pathlib.Path) -> pathlib.Path:
    """Write a full OpenFOAM case (dicts + STL) for one design."""
    import setup_openfoam_case as sof
    sof.main(design=design, rpm=design.rpm, case_dir=case_dir)
    return case_dir


def _last_row_z(dat_path: pathlib.Path) -> float | None:
    """Return total_z (4th column) of the last data row of an OF forces file."""
    if not dat_path.exists():
        return None
    last = None
    for line in dat_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        last = line
    if not last:
        return None
    parts = last.replace("(", " ").replace(")", " ").split()
    try:
        # columns: time total_x total_y total_z ...
        return float(parts[3])
    except (IndexError, ValueError):
        return None


def parse_cfd_result(case_dir: pathlib.Path, design: Design) -> dict | None:
    forces = case_dir / "postProcessing" / "forces"
    if not forces.exists():
        return None
    # pick the latest time directory
    times = sorted((p for p in forces.iterdir() if p.is_dir()),
                   key=lambda p: float(p.name) if p.name.replace('.', '', 1).isdigit() else -1)
    if not times:
        return None
    tdir = times[-1]
    thrust = _last_row_z(tdir / "force.dat")
    torque = _last_row_z(tdir / "moment.dat")
    if thrust is None or torque is None:
        return None
    omega = design.rpm * 2 * math.pi / 60
    power = abs(torque) * omega
    area = math.pi * design.prop_radius_m ** 2
    fm = (abs(thrust) ** 1.5 / (math.sqrt(2 * RHO_AIR * area) * power)
          if power > 0 else 0.0)
    return {"thrust_N": thrust, "torque_Nm": torque,
            "power_W": power, "cfd_FM": round(min(fm, 0.999), 4)}


def run_case(case_dir: pathlib.Path, foam: dict) -> bool:
    """Run run_cfd.sh for a prepared case.  Returns True on success."""
    script = "./run_cfd.sh"
    try:
        if foam["kind"] == "native":
            r = subprocess.run(["bash", script], cwd=case_dir, timeout=7200)
        elif foam["kind"] == "wsl":
            r = subprocess.run(["wsl", "bash", "-lc", f"cd '{case_dir.as_posix()}' && bash run_cfd.sh"],
                               timeout=7200)
        else:
            return False
        return r.returncode == 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def load_top_designs(pareto_json: pathlib.Path, k: int,
                     objective: str = "figure_of_merit") -> list[Design]:
    data = json.loads(pareto_json.read_text())
    front = data["pareto_front"]
    rev = OBJECTIVES.get(objective, "max") == "max"
    front.sort(key=lambda r: r["objectives"][objective], reverse=rev)
    designs = []
    for r in front[:k]:
        d = {kk: vv for kk, vv in r["design"].items()
             if kk in Design.__dataclass_fields__}
        designs.append(Design(**d))
    return designs


def main():
    ap = argparse.ArgumentParser(description="CFD-verify the top Pareto designs")
    ap.add_argument("--pareto", default=str(PARETO_JSON))
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--objective", default="figure_of_merit")
    ap.add_argument("--run", action="store_true",
                    help="actually run OpenFOAM if a toolchain is detected")
    args = ap.parse_args()

    pareto = pathlib.Path(args.pareto)
    if not pareto.exists():
        print(f"No Pareto file at {pareto}. Run the autoresearch loop first.")
        return

    designs = load_top_designs(pareto, args.top, args.objective)
    foam = detect_openfoam()

    print("=" * 64)
    print(f"  CFD verification of top {len(designs)} designs by {args.objective}")
    print(f"  OpenFOAM: {foam if foam else 'NOT FOUND (cases will be prepared only)'}")
    print("=" * 64)

    CASES_ROOT.mkdir(parents=True, exist_ok=True)
    results = []
    for i, d in enumerate(designs):
        case_dir = CASES_ROOT / f"design_{i:02d}"
        print(f"\n[{i}] B={d.n_blades} cr={d.chord_root_m:.3f} ct={d.chord_tip_m:.3f} "
              f"tw={d.twist_root_deg:.0f}/{d.twist_tip_deg:.0f} "
              f"amp={d.tubercle_amp_m:.4f} wl={d.tubercle_wl_m:.3f}")
        try:
            prepare_case(d, case_dir)
        except Exception as e:
            print(f"    case prep failed (CadQuery?): {e}")
            continue

        rec = {"index": i, "design": d.to_dict(), "case_dir": str(case_dir)}
        if args.run and foam and foam["kind"] in ("native", "wsl"):
            print("    running OpenFOAM (this can take many minutes)...")
            if run_case(case_dir, foam):
                cfd = parse_cfd_result(case_dir, d)
                if cfd:
                    rec.update(cfd)
                    print(f"    CFD: thrust={cfd['thrust_N']:.2f}N "
                          f"power={cfd['power_W']:.1f}W  FM={cfd['cfd_FM']}")
        results.append(rec)

    out = CASES_ROOT / "cfd_verification.json"
    out.write_text(json.dumps(results, indent=2))

    # Re-rank if we have CFD FM
    scored = [r for r in results if "cfd_FM" in r]
    if scored:
        scored.sort(key=lambda r: r["cfd_FM"], reverse=True)
        print("\n  CFD-verified ranking (by FM):")
        for r in scored:
            print(f"   #{r['index']}  CFD FM={r['cfd_FM']}  thrust={r['thrust_N']:.2f}N")
    else:
        print("\n  Cases prepared but not run. To run under WSL/Docker, e.g.:")
        print(f"    cd {CASES_ROOT / 'design_00'}")
        print("    bash run_cfd.sh        # needs OpenFOAM (simpleFoam, snappyHexMesh, ...)")
        print("  Then re-run this script with --run to parse forces and re-rank.")

    print(f"\n  Saved: {out}")


if __name__ == "__main__":
    main()

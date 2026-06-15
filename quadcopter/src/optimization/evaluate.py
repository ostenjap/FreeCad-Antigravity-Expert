"""
evaluate.py  —  GROUND TRUTH
============================
Scores a Design against the fixed physics models.  This is the ONLY place a
fitness number is produced; the LLM swarm never computes one that counts.

evaluate(design) returns a flat dict with:
  objectives   : the 3 Pareto objectives (see OBJECTIVES for max/min direction)
  metrics      : supporting raw numbers (thrust, power, stresses, ...)
  constraints  : named booleans
  feasible     : True iff every constraint passes
  design       : the design as a dict (for archiving)

Objectives
----------
  figure_of_merit      maximize  (hover efficiency, BEMT-lite)
  noise_reduction_dB   maximize  (tubercle acoustic benefit -> quieter)
  blade_mass_g         minimize  (lighter is better)
"""

from __future__ import annotations

import math

from . import _SRC  # noqa: F401
from .design import Design
from . import mass as _mass
from .performance import hover_performance
from propeller_physics import run_structural_check
from tubercle_analysis import full_report as tubercle_report

# objective name -> "max" | "min"
OBJECTIVES = {
    "figure_of_merit":    "max",
    "noise_reduction_dB": "max",
    "blade_mass_g":       "min",
}

TIP_MACH_LIMIT = 0.6
RESONANCE_GUARD_HZ = 15.0


def evaluate(design: Design) -> dict:
    design = design.clamped()

    # 1. Hover performance (geometry-dependent thrust / power / FM)
    perf = hover_performance(design)

    # 2. Structural check, fed with the BEMT thrust/torque so bending reflects
    #    the actual aerodynamic load of THIS geometry.
    spec = design.as_propeller_spec(thrust_N=max(perf.thrust_N, 1e-6),
                                    torque_Nm=max(perf.torque_Nm, 1e-9))
    srpt = run_structural_check(spec)

    # 3. Tubercle acoustic benefit (reused, now design-aware)
    trpt = tubercle_report(design.as_propeller_aero())
    noise_reduction = trpt["acoustic"]["total_noise_reduction_dB"]

    # 4. Mass
    blade_mass = _mass.blade_mass_g(design)
    total_mass = _mass.total_mass_g(design)

    # ---- constraints ----
    bpf = design.rpm / 60.0 * design.n_blades
    fn = srpt.natural_freq_Hz or 0.0
    constraints = {
        "performance_ok":   bool(perf.ok),
        "structural_pass":  srpt.margin_of_safety >= 0.0,
        "tip_mach_ok":      perf.tip_mach < TIP_MACH_LIMIT,
        "no_resonance":     abs(fn - bpf) > RESONANCE_GUARD_HZ,
        "produces_thrust":  perf.thrust_N > 0.0,
    }
    feasible = all(constraints.values())

    objectives = {
        "figure_of_merit":    round(perf.figure_of_merit, 5),
        "noise_reduction_dB": round(noise_reduction, 4),
        "blade_mass_g":       round(blade_mass, 4),
    }

    return {
        "objectives": objectives,
        "metrics": {
            "thrust_N":          round(perf.thrust_N, 4),
            "power_W":           round(perf.power_W, 3),
            "torque_Nm":         round(perf.torque_Nm, 5),
            "tip_mach":          round(perf.tip_mach, 4),
            "von_mises_MPa":     round(srpt.sigma_von_mises_MPa, 4),
            "margin_of_safety":  round(srpt.margin_of_safety, 4),
            "natural_freq_Hz":   round(fn, 2),
            "bpf_Hz":            round(bpf, 2),
            "total_mass_g":      round(total_mass, 3),
            "thrust_to_weight":  round(perf.thrust_N / (total_mass / 1000.0 * 9.81), 3)
                                 if total_mass > 0 else 0.0,
        },
        "constraints": constraints,
        "feasible": feasible,
        "design": design.to_dict(),
    }


def objective_values(result: dict) -> dict:
    """Pull just the objective dict out of an evaluate() result."""
    return result["objectives"]


# ---------------------------------------------------------------------------
# CLI: score the baseline and print it (verification entry-point)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Score a propeller Design (ground truth)")
    ap.add_argument("--json", help="path to a Design JSON to score (defaults to baseline)")
    args = ap.parse_args()

    if args.json:
        with open(args.json) as f:
            d = Design(**{k: v for k, v in json.load(f).items()
                          if k in Design.__dataclass_fields__})
    else:
        d = Design()  # baseline

    res = evaluate(d)
    print(json.dumps(res, indent=2))

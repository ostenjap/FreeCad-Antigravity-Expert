"""
performance.py
==============
Blade-Element Momentum Theory (BEMT) hover performance model, closed-form.

Why this exists
---------------
The published ``tubercle_analysis`` Figure-of-Merit depends only on the tubercle
A/lambda ratio (it modifies fixed CL/CD constants).  That makes chord, twist and
blade-count invisible and collapses the multi-objective Pareto front.  This
module adds a self-contained, geometry-dependent hover estimate so thrust, power
and FM respond to *every* design variable — producing genuine efficiency-vs-mass
-vs-noise trade-offs for the optimizer.

Method
------
Closed-form combined BEMT inflow for hover (Leishman, "Principles of Helicopter
Aerodynamics", eq. 3.131):

    lambda(r) = (sigma*Cla/16) * ( sqrt(1 + 32*theta'*r_bar / (sigma*Cla)) - 1 )

with local solidity sigma = B*c/(pi*R), pitch theta' measured from the zero-lift
line, and r_bar = r/R.  Induced power is included so FM is always physical (<1).
It is still an analytical surrogate (no wake contraction, lumped polar); the
OpenFOAM stage is the real truth.  This only needs to be smooth, monotone and
microsecond-cheap.

Tubercle coupling
-----------------
* Stall delay -> raises CLmax, letting loaded stations keep working.
* Drag        -> multiplied by a factor with an *interior optimum* in A/lambda
                 (Johari 2007): mild benefit at moderate amplitude, penalty when
                 too large.  This stops the optimizer trivially maxing amplitude.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

CL_ALPHA   = 5.9                    # lift-curve slope [1/rad]
ALPHA_0    = math.radians(-4.0)     # zero-lift angle (cambered NACA 4412)
CLMAX0     = 1.35                   # clean max lift coefficient
CD0        = 0.011                  # profile drag at zero lift
CD_K       = 0.020                  # quadratic drag factor (Cd = CD0 + k*CL^2)

TB_DRAG_A  = 0.22                   # tubercle drag-factor linear term
TB_DRAG_B  = 1.22                   # tubercle drag-factor quadratic term (interior optimum ~A/l=0.09)
TB_STALL_DELAY_PER_AR = 3.8         # deg extra stall margin per unit A/lambda

N_STATIONS  = 60
SOUND_SPEED = 343.0


@dataclass
class HoverPerformance:
    thrust_N:   float
    torque_Nm:  float
    power_W:    float
    figure_of_merit: float
    tip_mach:   float
    ok:         bool


def _drag_factor(ar: float) -> float:
    return 1.0 - TB_DRAG_A * ar + TB_DRAG_B * ar * ar


def hover_performance(design) -> HoverPerformance:
    B     = int(design.n_blades)
    R     = design.prop_radius_m
    hub   = design.hub_radius_m
    rho   = design.rho_air
    omega = design.rpm * 2.0 * math.pi / 60.0
    ar_tb = (design.tubercle_amp_m / design.tubercle_wl_m
             if design.tubercle_wl_m > 0 else 0.0)
    Vtip  = omega * R

    if B < 1 or R <= hub or omega <= 0:
        return HoverPerformance(0, 0, 0, 0.0, 0.0, ok=False)

    r_bar = np.linspace(hub / R, 1.0, N_STATIONS)
    chord = (design.chord_root_m
             + (r_bar - hub / R) / (1.0 - hub / R)
             * (design.chord_tip_m - design.chord_root_m))

    twist = np.radians(design.twist_root_deg
                       + (r_bar - hub / R) / (1.0 - hub / R)
                       * (design.twist_tip_deg - design.twist_root_deg))
    theta_p = twist - ALPHA_0                     # pitch from zero-lift line

    sigma = B * chord / (math.pi * R)             # local solidity
    sigma = np.maximum(sigma, 1e-6)

    clmax = CLMAX0 + CL_ALPHA * math.radians(TB_STALL_DELAY_PER_AR * ar_tb)
    drag_factor = _drag_factor(ar_tb)

    # Closed-form hover inflow (tip loss F = 1)
    disc = 1.0 + 32.0 * theta_p * r_bar / (sigma * CL_ALPHA)
    disc = np.maximum(disc, 0.0)
    lam = (sigma * CL_ALPHA / 16.0) * (np.sqrt(disc) - 1.0)
    lam = np.maximum(lam, 1e-6)

    phi = lam / np.maximum(r_bar, 1e-6)
    cl  = np.clip(CL_ALPHA * (theta_p - phi), -clmax, clmax)
    cd  = (CD0 + CD_K * cl * cl) * drag_factor

    dCT = 0.5 * sigma * cl * r_bar ** 2
    dCP = 0.5 * sigma * (phi * cl + cd) * r_bar ** 3

    CT = float(np.trapz(dCT, r_bar))
    CP = float(np.trapz(dCP, r_bar))

    if not (math.isfinite(CT) and math.isfinite(CP)) or CT <= 0 or CP <= 0:
        return HoverPerformance(0, 0, 0, 0.0, Vtip / SOUND_SPEED, ok=False)

    area   = math.pi * R * R
    thrust = CT * rho * area * Vtip ** 2
    power  = CP * rho * area * Vtip ** 3
    torque = power / omega
    fm     = (CT ** 1.5) / (math.sqrt(2.0) * CP)
    fm     = max(0.0, min(fm, 0.999))

    return HoverPerformance(
        thrust_N=thrust,
        torque_Nm=torque,
        power_W=power,
        figure_of_merit=fm,
        tip_mach=Vtip / SOUND_SPEED,
        ok=True,
    )

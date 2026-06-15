"""
mass.py
=======
Analytical mass estimate for a propeller Design — no CadQuery, so it costs
microseconds and can run inside the evaluation hot loop.  CadQuery is reserved
for exporting the final Pareto winners.

Method
------
Blade volume = integral over span of the airfoil cross-section area.
For a NACA 4-digit section of thickness ratio tau and chord c, the enclosed
area is well approximated by  A_section ~= 0.685 * tau * c^2.
Hub volume = solid cylinder minus the shaft bore.
"""

from __future__ import annotations

import math

import numpy as np

DENSITY_KG_M3 = 1300.0   # CF-PA6 30 wt%
SECTION_AREA_FACTOR = 0.685   # NACA 4-digit enclosed-area constant


def blade_volume_m3(design) -> float:
    R   = design.prop_radius_m
    hub = design.hub_radius_m
    r   = np.linspace(hub, R, 60)
    frac = (r - hub) / (R - hub)
    chord = design.chord_root_m + frac * (design.chord_tip_m - design.chord_root_m)
    area  = SECTION_AREA_FACTOR * design.thickness_ratio * chord * chord
    return float(np.trapz(area, r)) * int(design.n_blades)


def hub_volume_m3(design) -> float:
    r_hub = design.hub_radius_m
    h     = design.hub_height_m
    r_bore = design.shaft_hole_r_m
    return math.pi * (r_hub * r_hub - r_bore * r_bore) * h


def total_mass_g(design) -> float:
    vol = blade_volume_m3(design) + hub_volume_m3(design)
    return vol * DENSITY_KG_M3 * 1000.0


def blade_mass_g(design) -> float:
    """Mass of the blades alone (the part that scales with the search vars)."""
    return blade_volume_m3(design) * DENSITY_KG_M3 * 1000.0

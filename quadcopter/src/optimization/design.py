"""
design.py
=========
The design vector that the autoresearch loop searches over, its bounds, and
adapters onto the existing analysis dataclasses.

A ``Design`` carries everything needed to (a) build the CadQuery geometry,
(b) run the structural check, and (c) run the tubercle aero/acoustic model.
Field names deliberately match ``generate_propeller.BladeParams`` so a Design
can be passed straight into ``build_propeller(design)``.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import List, Tuple

from . import _SRC  # noqa: F401  (ensures src/ is on sys.path)
from propeller_physics import PropellerSpec
from tubercle_analysis import PropellerAero


# ---------------------------------------------------------------------------
# Search variables and their bounds  (lo, hi, is_integer)
# ---------------------------------------------------------------------------
# These 7 are what the optimizer/LLM swarm is allowed to vary.  Everything else
# in Design is fixed context (motor operating point, hub geometry, material).
BOUNDS: dict[str, Tuple[float, float, bool]] = {
    "chord_root_m":   (0.020, 0.034, False),
    "chord_tip_m":    (0.006, 0.014, False),
    "twist_root_deg": (25.0,  45.0,  False),
    "twist_tip_deg":  (6.0,   20.0,  False),
    "tubercle_amp_m": (0.0,   0.003, False),   # max ~9% root chord (realistic)
    "tubercle_wl_m":  (0.030, 0.070, False),   # min 30 mm → max ~3.8 bumps across span
    "n_blades":       (2,     6,     True),
}

SEARCH_VARS: List[str] = list(BOUNDS.keys())


@dataclass
class Design:
    # ---- search variables (optimized) ----
    chord_root_m:   float = 0.028
    chord_tip_m:    float = 0.010
    twist_root_deg: float = 35.0
    twist_tip_deg:  float = 12.0
    tubercle_amp_m: float = 0.003
    tubercle_wl_m:  float = 0.040
    n_blades:       int   = 5

    # ---- fixed geometry (not searched) ----
    prop_radius_m:  float = 0.127     # 10-inch / 2
    hub_radius_m:   float = 0.012
    hub_height_m:   float = 0.022
    shaft_hole_r_m: float = 0.003
    thickness_ratio: float = 0.12     # NACA 4412

    # ---- fixed operating point / environment ----
    rpm:             float = 8000.0
    total_thrust_N:  float = 15.0     # nominal; evaluate() replaces with BEMT thrust
    total_torque_Nm: float = 0.35     # nominal; evaluate() replaces with BEMT torque
    rho_air:         float = 1.225

    @property
    def diameter_m(self) -> float:
        return 2.0 * self.prop_radius_m

    @property
    def chord_eff_m(self) -> float:
        """Effective chord at the ~0.7R aeroacoustic station.

        The interpolation factor (0.555) is calibrated so the baseline design
        (28→10 mm taper) yields 0.018 m — matching the historical default in
        tubercle_analysis — while still scaling with the design's taper.
        """
        return self.chord_root_m + 0.555 * (self.chord_tip_m - self.chord_root_m)

    # ------------------------------------------------------------------
    # Vector <-> Design (for numeric optimizers)
    # ------------------------------------------------------------------
    def to_vector(self) -> List[float]:
        return [float(getattr(self, v)) for v in SEARCH_VARS]

    @classmethod
    def from_vector(cls, vec, **fixed) -> "Design":
        kw = dict(zip(SEARCH_VARS, vec))
        if "n_blades" in kw:
            kw["n_blades"] = int(round(kw["n_blades"]))
        kw.update(fixed)
        return cls(**kw)

    def clamped(self) -> "Design":
        """Return a copy with every search variable forced inside BOUNDS and
        the twist monotonicity constraint (root > tip) repaired."""
        kw = {}
        for v, (lo, hi, is_int) in BOUNDS.items():
            x = getattr(self, v)
            x = max(lo, min(hi, x))
            if is_int:
                x = int(round(x))
            kw[v] = x
        d = replace(self, **kw)
        # Keep twist monotonic root>=tip (physical for a hover prop)
        if d.twist_tip_deg > d.twist_root_deg:
            d = replace(d, twist_tip_deg=d.twist_root_deg)
        if d.chord_tip_m > d.chord_root_m:
            d = replace(d, chord_tip_m=d.chord_root_m)
        return d

    # ------------------------------------------------------------------
    # Adapters onto the existing analysis dataclasses
    # ------------------------------------------------------------------
    def as_propeller_spec(self, thrust_N: float = None,
                          torque_Nm: float = None) -> PropellerSpec:
        return PropellerSpec(
            n_blades=int(self.n_blades),
            diameter_m=self.diameter_m,
            hub_radius_m=self.hub_radius_m,
            chord_root_m=self.chord_root_m,
            chord_tip_m=self.chord_tip_m,
            thickness_ratio=self.thickness_ratio,
            rpm=self.rpm,
            rho_air=self.rho_air,
            total_thrust_N=self.total_thrust_N if thrust_N is None else thrust_N,
            total_torque_Nm=self.total_torque_Nm if torque_Nm is None else torque_Nm,
        )

    def as_propeller_aero(self) -> PropellerAero:
        return PropellerAero(
            rpm=self.rpm,
            diameter_m=self.diameter_m,
            n_blades=int(self.n_blades),
            chord_eff_m=self.chord_eff_m,
            rho_air=self.rho_air,
            tubercle_amp_m=self.tubercle_amp_m,
            tubercle_wl_m=self.tubercle_wl_m,
        )

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


def random_design(rng) -> Design:
    """Sample a uniformly-random feasible-by-bounds design (used to seed)."""
    vec = []
    for v, (lo, hi, is_int) in BOUNDS.items():
        x = rng.uniform(lo, hi)
        vec.append(int(round(x)) if is_int else x)
    return Design.from_vector(vec).clamped()

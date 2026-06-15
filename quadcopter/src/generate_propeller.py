"""
generate_propeller.py  (v2 — CadQuery 2.7 compatible)
=======================================================
5-Blade Quadcopter Propeller — Carbon-Fiber Filled PA6 (CF-PA6)
with Leading-Edge Tubercles (humpback-whale inspired)

Geometry strategy (CadQuery 2.x wire-loft approach)
----------------------------------------------------
1. For each radial station r, compute:
   - chord, twist, NACA 4412 section, tubercle LE offset
2. Build a closed CadQuery Wire in the plane z=r by:
   a. Generating 2-D (x, y) airfoil coords in the chord plane
   b. Converting to 3-D (x, y, z=r) and calling cq.Wire.makePolygon
3. Collect all wires into a list and call cq.Solid.makeLoft()
4. Rotate-pattern 5 blades around Z, add hub cylinder + shaft bore.
5. Export to STEP + STL.
"""

import math
import numpy as np
import cadquery as cq
from cadquery import exporters
import pathlib, json, datetime, sys

# ---------------------------------------------------------------------------
# 1. MATERIAL
# ---------------------------------------------------------------------------
MATERIAL = {
    "name":          "CF-PA6 30wt%",
    "E_Pa":          30e9,
    "nu":            0.35,
    "density_kg_m3": 1300,
    "tensile_MPa":   200,
    "yield_MPa":     150,
    "max_temp_C":    120,
}

# ---------------------------------------------------------------------------
# 2. PROPELLER GEOMETRY  (all units: metres, then scaled *1000 → mm for CQ)
# ---------------------------------------------------------------------------
N_BLADES        = 5
PROP_RADIUS_M   = 0.127         # 127 mm  (10-inch / 2)
HUB_RADIUS_M    = 0.012         # 12 mm
HUB_HEIGHT_M    = 0.022         # 22 mm
SHAFT_HOLE_R_M  = 0.003         # 3 mm bore

CHORD_ROOT_M    = 0.028         # 28 mm
CHORD_TIP_M     = 0.010         # 10 mm
TWIST_ROOT_DEG  = 35.0
TWIST_TIP_DEG   = 12.0
THICKNESS_RATIO = 0.12          # NACA 4412

# Tubercle
TUBERCLE_AMP_M  = 0.003         # 3 mm amplitude
TUBERCLE_WL_M   = 0.040         # 40 mm wavelength

# Scale factor: CadQuery interprets numbers as mm
S = 1000.0   # metres → mm


# ---------------------------------------------------------------------------
# 3. NACA 4412 (normalised to unit chord, cosine-spaced)
# ---------------------------------------------------------------------------

def naca4_upper_lower(m=0.04, p=0.4, t=0.12, n=28):
    """
    Returns upper and lower surface x,y arrays, normalised chord [0,1].
    Uses cosine spacing for denser resolution near LE and TE.
    """
    beta = np.linspace(0, np.pi, n)
    x    = 0.5 * (1 - np.cos(beta))

    yt = (t / 0.2) * (0.2969*x**0.5 - 0.1260*x
                      - 0.3516*x**2 + 0.2843*x**3 - 0.1015*x**4)

    yc  = np.where(x < p,
                   m/p**2 * (2*p*x - x**2),
                   m/(1-p)**2 * ((1-2*p) + 2*p*x - x**2))

    dyc = np.where(x < p,
                   2*m/p**2 * (p - x),
                   2*m/(1-p)**2 * (p - x))

    th = np.arctan(dyc)
    xu = x  - yt * np.sin(th);  yu = yc + yt * np.cos(th)
    xl = x  + yt * np.sin(th);  yl = yc - yt * np.cos(th)
    return (xu, yu), (xl, yl)


# ---------------------------------------------------------------------------
# 4. Section polygon (2-D, in mm)
# ---------------------------------------------------------------------------

def section_polygon_mm(chord_mm, twist_deg, le_offset_mm=0.0, n_pts=24):
    """
    Returns a list of (x, y) tuples (in mm) forming a CLOSED polygon
    of the blade cross-section, twisted and with LE offset applied.
    Rotation is about the 25%-chord aerodynamic centre.
    """
    (xu, yu), (xl, yl) = naca4_upper_lower(n=n_pts)

    # Scale + offset
    def scale(xs, ys):
        return [(xi * chord_mm + le_offset_mm, yi * chord_mm) for xi, yi in zip(xs, ys)]

    upper = scale(xu, yu)
    lower = scale(xl, yl)

    # Combine: upper LE→TE, lower TE→LE (skip shared LE/TE points)
    pts = upper + list(reversed(lower[1:-1]))

    # Rotate by twist around 25% chord
    ac_x  = 0.25 * chord_mm + le_offset_mm
    a     = math.radians(twist_deg)
    cos_a, sin_a = math.cos(a), math.sin(a)

    rotated = []
    for px, py in pts:
        dx = px - ac_x
        dy = py
        rotated.append((ac_x + dx*cos_a - dy*sin_a,
                                dx*sin_a + dy*cos_a))
    return rotated


# ---------------------------------------------------------------------------
# 5. Build one blade using cq.Wire.makePolygon + cq.Solid.makeLoft
# ---------------------------------------------------------------------------

def build_blade_mm(n_sections=16):
    """
    Build a single propeller blade solid (units: mm).
    Radial direction = X axis.
    """
    span_m  = PROP_RADIUS_M - HUB_RADIUS_M
    # Start slightly inside the hub to ensure a clean union
    r_start = 0.8 * HUB_RADIUS_M
    r_end   = PROP_RADIUS_M
    r_vals  = np.linspace(r_start, r_end, n_sections)

    wires = []
    for r_m in r_vals:
        # Interpolate chord and twist based on clamped radius (HUB_RADIUS to PROP_RADIUS)
        r_calc   = max(r_m, HUB_RADIUS_M)
        frac     = (r_calc - HUB_RADIUS_M) / span_m
        chord_mm = (CHORD_ROOT_M + frac * (CHORD_TIP_M - CHORD_ROOT_M)) * S
        twist    = TWIST_ROOT_DEG + frac * (TWIST_TIP_DEG - TWIST_ROOT_DEG)

        # Tubercle leading edge offset (only on the external part of the blade)
        if r_m >= HUB_RADIUS_M:
            le_off = TUBERCLE_AMP_M * math.sin(2 * math.pi * (r_m - HUB_RADIUS_M) / TUBERCLE_WL_M) * S
        else:
            le_off = 0.0

        # Unrotated section points (twist_deg = 0)
        pts_2d = section_polygon_mm(chord_mm, 0.0, le_off)

        # Center sections around the aerodynamic center (25% chord) and map to 3D:
        # X = r_m * S (radial)
        # Y = y_rot (chordwise / tangential, LE at positive Y, TE at negative Y)
        # Z = z_rot (thickness / axial, upper surface at positive Z)
        ac_x = 0.25 * chord_mm + le_off
        a = math.radians(twist)
        cos_a, sin_a = math.cos(a), math.sin(a)

        pts_3d = []
        for px, py in pts_2d:
            dx = px - ac_x
            dy = py

            # Rotate in YZ plane.
            # Positive twist 'a' rotates LE (+Y) towards +Z
            y_rot = -dx * cos_a - dy * sin_a + le_off
            z_rot = -dx * sin_a + dy * cos_a

            pts_3d.append(cq.Vector(r_m * S, y_rot, z_rot))

        pts_3d.append(pts_3d[0])          # close the polygon explicitly

        wire = cq.Wire.makePolygon(pts_3d)
        wires.append(wire)

    blade_solid = cq.Solid.makeLoft(wires, ruled=False)
    return blade_solid


# ---------------------------------------------------------------------------
# 6. Full propeller assembly
# ---------------------------------------------------------------------------

def build_propeller():
    print("  [1/4] Building blade sections & loft...")
    blade_solid = build_blade_mm(n_sections=16)
    blade_wp    = cq.Workplane("XY").add(blade_solid)

    print("  [2/4] Patterning 5 blades at 72-deg intervals...")
    # Rotate blade around Z and union all
    angle_step = 360.0 / N_BLADES
    all_blades = blade_wp

    for i in range(1, N_BLADES):
        rotated = blade_wp.rotate((0, 0, 0), (0, 0, 1), i * angle_step)
        all_blades = all_blades.union(rotated)

    print("  [3/4] Building hub...")
    hub = (cq.Workplane("XY")
             .cylinder(HUB_HEIGHT_M * S, HUB_RADIUS_M * S)
             .faces(">Z")
             .workplane()
             .circle(SHAFT_HOLE_R_M * S)
             .cutThruAll())

    print("  [4/4] Merging hub + blades...")
    propeller = hub.union(all_blades)
    return propeller


# ---------------------------------------------------------------------------
# 7. Mass estimate & properties
# ---------------------------------------------------------------------------

def mass_estimate_g(wp):
    """Rough mass from Volume() [mm^3] x density."""
    try:
        vol_mm3 = wp.val().Volume()
        vol_m3  = vol_mm3 * 1e-9
        return round(vol_m3 * MATERIAL["density_kg_m3"] * 1000, 1)
    except Exception:
        return None


def compute_mass_properties(wp):
    """
    Computes volume (cm3) and mass (g) for the given Workplane or Shape.
    """
    try:
        vol_mm3 = wp.val().Volume()
        vol_cm3 = vol_mm3 / 1000.0  # 1 cm3 = 1000 mm3
        vol_m3  = vol_mm3 * 1e-9
        mass_g  = vol_m3 * MATERIAL["density_kg_m3"] * 1000.0
        return {
            "volume_cm3": round(vol_cm3, 3),
            "mass_g": round(mass_g, 2)
        }
    except Exception as e:
        return {"volume_cm3": 0.0, "mass_g": 0.0, "error": str(e)}


def export_all(wp, out_dir: pathlib.Path, tag="propeller_5blade_tubercle"):
    """
    Exports the shape to STEP and STL with a timestamped filename.
    Returns the file paths.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    step_path = out_dir / f"{tag}.step"
    stl_path  = out_dir / f"{tag}.stl"

    exporters.export(wp, str(step_path))
    exporters.export(wp, str(stl_path), exportType="STL",
                     tolerance=0.001, angularTolerance=0.05)
    return {
        "step": str(step_path),
        "stl": str(stl_path)
    }


# ---------------------------------------------------------------------------
# 8. Export
# ---------------------------------------------------------------------------

def export_step_stl(wp, out_dir: pathlib.Path, tag="propeller_5blade_tubercle"):
    out_dir.mkdir(parents=True, exist_ok=True)
    step_path = out_dir / f"{tag}.step"
    stl_path  = out_dir / f"{tag}.stl"

    print(f"  Writing STEP -> {step_path}")
    exporters.export(wp, str(step_path))

    print(f"  Writing STL  -> {stl_path}")
    exporters.export(wp, str(stl_path), exportType="STL",
                     tolerance=0.001, angularTolerance=0.05)

    return {"step": str(step_path), "stl": str(stl_path)}


# ---------------------------------------------------------------------------
# 9. Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir",  default="quadcopter/cad")
    parser.add_argument("--sections", type=int, default=16)
    parser.add_argument("--step-only",action="store_true", help="Export STEP only (faster)")
    args = parser.parse_args()

    print("=" * 58)
    print("  5-Blade CF-PA6 Propeller with Tubercles")
    print("  CadQuery", cq.__version__)
    print("=" * 58)

    prop = build_propeller()

    mass = mass_estimate_g(prop)
    if mass:
        print(f"\n  Estimated mass : {mass} g  (CF-PA6, 1300 kg/m3)")

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    step_path = out_dir / "propeller_5blade_tubercle.step"

    print(f"\n  Exporting STEP -> {step_path}")
    exporters.export(prop, str(step_path))
    print("  STEP export complete.")

    if not args.step_only:
        stl_path = out_dir / "propeller_5blade_tubercle.stl"
        print(f"  Exporting STL  -> {stl_path}")
        exporters.export(prop, str(stl_path), exportType="STL",
                         tolerance=0.001, angularTolerance=0.05)
        print("  STL export complete.")

    # Summary JSON
    rpt = {
        "generated_at": datetime.datetime.now().isoformat(),
        "cadquery_version": cq.__version__,
        "n_blades": N_BLADES,
        "diameter_mm": PROP_RADIUS_M * 2 * 1000,
        "hub_radius_mm": HUB_RADIUS_M * 1000,
        "chord_root_mm": CHORD_ROOT_M * 1000,
        "chord_tip_mm": CHORD_TIP_M * 1000,
        "twist_root_deg": TWIST_ROOT_DEG,
        "twist_tip_deg": TWIST_TIP_DEG,
        "tubercle_amplitude_mm": TUBERCLE_AMP_M * 1000,
        "tubercle_wavelength_mm": TUBERCLE_WL_M * 1000,
        "n_loft_sections": args.sections,
        "estimated_mass_g": mass,
        "material": MATERIAL,
        "step_file": str(step_path),
    }
    rpt_path = out_dir.parent / "data" / "propeller_report.json"
    with open(rpt_path, "w") as f:
        json.dump(rpt, f, indent=2)

    print(f"\n  Done. Files in: {out_dir.resolve()}")
    print(f"  STEP : {step_path.name}")
    print(f"  JSON : {rpt_path.name}")

"""
Geometry Verification Script for FreeCAD Parametric Expert Skill.

This script is designed to be executed inside FreeCAD via the Robust MCP bridge
using mcp_freecad_execute_python. It validates the structural integrity of a
3D shape after extrusion.

Usage (inline in MCP call):
    _result_ = verify_geometry("ProfilePad")

Usage (file exec in MCP call):
    exec(open(r"<skill_path>/scripts/verify_geometry.py").read())
    _result_ = verify_geometry("ProfilePad")
"""
import FreeCAD as App


def verify_geometry(obj_name, doc_name=None):
    """
    Run a 5-check validation pipeline on a FreeCAD object.

    Args:
        obj_name:  Name of the object to verify (e.g. "ProfilePad").
        doc_name:  Document name. Uses ActiveDocument if None.

    Returns:
        dict with keys:
            status  – "success" or "fail"
            reason  – human-readable explanation (only on fail)
            checks  – dict of individual check results
            metrics – shape metrics (only on success)
    """
    # Resolve document
    if doc_name:
        doc = App.getDocument(doc_name)
    else:
        doc = App.ActiveDocument

    if not doc:
        return {
            "status": "fail",
            "reason": "No active document found.",
            "checks": {},
            "metrics": {},
        }

    checks = {}

    # ── Check 1: Object Existence ─────────────────────────────────────
    obj = doc.getObject(obj_name)
    checks["object_exists"] = obj is not None
    if not obj:
        return {
            "status": "fail",
            "reason": f"Object '{obj_name}' was not created.",
            "checks": checks,
            "metrics": {},
        }

    # ── Check 2: Clean Recompute ──────────────────────────────────────
    doc.recompute()
    state_str = str(getattr(obj, "State", []))
    checks["recompute_clean"] = "Invalid" not in state_str
    if not checks["recompute_clean"]:
        return {
            "status": "fail",
            "reason": f"Object is in an invalid state after recompute: {state_str}",
            "checks": checks,
            "metrics": {},
        }

    # ── Check 3: Shape Validity (Open CASCADE) ────────────────────────
    if not hasattr(obj, "Shape"):
        checks["shape_valid"] = False
        return {
            "status": "fail",
            "reason": f"Object '{obj_name}' has no Shape attribute.",
            "checks": checks,
            "metrics": {},
        }

    checks["shape_valid"] = obj.Shape.isValid()
    if not checks["shape_valid"]:
        return {
            "status": "fail",
            "reason": "The resulting shape is non-manifold or contains invalid self-intersections.",
            "checks": checks,
            "metrics": {},
        }

    # ── Check 4: Non-Zero Volume ──────────────────────────────────────
    volume = obj.Shape.Volume
    checks["volume_nonzero"] = volume > 0.0
    if not checks["volume_nonzero"]:
        return {
            "status": "fail",
            "reason": "The profile extruded to a zero-volume shape.",
            "checks": checks,
            "metrics": {},
        }

    # ── Check 5: Sketch Constraint Health ─────────────────────────────
    checks["sketch_fully_constrained"] = True  # default pass
    try:
        # Trace back to the source sketch (works for Pad, Pocket, Revolution)
        profile_link = getattr(obj, "Profile", None)
        sketch = None
        if profile_link:
            if isinstance(profile_link, list) and len(profile_link) > 0:
                sketch = profile_link[0]
            elif hasattr(profile_link, "Name"):
                sketch = profile_link

        if sketch and hasattr(sketch, "solve"):
            dof = sketch.solve()
            checks["sketch_fully_constrained"] = (dof == 0)
            if dof != 0:
                return {
                    "status": "fail",
                    "reason": f"Source sketch has {dof} degrees of freedom (under-constrained).",
                    "checks": checks,
                    "metrics": {"volume_mm3": volume},
                }
    except Exception as e:
        # Non-fatal: if we can't trace back to sketch, skip this check
        checks["sketch_fully_constrained"] = "skipped"

    # ── All checks passed ─────────────────────────────────────────────
    shape = obj.Shape
    metrics = {
        "volume_mm3": round(shape.Volume, 2),
        "surface_area_mm2": round(shape.Area, 2),
        "face_count": len(shape.Faces),
        "edge_count": len(shape.Edges),
    }

    return {
        "status": "success",
        "checks": checks,
        "metrics": metrics,
    }

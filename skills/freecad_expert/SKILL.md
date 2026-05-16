---
name: FreeCAD Parametric Expert
description: Multi-agent orchestration skill for producing production-ready parametric CAD models in FreeCAD 1.1 via the Robust MCP bridge. Implements a Sketch Designer → API Agent → Geometry Verifier loop with automatic retry on failure.
---

# FreeCAD 1.1 Parametric Expert — Orchestration Skill

This skill defines a **deterministic multi-agent pipeline** for generating
logically sound, production-ready parametric CAD models through the Robust MCP
bridge. It prevents the most common LLM-CAD failure modes: the Topological
Naming Problem, non-manifold geometry, zero-volume extrusions, and broken
sketch constraints.

---

## Orchestration Loop

When the user requests a parametric part, you **must** follow this loop exactly.
Do **not** skip the verification step.

```
[User Input: e.g. "T-Slot 2020 Profile"]
              │
              ▼
   ┌─────────────────────┐
   │  Orchestrator (You)  │◀──────────────────────────────┐
   └─────────────────────┘                               │
              │                                          │
              ▼                                          │
   ┌─────────────────────┐                               │
   │ Sketch Designer Agt │  (blueprints/Agent_SketchDesigner.md)
   └─────────────────────┘                               │
              │ outputs: coordinates, constraints, params│
              ▼                                          │
   ┌─────────────────────┐                               │ Fix Script /
   │  FreeCAD API Agent  │  (blueprints/Agent_FreeCAD_API.md)
   └─────────────────────┘                               │ Regenerate
              │ outputs: atomic Python scripts           │
              ▼                                          │
   ┌─────────────────────┐      No (Invalid Geometry)    │
   │  Geometry Verifier  │──────────────────────────────►┘
   └─────────────────────┘  (blueprints/Agent_GeometryVerifier.md)
              │ Yes (passes all checks)
              ▼
    [Model Finalized in FreeCAD]
```

### Step-by-step execution

1. **Parse the request** — identify profile type, key dimensions, and
   parametric variables the user wants to control.
2. **Assume the Sketch Designer role** — read
   `blueprints/Agent_SketchDesigner.md`. Produce the 2D geometric plan:
   coordinate list, constraint table, and spreadsheet alias map. Output this
   as structured data (not code yet).
3. **Switch to FreeCAD API Agent role** — read
   `blueprints/Agent_FreeCAD_API.md`. Convert the geometric plan into
   atomic `mcp_freecad_execute_python` calls following all FreeCAD 1.1
   API rules.
4. **Run the Geometry Verifier** — after the 3D feature is created, execute
   the verification script from `scripts/verify_geometry.py` via MCP.
   - If the verifier returns `"fail"`, attach the error reason and loop
     back to step 2. Adjust the coordinates or constraints accordingly.
     Maximum 3 retry attempts before surfacing the error to the user.
   - If the verifier returns `"success"`, proceed to finalization.
5. **Finalize** — take a screenshot, present the result, and clear the
   generation context. Only pass the spreadsheet alias map forward for
   future parametric modifications.

---

## Key API Changes (FreeCAD 1.1+)

| Legacy | FreeCAD 1.1+ | Notes |
|--------|-------------|-------|
| `Support` | `AttachmentSupport` | Sketch attachment |
| `DataSupport` | `DataAttachmentSupport` | Data layer |
| `MapMode` values | Same | Critical for sketch alignment |
| Sub-property placement | `obj.Placement = App.Placement(...)` | Single recompute trigger |

## Safe Attachment Pattern

```python
sketch.AttachmentSupport = [(body, 'XY_Plane')]
sketch.MapMode = 'FlatFace'
doc.recompute()
```

---

## Stability Best Practices

1. **Atomic Operations**: Never combine Document Creation, Sketching, and
   Padding in a single `execute_python` call. Split them to let the bridge
   breathe between recomputes.
2. **Explicit Recompute**: Call `doc.recompute()` after each complete feature.
   Never recompute inside high-frequency loops.
3. **Spreadsheet First**: Initialize parameters in a `Spreadsheet::Sheet`
   named `Params` *before* creating geometry so expressions have valid targets.
4. **Queue Flushing**: Wait ~2 seconds between calls when the bridge is
   sluggish to let the GUI thread flush its event queue.

---

## Optimization Rules

### Isolate via Custom Spreadsheets
All parametric adjustments must be made by modifying spreadsheet cell values
through MCP, **not** by rewriting sketch geometry code. The LLM must never
edit an existing complex script block — it must only change cell values.

### Keep Context Clean
Once a step (e.g., the 2D cross-section) is verified, **clear the generation
context**. Pass only the resulting `Params` alias map to the next stage. This
prevents token bloat and reduces hallucination risk in later stages.

### Headless Iteration (Optional)
For rapid iteration, the bridge can be run via `freecadcmd` (headless). Use
the GUI only to inspect the finalized, verified model. See
`scripts/restart_bridge.py` for bridge lifecycle management.

---

## Agent Blueprints

| Agent | File | Responsibility |
|-------|------|----------------|
| Sketch Designer | [`Agent_SketchDesigner.md`](blueprints/Agent_SketchDesigner.md) | 2D geometry, constraints, parametric binding |
| FreeCAD API Agent | [`Agent_FreeCAD_API.md`](blueprints/Agent_FreeCAD_API.md) | Translates geometric plan into atomic FreeCAD Python |
| Geometry Verifier | [`Agent_GeometryVerifier.md`](blueprints/Agent_GeometryVerifier.md) | Validates shape integrity before finalization |

## Verification Scripts

| Script | File | Purpose |
|--------|------|---------|
| Shape validator | [`verify_geometry.py`](scripts/verify_geometry.py) | Checks manifold, volume, constraint solver status |
| Bridge restart | [`restart_bridge.py`](scripts/restart_bridge.py) | Recovers the MCP bridge without restarting FreeCAD |

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

## Orchestration Loop

When the user requests a parametric part, you **must** follow one of the orchestration loops below. Do **not** skip the verification step.

### Route A: Native FreeCAD 1.1 Pipeline
Use this route for highly parametric models requiring native spreadsheet control directly in FreeCAD.
```
[User Input] ──► [Sketch Designer] ──► [FreeCAD API Agent] ──► [Geometry Verifier]
```

### Route B: CadQuery Pipeline (Zero-To-CAD-1m)
Use this route for fast generative builds, leveraging the synthetic patterns proved by the Zero-To-CAD-1m dataset.
```
[User Input] ──► [CadQuery API Agent] ──► [STEP Export] ──► [FreeCAD Import] ──► [Geometry Verifier]
```

---

## Zero-To-CAD-1m Dataset Integration

The workspace includes scripts to pull reference models from the 1-million-part synthetic dataset:
- Run `python scripts/download_zero_to_cad.py` to cache parquet validation partitions and extract CadQuery templates.
- Use these templates as few-shot context when generating complex mechanical parts via the **CadQuery API Agent**.

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

1. **Atomic Operations**: Never combine Document Creation, Sketching, and Padding in a single `execute_python` call. Split them to let the bridge breathe between recomputes.
2. **Explicit Recompute**: Call `doc.recompute()` after each complete feature. Never recompute inside high-frequency loops.
3. **Spreadsheet First**: Initialize parameters in a `Spreadsheet::Sheet` named `Params` *before* creating geometry so expressions have valid targets.
4. **Queue Flushing**: Wait ~2 seconds between calls when the bridge is sluggish to let the GUI thread flush its event queue.

---

## Optimization Rules

### Isolate via Custom Spreadsheets
All parametric adjustments must be made by modifying spreadsheet cell values through MCP, **not** by rewriting sketch geometry code. The LLM must never edit an existing complex script block — it must only change cell values.

### Keep Context Clean
Once a step is verified, **clear the generation context**. Pass only the resulting `Params` alias map to the next stage. This prevents token bloat and reduces hallucination risk in later stages.

---

## Agent Blueprints

| Agent | File | Responsibility |
|-------|------|----------------|
| Sketch Designer | [`Agent_SketchDesigner.md`](blueprints/Agent_SketchDesigner.md) | 2D geometry, constraints, parametric binding |
| FreeCAD API Agent | [`Agent_FreeCAD_API.md`](blueprints/Agent_FreeCAD_API.md) | Translates geometric plan into atomic FreeCAD Python |
| CadQuery API Agent | [`Agent_CadQuery_API.md`](blueprints/Agent_CadQuery_API.md) | Generates CadQuery scripts, exports STEP, and imports into FreeCAD |
| Geometry Verifier | [`Agent_GeometryVerifier.md`](blueprints/Agent_GeometryVerifier.md) | Validates shape integrity before finalization |

## Verification Scripts

| Script | File | Purpose |
|--------|------|---------|
| Shape validator | [`verify_geometry.py`](scripts/verify_geometry.py) | Checks manifold, volume, constraint solver status |
| Zero-To-CAD downloader | [`download_zero_to_cad.py`](scripts/download_zero_to_cad.py) | Downloads, extracts, and summarizes Zero-To-CAD dataset samples |
| Bridge restart | [`restart_bridge.py`](scripts/restart_bridge.py) | Recovers the MCP bridge without restarting FreeCAD |


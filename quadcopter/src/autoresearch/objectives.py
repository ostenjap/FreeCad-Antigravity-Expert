"""
objectives.py
=============
The harness configuration that Claude/Opus sets — "what perfect means" plus the
run budget and swarm knobs.  The objective DIRECTIONS themselves live in
optimization.evaluate.OBJECTIVES (the ground truth); this just carries the
human-facing goal text and loop parameters.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class Objective:
    description: str = (
        "Find Pareto-optimal 10-inch quadcopter propellers that maximize hover "
        "Figure of Merit, maximize tubercle noise reduction, and minimize blade "
        "mass, subject to structural margin >= 0, tip Mach < 0.6, and no "
        "blade-pass resonance."
    )
    time_budget_s: float = 120.0      # wall-clock stop rule
    concurrency: int = 3              # logical swarm concurrency
    proposals_per_gen: int = 2        # swarm proposer tasks per generation
    designs_per_proposal: int = 5     # designs each proposer should return
    mutants_per_gen: int = 16         # deterministic GA mutants per generation
    lhs_per_gen: int = 8              # fresh Latin-hypercube samples per generation
    code_every: int = 4              # ask the coder for a new operator every N gens
    reflect_every: int = 2            # run the analyst every N gens
    seed: int = 0
    use_llm: bool = True              # if False, run a pure deterministic GA

    def save(self, path: Path):
        Path(path).write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls, path: str | None = None) -> "Objective":
        if not path:
            return cls()
        data = json.loads(Path(path).read_text())
        return cls(**{k: v for k, v in data.items()
                      if k in cls.__dataclass_fields__})

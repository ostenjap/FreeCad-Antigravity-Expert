"""
notebook.py
===========
Persistent research archive + human-readable journal for an autoresearch run.

* archive  : every evaluated candidate (used to recompute the global Pareto front)
* journal  : a markdown log Opus/the analyst append to each generation
* outputs  : pareto_front.json, all_candidates.csv, research_journal.md
"""

from __future__ import annotations

import csv
import datetime
import json
from pathlib import Path
from typing import List

from optimization.evaluate import OBJECTIVES
from optimization.pareto import pareto_front


class ResearchNotebook:
    def __init__(self, objective_desc: str):
        self.objective_desc = objective_desc
        self.results: List[dict] = []      # all evaluated candidates
        self.journal: List[str] = []
        self.generations = 0
        self.started = datetime.datetime.now()
        self._log_header()

    def _log_header(self):
        self.journal.append(f"# Propeller Autoresearch Journal\n")
        self.journal.append(f"_Started {self.started.isoformat(timespec='seconds')}_\n")
        self.journal.append(f"\n**Objective:** {self.objective_desc}\n")
        self.journal.append(f"\n**Optimizing:** "
                            + ", ".join(f"{k} ({v})" for k, v in OBJECTIVES.items())
                            + "\n")

    # -- data --------------------------------------------------------------
    def add(self, results: List[dict]):
        self.results.extend(results)

    def front(self) -> List[dict]:
        return pareto_front(self.results)

    def best(self, objective: str = None) -> dict | None:
        front = self.front()
        if not front:
            return None
        obj = objective or next(iter(OBJECTIVES))
        rev = OBJECTIVES[obj] == "max"
        return sorted(front, key=lambda r: r["objectives"][obj], reverse=rev)[0]

    # -- journal -----------------------------------------------------------
    def log_generation(self, gen: int, n_new: int, n_feasible: int,
                       reflection: str = None):
        self.generations = gen
        front = self.front()
        line = [f"\n## Generation {gen}\n",
                f"- evaluated this gen: {n_new}  (feasible: {n_feasible})",
                f"- total evaluated: {len(self.results)}",
                f"- Pareto-front size: {len(front)}"]
        if front:
            for obj, direction in OBJECTIVES.items():
                vals = [r["objectives"][obj] for r in front]
                best = max(vals) if direction == "max" else min(vals)
                line.append(f"- best {obj}: {best:.4f}")
        if reflection:
            line.append(f"\n**Analyst:** {reflection}")
        self.journal.append("\n".join(line) + "\n")

    # -- persistence -------------------------------------------------------
    def save(self, out_data: Path, out_docs: Path):
        out_data.mkdir(parents=True, exist_ok=True)
        out_docs.mkdir(parents=True, exist_ok=True)
        front = self.front()

        with open(out_data / "pareto_front.json", "w") as f:
            json.dump({
                "objective": self.objective_desc,
                "directions": OBJECTIVES,
                "generations": self.generations,
                "total_evaluated": len(self.results),
                "pareto_front": front,
            }, f, indent=2)

        # all candidates CSV (objectives + key metrics + design vars)
        if self.results:
            obj_keys = list(OBJECTIVES.keys())
            des_keys = list(self.results[0]["design"].keys())
            with open(out_data / "all_candidates.csv", "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["feasible"] + obj_keys + ["on_front"] + des_keys)
                front_ids = {id(r) for r in front}
                for r in self.results:
                    w.writerow(
                        [r["feasible"]]
                        + [r["objectives"][k] for k in obj_keys]
                        + [id(r) in front_ids]
                        + [r["design"][k] for k in des_keys]
                    )

        with open(out_docs / "research_journal.md", "w", encoding="utf-8") as f:
            f.write("\n".join(self.journal))

        return {
            "pareto_front_json": str(out_data / "pareto_front.json"),
            "all_candidates_csv": str(out_data / "all_candidates.csv"),
            "journal_md": str(out_docs / "research_journal.md"),
        }

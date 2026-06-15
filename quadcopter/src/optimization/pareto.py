"""
pareto.py
=========
Multi-objective non-dominated sorting.  Small and dependency-free (O(n^2),
fine for the few-thousand candidates an autoresearch run produces).
"""

from __future__ import annotations

from typing import Dict, List

from .evaluate import OBJECTIVES


def _to_min_vector(obj: Dict[str, float], directions: Dict[str, str]) -> List[float]:
    """Convert an objective dict to a pure-minimization vector (negate maxima)."""
    return [(-obj[k] if directions[k] == "max" else obj[k]) for k in directions]


def dominates(a: Dict[str, float], b: Dict[str, float],
              directions: Dict[str, str] = OBJECTIVES) -> bool:
    """True if a dominates b (no worse on every objective, strictly better on one)."""
    va = _to_min_vector(a, directions)
    vb = _to_min_vector(b, directions)
    no_worse = all(x <= y for x, y in zip(va, vb))
    strictly = any(x < y for x, y in zip(va, vb))
    return no_worse and strictly


def non_dominated_indices(objs: List[Dict[str, float]],
                          directions: Dict[str, str] = OBJECTIVES) -> List[int]:
    """Indices of the Pareto-optimal (non-dominated) entries in ``objs``."""
    n = len(objs)
    keep = []
    for i in range(n):
        dominated = False
        for j in range(n):
            if i == j:
                continue
            if dominates(objs[j], objs[i], directions):
                dominated = True
                break
        if not dominated:
            keep.append(i)
    return keep


def pareto_front(results: List[dict],
                 directions: Dict[str, str] = OBJECTIVES,
                 feasible_only: bool = True) -> List[dict]:
    """Given a list of evaluate() results, return the non-dominated subset.

    De-duplicates identical objective vectors so the front stays clean.
    """
    pool = [r for r in results if (r.get("feasible", True) or not feasible_only)]
    if not pool:
        return []
    objs = [r["objectives"] for r in pool]
    idx = non_dominated_indices(objs, directions)

    seen = set()
    front = []
    for i in idx:
        key = tuple(round(v, 6) for v in pool[i]["objectives"].values())
        if key in seen:
            continue
        seen.add(key)
        front.append(pool[i])
    # Sort the front by the primary objective for stable presentation
    primary = next(iter(directions))
    front.sort(key=lambda r: r["objectives"][primary],
               reverse=(directions[primary] == "max"))
    return front

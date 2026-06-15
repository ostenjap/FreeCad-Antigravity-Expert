"""
optimization
============
Deterministic "lab" for the propeller autoresearch loop.

This package is the GROUND TRUTH: every candidate design proposed by the local
LLM swarm is scored here, in plain Python, against fixed physics models.  The
LLM never computes a fitness number that counts — it only proposes parameter
vectors (and, optionally, sandboxed operator/surrogate code).  See
``autoresearch/`` for the loop that drives this.

Modules
-------
design       Design dataclass, search-variable bounds, vector<->Design, adapters.
performance  BEMT-lite hover performance (thrust, power, Figure of Merit).
mass         Analytical blade-mass estimate (no CadQuery).
evaluate     evaluate(Design) -> objectives + constraints + feasibility.
pareto       Fast non-dominated sort / Pareto-front extraction.
"""

import sys
import pathlib

# The sibling analysis modules (propeller_physics, tubercle_analysis,
# generate_propeller) live in the parent ``src/`` dir, which is not a package.
# Make them importable regardless of how this package is launched.
_SRC = pathlib.Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

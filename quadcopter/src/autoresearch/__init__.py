"""
autoresearch
============
The Karpathy-style autonomous research loop for propeller design.

Roles
-----
* Claude/Opus is the HARNESS: it sets the objective (objectives.py), authors the
  prompt-skills the local agents run (skills/), and reflects between generations.
* A swarm of LOCAL LLMs (Ollama on this machine) does the high-volume "small
  stuff": propose / mutate candidate designs, and occasionally write a sandboxed
  mutation operator.  See local_llm.py + swarm.py.
* The deterministic optimization/ package is the GROUND TRUTH that scores every
  candidate.  The LLM never produces a fitness number that counts.

Entry point: ``python -m autoresearch.researcher --budget <seconds>``
"""

import sys
import pathlib

_SRC = pathlib.Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

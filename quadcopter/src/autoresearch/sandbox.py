"""
sandbox.py
==========
Guarded execution of LLM-generated Python (the "LLM may write/tune analysis
code" capability).  This is a *soft* sandbox suited to self-generated code on a
trusted local machine — not a defence against deliberately hostile code.

Two layers:
  1. AST allowlist — reject imports of anything except math/numpy/random, plus
     dunder access, and dangerous builtins (open/exec/eval/__import__/compile).
  2. Subprocess isolation — run the screened code in a fresh `python` process
     with a hard timeout and a scratch CWD; parse a single JSON line from stdout.

Contract for a mutation operator.  The generated code must define:

    def mutate(parents, bounds, rng):
        # parents : list[list[float]]  (each a design vector, order = SEARCH_VARS)
        # bounds  : list[[lo, hi]]
        # rng     : random.Random
        # return  : list[list[float]]  (child vectors)
        ...

Any error, timeout, disallowed construct, or malformed return -> the operator is
discarded (empty list) and the generation proceeds.  Worst case is a wasted slot,
never a corrupted archive: every returned vector is re-clamped and re-scored by
the deterministic evaluate().
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import List

ALLOWED_IMPORTS = {"math", "numpy", "random"}
FORBIDDEN_NAMES = {
    "open", "exec", "eval", "compile", "__import__", "input",
    "os", "sys", "subprocess", "socket", "shutil", "pathlib",
    "globals", "locals", "vars", "getattr", "setattr", "delattr",
}


class SandboxRejected(Exception):
    pass


def screen_code(code: str) -> None:
    """Raise SandboxRejected if the code uses anything outside the allowlist."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise SandboxRejected(f"syntax error: {e}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in ALLOWED_IMPORTS:
                    raise SandboxRejected(f"import not allowed: {a.name}")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in ALLOWED_IMPORTS:
                raise SandboxRejected(f"import-from not allowed: {node.module}")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__"):
                raise SandboxRejected(f"dunder access not allowed: {node.attr}")
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_NAMES:
                raise SandboxRejected(f"name not allowed: {node.id}")


_RUNNER = textwrap.dedent('''
    import json, random, sys, math
    try:
        import numpy as np  # noqa
    except Exception:
        np = None

    USER_CODE = {user_code!r}
    payload = json.loads(sys.stdin.read())
    ns = {{"np": np, "numpy": np, "math": math, "random": random}}
    exec(USER_CODE, ns)
    mutate = ns.get("mutate")
    if mutate is None:
        print("[]"); sys.exit(0)
    rng = random.Random(payload.get("seed", 0))
    children = mutate(payload["parents"], payload["bounds"], rng)
    out = []
    for c in (children or []):
        vec = [float(x) for x in c]
        out.append(vec)
    print(json.dumps(out))
''')


def run_mutation_operator(code: str,
                          parents: List[List[float]],
                          bounds: List[List[float]],
                          seed: int = 0,
                          timeout: float = 5.0,
                          max_children: int = 64) -> List[List[float]]:
    """Screen + run an LLM-generated `mutate` operator in an isolated subprocess.
    Returns child vectors, or [] on any failure."""
    try:
        screen_code(code)
    except SandboxRejected:
        return []

    runner = _RUNNER.format(user_code=code)
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "op.py"
        script.write_text(runner, encoding="utf-8")
        payload = json.dumps({"parents": parents, "bounds": bounds, "seed": seed})
        try:
            proc = subprocess.run(
                [sys.executable, "-E", str(script)],
                input=payload, capture_output=True, text=True,
                timeout=timeout, cwd=tmp,
            )
        except (subprocess.TimeoutExpired, OSError):
            return []
        if proc.returncode != 0:
            return []
        try:
            children = json.loads(proc.stdout.strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError):
            return []
    if not isinstance(children, list):
        return []
    # Keep only well-formed numeric vectors of the right width.
    width = len(bounds)
    clean = [c for c in children
             if isinstance(c, list) and len(c) == width
             and all(isinstance(x, (int, float)) for x in c)]
    return clean[:max_children]


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    bounds = [[0.02, 0.034], [0.006, 0.014]]
    # 1) malicious -> rejected
    bad = "import os\ndef mutate(parents, bounds, rng):\n    os.system('echo hi')\n    return parents"
    try:
        screen_code(bad)
        print("FAIL: malicious code passed screening")
    except SandboxRejected as e:
        print("OK   rejected malicious code:", e)
    # 2) valid operator -> runs
    good = textwrap.dedent("""
        def mutate(parents, bounds, rng):
            out = []
            for p in parents:
                child = [min(b[1], max(b[0], x * (1 + rng.uniform(-0.1, 0.1))))
                         for x, b in zip(p, bounds)]
                out.append(child)
            return out
    """)
    kids = run_mutation_operator(good, [[0.028, 0.010]], bounds, seed=1)
    print("OK   valid operator produced", len(kids), "children:", kids)

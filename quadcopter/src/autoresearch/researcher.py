"""
researcher.py  —  the autoresearch loop
=======================================
Claude/Opus is the harness: it sets the objective (objectives.py) and authored
the skills (skills/). This loop runs the Karpathy-style cycle each generation:

    PROPOSE (swarm) -> MUTATE/CODE (swarm + GA) -> EVALUATE (ground truth)
    -> SELECT (Pareto) -> REFLECT (swarm) -> SCRIBE (journal)

The local-LLM swarm does the high-volume "small stuff"; the deterministic
optimization/ package scores everything. Deterministic GA operators always run
too, so the front improves even with --no-llm or a flaky local model.

Run:  python -m autoresearch.researcher --budget 120
"""

from __future__ import annotations

import argparse
import random
import time
from pathlib import Path
from typing import List

import numpy as np

from . import _SRC  # noqa: F401
from .objectives import Objective
from .notebook import ResearchNotebook
from . import swarm
from . import sandbox
from . import local_llm

from optimization.design import Design, BOUNDS, SEARCH_VARS, random_design
from optimization.evaluate import evaluate, OBJECTIVES

SKILLS_DIR = Path(__file__).resolve().parent / "skills"
ROOT = _SRC.parent                      # quadcopter/
OUT_DATA = ROOT / "data" / "optimization"
OUT_DOCS = ROOT / "docs"

BOUND_LIST = [[BOUNDS[v][0], BOUNDS[v][1]] for v in SEARCH_VARS]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def load_skill(name: str) -> str:
    return (SKILLS_DIR / f"{name}.md").read_text(encoding="utf-8")


def design_from_partial(d: dict) -> Design:
    """Build a Design from a dict that may contain only the search variables."""
    kw = {k: d[k] for k in SEARCH_VARS if k in d and isinstance(d[k], (int, float))}
    return Design(**kw).clamped()


def design_from_vector(vec) -> Design:
    return Design.from_vector(vec).clamped()


def safe_eval(design: Design):
    try:
        return evaluate(design)
    except Exception:
        return None


def lhs_designs(n: int, rng: random.Random) -> List[Design]:
    """Latin-hypercube samples across the bounds (scipy if available)."""
    try:
        from scipy.stats import qmc
        sampler = qmc.LatinHypercube(d=len(SEARCH_VARS), seed=rng.randint(0, 2**31))
        unit = sampler.random(n)
        lo = np.array([b[0] for b in BOUND_LIST])
        hi = np.array([b[1] for b in BOUND_LIST])
        pts = lo + unit * (hi - lo)
        return [design_from_vector(p) for p in pts]
    except Exception:
        return [random_design(rng) for _ in range(n)]


def ga_mutants(parents: List[Design], n: int, rng: random.Random) -> List[Design]:
    """Deterministic GA: gaussian mutation, DE-style recombination, blade steps."""
    if not parents:
        return [random_design(rng) for _ in range(n)]
    out = []
    pv = [p.to_vector() for p in parents]
    for _ in range(n):
        mode = rng.random()
        if mode < 0.5 or len(pv) < 3:                 # gaussian mutation
            base = list(rng.choice(pv))
            for i, (lo, hi) in enumerate(BOUND_LIST):
                if rng.random() < 0.5:
                    base[i] += rng.gauss(0, 0.12) * (hi - lo)
        else:                                          # differential evolution
            a, b, c = rng.sample(pv, 3)
            F = 0.6
            base = [a[i] + F * (b[i] - c[i]) for i in range(len(a))]
            if rng.random() < 0.3:                     # occasional blade step
                base[-1] += rng.choice([-1, 1])
        out.append(design_from_vector(base))
    return out


def front_summary(front: List[dict], limit: int = 8) -> str:
    if not front:
        return "(front empty)"
    lines = []
    for r in front[:limit]:
        o, d = r["objectives"], r["design"]
        lines.append(
            f'FM={o["figure_of_merit"]:.3f} noise={o["noise_reduction_dB"]:.2f} '
            f'mass={o["blade_mass_g"]:.1f}g | B={d["n_blades"]} '
            f'cr={d["chord_root_m"]:.3f} ct={d["chord_tip_m"]:.3f} '
            f'tw={d["twist_root_deg"]:.0f}/{d["twist_tip_deg"]:.0f} '
            f'amp={d["tubercle_amp_m"]:.4f} wl={d["tubercle_wl_m"]:.3f}'
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# swarm steps (best-effort; all degrade gracefully)
# ---------------------------------------------------------------------------
def swarm_propose(obj: Objective, front: List[dict], reflection: str) -> List[Design]:
    sys_prompt = load_skill("proposer")
    ctx = (f"Objective: {obj.description}\n\n"
           f"Current Pareto front (best designs so far):\n{front_summary(front)}\n\n")
    if reflection:
        ctx += f"Analyst guidance for this round: {reflection}\n\n"
    ctx += f'Return JSON with exactly {obj.designs_per_proposal} designs.'
    tasks = [swarm.SwarmTask(role="propose", system=sys_prompt, user=ctx,
                             timeout=90, temperature=0.9, num_predict=600)
             for _ in range(obj.proposals_per_gen)]
    results = swarm.run_batch(tasks, concurrency=obj.concurrency)
    designs = []
    for r in results:
        if isinstance(r, dict) and isinstance(r.get("designs"), list):
            for d in r["designs"]:
                if isinstance(d, dict):
                    designs.append(design_from_partial(d))
    return designs


def swarm_mutate(obj: Objective, parents: List[dict]) -> List[Design]:
    if not parents:
        return []
    sys_prompt = load_skill("mutator")
    tasks = []
    for r in parents[:obj.proposals_per_gen]:
        d = r["design"]
        parent = {k: d[k] for k in SEARCH_VARS}
        ctx = (f"Parent design:\n{parent}\n\n"
               f"Return JSON with 4 mutants of this parent.")
        tasks.append(swarm.SwarmTask(role="mutate", system=sys_prompt, user=ctx,
                                     timeout=90, temperature=0.8, num_predict=450))
    results = swarm.run_batch(tasks, concurrency=obj.concurrency)
    designs = []
    for r in results:
        if isinstance(r, dict) and isinstance(r.get("designs"), list):
            for d in r["designs"]:
                if isinstance(d, dict):
                    designs.append(design_from_partial(d))
    return designs


def swarm_code_operator(parents: List[dict], seed: int) -> List[Design]:
    """Ask the coder for a mutate() operator, sandbox-run it on the parents."""
    sys_prompt = load_skill("coder")
    parent_vecs = [[r["design"][k] for k in SEARCH_VARS] for r in parents[:6]]
    ctx = (f"Current best design vectors (order={SEARCH_VARS}):\n{parent_vecs}\n\n"
           f"Bounds (order matches):\n{BOUND_LIST}\n\n"
           "Write the mutate() operator now. Return ONLY {\"code\": \"...\"}.")
    res = swarm.run_batch(
        [swarm.SwarmTask(role="code", system=sys_prompt, user=ctx,
                         timeout=150, temperature=0.5, num_predict=900)],
        concurrency=1)[0]
    if not (isinstance(res, dict) and isinstance(res.get("code"), str)):
        return []
    child_vecs = sandbox.run_mutation_operator(res["code"], parent_vecs,
                                               BOUND_LIST, seed=seed)
    return [design_from_vector(v) for v in child_vecs]


def swarm_reflect(obj: Objective, front: List[dict]) -> str:
    sys_prompt = load_skill("analyst")
    ctx = (f"Objective: {obj.description}\n\n"
           f"Current Pareto front:\n{front_summary(front, limit=10)}\n\n"
           "Give your reflection and focus directives as JSON.")
    res = swarm.run_batch(
        [swarm.SwarmTask(role="reflect", system=sys_prompt, user=ctx,
                         timeout=120, temperature=0.6, num_predict=400)],
        concurrency=1)[0]
    if isinstance(res, dict):
        refl = res.get("reflection", "")
        focus = res.get("focus", [])
        if isinstance(focus, list) and focus:
            refl = (refl + " Focus: " + "; ".join(str(f) for f in focus)).strip()
        return refl
    return ""


# ---------------------------------------------------------------------------
# main loop
# ---------------------------------------------------------------------------
def run(obj: Objective):
    rng = random.Random(obj.seed)
    nb = ResearchNotebook(obj.description)

    llm_up = obj.use_llm and local_llm.available()
    print("=" * 64)
    print("  Propeller Autoresearch - Karpathy loop")
    print(f"  budget={obj.time_budget_s:.0f}s  concurrency={obj.concurrency}  "
          f"LLM swarm={'ON ('+', '.join(local_llm.list_models())+')' if llm_up else 'OFF (deterministic GA)'}")
    print("=" * 64)

    # Seed: baseline + LHS
    seed_designs = [Design()] + lhs_designs(obj.lhs_per_gen * 2, rng)
    seed_results = [r for r in (safe_eval(d) for d in seed_designs) if r]
    nb.add(seed_results)
    nb.log_generation(0, len(seed_results),
                      sum(r["feasible"] for r in seed_results),
                      reflection="seed population")
    print(f"  gen 0: seeded {len(seed_results)} designs, "
          f"front={len(nb.front())}")

    t0 = time.time()
    deadline = t0 + obj.time_budget_s
    gen = 0
    reflection = ""
    while time.time() < deadline:
        gen += 1
        front = nb.front()
        candidates: List[Design] = []

        # 1+2. swarm propose + mutate (best-effort). Each local-LLM call is slow
        # on a small GPU, so skip remaining swarm steps once the budget is spent;
        # the fast deterministic GA below always runs and banks progress.
        if llm_up and time.time() < deadline:
            candidates += swarm_propose(obj, front, reflection)
            if time.time() < deadline:
                candidates += swarm_mutate(obj, front)
            # 2b. occasionally let a coder write a sandboxed operator
            if gen % obj.code_every == 0 and time.time() < deadline:
                coded = swarm_code_operator(front, seed=rng.randint(0, 10**6))
                if coded:
                    print(f"  gen {gen}: coder operator produced {len(coded)} children")
                candidates += coded

        # deterministic operators always run (guarantees progress)
        parents = [r for r in front]
        candidates += ga_mutants([design_from_partial(r["design"]) for r in parents],
                                 obj.mutants_per_gen, rng)
        candidates += lhs_designs(obj.lhs_per_gen, rng)

        # 3. EVALUATE (ground truth)
        new_results = [r for r in (safe_eval(d) for d in candidates) if r]
        n_feas = sum(r["feasible"] for r in new_results)

        # 4. SELECT
        nb.add(new_results)

        # 5. REFLECT (steers next gen) — skip if no next gen will run
        if llm_up and gen % obj.reflect_every == 0 and time.time() < deadline:
            reflection = swarm_reflect(obj, nb.front())

        # 6. SCRIBE (journal)
        nb.log_generation(gen, len(new_results), n_feas, reflection or None)
        front = nb.front()
        best_fm = max((r["objectives"]["figure_of_merit"] for r in front), default=0)
        elapsed = time.time() - t0
        print(f"  gen {gen:2d}: +{len(new_results):3d} eval ({n_feas} feasible)  "
              f"front={len(front):3d}  bestFM={best_fm:.3f}  [{elapsed:.0f}s]")

    # ---- report ----
    paths = nb.save(OUT_DATA, OUT_DOCS)
    front = nb.front()
    print("\n" + "=" * 64)
    print(f"  DONE  generations={gen}  evaluated={len(nb.results)}  "
          f"Pareto-front={len(front)}")
    print("=" * 64)
    print("  Top designs by each objective:")
    for obj_name, direction in OBJECTIVES.items():
        best = nb.best(obj_name)
        if best:
            o, d = best["objectives"], best["design"]
            print(f"   * best {obj_name:18s}: FM={o['figure_of_merit']:.3f} "
                  f"noise={o['noise_reduction_dB']:.2f} mass={o['blade_mass_g']:.1f}g "
                  f"| B={d['n_blades']} cr={d['chord_root_m']:.3f} "
                  f"tw={d['twist_root_deg']:.0f}/{d['twist_tip_deg']:.0f} "
                  f"amp={d['tubercle_amp_m']:.4f} wl={d['tubercle_wl_m']:.3f}")
    print("\n  Saved:")
    for k, v in paths.items():
        print(f"   - {k}: {v}")
    try:
        _plot_front(front, OUT_DOCS / "pareto.png")
        print(f"   - pareto_png: {OUT_DOCS / 'pareto.png'}")
    except Exception as e:
        print(f"   (plot skipped: {e})")
    return nb


def _plot_front(front: List[dict], path: Path):
    if not front:
        return
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fm = [r["objectives"]["figure_of_merit"] for r in front]
    noise = [r["objectives"]["noise_reduction_dB"] for r in front]
    mass = [r["objectives"]["blade_mass_g"] for r in front]
    fig, ax = plt.subplots(figsize=(7, 5))
    sc = ax.scatter(fm, noise, c=mass, s=60, cmap="viridis", edgecolor="k")
    ax.set_xlabel("Figure of Merit (↑ better)")
    ax.set_ylabel("Noise reduction dB (↑ better)")
    ax.set_title("Propeller Pareto front (color = blade mass, g)")
    fig.colorbar(sc, label="blade mass (g)")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Propeller autoresearch loop")
    ap.add_argument("--budget", type=float, default=120.0, help="wall-clock seconds")
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-llm", action="store_true", help="deterministic GA only")
    ap.add_argument("--config", help="path to an Objective JSON")
    args = ap.parse_args()

    obj = Objective.load(args.config)
    obj.time_budget_s = args.budget
    obj.concurrency = args.concurrency
    obj.seed = args.seed
    if args.no_llm:
        obj.use_llm = False

    run(obj)

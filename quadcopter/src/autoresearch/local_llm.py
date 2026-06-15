"""
local_llm.py
============
Thin client for the local Ollama server (http://localhost:11434).  Uses only the
standard library so there are no extra dependencies.

Model routing (chosen for a 4 GB GTX 1650):
  propose / mutate   -> phi4-mini:latest      (fits VRAM, fast, supports tools)
  code / reflect      -> qwen2.5-coder:7b      (best coder; spills to CPU, used sparingly)
  trivial / scribe    -> deepseek-coder:1.3b   (tiny, very fast, completion-only)

If a routed model is missing, we fall back to whatever is installed.  Every call
is best-effort: callers must treat a None/empty return as "the swarm produced
nothing" and fall back to deterministic behaviour.
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error

ENDPOINT = "http://localhost:11434"

ROLE_MODELS = {
    "propose": "phi4-mini:latest",
    "mutate":  "phi4-mini:latest",
    # qwen2.5-coder:7b is the strongest coder but ~4.7 GB spills to CPU on a 4 GB
    # card and is slow.  Reserve it for the (occasional) code step only; keep the
    # per-generation hot path (reflect) on the VRAM-resident phi4-mini.
    "code":    "qwen2.5-coder:7b",
    "reflect": "phi4-mini:latest",
    "trivial": "deepseek-coder:1.3b",
}


def _post(path: str, payload: dict, timeout: float):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(ENDPOINT + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def list_models() -> list[str]:
    try:
        req = urllib.request.Request(ENDPOINT + "/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            tags = json.loads(resp.read().decode("utf-8"))
        return [m["name"] for m in tags.get("models", [])]
    except Exception:
        return []


def available() -> bool:
    return len(list_models()) > 0


def resolve_model(role: str) -> str | None:
    """Map a role to an installed model, falling back gracefully."""
    installed = list_models()
    if not installed:
        return None
    want = ROLE_MODELS.get(role)
    if want in installed:
        return want
    # Fall back: prefer something with the same family, else the first model.
    for m in installed:
        if want and want.split(":")[0] in m:
            return m
    return installed[0]


def chat(role: str, system: str, user: str,
         json_mode: bool = True, timeout: float = 120.0,
         temperature: float = 0.7, num_predict: int = 1024) -> str | None:
    """Single chat completion for a role.  Returns raw content text or None."""
    model = resolve_model(role)
    if model is None:
        return None
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {"temperature": temperature, "num_predict": num_predict},
    }
    if json_mode:
        payload["format"] = "json"
    try:
        out = _post("/api/chat", payload, timeout)
        return out.get("message", {}).get("content")
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# CLI: connectivity + JSON round-trip check
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Local LLM (Ollama) connectivity check")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    models = list_models()
    print(f"Ollama @ {ENDPOINT}")
    print(f"Installed models ({len(models)}):")
    for m in models:
        print(f"  - {m}")
    print("\nRole routing:")
    for role in ROLE_MODELS:
        print(f"  {role:8s} -> {resolve_model(role)}")

    if args.check and models:
        print("\nJSON round-trip via 'propose' role...")
        out = chat("propose",
                   system="You output only JSON.",
                   user='Return a JSON object {"ok": true, "n": 3}.',
                   json_mode=True, timeout=60, num_predict=64)
        print("  raw:", out)

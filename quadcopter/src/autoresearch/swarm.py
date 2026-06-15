"""
swarm.py
========
Fan a batch of LLM calls out to the local Ollama server concurrently, with a
hard concurrency cap (a 4 GB GPU can only do so much at once) and robust JSON
parsing.  Threads, not asyncio: urllib is blocking and HTTP fan-out over a
ThreadPoolExecutor is simpler and reliable on Windows.

Every result is best-effort.  A failed/garbage call yields None so the caller
can drop it — the deterministic core never depends on the swarm succeeding.
"""

from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, List, Optional

from . import local_llm

# Logical concurrency; keep modest so Ollama (OLLAMA_NUM_PARALLEL) doesn't thrash VRAM.
DEFAULT_CONCURRENCY = int(os.environ.get("SWARM_CONCURRENCY", "3"))


@dataclass
class SwarmTask:
    role:   str
    system: str
    user:   str
    json_mode: bool = True
    timeout: float = 120.0
    temperature: float = 0.7
    num_predict: int = 1024


def extract_json(text: Optional[str]):
    """Pull the first JSON object/array out of an LLM response, tolerating
    code fences and chatter.  Returns the parsed value or None."""
    if not text:
        return None
    text = text.strip()
    # Strip ``` fences if present
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    # Find the first balanced {...} or [...]
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = text.find(open_ch)
        if start < 0:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == open_ch:
                depth += 1
            elif text[i] == close_ch:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except Exception:
                        break
    return None


def run_one(task: SwarmTask):
    raw = local_llm.chat(task.role, task.system, task.user,
                         json_mode=task.json_mode, timeout=task.timeout,
                         temperature=task.temperature, num_predict=task.num_predict)
    if not task.json_mode:
        return raw
    return extract_json(raw)


def run_batch(tasks: List[SwarmTask],
              concurrency: int = DEFAULT_CONCURRENCY) -> List[Optional[object]]:
    """Run tasks concurrently; results align with input order.  Parsed (or None)."""
    results: List[Optional[object]] = [None] * len(tasks)
    if not tasks:
        return results
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as ex:
        futs = {ex.submit(run_one, t): i for i, t in enumerate(tasks)}
        for fut in as_completed(futs):
            i = futs[fut]
            try:
                results[i] = fut.result()
            except Exception:
                results[i] = None
    return results

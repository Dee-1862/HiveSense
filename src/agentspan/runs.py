"""
Durable registry of HiveDoctor treatment runs (the dashboard's view into Agentspan).

Agentspan persists the actual workflow state server-side (that is the whole point -
the run survives our process dying). This file keeps the lightweight, JSON-serialisable
*projection* the dashboard polls: each run's status, the plan, the pending approval, and
the step log. The live AgentHandle (not serialisable) is held in memory and re-attached
to its run by workflow_id; if our process restarts, the run metadata reloads from disk
and the handle is re-bound lazily by reconnecting to the Agentspan server.
"""

from __future__ import annotations

import os
import json
import threading
from typing import Dict, List, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PATH = os.path.join(_ROOT, "data", "treatments.json")
_LOCK = threading.RLock()

# in-memory map workflow_id -> live AgentHandle (rebuilt on demand, never persisted)
_HANDLES: Dict[str, object] = {}


def _load() -> Dict[str, dict]:
    try:
        with open(_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(runs: Dict[str, dict]) -> None:
    os.makedirs(os.path.dirname(_PATH), exist_ok=True)
    tmp = _PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(runs, f, indent=2)
    os.replace(tmp, _PATH)


def create_run(workflow_id: str, hive_id: str, now: str) -> dict:
    with _LOCK:
        runs = _load()
        run = {
            "id": workflow_id, "hive_id": hive_id, "status": "running",
            "created": now, "updated": now,
            "steps": [], "findings": {}, "plan": None,
            "pending": None, "decision": None, "result": None,
        }
        runs[workflow_id] = run
        _save(runs)
        return run


def update_run(workflow_id: str, now: str, **fields) -> Optional[dict]:
    with _LOCK:
        runs = _load()
        run = runs.get(workflow_id)
        if run is None:
            return None
        run.update(fields)
        run["updated"] = now
        runs[workflow_id] = run
        _save(runs)
        return run


def add_step(workflow_id: str, now: str, label: str, detail) -> Optional[dict]:
    with _LOCK:
        runs = _load()
        run = runs.get(workflow_id)
        if run is None:
            return None
        run.setdefault("steps", []).append({"label": label, "detail": detail, "ts": now})
        run["updated"] = now
        runs[workflow_id] = run
        _save(runs)
        return run


def get_run(workflow_id: str) -> Optional[dict]:
    with _LOCK:
        return _load().get(workflow_id)


def list_runs() -> List[dict]:
    with _LOCK:
        return sorted(_load().values(), key=lambda r: r.get("created", ""), reverse=True)


def set_handle(workflow_id: str, handle: object) -> None:
    with _LOCK:
        _HANDLES[workflow_id] = handle


def get_handle(workflow_id: str) -> Optional[object]:
    with _LOCK:
        return _HANDLES.get(workflow_id)

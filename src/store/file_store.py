"""
File backend: the original data/verdicts.json behaviour, verbatim.

This is the always-available default. It rewrites the whole JSON file on every
append (the historical behaviour) - which is exactly the cost the Redis backend
improves on, and what bench/redis_bench.py measures.
"""

import os
import json

from .base import Store

# src/store/file_store.py -> repo root is three levels up
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VERDICTS_FILE = os.path.join(ROOT, "data", "verdicts.json")


class FileStore(Store):
    def __init__(self, path: str = VERDICTS_FILE):
        self.path = path

    def load_verdicts(self) -> dict:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_verdicts(self, verdicts: dict) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(verdicts, f, indent=2)

    def append_verdict(self, verdict: dict, max_points: int = 96) -> None:
        hive = verdict.get("hive_id")
        if not hive:
            return
        verdicts = self.load_verdicts()
        hist = verdicts.get(hive, [])
        if not isinstance(hist, list):
            hist = [hist]
        hist.append(verdict)
        verdicts[hive] = hist[-max_points:]
        self.save_verdicts(verdicts)

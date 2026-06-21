"""
Store factory: pick the backend from the USE_REDIS env var, degrade gracefully.

    USE_REDIS unset/0  -> FileStore (data/verdicts.json, the default demo path)
    USE_REDIS=1        -> RedisStore, BUT if Redis can't be reached we log a
                          warning and fall back to FileStore so the demo never breaks.

The chosen backend is cached as a process singleton. Everything else in the app
goes through hive_state.py, which delegates here - so flipping USE_REDIS is the
only switch needed.
"""

import os
import logging

from .base import Store
from .file_store import FileStore

log = logging.getLogger("hivesense.store")

_store: Store | None = None


def _truthy(v) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def get_store() -> Store:
    global _store
    if _store is not None:
        return _store
    if _truthy(os.getenv("USE_REDIS", "")):
        try:
            from .redis_store import RedisStore
            _store = RedisStore()
            log.warning("HiveSense store: Redis backend active (%s)", _store.url)
        except Exception as e:  # connection refused, module missing, etc.
            log.warning("USE_REDIS set but Redis unavailable (%s) - "
                        "falling back to the file store.", e)
            _store = FileStore()
    else:
        _store = FileStore()
    return _store


def reset_store() -> None:
    """Drop the cached backend (tests / benchmarks that re-init)."""
    global _store
    _store = None

"""
Storage backend contract for the apiary state.

The fleet, coordinator, dashboard API and ASI:One agent all talk to a `Store`
instead of touching files directly. Two backends implement it:

  - FileStore  : the original data/verdicts.json behaviour (always available).
  - RedisStore : Redis Stack (RedisJSON + TimeSeries + RediSearch vectors + Pub/Sub).

The first three methods are the legacy contract every caller already relies on
(via hive_state.py). The remaining methods are the new Redis-only capabilities;
they default to safe no-ops here so a caller can invoke them unconditionally and
get sensible behaviour on the file store (no vector search, no time series, etc.).
"""

from abc import ABC, abstractmethod


class Store(ABC):
    # --- legacy contract (file + redis) ------------------------------------ #
    @abstractmethod
    def load_verdicts(self) -> dict:
        """Return {hive_id: [verdict_dict, ...]} (or {} if unavailable)."""

    @abstractmethod
    def save_verdicts(self, verdicts: dict) -> None:
        """Replace the whole store."""

    @abstractmethod
    def append_verdict(self, verdict: dict, max_points: int = 96) -> None:
        """Append one verdict to its hive's rolling history (trim to max_points)."""

    def latest(self, hive_id: str):
        """Most recent verdict for a hive, or None."""
        hist = self.load_verdicts().get(hive_id) or []
        return hist[-1] if isinstance(hist, list) and hist else None

    # --- new capabilities (redis-only; no-ops on the file store) ----------- #
    def record_reading(self, hive_id: str, verdict: dict, embedding=None,
                        image_blob: bytes | None = None) -> str | None:
        """Persist a full multimodal reading (verdict doc + time series + searchable
        embedding + packed media blob). Returns the reading key, or None if unsupported."""
        return None

    def search_similar(self, embedding, k: int = 5, hive: str | None = None) -> list:
        """k-NN over stored reading embeddings. Returns [{key, hive, score, ...}]."""
        return []

    def ts_range(self, hive_id: str, field: str, frm: int = "-", to: int = "+") -> list:
        """[(ts_ms, value), ...] for one hive metric time series."""
        return []

    def publish_update(self, verdict: dict) -> None:
        """Publish a live update to subscribers (dashboard SSE)."""
        return None

    def available(self) -> bool:
        """True if the richer (Redis) features are live."""
        return False

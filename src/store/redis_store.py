"""
Redis Stack backend for the apiary state.

One backend, four Redis Stack capabilities, each mapped to a real need the file
store cannot meet:

  RedisJSON       hs:hive:{id}        latest verdict document
                  hs:hive:{id}:hist   rolling history (JSON.ARRAPPEND + ARRTRIM)
                  hs:hives            SET of known hive ids (avoids SCAN on read)
  RedisTimeSeries hs:ts:{id}:{metric} acoustic_stress / traffic / mite_rate,
                  RETENTION 24h  -> the rolling window is enforced by Redis, not by
                  rewriting a file. TS.MRANGE reads every hive in one call.
  RediSearch      hs:reading:{id}:{ts} HASH {vec, hive, ts, ...metadata, blob},
                  HNSW vector index hs:idx -> filtered k-NN ("find past states like
                  this one") powering retrieval-augmented reasoning.
  Pub/Sub         hs:events           live push to the dashboard (SSE bridge).

Honest framing: none of this makes Redis magically faster than a file - the wins are
(1) appending one document vs rewriting the whole JSON store each time, (2) built-in
retention, (3) vector k-NN the file store simply cannot do, and (4) one key + one
round-trip per multimodal reading via the stego blob. See bench/redis_bench.py.

Construction pings Redis; if it is unreachable the constructor raises and the factory
(src/store/__init__.py) falls back to the file store.
"""

import os
import time
import json
import logging
import datetime

import redis
from redis.commands.search.field import TagField, NumericField, VectorField
from redis.commands.search.index_definition import IndexDefinition, IndexType
from redis.commands.search.query import Query

from .base import Store

log = logging.getLogger("hivesense.store.redis")

# Must match src/embedding.py: acoustic(22) + vision(64) fused, L2-normalised.
EMB_DIM = 86

PREFIX = "hs:"
HIVES_SET = "hs:hives"
INDEX = "hs:idx"
READING_PREFIX = "hs:reading:"
EVENTS_CHANNEL = "hs:events"
TS_RETENTION_MS = 24 * 60 * 60 * 1000  # 24h rolling window, enforced by Redis
# verdict field -> time series metric suffix
TS_METRICS = {"acoustic_stress": "acoustic_stress",
              "traffic": "traffic",
              "vision_mite_rate": "mite_rate"}


def _to_f32_bytes(embedding) -> bytes:
    """Coerce a vector (np.ndarray / list / bytes) to little-endian float32 bytes."""
    if isinstance(embedding, (bytes, bytearray)):
        return bytes(embedding)
    import numpy as np
    return np.asarray(embedding, dtype="float32").tobytes()


class RedisStore(Store):
    def __init__(self, url: str | None = None):
        self.url = url or os.getenv("REDIS_URL", "redis://localhost:6379")
        # decode_responses=False: we read/write binary vector + blob fields.
        # socket timeouts are the safety net for the agent loop: a slow/dead Redis fails
        # fast (caught + logged) instead of blocking a hive agent's async cycle.
        timeout = float(os.getenv("REDIS_TIMEOUT", "2.0"))
        self.r = redis.Redis.from_url(self.url, decode_responses=False,
                                      socket_timeout=timeout, socket_connect_timeout=timeout)
        self.r.ping()  # raises if Redis is unreachable -> factory falls back
        # Require Redis Stack: a plain redis would accept ping then fail every JSON/search
        # op and silently drop writes. Better to fall back to the file store.
        mods = self._modules()
        if not ({"rejson", "search"} <= mods):
            raise RuntimeError(
                f"Redis at {self.url} is missing the Stack modules ReJSON/search "
                f"(found {sorted(mods) or 'none'}). Run redis/redis-stack.")
        self._ts_created: set[str] = set()
        self._seq = 0
        self._ensure_index()

    def _modules(self) -> set:
        out = set()
        try:
            for m in self.r.module_list():
                name = m.get(b"name") or m.get("name")
                if isinstance(name, (bytes, bytearray)):
                    name = name.decode()
                if name:
                    out.add(name.lower())
        except Exception:
            pass
        return out

    # ------------------------------------------------------------------ #
    # legacy contract: live verdict state (RedisJSON + history)
    # ------------------------------------------------------------------ #
    def load_verdicts(self) -> dict:
        out = {}
        try:
            ids = [m.decode() for m in self.r.smembers(HIVES_SET)]
            for hid in ids:
                hist = self.r.json().get(f"hs:hive:{hid}:hist")
                if hist:
                    out[hid] = hist
        except Exception:
            log.exception("redis load_verdicts failed")
        return out

    def save_verdicts(self, verdicts: dict) -> None:
        """Replace the whole store (used by seeding / benchmarks)."""
        try:
            pipe = self.r.pipeline()
            # clear existing hive docs so this is a true replace
            for hid in [m.decode() for m in self.r.smembers(HIVES_SET)]:
                pipe.delete(f"hs:hive:{hid}", f"hs:hive:{hid}:hist")
            pipe.delete(HIVES_SET)
            pipe.execute()
            for hid, hist in verdicts.items():
                hist = hist if isinstance(hist, list) else [hist]
                self.r.json().set(f"hs:hive:{hid}:hist", "$", hist)
                if hist:
                    self.r.json().set(f"hs:hive:{hid}", "$", hist[-1])
                self.r.sadd(HIVES_SET, hid)
                for v in hist:
                    self._add_timeseries(hid, v)
        except Exception:
            log.exception("redis save_verdicts failed")

    def append_verdict(self, verdict: dict, max_points: int = 96) -> None:
        hive = verdict.get("hive_id")
        if not hive:
            return
        hist_key = f"hs:hive:{hive}:hist"
        try:
            if not self.r.exists(hist_key):
                self.r.json().set(hist_key, "$", [])
            self.r.json().arrappend(hist_key, "$", verdict)
            # JSON.ARRTRIM keeps the last max_points - the rolling window, no full rewrite
            self.r.json().arrtrim(hist_key, "$", -max_points, -1)
            self.r.json().set(f"hs:hive:{hive}", "$", verdict)  # latest doc
            self.r.sadd(HIVES_SET, hive)
        except Exception:
            log.exception("redis append_verdict failed for %s", hive)
            return
        # best-effort enrichments: never break the state write
        self._add_timeseries(hive, verdict)
        self.publish_update(verdict)

    # ------------------------------------------------------------------ #
    # RedisTimeSeries
    # ------------------------------------------------------------------ #
    def _ensure_ts(self, key: str, hive: str, metric: str) -> None:
        if key in self._ts_created:
            return
        try:
            self.r.ts().create(key, retention_msecs=TS_RETENTION_MS,
                               duplicate_policy="last",
                               labels={"hive": hive, "metric": metric})
        except redis.ResponseError:
            pass  # already exists
        self._ts_created.add(key)

    def _add_timeseries(self, hive: str, verdict: dict) -> None:
        ts_ms = self._ts_ms(verdict)
        for field, metric in TS_METRICS.items():
            if field not in verdict:
                continue
            key = f"hs:ts:{hive}:{metric}"
            try:
                self._ensure_ts(key, hive, metric)
                self.r.ts().add(key, ts_ms, float(verdict.get(field) or 0.0))
            except Exception:
                log.debug("ts add skipped for %s", key, exc_info=True)

    def ts_range(self, hive_id: str, field: str, frm="-", to="+") -> list:
        metric = TS_METRICS.get(field, field)
        try:
            return self.r.ts().range(f"hs:ts:{hive_id}:{metric}", frm, to)
        except Exception:
            return []

    # ------------------------------------------------------------------ #
    # RediSearch vector index + multimodal readings
    # ------------------------------------------------------------------ #
    def _ensure_index(self) -> None:
        try:
            self.r.ft(INDEX).info()
            return  # already exists
        except redis.ResponseError:
            pass
        schema = (
            TagField("hive"),
            NumericField("ts"),
            TagField("varroa_status"),
            TagField("needs_human"),
            TagField("vision_ran"),
            NumericField("acoustic_stress"),
            VectorField("vec", "HNSW",
                        {"TYPE": "FLOAT32", "DIM": EMB_DIM, "DISTANCE_METRIC": "COSINE"}),
        )
        defn = IndexDefinition(prefix=[READING_PREFIX], index_type=IndexType.HASH)
        try:
            self.r.ft(INDEX).create_index(schema, definition=defn)
            log.warning("created RediSearch index %s (DIM=%d)", INDEX, EMB_DIM)
        except redis.ResponseError as e:
            if "Index already exists" not in str(e):
                raise

    def record_reading(self, hive_id: str, verdict: dict, embedding=None,
                        image_blob: bytes | None = None) -> str | None:
        """Store one searchable multimodal reading: the fused embedding (indexed for
        k-NN) plus metadata and the stego blob (one key carries both modalities)."""
        if embedding is None:
            return None
        ts_ms = self._ts_ms(verdict)
        self._seq = (self._seq + 1) % 1_000_000
        key = f"{READING_PREFIX}{hive_id}:{ts_ms}:{self._seq}"
        mapping = {
            "vec": _to_f32_bytes(embedding),
            "hive": hive_id,
            "ts": ts_ms,
            "varroa_status": verdict.get("varroa_status", "?"),
            "needs_human": str(bool(verdict.get("needs_human", False))).lower(),
            "vision_ran": str(bool(verdict.get("vision_ran", False))).lower(),
            "acoustic_stress": float(verdict.get("acoustic_stress", 0.0) or 0.0),
            "vision_source": verdict.get("vision_source", "") or "",
        }
        if image_blob:
            mapping["blob"] = image_blob
        try:
            self.r.hset(key, mapping=mapping)
            return key
        except Exception:
            log.exception("redis record_reading failed for %s", hive_id)
            return None

    def search_similar(self, embedding, k: int = 5, hive: str | None = None) -> list:
        vec = _to_f32_bytes(embedding)
        filt = f"@hive:{{{hive}}}" if hive else "*"
        try:
            q = (
                Query(f"({filt})=>[KNN {k} @vec $vec AS score]")
                .sort_by("score")
                .return_fields("hive", "ts", "varroa_status", "needs_human", "score")
                .paging(0, k)
                .dialect(2)
            )
            res = self.r.ft(INDEX).search(q, query_params={"vec": vec})
        except Exception:
            log.exception("redis search_similar failed")
            return []
        out = []
        for d in res.docs:
            out.append({
                "key": d.id.decode() if isinstance(d.id, bytes) else d.id,
                "hive": _dec(getattr(d, "hive", "")),
                "ts": int(_dec(getattr(d, "ts", 0)) or 0),
                "varroa_status": _dec(getattr(d, "varroa_status", "")),
                "needs_human": _dec(getattr(d, "needs_human", "")),
                "score": float(_dec(getattr(d, "score", 1.0)) or 1.0),  # cosine distance
            })
        return out

    def get_blob(self, reading_key: str) -> bytes | None:
        """Fetch the packed multimodal blob for a reading (single key, single round-trip)."""
        try:
            return self.r.hget(reading_key, "blob")
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    # Pub/Sub
    # ------------------------------------------------------------------ #
    def publish_update(self, verdict: dict) -> None:
        try:
            self.r.publish(EVENTS_CHANNEL, json.dumps({
                "hive_id": verdict.get("hive_id"),
                "varroa_status": verdict.get("varroa_status"),
                "needs_human": bool(verdict.get("needs_human", False)),
                "ts": verdict.get("timestamp", ""),
            }))
        except Exception:
            log.debug("redis publish failed", exc_info=True)

    def subscribe(self):
        """Yield JSON update strings from the events channel (for the dashboard SSE bridge)."""
        ps = self.r.pubsub()
        ps.subscribe(EVENTS_CHANNEL)
        for msg in ps.listen():
            if msg.get("type") == "message":
                data = msg["data"]
                yield data.decode() if isinstance(data, (bytes, bytearray)) else data

    def available(self) -> bool:
        return True

    # ------------------------------------------------------------------ #
    def _ts_ms(self, verdict: dict) -> int:
        ts = verdict.get("timestamp")
        if ts:
            try:
                return int(datetime.datetime.fromisoformat(ts).timestamp() * 1000)
            except Exception:
                pass
        return int(time.time() * 1000)


def _dec(v):
    return v.decode() if isinstance(v, (bytes, bytearray)) else v

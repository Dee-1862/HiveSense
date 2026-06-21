"""
Seed Redis with the UNIMODAL (fused-vector) memory for the existing 24h apiary data.

So that a demo has real content to pull up: every verdict in data/verdicts.json becomes a fused
86-d vector in the Redis HNSW index (plus the live JSON state + per-hive time series). After this,
`/api/similar?hive=A3` returns real neighbours, RedisInsight shows hs:reading:* / hs:idx, and
scripts/redis_show.py can visualise a hive's fused fingerprint + nearest past states.

Run:  USE_REDIS=1 python scripts/seed_redis_unimodal.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass
os.environ.setdefault("USE_REDIS", "1")

from src.store import get_store           # noqa: E402
from src.store.file_store import FileStore  # noqa: E402
from src import embedding                 # noqa: E402


def fused_embedding(verdict):
    """One fused 86-d vector for a stored verdict (same mapping /api/similar uses)."""
    sample = {
        "acoustic_stress": float(verdict.get("acoustic_stress", 0.0) or 0.0),
        "vision_mite_rate": float(verdict.get("vision_mite_rate", 0.0) or 0.0),
        "net_traffic": float(verdict.get("traffic", 0.0) or 0.0),
        "queenless_score": 1.0 if verdict.get("queenless_alert") else 0.0,
        "swarm_band_hz": 150.0 if verdict.get("swarm_alert") else 400.0,
        "swarm_rising": bool(verdict.get("swarm_alert")),
    }
    return embedding.embed_sample(sample)


def main():
    store = get_store()
    if not store.available():
        print("Redis is not live - set USE_REDIS=1 and REDIS_URL (.env). Nothing seeded.")
        return 1

    verdicts = FileStore().load_verdicts()   # the seeded 24h history (file is the source)
    if not verdicts:
        print("data/verdicts.json is empty - run seed_apiary.py first.")
        return 1

    print(f"Seeding Redis from {len(verdicts)} hives "
          f"({sum(len(h) for h in verdicts.values())} verdict points)...")

    # 1) live state: RedisJSON history/latest + RedisTimeSeries (this is the slow part on a
    #    remote Redis - one network op per point - so it prints progress and may take ~1 min)
    store.save_verdicts(verdicts)
    print("  state (RedisJSON + TimeSeries) written.")

    # 2) one fused vector per verdict -> the HNSW index (the unimodal memory)
    n = 0
    for hive, hist in verdicts.items():
        for v in (hist if isinstance(hist, list) else [hist]):
            if not isinstance(v, dict):
                continue
            emb, src = fused_embedding(v)
            vd = dict(v); vd["vision_source"] = src
            if store.record_reading(hive, vd, emb):
                n += 1
        print(f"  {hive}: vectors so far = {n}")

    print(f"\nDone. {n} fused unimodal vectors indexed in Redis (index hs:idx).")
    print("Pull it up:  USE_REDIS=1 python scripts/redis_show.py --hive A3")
    print("Or:          curl 'http://127.0.0.1:8000/api/similar?hive=A3'")
    return 0


if __name__ == "__main__":
    sys.exit(main())

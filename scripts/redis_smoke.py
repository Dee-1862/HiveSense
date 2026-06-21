"""
One-command smoke test for the Redis Stack integration.

Run it after starting Redis Stack:

    docker run -d --name redis-stack -p 6379:6379 -p 8001:8001 redis/redis-stack:latest
    USE_REDIS=1 python scripts/redis_smoke.py

It exercises every Redis capability the app uses and prints PASS/FAIL per check, so you
can confirm the live path works before running the fleet. It writes to a throwaway hive
(SMOKE) and cleans up after itself.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from dotenv import load_dotenv
    load_dotenv()  # pick up REDIS_URL / USE_REDIS from .env
except Exception:
    pass
os.environ.setdefault("USE_REDIS", "1")

from src import embedding  # noqa: E402

HIVE = "SMOKE"


def main():
    try:
        from src.store.redis_store import RedisStore
        rs = RedisStore()
    except Exception as e:
        print(f"FAIL: could not connect to Redis Stack ({e})")
        print("Start it with: docker run -d -p 6379:6379 -p 8001:8001 redis/redis-stack:latest")
        return 1

    ok = True

    def check(label, cond):
        nonlocal ok
        ok = ok and bool(cond)
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}")

    print("Redis Stack smoke test")

    # 1. RedisJSON: append + reconstruct
    for i in range(3):
        rs.append_verdict({"hive_id": HIVE, "varroa_status": "watch",
                           "acoustic_stress": 0.3 + 0.1 * i, "traffic": 10 * i,
                           "vision_mite_rate": 0.0, "needs_human": False,
                           "timestamp": f"2026-06-21T00:00:0{i}"})
    v = rs.load_verdicts().get(HIVE, [])
    check("RedisJSON append + load_verdicts roundtrip (3 points)", len(v) == 3)
    check("RedisJSON latest doc", (rs.latest(HIVE) or {}).get("traffic") == 20)

    # 2. RedisTimeSeries
    series = rs.ts_range(HIVE, "acoustic_stress")
    check("RedisTimeSeries acoustic_stress has points", len(series) >= 3)

    # 3. One fused multimodal vector per reading -> RediSearch HNSW k-NN
    sample = {"acoustic_stress": 0.8, "vision_mite_rate": 0.05, "net_traffic": 5}
    emb, src = embedding.embed_sample(sample)
    key = rs.record_reading(HIVE, {"hive_id": HIVE, "varroa_status": "alert",
                                   "acoustic_stress": 0.8, "vision_ran": True,
                                   "vision_source": src, "timestamp": "2026-06-21T00:01:00"}, emb)
    check("record_reading returned a key", bool(key))
    hits = rs.search_similar(emb, k=3)
    check("vector k-NN returns the reading", any(h["key"] == key for h in hits))
    check("filtered k-NN (@hive:SMOKE)", len(rs.search_similar(emb, k=3, hive=HIVE)) >= 1)

    # cleanup
    rr = rs.r
    rr.delete(f"hs:hive:{HIVE}", f"hs:hive:{HIVE}:hist",
              f"hs:ts:{HIVE}:acoustic_stress", f"hs:ts:{HIVE}:traffic", f"hs:ts:{HIVE}:mite_rate")
    rr.srem("hs:hives", HIVE)
    if key:
        rr.delete(key)
    print("cleanup done.")

    print("\nRESULT:", "ALL PASS - Redis path is live." if ok else "SOME CHECKS FAILED.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

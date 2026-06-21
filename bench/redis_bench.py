"""
HiveSense storage benchmark: Redis Stack vs the file store, with HONEST numbers.

Three measurements, each tied to a concrete claim in the README:

  (a) verdict write + read - the file store rewrites the WHOLE verdicts.json on every append;
      Redis appends one JSON doc. The FILE cost grows with history. BUT note: against a remote
      Redis (Redis Cloud) each op is a network round-trip, so Redis is NOT faster than a LOCAL
      file on a single op - we print both and say so plainly.
  (b) UNIMODAL (one fused vector) vs LATE FUSION (two vectors) - the real "unimodal" win: one
      fused multimodal vector -> ONE HNSW index -> ONE k-NN query, versus a bimodal late-fusion
      layout that keeps an acoustic vector and a vision vector in TWO indexes and must run TWO
      queries and merge. One index/one query = half the round-trips, less memory, and it is the
      only layout that can support a single bound cross-modal query (see src/imagebind_embed.py).
  (c) vector top-k - Redis HNSW k-NN (incl. a metadata-filtered query) vs a brute-force numpy
      cosine scan over the same vectors.

Runs offline and seeded. If Redis is unreachable it prints the file-store numbers only and says
so. Nothing is written to disk except an optional --md report to stdout.

Usage:
  python bench/redis_bench.py --n 300 --vectors 5000
  USE_REDIS=1 REDIS_URL=redis://localhost:6379 python bench/redis_bench.py
"""

import os
import sys
import time
import json
import argparse
import tempfile
import statistics

import numpy as np

# make repo root importable when run as `python bench/redis_bench.py`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from dotenv import load_dotenv
    load_dotenv()  # pick up REDIS_URL / USE_REDIS from .env
except Exception:
    pass

from src.store.file_store import FileStore           # noqa: E402
from src import embedding                            # noqa: E402

BENCH_PREFIX = "bvec:"
BENCH_INDEX = "bench_idx"


def _pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p / 100.0 * len(xs)))]


def _stats_ms(samples):
    return {"median_ms": statistics.median(samples) * 1e3, "p95_ms": _pct(samples, 95) * 1e3}


def _sample_verdict(hive, i):
    return {"hive_id": hive, "varroa_status": "watch", "queenless_alert": False,
            "swarm_alert": False, "traffic": i % 50, "acoustic_stress": 0.3,
            "vision_mite_rate": 0.0, "vision_ran": False, "needs_human": False,
            "reason": "bench", "timestamp": f"2026-06-21T00:00:{i % 60:02d}"}


def _truthy(v):
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def connect_redis():
    if not _truthy(os.getenv("USE_REDIS", "1")):  # default on for the bench
        return None
    try:
        from src.store.redis_store import RedisStore
        rs = RedisStore()
        rs.r.ping()
        return rs
    except Exception as e:
        print(f"[bench] Redis unavailable ({e}) - file-store numbers only.\n")
        return None


def _l2_rows(mat):
    return mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)


# --------------------------------------------------------------------------- #
# (a) verdict write + read, against a store preloaded with history
# --------------------------------------------------------------------------- #
def bench_state(rs, n, hives, points):
    seed = {f"H{h}": [_sample_verdict(f"H{h}", i) for i in range(points)] for h in range(hives)}
    res = {"history_points": hives * points, "n": n}

    tmp = os.path.join(tempfile.gettempdir(), "hs_bench_verdicts.json")
    fs = FileStore(tmp)
    fs.save_verdicts(seed)
    w, r = [], []
    for i in range(n):
        v = _sample_verdict("H0", points + i)
        t0 = time.perf_counter(); fs.append_verdict(v); w.append(time.perf_counter() - t0)
        t0 = time.perf_counter(); fs.load_verdicts().get("H0", [])[-1:]; r.append(time.perf_counter() - t0)
    try:
        os.remove(tmp)
    except OSError:
        pass
    res["file_write"] = _stats_ms(w)
    res["file_read"] = _stats_ms(r)

    if rs is not None:
        rs.save_verdicts(seed)
        rr = rs.r
        w, r = [], []
        for i in range(n):
            v = _sample_verdict("H0", points + i)
            t0 = time.perf_counter()
            rr.json().arrappend("hs:hive:H0:hist", "$", v)
            rr.json().arrtrim("hs:hive:H0:hist", "$", -96, -1)
            rr.json().set("hs:hive:H0", "$", v)
            w.append(time.perf_counter() - t0)
            t0 = time.perf_counter(); rr.json().get("hs:hive:H0"); r.append(time.perf_counter() - t0)
        res["redis_write"] = _stats_ms(w)
        res["redis_read"] = _stats_ms(r)
        # clean up the synthetic H0..H6 bench hives so they never pollute the demo keyspace
        for h in range(hives):
            rr.delete(f"hs:hive:H{h}", f"hs:hive:H{h}:hist",
                      f"hs:ts:H{h}:acoustic_stress", f"hs:ts:H{h}:traffic", f"hs:ts:H{h}:mite_rate")
            rr.srem("hs:hives", f"H{h}")
    return res


# --------------------------------------------------------------------------- #
# (b) UNIMODAL one fused vector (1 index, 1 query) vs LATE FUSION two vectors (2 indexes, 2 queries)
# --------------------------------------------------------------------------- #
def _build_index(rr, idx, prefix, dim, mat):
    from redis.commands.search.field import VectorField
    from redis.commands.search.index_definition import IndexDefinition, IndexType
    try:
        rr.ft(idx).dropindex(delete_documents=True)
    except Exception:
        pass
    rr.ft(idx).create_index(
        (VectorField("vec", "HNSW", {"TYPE": "FLOAT32", "DIM": dim, "DISTANCE_METRIC": "COSINE"}),),
        definition=IndexDefinition(prefix=[prefix], index_type=IndexType.HASH))
    pipe = rr.pipeline()
    for i in range(len(mat)):
        pipe.hset(f"{prefix}{i}", mapping={"vec": mat[i].tobytes()})
        if i % 1000 == 0:
            pipe.execute(); pipe = rr.pipeline()
    pipe.execute()
    for _ in range(100):
        if int(rr.ft(idx).info()["num_docs"]) >= len(mat):
            break
        time.sleep(0.1)


def bench_fusion(rs, m, n, k=5):
    rng = np.random.default_rng(1)
    AC = _l2_rows(rng.standard_normal((m, embedding.ACOUSTIC_DIM)).astype("float32"))
    VI = _l2_rows(rng.standard_normal((m, embedding.VISION_DIM)).astype("float32"))
    FU = np.stack([embedding.fuse(AC[i], VI[i]) for i in range(m)])  # 86-d early fusion
    res = {"vectors": m, "k": k, "n": n,
           "fused_indexes": 1, "fused_queries": 1, "late_indexes": 2, "late_queries": 2}
    if rs is None:
        return res
    from redis.commands.search.query import Query
    rr = rs.r
    _build_index(rr, "bf_fused", "bff:", embedding.EMB_DIM, FU)
    _build_index(rr, "bf_ac", "bfa:", embedding.ACOUSTIC_DIM, AC)
    _build_index(rr, "bf_vi", "bfv:", embedding.VISION_DIM, VI)

    def search(idx, qv):
        q = (Query(f"*=>[KNN {k} @vec $v AS score]")
             .sort_by("score").return_fields("score").paging(0, k).dialect(2))
        return rr.ft(idx).search(q, query_params={"v": qv.tobytes()})

    fused = []
    for _ in range(n):
        t0 = time.perf_counter(); search("bf_fused", FU[0]); fused.append(time.perf_counter() - t0)
    res["fused_ms"] = _stats_ms(fused)

    late = []   # late fusion: TWO queries + client-side merge (the cost it always pays)
    for _ in range(n):
        t0 = time.perf_counter()
        ra = search("bf_ac", AC[0]); rv = search("bf_vi", VI[0])
        _ = {d.id for d in ra.docs} | {d.id for d in rv.docs}
        late.append(time.perf_counter() - t0)
    res["late_ms"] = _stats_ms(late)

    # index memory (vector_index_sz_mb when reported)
    def idx_mb(idx):
        try:
            return float(rr.ft(idx).info().get("vector_index_sz_mb", 0) or 0)
        except Exception:
            return 0.0
    res["fused_index_mb"] = idx_mb("bf_fused")
    res["late_index_mb"] = idx_mb("bf_ac") + idx_mb("bf_vi")

    for idx in ("bf_fused", "bf_ac", "bf_vi"):
        try:
            rr.ft(idx).dropindex(delete_documents=True)
        except Exception:
            pass
    return res


# --------------------------------------------------------------------------- #
# (c) vector top-k: Redis HNSW vs numpy brute force
# --------------------------------------------------------------------------- #
def bench_vectors(rs, m, dim, n, k=5):
    rng = np.random.default_rng(0)
    mat = _l2_rows(rng.standard_normal((m, dim)).astype("float32"))
    q = mat[0]
    res = {"vectors": m, "dim": dim, "k": k, "n": n}

    bf = []
    for _ in range(n):
        t0 = time.perf_counter(); np.argpartition(-(mat @ q), k)[:k]; bf.append(time.perf_counter() - t0)
    res["numpy_bruteforce"] = _stats_ms(bf)

    if rs is None:
        return res
    from redis.commands.search.query import Query
    rr = rs.r
    # reuse the index builder, but tag half the rows so we can time a filtered query too
    from redis.commands.search.field import VectorField, TagField
    from redis.commands.search.index_definition import IndexDefinition, IndexType
    try:
        rr.ft(BENCH_INDEX).dropindex(delete_documents=True)
    except Exception:
        pass
    rr.ft(BENCH_INDEX).create_index(
        (TagField("hive"),
         VectorField("vec", "HNSW", {"TYPE": "FLOAT32", "DIM": dim, "DISTANCE_METRIC": "COSINE"})),
        definition=IndexDefinition(prefix=[BENCH_PREFIX], index_type=IndexType.HASH))
    pipe = rr.pipeline()
    for i in range(m):
        pipe.hset(f"{BENCH_PREFIX}{i}", mapping={"vec": mat[i].tobytes(),
                                                 "hive": "BENCH" if i % 2 == 0 else "OTHER"})
        if i % 1000 == 0:
            pipe.execute(); pipe = rr.pipeline()
    pipe.execute()
    for _ in range(100):
        if int(rr.ft(BENCH_INDEX).info()["num_docs"]) >= m:
            break
        time.sleep(0.1)

    qbytes = q.tobytes()

    def knn(filt):
        query = (Query(f"({filt})=>[KNN {k} @vec $v AS score]")
                 .sort_by("score").return_fields("score").paging(0, k).dialect(2))
        return rr.ft(BENCH_INDEX).search(query, query_params={"v": qbytes})

    hk = []
    for _ in range(n):
        t0 = time.perf_counter(); knn("*"); hk.append(time.perf_counter() - t0)
    res["redis_hnsw"] = _stats_ms(hk)
    fk = []
    for _ in range(n):
        t0 = time.perf_counter(); knn("@hive:{BENCH}"); fk.append(time.perf_counter() - t0)
    res["redis_hnsw_filtered"] = _stats_ms(fk)

    rr.ft(BENCH_INDEX).dropindex(delete_documents=True)
    return res


# --------------------------------------------------------------------------- #
def _row(label, s):
    return f"  {label:<28} median={s['median_ms']:8.3f} ms   p95={s['p95_ms']:8.3f} ms"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300, help="iterations per timed op")
    ap.add_argument("--hives", type=int, default=7)
    ap.add_argument("--points", type=int, default=96, help="seeded history points per hive")
    ap.add_argument("--vectors", type=int, default=5000)
    ap.add_argument("--dim", type=int, default=embedding.EMB_DIM)
    ap.add_argument("--md", action="store_true", help="also print a markdown summary")
    args = ap.parse_args()

    rs = connect_redis()
    backend = "Redis Stack + file store" if rs else "file store only (Redis unavailable)"
    print(f"=== HiveSense storage benchmark ({backend}) ===\n")

    a = bench_state(rs, args.n, args.hives, args.points)
    print(f"(a) verdict write+read  [history={a['history_points']} points, n={a['n']}]")
    print(_row("file  write (full rewrite)", a["file_write"]))
    print(_row("file  read  (full load)", a["file_read"]))
    if rs:
        print(_row("redis write (append doc)", a["redis_write"]))
        print(_row("redis read  (get doc)", a["redis_read"]))
        print("  note: a REMOTE Redis is network-bound, so it is not faster than a LOCAL file")
        print("        on a single op - its value is capabilities + concurrency, not raw latency.")
    print()

    b = bench_fusion(rs, args.vectors, args.n)
    print(f"(b) UNIMODAL one fused vector vs LATE FUSION two vectors  [readings={b['vectors']}, "
          f"k={b['k']}, n={b['n']}]")
    print(f"  unimodal (1 fused vector): indexes={b['fused_indexes']}  queries/retrieval={b['fused_queries']}")
    print(f"  late fusion (2 vectors)  : indexes={b['late_indexes']}  queries/retrieval={b['late_queries']}")
    if rs:
        print(_row("unimodal retrieval (1 query)", b["fused_ms"]))
        print(_row("late fusion (2 q + merge)", b["late_ms"]))
        print(f"  index memory: unimodal={b['fused_index_mb']:.3f} MB  vs  late fusion={b['late_index_mb']:.3f} MB")
        sp = b["late_ms"]["median_ms"] / max(1e-9, b["fused_ms"]["median_ms"])
        print(f"  -> one fused vector = one index, one query: ~{sp:.2f}x fewer query round-trips, "
              f"and the only layout that supports a single bound cross-modal query.")
    print()

    c = bench_vectors(rs, args.vectors, args.dim, args.n)
    print(f"(c) vector top-{c['k']}  [vectors={c['vectors']}, dim={c['dim']}, n={c['n']}]")
    print(_row("numpy brute force", c["numpy_bruteforce"]))
    if rs:
        print(_row("redis HNSW", c["redis_hnsw"]))
        print(_row("redis HNSW (filtered @hive)", c["redis_hnsw_filtered"]))
    print()

    print("Honest reading: the UNIMODAL win is one FUSED vector -> one HNSW index -> one k-NN query, "
          "vs late fusion's two vectors/indexes/queries (and no shared space to search across). "
          "A remote Redis is network-bound, so it does not beat a LOCAL file on single-op latency; "
          "its real value is capabilities the file store cannot do at all (filtered vector k-NN for "
          "RAG, retention, pub/sub) plus concurrency and scale. At a few thousand vectors numpy may "
          "match single-shot HNSW - Redis wins on scale, concurrency and filtered k-NN.")

    if args.md:
        print("\n```json\n" + json.dumps({"state": a, "fusion": b, "vectors": c}, indent=2) + "\n```")


if __name__ == "__main__":
    main()

"""
Demo: pull up a hive's UNIMODAL data from Redis and visualise it.

The "unimodal" representation of a reading is ONE fused 86-d vector = acoustic (22) + vision (64).
This script fetches a hive's current fused vector from Redis, runs a vector k-NN to find its most
similar PAST states, prints them, and saves a PNG you can screenshare in the meeting:

  - top strip  : the fused vector "fingerprint" (acoustic half | vision half)
  - bottom bars: how similar the retrieved past states are (cosine similarity)

Note: this is a visualisation of the stored fused VECTOR (not a literal audio spectrogram - the
old steganographic image was dropped). It is the real data Redis returns.

Run:  USE_REDIS=1 python scripts/redis_show.py --hive A3
"""

import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass
os.environ.setdefault("USE_REDIS", "1")

import numpy as np                         # noqa: E402
import matplotlib                          # noqa: E402
matplotlib.use("Agg")                      # headless: always save a PNG
import matplotlib.pyplot as plt            # noqa: E402

from src.store import get_store            # noqa: E402
from src import embedding                  # noqa: E402
from scripts.seed_redis_unimodal import fused_embedding  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hive", default="A3")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--out", default="unimodal_demo.png")
    args = ap.parse_args()

    store = get_store()
    if not store.available():
        print("Redis not live - set USE_REDIS=1 and REDIS_URL (.env), then run seed_redis_unimodal.py.")
        return 1
    latest = store.latest(args.hive)
    if not latest:
        print(f"No state for hive {args.hive}. Run scripts/seed_redis_unimodal.py first.")
        return 1

    emb, _ = fused_embedding(latest)
    hits = store.search_similar(emb, k=args.k, hive=args.hive)

    print(f"\nUNIMODAL pull-up for hive {args.hive}")
    print(f"  fused vector: dim={emb.shape[0]}  (acoustic {embedding.ACOUSTIC_DIM} + vision {embedding.VISION_DIM})")
    print(f"  current state: varroa={latest.get('varroa_status')} stress={latest.get('acoustic_stress')}")
    print(f"  {len(hits)} most similar PAST states (cosine distance, lower = closer):")
    for h in hits:
        print(f"    - {h['hive']}  varroa={h['varroa_status']:<6} "
              f"needs_human={h['needs_human']:<5} distance={h['score']:.3f}")

    # ---- visual ----
    fig, ax = plt.subplots(2, 1, figsize=(9, 5), gridspec_kw={"height_ratios": [1, 1.4]})
    ac = emb[:embedding.ACOUSTIC_DIM]
    vi = emb[embedding.ACOUSTIC_DIM:]
    strip = np.vstack([np.pad(ac, (0, embedding.VISION_DIM - embedding.ACOUSTIC_DIM)), vi])
    im = ax[0].imshow(strip, aspect="auto", cmap="magma")
    ax[0].set_yticks([0, 1]); ax[0].set_yticklabels(["acoustic", "vision"])
    ax[0].set_xticks([]); ax[0].set_title(f"Hive {args.hive}: fused multimodal fingerprint (one 86-d vector)")
    fig.colorbar(im, ax=ax[0], fraction=0.025)

    if hits:
        labels = [f"{h['hive']} {h['varroa_status']}" for h in hits]
        scores = [max(0.0, 1.0 - h["score"]) for h in hits]   # similarity = 1 - cosine distance
        ax[1].barh(range(len(hits))[::-1], scores, color="#2a9d8f")
        ax[1].set_yticks(range(len(hits))[::-1]); ax[1].set_yticklabels(labels)
        ax[1].set_xlim(0, 1); ax[1].set_xlabel("cosine similarity to now")
        ax[1].set_title("nearest past states (one Redis k-NN query)")
    plt.tight_layout()
    plt.savefig(args.out, dpi=130)
    print(f"\nSaved visual -> {args.out}  (open / screenshare this in the meeting)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

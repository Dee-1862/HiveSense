"""
To-bee ("To bee or not to bee", NU-Hive + OSBH) loader.

Builds two supervised feature tables and caches them to CSV so notebooks stay fast:

  - gate_features.csv  : MFCC+SSD per labelled interval + bee/noBee label + hive id
  - queen_features.csv : MFCC+SSD aggregated over bee intervals per file + queenless
                         label + hive id

Labels:
  * Gate     : the `.lab` files mark intervals as `bee` / `nobee` (input validity).
  * Queenless: encoded in the filename. queenless = {NO_QueenBee, Missing Queen};
               queenright = {QueenBee, Active}. `Swarm` files are excluded from the
               queenless task (different state). NOTE: the old dataset_parsers.py used
               `"QueenBee" in name` which is TRUE for "NO_QueenBee" - a silent label
               flip. This loader matches the negative token first to avoid that bug.

Each audio file is loaded once at 16 kHz; intervals are sliced in memory.
Hive-held-out CV uses `hive_id` (the leading filename token, e.g. CF003 / Hive1).
"""

import os
import glob
import re
import numpy as np
import pandas as pd
import librosa
from scipy.stats import skew as _skew, kurtosis as _kurt

TOBEE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dataset", "to_bee_or_no_to_bee"
)
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "eda", "cache")
SR = 16000
MIN_INTERVAL_SEC = 1.0      # ignore intervals shorter than this
MAX_INTERVALS_PER_FILE = 40  # bound runtime; sample across the file if more


def _base(p):
    return os.path.splitext(os.path.basename(p))[0]


def hive_id(base):
    """Leading token identifies the colony: 'CF003 - Active ...' -> CF003,
    'Hive1_..._QueenBee_H1...' -> Hive1."""
    return re.split(r"[ _]", base.strip())[0]


def queen_label(base):
    bl = base.lower()
    if "no_queenbee" in bl or "missing queen" in bl:
        return "queenless"
    if "queenbee" in bl or "active" in bl:
        return "queenright"
    if "swarm" in bl:
        return "swarm"
    return "unknown"


def parse_lab(path):
    """Return list of (start, end, label) from a .lab file (skips the id header line)."""
    out = []
    with open(path) as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 3:
                try:
                    out.append((float(parts[0]), float(parts[1]), parts[2].lower()))
                except ValueError:
                    continue  # header line (file id)
    return out


def feats_from_signal(y, sr=SR):
    """13 MFCC means + 9 spectral-shape descriptors (the Abdollahi-style feature set)."""
    f = {}
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    for i, m in enumerate(np.mean(mfcc, axis=1)):
        f[f"mfcc_{i}"] = m
    f["centroid"] = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
    f["spread"] = float(np.mean(librosa.feature.spectral_bandwidth(y=y, sr=sr)))
    f["rolloff"] = float(np.mean(librosa.feature.spectral_rolloff(y=y, sr=sr)))
    f["flatness"] = float(np.mean(librosa.feature.spectral_flatness(y=y)))
    S, _ = librosa.magphase(librosa.stft(y))
    Sn = S / (np.sum(S, axis=0, keepdims=True) + 1e-10)
    f["entropy"] = float(np.mean(-np.sum(Sn * np.log2(Sn + 1e-10), axis=0)))
    f["crest"] = float(np.mean(np.max(S, axis=0) / (np.mean(S, axis=0) + 1e-10)))
    f["flux"] = float(np.mean(np.sqrt(np.sum(np.diff(S, axis=1) ** 2, axis=0)))) if S.shape[1] > 1 else 0.0
    f["skewness"] = float(np.mean(_skew(S, axis=0)))
    f["kurtosis"] = float(np.mean(_kurt(S, axis=0)))
    return f


def _audio_files():
    return sorted(glob.glob(os.path.join(TOBEE_DIR, "*.wav")) +
                  glob.glob(os.path.join(TOBEE_DIR, "*.mp3")))


def build_and_cache():
    """Extract gate + queen feature tables (one pass over the audio) and cache to CSV."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    gate_rows, queen_rows = [], []

    for path in _audio_files():
        base = _base(path)
        lab_path = os.path.join(TOBEE_DIR, base + ".lab")
        if not os.path.exists(lab_path):
            continue
        intervals = parse_lab(lab_path)
        if not intervals:
            continue
        try:
            y, sr = librosa.load(path, sr=SR)
        except Exception as e:
            print(f"  [skip] {base}: {e}")
            continue

        usable = [(s, e, lab) for (s, e, lab) in intervals if e - s >= MIN_INTERVAL_SEC]
        if len(usable) > MAX_INTERVALS_PER_FILE:
            idx = np.linspace(0, len(usable) - 1, MAX_INTERVALS_PER_FILE).astype(int)
            usable = [usable[i] for i in idx]

        bee_chunks = []
        for (s, e, lab) in usable:
            seg = y[int(s * sr):int(e * sr)]
            if seg.size < sr * 0.5:
                continue
            fr = feats_from_signal(seg, sr)
            fr.update({"label": 1 if lab == "bee" else 0, "hive_id": hive_id(base), "file": base})
            gate_rows.append(fr)
            if lab == "bee":
                bee_chunks.append(seg)

        q = queen_label(base)
        if q in ("queenright", "queenless") and bee_chunks:
            agg = feats_from_signal(np.concatenate(bee_chunks), sr)
            agg.update({"label": 1 if q == "queenright" else 0,  # 1 = queenright
                        "queen_state": q, "hive_id": hive_id(base), "file": base})
            queen_rows.append(agg)

    gate_df = pd.DataFrame(gate_rows)
    queen_df = pd.DataFrame(queen_rows)
    gate_df.to_csv(os.path.join(CACHE_DIR, "gate_features.csv"), index=False)
    queen_df.to_csv(os.path.join(CACHE_DIR, "queen_features.csv"), index=False)
    return gate_df, queen_df


def feature_columns(df):
    meta = {"label", "hive_id", "file", "queen_state"}
    return [c for c in df.columns if c not in meta]


if __name__ == "__main__":
    g, q = build_and_cache()
    print(f"[gate]  rows={len(g)} hives={g['hive_id'].nunique()} "
          f"balance={g['label'].value_counts().to_dict()}")
    print(f"[queen] rows={len(q)} hives={q['hive_id'].nunique()} "
          f"balance={q['label'].value_counts().to_dict()}")
    print(f"cached -> {CACHE_DIR}")

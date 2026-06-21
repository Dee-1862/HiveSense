"""
Multimodal embedding: fuse the acoustic and vision signals of one hive reading into a
single vector we can store and k-NN search in Redis ("find past states like this one").

  acoustic : 22-dim (13 MFCC + 9 spectral-shape, the existing tobee_loader feature set).
             From a real waveform when available; otherwise a deterministic vector
             derived from the cycle's scalar signals (so similar regimes still cluster).
  vision   : 64-dim. Real path = pool the ViViT encoder's CLS token (768-d) through a
             fixed seeded random projection to 64-d (Johnson-Lindenstrauss; preserves
             cosine geometry, adds no trained weights). Fallback = handcrafted 64-d from
             the sample. The source is reported so we never claim a trained encoder we
             did not run.
  fuse     : concat(L2(acoustic), L2(vision)) then L2-normalise -> 86-d (cosine-ready).

Honest note: the fallback vectors are deterministic projections of the simulated feed,
not learned embeddings. They make the similarity-search demo coherent; the *real*
embedding is the ViViT-CLS path, used when an actual clip tensor is supplied.
"""

import numpy as np

ACOUSTIC_DIM = 22
VISION_DIM = 64
EMB_DIM = ACOUSTIC_DIM + VISION_DIM  # 86 - must match src/store/redis_store.py

# order of tobee_loader.feats_from_signal keys, so a real feature dict maps consistently
_ACOUSTIC_KEYS = ([f"mfcc_{i}" for i in range(13)] +
                  ["centroid", "spread", "rolloff", "flatness",
                   "entropy", "crest", "flux", "skewness", "kurtosis"])


def _l2(v, eps=1e-9):
    v = np.asarray(v, dtype=np.float32)
    return v / (np.linalg.norm(v) + eps)


def _expand(base, n):
    """Deterministically expand a short base vector to length n, keeping the base
    dominant so similar inputs stay close under cosine distance."""
    base = np.asarray(base, dtype=np.float32)
    reps = int(np.ceil(n / len(base)))
    tiled = np.tile(base, reps)[:n]
    pos = np.cos(np.arange(n, dtype=np.float32) * 0.3)  # gentle positional texture
    return (tiled * (1.0 + 0.1 * pos)).astype(np.float32)


# --------------------------------------------------------------------------- #
# acoustic
# --------------------------------------------------------------------------- #
def acoustic_features(sample, y=None, sr=16000) -> np.ndarray:
    """22-dim acoustic vector. If a waveform `y` is given, use the real MFCC/SSD
    feature set; otherwise derive a deterministic vector from the cycle's signals."""
    if y is not None:
        from src.tobee_loader import feats_from_signal  # lazy: pulls librosa
        f = feats_from_signal(y, sr)
        return np.asarray([f.get(k, 0.0) for k in _ACOUSTIC_KEYS], dtype=np.float32)
    base = [
        float(sample.get("acoustic_stress", 0.0)),
        float(sample.get("queenless_score", 0.0)),
        float(sample.get("swarm_band_hz", 0.0)) / 500.0,
        float(sample.get("net_traffic", 0.0)) / 100.0,
        float(sample.get("vision_mite_rate", 0.0)) * 10.0,
        1.0 if sample.get("swarm_rising") else 0.0,
    ]
    return _expand(base, ACOUSTIC_DIM)


# --------------------------------------------------------------------------- #
# vision
# --------------------------------------------------------------------------- #
def vision_features(sample, clip=None, model=None) -> tuple[np.ndarray, str]:
    """(64-dim vector, source). Real ViViT-CLS embedding when a clip tensor + model are
    supplied; otherwise a deterministic handcrafted vector from the sample."""
    if clip is not None and model is not None:
        try:
            from src.vit4v_infer import embed_clip
            return embed_clip(model, clip).astype(np.float32), "vivit-cls"
        except Exception:
            pass
    base = [
        float(sample.get("vision_mite_rate", 0.0)) * 10.0,
        float(sample.get("acoustic_stress", 0.0)),
        float(sample.get("net_traffic", 0.0)) / 100.0,
        float(sample.get("queenless_score", 0.0)),
    ]
    return _expand(base, VISION_DIM), "handcrafted"


# --------------------------------------------------------------------------- #
# fuse
# --------------------------------------------------------------------------- #
def fuse(acoustic, vision) -> np.ndarray:
    """concat(L2(acoustic), L2(vision)) -> L2-normalise -> 86-d float32."""
    return _l2(np.concatenate([_l2(acoustic), _l2(vision)])).astype(np.float32)


def embed_sample(sample, clip=None, model=None) -> tuple[np.ndarray, str]:
    """Convenience: full 86-d multimodal embedding + the vision source label."""
    a = acoustic_features(sample)
    v, source = vision_features(sample, clip=clip, model=model)
    return fuse(a, v), source


def to_bytes(vec) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def from_bytes(b) -> np.ndarray:
    return np.frombuffer(b, dtype=np.float32)

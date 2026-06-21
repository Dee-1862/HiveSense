"""
Per-hive realistic sensor feed (simulated) for the live fleet.

Each hive follows a fixed "regime" so the 7 reasoning agents produce a coherent,
demo-able apiary - BUT this only emits RAW SIGNALS (acoustic stress, vision mite-rate,
etc.). The hive agent still does the genuine reasoning on them (decide-vision, reconcile,
escalate). So: simulated feed, real agent decisions. No live hardware is implied.
"""

import math
import random

POSITIONS = {
    "A1": [0.0, 0.0], "A2": [3.0, 0.0], "A3": [6.0, 0.0],
    "B1": [0.0, 3.0], "B2": [3.0, 3.0], "B3": [6.0, 3.0],
    "C1": [0.0, 6.0],
}


def _diurnal(now):
    h = now.hour + now.minute / 60.0
    return max(0, int(45 * math.sin(math.pi * h / 24.0)))


def hive_sample(hive_id, now, rng=random):
    """Raw one-cycle signals for `hive_id`, consistent with its storyline."""
    s = {
        "acoustic_stress": round(rng.uniform(0.05, 0.25), 2),  # healthy baseline
        "vision_mite_rate": 0.0,
        "queenless_score": round(rng.uniform(0.0, 0.4), 2),
        "swarm_band_hz": round(rng.uniform(300, 500), 1),
        "swarm_rising": False,
        "net_traffic": _diurnal(now) + rng.randint(-8, 8),
    }
    if hive_id == "A3":                      # varroa: acoustic stress AND visible mites
        s["acoustic_stress"] = round(rng.uniform(0.70, 0.90), 2)
        s["vision_mite_rate"] = round(rng.uniform(0.045, 0.060), 3)
    elif hive_id == "B1":                    # clash: acoustic stressed, vision sees nothing
        s["acoustic_stress"] = round(rng.uniform(0.70, 0.85), 2)
        s["vision_mite_rate"] = 0.0
        s["net_traffic"] = 60 + rng.randint(-6, 6)
    elif hive_id == "B2":                    # pre-swarm: rising low-freq spike + mass outflux
        s["swarm_band_hz"] = round(rng.uniform(120, 260), 1)
        s["swarm_rising"] = True
        s["net_traffic"] = -75 + rng.randint(-6, 6)
    elif hive_id == "B3":                    # queenless roar
        s["queenless_score"] = round(rng.uniform(0.85, 0.98), 2)
    return s

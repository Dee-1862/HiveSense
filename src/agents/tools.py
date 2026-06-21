"""
Detector tools the hive brain can call.

Per the model-vs-agent split: these are plain functions (the models), NOT agents.
The reasoning hive agent calls them as tools and decides when. Each returns a small
dict {detector, score, label} so the agent treats them uniformly - an RF model, the
Vit4V vision model, or the Ferrari swarm rule all wrap the same way.

Each tool takes a `sample` dict (one cycle of raw signals from the hive's sensors).
In production `sample` comes from the live mic / tunnel camera / entrance counter; here
a stub feed stands in so the agent architecture can run end to end. Swapping a stub for
a trained model touches only the body of these functions, never the agent.
"""

VARROA_RATE_THRESHOLD = 0.03   # 3 mites / 100 bees (economic threshold)


def acoustic_mite(sample):
    """Always-on, cheap: in-hive colony stress from sound (RF on MFCC/SSD in production)."""
    s = float(sample.get("acoustic_stress", 0.0))
    label = "stressed" if s > 0.6 else "watch" if s > 0.4 else "ok"
    return {"detector": "acoustic_mite", "score": s, "label": label}


def vision_varroa(sample, clip_path=None):
    """Expensive, triggered: per-bee mite rate from the tunnel camera (Vit4V).

    If `clip_path` is given, run the real Vit4V model on that VD2 clip; otherwise use
    the stubbed per-bee rate from `sample`.
    """
    if clip_path:
        from run_demo import load_model, predict_video, _verdict  # lazy: heavy import
        probs, preds = predict_video(load_model(), clip_path)
        label, mean_p, _ = _verdict(probs, preds)
        return {"detector": "vision_varroa", "score": float(mean_p or 0.0),
                "label": "infested" if label == "INFESTED" else "clear"}
    rate = float(sample.get("vision_mite_rate", 0.0))
    return {"detector": "vision_varroa", "score": rate,
            "label": "infested" if rate >= VARROA_RATE_THRESHOLD else "clear"}


def queenless(sample):
    s = float(sample.get("queenless_score", 0.0))
    return {"detector": "queenless", "score": s,
            "label": "queenless" if s > 0.8 else "queenright"}


def swarm(sample):
    """Ferrari frequency rule: a rising fundamental in the ~90-300 Hz band before liftoff."""
    f = float(sample.get("swarm_band_hz", 0.0))
    rising = bool(sample.get("swarm_rising", False))
    fire = rising and 90.0 <= f <= 300.0
    return {"detector": "swarm", "score": 1.0 if fire else 0.0,
            "label": "swarming" if fire else "normal"}


def traffic(sample):
    """Net entrance flow this cycle: + influx / - outflux (entrance counter)."""
    n = int(sample.get("net_traffic", 0))
    label = "influx" if n >= 50 else "outflux" if n <= -50 else "balanced"
    return {"detector": "traffic", "score": float(n), "label": label}

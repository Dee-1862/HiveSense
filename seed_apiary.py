"""
Seed 24 hours of verdict history for all 7 hives into data/verdicts.json.

This is the single source of truth the whole demo reads:
  - asi1_agent.py  -> answers ASI:One chat from it (latest per hive),
  - the frontend   -> can render 24h trends + current status from it,
  - the live fleet -> the coordinator keeps appending to it as new verdicts arrive.

We don't randomise: each hive follows a coherent story grounded in what the models
actually detect, so the dashboard and the agent tell the same, believable narrative.

Run once:  python seed_apiary.py   (re-run anytime to reset the 24h window to "now").
"""

import os
import json
import math
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "data", "verdicts.json")

POINTS = 48                       # 24h at 30-min spacing
STEP = timedelta(minutes=30)

# Yard layout [x, y] in metres (A3/B1 etc. match the dashboard tile codes).
POSITIONS = {
    "A1": [0, 0], "A2": [3, 0], "A3": [6, 0],
    "B1": [0, 3], "B2": [3, 3], "B3": [6, 3],
    "C1": [0, 6],
}


def _verdict(hive, ts, varroa="clear", queenless=False, swarm=False,
             traffic=0, needs_human=False, reason=""):
    # derive the per-detector signals from the hive's state (so the dashboard can show
    # WHY: acoustic stress vs vision mite-rate, and whether the vision test ran).
    acoustic = {"clear": 0.15, "watch": 0.5, "alert": 0.8}.get(varroa, 0.15)
    if needs_human:                 # clash = acoustic stressed but vision clear
        acoustic = max(acoustic, 0.7)
    if queenless or swarm:
        acoustic = max(acoustic, 0.55)
    vision_ran = varroa in ("watch", "alert") or needs_human
    mite_rate = {"alert": 0.05, "watch": 0.02}.get(varroa, 0.0)
    if needs_human:                 # the clash: vision sees no mites
        mite_rate = 0.0
    return {
        "hive_id": hive, "varroa_status": varroa, "queenless_alert": queenless,
        "swarm_alert": swarm, "traffic": int(traffic), "needs_human": needs_human,
        "reason": reason, "position": POSITIONS[hive],
        "acoustic_stress": round(acoustic, 2), "vision_mite_rate": mite_rate,
        "vision_ran": vision_ran,
        "timestamp": ts.isoformat(),
    }


def story(hive, i, ts):
    """Return a verdict for hive at step i (0=24h ago, POINTS-1=now)."""
    frac = i / (POINTS - 1)                       # 0..1 across the day
    base_traffic = int(40 * math.sin(frac * math.pi))  # diurnal: low at night, peak midday

    if hive in ("A1", "A2", "C1"):               # steady healthy colonies
        return _verdict(hive, ts, "clear", traffic=base_traffic + (5 if hive == "A1" else -5))

    if hive == "A3":                             # varroa rising through the day -> alert
        varroa = "clear" if frac < 0.4 else "watch" if frac < 0.8 else "alert"
        reason = "Acoustic stress and visible mites agree: treat this week." if varroa == "alert" else ""
        return _verdict(hive, ts, varroa, traffic=base_traffic, reason=reason)

    if hive == "B1":                             # acoustic/vision clash in the last ~3h
        clash = frac > 0.88
        return _verdict(hive, ts, "watch" if clash else "clear",
                        traffic=base_traffic + (60 if clash else 0),
                        needs_human=clash,
                        reason="Signals disagree: acoustic=stressed but vision=clear. Please inspect and confirm." if clash else "")

    if hive == "B2":                             # pre-swarm spike late in the day
        swarm = frac > 0.82
        return _verdict(hive, ts, "clear", swarm=swarm,
                        traffic=(-75 if swarm else base_traffic),
                        reason="Swarm spike detected; heads-up to the yard." if swarm else "")

    if hive == "B3":                             # goes queenless mid-day onward
        ql = frac > 0.55
        return _verdict(hive, ts, "clear", queenless=ql, traffic=base_traffic - 10,
                        reason="Queenless roar detected." if ql else "")

    return _verdict(hive, ts, "clear", traffic=base_traffic)


def main():
    now = datetime.now()
    start = now - (POINTS - 1) * STEP
    verdicts = {}
    for hive in POSITIONS:
        hist = [story(hive, i, start + i * STEP) for i in range(POINTS)]
        verdicts[hive] = hist
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(verdicts, f, indent=2)
    span_h = (POINTS - 1) * STEP.total_seconds() / 3600
    print(f"wrote {OUT}: {len(verdicts)} hives x {POINTS} points "
          f"({span_h:.0f}h history, 30-min spacing)")
    # quick latest-status readout
    for h, hist in verdicts.items():
        v = hist[-1]
        print(f"  {h}: varroa={v['varroa_status']} queenless={v['queenless_alert']} "
              f"swarm={v['swarm_alert']} needs_human={v['needs_human']}")


if __name__ == "__main__":
    main()

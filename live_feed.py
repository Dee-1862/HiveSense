"""
Live apiary feed - extends the seeded 24h history in real time.

Every FEED_INTERVAL seconds it appends one new verdict per hive (continuing each hive's
storyline, with diurnal + noisy traffic) to data/verdicts.json, and prints the
Godfather's apiary-wide read. The api_server re-reads the file per request, so the
dashboard updates live; the ASI:One agent's answers change too.

HONEST FRAMING: the sensor FEED is simulated (no live 7-hive hardware), but the agent
logic and ML models are real. Present as "real agents/models on a simulated apiary feed."

Run (own terminal):  python live_feed.py      (Ctrl+C to stop)
                     FEED_INTERVAL=5 python live_feed.py
Needs the seed first: python seed_apiary.py
"""

import os
import time
import math
import random
from datetime import datetime

import hive_state
import godfather
from seed_apiary import _verdict, POSITIONS

INTERVAL = float(os.getenv("FEED_INTERVAL", "10"))

# Each hive's steady "regime" = where the 24h seed left it. The feed keeps them here
# (so the demo narrative is stable) while traffic and acoustic signals move believably.
REGIME = {
    "A1": {"varroa": "clear"},
    "A2": {"varroa": "clear"},
    "C1": {"varroa": "clear"},
    "A3": {"varroa": "alert", "reason": "Acoustic stress and visible mites agree: treat this week."},
    "B1": {"varroa": "watch", "needs_human": True,
           "reason": "Signals disagree: acoustic=stressed but vision=clear. Please inspect and confirm."},
    "B2": {"varroa": "clear", "swarm": True, "reason": "Swarm spike detected; heads-up to the yard."},
    "B3": {"varroa": "clear", "queenless": True, "reason": "Queenless roar detected."},
}


def _diurnal(now):
    """Rough day/night foraging curve: low at night, peak midday."""
    h = now.hour + now.minute / 60.0
    return int(45 * max(0.0, math.sin(math.pi * h / 24.0)))


def next_verdict(hive, now):
    r = REGIME[hive]
    traffic = _diurnal(now) + random.randint(-8, 8)
    if r.get("swarm"):
        traffic = -75 + random.randint(-6, 6)          # mass outflux during a swarm
    elif r.get("needs_human"):
        traffic = 60 + random.randint(-6, 6)            # the clash hive runs hot
    return _verdict(
        hive, now,
        varroa=r.get("varroa", "clear"),
        queenless=r.get("queenless", False),
        swarm=r.get("swarm", False),
        traffic=traffic,
        needs_human=r.get("needs_human", False),
        reason=r.get("reason", ""),
    )


def main():
    print(f"Live feed: appending 1 verdict/hive every {INTERVAL:.0f}s. Ctrl+C to stop.")
    try:
        while True:
            now = datetime.now()
            for hive in POSITIONS:
                hive_state.append_verdict(next_verdict(hive, now))
            head = godfather.apiary_analysis(hive_state.load_verdicts())["headline"]
            print(f"[{now:%H:%M:%S}] {head}")
            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        print("\nlive feed stopped.")


if __name__ == "__main__":
    main()

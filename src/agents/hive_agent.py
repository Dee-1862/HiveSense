"""
Reasoning hive agent - one per hive (the 7 brains).

Unlike the old deterministic supervisor, this agent DECIDES like a beekeeper would:
  1. read the cheap always-on acoustic signal,
  2. let the brain decide whether the reading warrants the expensive tunnel-vision test,
  3. reconcile the two independent estimators; if they CLASH it does not guess - it sets
     needs_human and asks a beekeeper to inspect,
  4. learn from the beekeeper's feedback (stored and fed back into the brain next time).

Models are called as TOOLS (see tools.py); the brain is reasoning.py (ASI:One asi1-mini
with a deterministic fallback). The agent emits the same Verdict the dashboard reads,
now carrying needs_human + reason.
"""

import random
import datetime
from uagents import Agent, Context

from .schema import Verdict, HumanFeedback
from . import tools, reasoning


def _sample(rng):
    """One cycle of raw signals - a stand-in for live mic / tunnel / entrance sensors.
    Deliberately produces occasional acoustic/vision CLASHES so the human path fires."""
    roll = rng.random()
    if roll < 0.12:        # clash: colony sounds stressed but no visible mites
        ac, vis = 0.75, 0.0
    elif roll < 0.20:      # clash: colony calm but camera sees mites
        ac, vis = 0.20, 0.06
    elif roll < 0.30:      # genuine infestation: both agree
        ac, vis = 0.80, 0.07
    else:                  # healthy
        ac, vis = rng.uniform(0.0, 0.4), rng.uniform(0.0, 0.02)
    return {
        "acoustic_stress": ac,
        "vision_mite_rate": vis,
        "queenless_score": 0.95 if rng.random() < 0.04 else rng.uniform(0.0, 0.5),
        "swarm_band_hz": rng.uniform(90, 300) if rng.random() < 0.05 else rng.uniform(300, 500),
        "swarm_rising": rng.random() < 0.05,
        "net_traffic": int(rng.gauss(0, 60)),
    }


def create_hive_agent(hive_id, seed, coordinator_address, position=None,
                      clip_path=None, period=20.0):
    """clip_path: optional VD2 .mkv so the vision tool runs the REAL Vit4V model."""
    position = position or [0.0, 0.0]
    agent = Agent(name=f"hive_{hive_id}", seed=seed)
    rng = random.Random(hash(seed) & 0xFFFFFFFF)

    @agent.on_interval(period=period)
    async def cycle(ctx: Context):
        sample = _sample(rng)
        history = ctx.storage.get("history") or []
        feedback = (ctx.storage.get("feedback") or [])[-1:] or None

        # 1. cheap, always-on
        acoustic = tools.acoustic_mite(sample)
        # 2. brain decides whether to spend the vision test
        run_vision, why = reasoning.should_run_vision(acoustic, history)
        if run_vision:
            vision = tools.vision_varroa(sample, clip_path=clip_path)
            rec = reasoning.reconcile(acoustic, vision, feedback=feedback)
            ctx.logger.info(
                f"[{hive_id}] vision triggered ({why}); acoustic={acoustic['label']} "
                f"vision={vision['label']} -> {rec['varroa_status']} needs_human={rec['needs_human']}"
            )
        else:
            rec = {"varroa_status": "clear" if acoustic["label"] == "ok" else "watch",
                   "needs_human": False, "reason": why}
            ctx.logger.info(f"[{hive_id}] acoustic={acoustic['label']} ({why}); vision skipped")

        # 3. the other detectors are deterministic, fold into the Verdict
        q, sw, tr = tools.queenless(sample), tools.swarm(sample), tools.traffic(sample)
        verdict = Verdict(
            hive_id=hive_id,
            varroa_status=rec["varroa_status"],
            queenless_alert=(q["label"] == "queenless"),
            swarm_alert=(sw["label"] == "swarming"),
            traffic=int(tr["score"]),
            position=position,
            needs_human=rec["needs_human"],
            reason=rec["reason"],
            timestamp=datetime.datetime.now().isoformat(),
        )
        history.append({"varroa_status": rec["varroa_status"], "acoustic": acoustic["label"]})
        ctx.storage.set("history", history[-10:])

        if coordinator_address:
            await ctx.send(coordinator_address, verdict)
        if rec["needs_human"]:
            ctx.logger.warning(f"[{hive_id}] NEEDS HUMAN: {rec['reason']}")

    # 4. learn from the beekeeper's reply (routed by the coordinator)
    @agent.on_message(model=HumanFeedback)
    async def on_feedback(ctx: Context, sender: str, msg: HumanFeedback):
        fb = ctx.storage.get("feedback") or []
        fb.append({"text": msg.text, "ts": msg.ts})
        ctx.storage.set("feedback", fb[-5:])
        ctx.logger.info(f"[{hive_id}] human feedback logged: {msg.text}")

    return agent

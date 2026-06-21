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
from . import tools, reasoning, feed

# Redis-backed multimodal memory (vector search + stego packing). All of this is
# optional: get_store() returns a Redis backend only when USE_REDIS=1 and Redis is
# reachable, otherwise store.available() is False and every block below is skipped.
from src.store import get_store


def _similar_summary(store, emb, hive_id, k=3):
    """Retrieve this hive's most similar past readings (Redis k-NN) as a short
    natural-language recall the brain can reason over. Empty string if unavailable."""
    if emb is None:
        return ""
    try:
        neigh = store.search_similar(emb, k=k, hive=hive_id)
    except Exception:
        return ""
    parts = []
    for n in neigh:
        tag = " (needed inspection)" if str(n.get("needs_human")) == "true" else ""
        parts.append(f"{n.get('varroa_status', '?')}{tag}")
    return f"{len(parts)} similar past states: " + ", ".join(parts) if parts else ""


def create_hive_agent(hive_id, seed, coordinator_address, position=None,
                      clip_path=None, period=8.0):
    """clip_path: optional VD2 .mkv so the vision tool runs the REAL Vit4V model."""
    position = position or [0.0, 0.0]
    agent = Agent(name=f"hive_{hive_id}", seed=seed)
    rng = random.Random(hash(seed) & 0xFFFFFFFF)

    @agent.on_interval(period=period)
    async def cycle(ctx: Context):
        sample = feed.hive_sample(hive_id, datetime.datetime.now(), rng)
        history = ctx.storage.get("history") or []
        feedback = (ctx.storage.get("feedback") or [])[-1:] or None

        # multimodal embedding for this reading (only when the Redis memory is live)
        store = get_store()
        emb = vision_source = None
        if store.available():
            try:
                from src import embedding
                emb, vision_source = embedding.embed_sample(sample)
            except Exception:
                ctx.logger.debug("embedding failed", exc_info=True)

        # 1. cheap, always-on acoustic
        acoustic = tools.acoustic_mite(sample)
        # 2. brain decides whether to spend the expensive vision test
        run_vision, why = reasoning.should_run_vision(acoustic, history)
        vision_rate = 0.0
        if run_vision:
            vision = tools.vision_varroa(sample, clip_path=clip_path)
            vision_rate = float(vision["score"])
            # RAG: retrieve this hive's most similar past states to inform the call
            similar = _similar_summary(store, emb, hive_id)
            rec = reasoning.reconcile(acoustic, vision, feedback=feedback, similar=similar)
            ctx.logger.info(
                f"[{hive_id}] vision triggered ({why}); acoustic={acoustic['label']} "
                f"vision={vision['label']} -> {rec['varroa_status']} needs_human={rec['needs_human']}"
                + (f"; recalled {similar}" if similar else "")
            )
        else:
            rec = {"varroa_status": "clear" if acoustic["label"] == "ok" else "watch",
                   "needs_human": False, "reason": why}
            ctx.logger.info(f"[{hive_id}] acoustic={acoustic['label']} ({why}); vision skipped")

        # 3. the other detectors fold into the Verdict (with the per-detector signals)
        q, sw, tr = tools.queenless(sample), tools.swarm(sample), tools.traffic(sample)
        verdict = Verdict(
            hive_id=hive_id,
            varroa_status=rec["varroa_status"],
            queenless_alert=(q["label"] == "queenless"),
            swarm_alert=(sw["label"] == "swarming"),
            traffic=int(tr["score"]),
            position=position,
            acoustic_stress=float(sample["acoustic_stress"]),
            vision_mite_rate=vision_rate,
            vision_ran=run_vision,
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

        # 4. record the searchable multimodal reading: embedding (for k-NN) + the stego
        #    blob (acoustic features packed into one image -> ONE Redis key, both modalities)
        if emb is not None:
            try:
                from src import embedding
                import stego
                vd = verdict.model_dump()
                vd["vision_source"] = vision_source
                payload = embedding.to_bytes(embedding.acoustic_features(sample))
                blob = stego.encode(stego.solid_carrier(), payload)
                store.record_reading(hive_id, vd, emb, image_blob=blob)
            except Exception:
                ctx.logger.debug("record_reading skipped", exc_info=True)

    # 4. learn from the beekeeper's reply (routed by the coordinator)
    @agent.on_message(model=HumanFeedback)
    async def on_feedback(ctx: Context, sender: str, msg: HumanFeedback):
        fb = ctx.storage.get("feedback") or []
        fb.append({"text": msg.text, "ts": msg.ts})
        ctx.storage.set("feedback", fb[-5:])
        ctx.logger.info(f"[{hive_id}] human feedback logged: {msg.text}")

    return agent

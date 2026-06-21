from datetime import datetime, timezone
from uuid import uuid4

from uagents import Agent, Context, Protocol
# Official ASI:One chat protocol. Confirm the import path against the current
# "Enable Chat Protocol" docs if it moves between uagents versions.
from uagents_core.contrib.protocols.chat import (
    chat_protocol_spec,
    ChatMessage,
    ChatAcknowledgement,
    TextContent,
)

# NOTE: we use the OFFICIAL ChatMessage above. The local dashboard still uses the
# REST endpoint below, so ApiaryStatusResponse stays.
from .schema import Verdict, ApiaryStatusResponse, HumanFeedback

# shared 24h verdict store (root-level hive_state.py), used by the dashboard + ASI:One agent
import os as _os
import sys as _sys
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)
try:
    import hive_state
except Exception:
    hive_state = None
try:
    import godfather as _godfather
except Exception:
    _godfather = None


def _apiary_answer(verdicts: dict, question: str) -> str:
    """Format already-computed verdicts into a sentence. No health decision happens here -
    ASI:One only phrases this; your models already made the calls."""
    if not verdicts:
        return "I have not received any data from the apiary yet."

    lines = []
    for hive_id, hist in verdicts.items():
        if not hist:
            continue
        latest = Verdict(**hist[-1])
        flag = f"  [NEEDS INSPECTION: {latest.reason}]" if getattr(latest, "needs_human", False) else ""
        lines.append(
            f"Hive {hive_id}: varroa={latest.varroa_status}, "
            f"swarm={latest.swarm_alert}, queenless={latest.queenless_alert}, "
            f"net_traffic={latest.traffic}{flag}"
        )

    body = "\n".join(lines)
    q = question.lower()
    if any(k in q for k in ("status", "alert", "okay", "ok", "health", "bees", "worry", "fine")):
        return "Apiary status:\n" + body
    # ASI:One users phrase things many ways, so default to giving the status anyway.
    return "I'm the HiveSense fleet coordinator. Current apiary status:\n" + body


def create_coordinator(agent_name: str, seed: str, port: int = 8000,
                       mailbox: bool = True, endpoint: str | None = None) -> Agent:
    """Fleet coordinator. Three connectivity modes (the agent always serves its local
    HTTP server on `port`, so the dashboard's /api/status keeps working in all of them):

      - endpoint=<public url>  : SELF-HOSTED. Advertise a public URL (e.g. an ngrok
                                 https tunnel to this port, ending in /submit). Use this
                                 when registering via the Agentverse "Agent Endpoint URL"
                                 form. Overrides mailbox.
      - mailbox=True (default) : connect via Agentverse mailbox (no public URL needed).
      - mailbox=False          : pure local dev, no Agentverse.
    """
    if endpoint:
        coordinator = Agent(name=agent_name, seed=seed, port=port, endpoint=[endpoint])
    else:
        coordinator = Agent(name=agent_name, seed=seed, port=port, mailbox=mailbox)

    # ---- internal pipe: supervisors -> coordinator (unchanged, deterministic) ----
    @coordinator.on_message(model=Verdict)
    async def handle_verdict(ctx: Context, sender: str, msg: Verdict):
        ctx.logger.info(
            f"Verdict from hive {msg.hive_id}: varroa={msg.varroa_status}, "
            f"queenless={msg.queenless_alert}, swarm={msg.swarm_alert}"
        )
        verdicts = ctx.storage.get("verdicts") or {}
        verdicts.setdefault(msg.hive_id, [])
        verdicts[msg.hive_id].append(msg.model_dump())
        verdicts[msg.hive_id] = verdicts[msg.hive_id][-5:]  # keep last 5 for trend
        ctx.storage.set("verdicts", verdicts)

        # append to the shared 24h store (dashboard + ASI:One agent read this)
        if hive_state:
            try:
                hive_state.append_verdict(msg.model_dump())
            except Exception:
                ctx.logger.exception("could not append verdict to shared store")

        # remember each hive agent's address so we can route the beekeeper's feedback back
        addrs = ctx.storage.get("hive_addrs") or {}
        addrs[msg.hive_id] = sender
        ctx.storage.set("hive_addrs", addrs)
        if getattr(msg, "needs_human", False):
            ctx.logger.warning(f"HUMAN NEEDED at hive {msg.hive_id}: {msg.reason}")

        correlate(ctx, verdicts)

    # ---- local dashboard feed: REST GET consumed by the Vite frontend ----
    @coordinator.on_rest_get("/api/status", ApiaryStatusResponse)
    async def get_status(ctx: Context) -> ApiaryStatusResponse:
        # Serve the shared 24h store (seed + live appends) so the dashboard gets full
        # history; fall back to in-memory last-5 if the store is unavailable.
        verdicts = (hive_state.load_verdicts() if hive_state else None) or ctx.storage.get("verdicts") or {}
        return ApiaryStatusResponse(hives=verdicts)

    # ---- official ASI:One chat protocol (the part that makes it discoverable) ----
    chat = Protocol(spec=chat_protocol_spec)

    @chat.on_message(ChatMessage)
    async def handle_chat(ctx: Context, sender: str, msg: ChatMessage):
        # 1. acknowledge receipt (the protocol expects this)
        await ctx.send(sender, ChatAcknowledgement(
            timestamp=datetime.now(timezone.utc),
            acknowledged_msg_id=msg.msg_id,
        ))
        # 2. pull the user's text out of the content list
        question = " ".join(c.text for c in msg.content if isinstance(c, TextContent))
        ctx.logger.info(f"Chat query from {sender}: {question}")
        # 3. is this the beekeeper replying to a needs_human escalation? if the message
        #    names a hive and reads like an inspection note, route it to that hive agent.
        verdicts = ctx.storage.get("verdicts") or {}
        addrs = ctx.storage.get("hive_addrs") or {}
        ql = question.lower()
        target = next((h for h in addrs if h.lower() in ql), None)
        feedback_words = ("checked", "inspected", "confirmed", "it's", "it is", "was",
                          "actually", "robbing", "fine", "treated", "feedback",
                          "no mites", "not varroa", "queenless", "swarm")
        if target and any(w in ql for w in feedback_words):
            await ctx.send(addrs[target], HumanFeedback(
                hive_id=target, text=question, ts=datetime.now(timezone.utc).isoformat()))
            answer = f"Thanks - logged your inspection note for hive {target} and sent it to that hive's agent."
        else:
            answer = _apiary_answer(verdicts, question)
        # 4. reply in the protocol's format
        await ctx.send(sender, ChatMessage(
            timestamp=datetime.now(timezone.utc),
            msg_id=uuid4(),
            content=[TextContent(type="text", text=answer)],
        ))

    @chat.on_message(ChatAcknowledgement)
    async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
        pass  # no-op; prevents "unhandled message" warnings

    coordinator.include(chat, publish_manifest=True)  # <-- publishes chat-compat to Agentverse
    return coordinator


def create_godfather(agent_name: str = "hivesense_godfather",
                     seed: str = "hivesense_godfather_seed") -> Agent:
    """Local in-fleet Godfather (no mailbox / no REST / no chat). It receives every
    hive's Verdict, writes the shared store, and runs the apiary-wide analysis in turn -
    so the orchestration is real and visible in the terminal. Put this in the same Bureau
    as the hive agents (see run_fleet.py); serving and chat are handled by api_server.py
    and asi1_agent.py respectively."""
    gf = Agent(name=agent_name, seed=seed)

    @gf.on_message(model=Verdict)
    async def handle(ctx: Context, sender: str, msg: Verdict):
        if hive_state:
            try:
                hive_state.append_verdict(msg.model_dump())
            except Exception:
                ctx.logger.exception("godfather: could not append to store")
        if _godfather is not None and hive_state is not None:
            a = _godfather.apiary_analysis(hive_state.load_verdicts())
            if a["emergent"] or a["needs_human"]:   # only shout when there's something to say
                ctx.logger.warning(f"[godfather] {a['headline']}")
                for e in a["emergent"]:
                    ctx.logger.warning(f"[godfather] {e}")

    return gf


# A hive closer than this (metres) to a neighbour can rob / be robbed by it.
NEIGHBOR_DIST = 10.0
# Net bees/cycle that counts as a real surge or drain rather than normal jitter.
FLOW_THRESHOLD = 50


def _distance(p, q):
    """Euclidean distance between two [x, y] positions; inf if either is missing."""
    if not p or not q or len(p) < 2 or len(q) < 2:
        return float("inf")
    return ((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2) ** 0.5


def correlate(ctx: Context, verdicts: dict):
    """Correlate AGGREGATE signals across hives. We never track individual bees.
    Honest cross-hive patterns:
      - several hives in varroa 'alert' at once   -> regional outbreak
      - varroa newly rising across hives          -> drift-driven spread
      - a hive swarming                           -> broadcast a heads-up to the yard
      - strong influx at one hive vs strong outflux at a NEIGHBOUR -> possible
        robbing (a traffic signal, distinct from the varroa-status spread signal)
    """
    swarming = []
    varroa_alert = []
    varroa_rising = []  # trend across stored history, not just current state
    latest_by_hive = {}

    for hive_id, hist in verdicts.items():
        if not hist:
            continue
        latest = Verdict(**hist[-1])
        latest_by_hive[hive_id] = latest
        if latest.swarm_alert:
            swarming.append(hive_id)
        if latest.varroa_status == "alert":
            varroa_alert.append(hive_id)
        statuses = [Verdict(**v).varroa_status for v in hist]
        if statuses[-1] == "alert" and "alert" not in statuses[:-1]:
            varroa_rising.append(hive_id)

    # swarm is detected locally at the source hive; the coordinator only relays it,
    # it never claims the same bees arrived at a specific other hive.
    if len(swarming) >= 2:
        ctx.logger.warning(
            f"EMERGENT: simultaneous swarming across hives {swarming} "
            f"(possible shared trigger such as weather or forage dearth)"
        )
    elif len(swarming) == 1:
        ctx.logger.info(
            f"NOTICE: hive {swarming[0]} is swarming. Heads-up to the yard; "
            f"watch neighbours for arrivals."
        )

    # varroa: aggregate, apiary-level spread signal.
    if len(varroa_alert) >= 2:
        ctx.logger.warning(
            f"EMERGENT: regional varroa outbreak across hives {varroa_alert}. "
            f"Treat the row, not just one hive."
        )
    if len(varroa_rising) >= 2:
        ctx.logger.warning(
            f"EMERGENT: varroa rising across multiple hives {varroa_rising} - "
            f"likely drift-driven spread through the apiary."
        )

    # robbing: one hive draining (outflux) while a NEARBY hive surges (influx) in the
    # same cycle. This is a traffic pattern, not a health-status spread - a strong
    # hive raiding a weak neighbour. We only flag yard pairs that are close enough.
    hive_ids = list(latest_by_hive)
    for i in range(len(hive_ids)):
        for j in range(i + 1, len(hive_ids)):
            a = latest_by_hive[hive_ids[i]]
            b = latest_by_hive[hive_ids[j]]
            if _distance(a.position, b.position) > NEIGHBOR_DIST:
                continue
            robbed = robber = None
            if a.traffic >= FLOW_THRESHOLD and b.traffic <= -FLOW_THRESHOLD:
                robbed, robber = b.hive_id, a.hive_id
            elif b.traffic >= FLOW_THRESHOLD and a.traffic <= -FLOW_THRESHOLD:
                robbed, robber = a.hive_id, b.hive_id
            if robbed:
                ctx.logger.warning(
                    f"EMERGENT: possible robbing - hive {robbed} draining while "
                    f"neighbour {robber} surges. Reduce {robbed}'s entrance and "
                    f"inspect; this is a traffic signal, not varroa spread."
                )

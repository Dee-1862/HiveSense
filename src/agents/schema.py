from uagents import Model
from typing import Dict, List, Any

class DetectorRequest(Model):
    reference: str
    hive_id: str

class DetectorResult(Model):
    detector: str
    score: float
    label: str
    valid: bool
    ts: str

class Verdict(Model):
    hive_id: str
    varroa_status: str # 'clear', 'watch', 'alert'
    queenless_alert: bool
    swarm_alert: bool
    traffic: int = 0  # net bee flow this cycle: + = net influx, - = net outflux
    position: List[float] = [0.0, 0.0]  # hive location in the yard [x, y] metres, for neighbour checks
    # per-detector signals (so the dashboard can show the acoustic-vs-vision reasoning)
    acoustic_stress: float = 0.0   # colony acoustic stress 0..1 (always measured)
    vision_mite_rate: float = 0.0  # per-bee mite rate from the tunnel camera (when vision ran)
    vision_ran: bool = False       # did the expensive vision test run this cycle?
    # --- human-in-the-loop fields (NEW: frontend should render these) ---
    # needs_human is set when the hive agent cannot resolve a conflict on its own
    # (e.g. acoustic and vision disagree) and wants a beekeeper to inspect.
    needs_human: bool = False
    reason: str = ""           # plain-language explanation written by the reasoning agent
    timestamp: str = ""

# FRONTEND COORDINATION: `needs_human` and `reason` are new Verdict fields. They default
# so old consumers keep working, but the dashboard should surface needs_human (e.g. an
# "inspect" badge) and show `reason`. Coordinate with the frontend session before relying on them.

class HumanFeedback(Model):
    """A beekeeper's reply to a needs_human escalation, routed coordinator -> hive."""
    hive_id: str
    text: str
    ts: str

# NOTE: the custom ChatMessage was removed. The coordinator now speaks the official
# ASI:One chat protocol (uagents_core.contrib.protocols.chat), not a local schema.

class ApiaryStatusResponse(Model):
    hives: Dict[str, List[Dict[str, Any]]]

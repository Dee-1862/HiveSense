"""
HiveDoctor - a selective, durable human-in-the-loop treatment agent on Orkes Agentspan.

THE IDEA (one line): an agent that knows when NOT to ask. It treats the beekeeper's
attention as the scarce resource and interrupts them only when a Value-of-Information
calculation says their judgement is worth more than the cost of the interruption
(see voi.py). When it does need a human, Agentspan holds that pause durably - the
question survives a crash and resumes by workflow_id. Non-invasive twice: we don't
disturb the colony to sense it, and we don't disturb the beekeeper unless the math
says they're needed.

HOW IT USES AGENTSPAN: the treatment action is an Agentspan @tool marked
approval_required=True. The VoI gate decides whether to invoke that durable pause:
  - ask      -> Agentspan pauses server-side, waits indefinitely for the beekeeper
  - auto_act -> confident; the agent acts on its own, no interruption
  - auto_hold-> confident it's calm; keep monitoring, no interruption

Degrades gracefully: with `agentspan server start` runs execute on the durable engine;
without it, the same gate + approval flow run through a durable on-disk registry
(runs.py) so a demo never breaks. The VoI gate itself is closed-form and always runs.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from . import voi, runs

# ---- shared store with the rest of the fleet (verdicts the sensing agents wrote) ----
import sys as _sys
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)
try:
    import hive_state
except Exception:  # pragma: no cover - store optional in unit tests
    hive_state = None


# --------------------------------------------------------------------------- #
# Agentspan SDK (optional import: the VoI gate runs without it too)
# --------------------------------------------------------------------------- #
try:
    from agentspan.agents import Agent, tool, run as agentspan_run
    HAS_AGENTSPAN = True
except Exception:  # SDK not installed -> no-op decorator so the tools stay callable
    HAS_AGENTSPAN = False

    def tool(*dargs, **dkwargs):
        """Stand-in for agentspan's @tool: supports @tool and @tool(approval_required=True)."""
        if dargs and callable(dargs[0]):
            return dargs[0]
        def deco(fn):
            return fn
        return deco


TREATMENT = "oxalic acid dribble (3.2% w/v in 1:1 syrup)"
DOSE = "5 mL per occupied seam"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _model() -> str:
    """Agentspan model string. This project uses Gemini for all LLM reasoning (set
    GEMINI_API_KEY); override the exact model with AGENTSPAN_MODEL if needed."""
    return os.getenv("AGENTSPAN_MODEL", "google_gemini/gemini-2.5-flash")


# --------------------------------------------------------------------------- #
# Tools the Agentspan agent exposes. assess_colony is the VoI brain; apply_treatment
# is the durable human-in-the-loop gate.
# --------------------------------------------------------------------------- #
@tool
def assess_colony(acoustic_stress: float, vision_rate: float, vision_ran: bool) -> dict:
    """Fuse the sensors into P(infested) and run the Value-of-Information gate to decide
    whether to act alone or ask the beekeeper. Closed-form, no LLM."""
    p = voi.infestation_probability(acoustic_stress, vision_rate, vision_ran)
    gate = voi.voi_gate(p, voi.COSTS["varroa"])
    gate["explain"] = voi.explain(gate, "varroa")
    return gate


@tool(approval_required=True)
def apply_treatment(hive_id: str, treatment: str, dose: str) -> dict:
    """Apply a varroa treatment to a hive. THIS IS THE DURABLE HUMAN-IN-THE-LOOP GATE:
    when the VoI gate decides the call is too close to make alone, Agentspan pauses here
    and holds the run server-side until the beekeeper approves or denies - surviving a
    crash. No treatment is recorded without that sign-off."""
    return {"hive_id": hive_id, "treatment": treatment, "dose": dose,
            "applied_at": _now(), "status": "applied"}


def build_agent():
    """The Agentspan agent: assess with VoI, then (only if needed) pause for approval.
    Returns None if the SDK is not installed (the registry path still works)."""
    if not HAS_AGENTSPAN:
        return None
    return Agent(
        name="hive_doctor", model=_model(),
        instructions=("You look after a beehive. First call assess_colony to get the "
                      "Value-of-Information decision. If it says ask, call apply_treatment "
                      "(it needs the beekeeper's approval) and wait. If it says act, call "
                      "apply_treatment directly. If it says hold, do nothing and explain "
                      "why in one plain, friendly sentence."),
        tools=[assess_colony, apply_treatment])


# --------------------------------------------------------------------------- #
# The brain: read a hive's latest signals, run the VoI gate per condition.
# Deterministic - the single source of truth for both the live run and the dashboard.
# --------------------------------------------------------------------------- #
def _latest(hive_id: str) -> dict:
    verdicts = (hive_state.load_verdicts() if hive_state else {}) or {}
    hist = verdicts.get(hive_id) or []
    return (hist[-1] if hist else {}) or {}


def compute_decision(hive_id: str) -> dict:
    """Run the VoI gate for this hive (varroa from the fused sensors; queenless/swarm
    from their flags) and build a plain-language plan + the gate maths for the demo."""
    v = _latest(hive_id)
    acoustic = float(v.get("acoustic_stress", 0.0) or 0.0)
    vision = float(v.get("vision_mite_rate", 0.0) or 0.0)
    vision_ran = bool(v.get("vision_ran", False))

    # varroa: the calibrated, fused belief feeds the gate
    p = voi.infestation_probability(acoustic, vision, vision_ran)
    varroa = voi.voi_gate(p, voi.COSTS["varroa"])
    varroa["condition"] = "varroa"
    varroa["explain"] = voi.explain(varroa, "varroa")

    # queenless / swarm: coarse belief from the verdict flags (these detectors emit a
    # boolean today; the gate works the moment they emit a probability instead)
    gates = [varroa]
    for cond, flag in (("queenless", "queenless_alert"), ("swarm", "swarm_alert")):
        pc = 0.7 if v.get(flag) else 0.02
        g = voi.voi_gate(pc, voi.COSTS[cond])
        g["condition"] = cond
        g["explain"] = voi.explain(g, cond)
        g["coarse"] = True   # honest: not a calibrated probability yet
        gates.append(g)

    # the agent's overall decision = the most demanding condition (ask > act > hold)
    rank = {"ask": 2, "auto_act": 1, "auto_hold": 0}
    lead = max(gates, key=lambda g: rank[g["decision"]])
    plan = {
        "hive_id": hive_id, "treatment": TREATMENT, "dose": DOSE,
        "decision": lead["decision"], "lead_condition": lead["condition"],
        "gates": gates, "varroa": varroa,
        "headline": _headline(hive_id, lead),
    }
    return plan


def _headline(hive_id: str, lead: dict) -> str:
    name = {"varroa": "mites", "queenless": "the queen", "swarm": "swarming"}[lead["condition"]]
    if lead["decision"] == "ask":
        return (f"Hive {hive_id}: a close call on {name}. I'm asking you because your "
                f"call here is worth more than the interruption.")
    if lead["decision"] == "auto_act":
        return (f"Hive {hive_id}: clear sign of {name} trouble. I'm handling it myself - "
                "no need to interrupt you.")
    return f"Hive {hive_id}: all calm. Just keeping watch, nothing you need to do."


# --------------------------------------------------------------------------- #
# Durable lifecycle for the dashboard. The VoI gate decides the path:
#   ask       -> pause on the durable approval gate (status awaiting_approval)
#   auto_act  -> the agent treats on its own (status auto_treated)
#   auto_hold -> keep monitoring (status auto_monitor)
# --------------------------------------------------------------------------- #
def start(hive_id: str) -> dict:
    """Assess a hive and route it through the VoI gate."""
    workflow_id = f"hd_{hive_id}_{uuid.uuid4().hex[:8]}"
    now = _now()
    runs.create_run(workflow_id, hive_id, now)
    plan = compute_decision(hive_id)

    # log the VoI maths for the live "here's why" moment
    for g in plan["gates"]:
        runs.add_step(workflow_id, now, f"VoI gate · {g['condition']}",
                      {"p": g["p"], "EVPI": g["evpi"], "c_ask": g["c_ask"],
                       "threshold": g["threshold"], "decision": g["decision"]})

    decision = plan["decision"]
    if decision == "ask":
        pending = {"tool": "apply_treatment", "summary": plan["headline"],
                   "fields": {"approve": {"type": "boolean", "desc": "Treat this hive?"},
                              "note": {"type": "string", "desc": "Optional note"}},
                   "proposed": {"treatment": TREATMENT, "dose": DOSE}}
        runs.update_run(workflow_id, now, status="awaiting_approval", plan=plan, pending=pending)
        _maybe_launch_live(workflow_id, hive_id)
    elif decision == "auto_act":
        applied = apply_treatment(hive_id=hive_id, treatment=TREATMENT, dose=DOSE)
        runs.add_step(workflow_id, now, "auto-act (confident)", applied)
        runs.update_run(workflow_id, now, status="auto_treated", plan=plan,
                        result={"status": "treatment_applied", "autonomous": True,
                                "detail": applied})
    else:  # auto_hold
        runs.update_run(workflow_id, now, status="auto_monitor", plan=plan,
                        result={"status": "monitoring", "autonomous": True})
    return runs.get_run(workflow_id)


def respond(workflow_id: str, approve: bool, note: str = "") -> dict:
    """Resume a paused run with the beekeeper's decision (the human-in-the-loop reply)."""
    run = runs.get_run(workflow_id)
    if run is None:
        raise KeyError(workflow_id)
    if run.get("status") != "awaiting_approval":
        return run
    now = _now()

    # forward to the live Agentspan handle if present (resumes the durable workflow
    # exactly where it paused); registry stays the source of truth for the UI
    handle = runs.get_handle(workflow_id)
    if handle is not None:
        try:
            handle.respond({"approve": bool(approve), "note": note})
        except Exception:
            pass

    if not approve:
        runs.add_step(workflow_id, now, "beekeeper", {"decision": "denied", "note": note})
        return runs.update_run(workflow_id, now, status="denied",
                               decision={"approve": False, "note": note},
                               result={"status": "denied_by_beekeeper"})
    applied = apply_treatment(hive_id=run["hive_id"], treatment=TREATMENT, dose=DOSE)
    runs.add_step(workflow_id, now, "beekeeper", {"decision": "approved", "note": note})
    return runs.update_run(workflow_id, now, status="approved",
                           decision={"approve": True, "note": note},
                           result={"status": "treatment_applied", "detail": applied})


def _maybe_launch_live(workflow_id: str, hive_id: str) -> None:
    """If the Agentspan SDK + server are available, launch the real durable run in the
    background so it executes on Conductor and the run survives a crash. Never raises."""
    if not HAS_AGENTSPAN or os.getenv("AGENTSPAN_LIVE", "0") != "1":
        return
    try:
        import threading
        agent = build_agent()
        if agent is None:
            return
        v = _latest(hive_id)
        prompt = (f"Look after hive {hive_id}. acoustic_stress={v.get('acoustic_stress', 0.0)}, "
                  f"vision_rate={v.get('vision_mite_rate', 0.0)}, vision_ran={bool(v.get('vision_ran'))}. "
                  "Use assess_colony, then act per its decision.")

        def _go():
            try:
                runs.set_handle(workflow_id, agentspan_run(agent, prompt))
            except Exception:
                pass

        threading.Thread(target=_go, daemon=True).start()
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# CLI demo
# --------------------------------------------------------------------------- #
def run_cli(hive_id: str) -> dict:
    plan = compute_decision(hive_id)
    print(f"\n=== HiveDoctor (VoI gate): hive {hive_id} ===")
    print(plan["headline"])
    print("\n  Per-condition Value-of-Information decision:")
    for g in plan["gates"]:
        tag = "ASK YOU" if g["needs_human"] else ("ACT" if g["action"] == "act" else "HOLD")
        coarse = " (coarse signal)" if g.get("coarse") else ""
        print(f"   - {g['condition']:<9} p={g['p']:.2f}  EVPI=${g['evpi']:.2f} vs ask=${g['c_ask']}"
              f"  -> {tag}{coarse}")
        print(f"       {g['explain']}")
    print(f"\n  Overall: {plan['decision'].upper()} (driven by {plan['lead_condition']})")
    return plan


if __name__ == "__main__":
    run_cli(_sys.argv[1] if len(_sys.argv) > 1 else "A3")

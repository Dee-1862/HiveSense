"""
Value-of-Information gate: the agent that knows when NOT to ask.

Most human-in-the-loop demos pause on every action. That is the easy version, and in
the real world it causes alarm fatigue - the failure mode of every monitoring system,
from ICU alarms to beekeeping apps. They don't fail by missing things; they fail by
crying wolf until people mute them.

This gate does the opposite. It treats the beekeeper's ATTENTION as the scarce resource
and spends it deliberately: a small, closed-form decision-theory calculation decides
whether interrupting the beekeeper is worth more than the cost of the interruption. It
asks only on genuine close calls and stays quiet when it is confident either way.

Grounding: "Value of Information: A Framework for Human-Agent Communication"
(arXiv 2601.06407, Jan 2026) uses Value of Information to weigh an agent's expected
utility gain from asking against the cognitive cost on the user. Lineage: Howard's
Value of Information (1966) -> Horvitz on the cost of interrupting a user -> KnowNo
(Princeton/DeepMind, ask-when-uncertain via conformal prediction) -> HuLA -> the
Jan 2026 framework. Our contribution is the TRANSPLANT plus the GUARANTEE: first VoI
-gated human-in-the-loop on a non-invasive physical colony-monitoring mesh, coupled to
Agentspan so the question survives a crash. The VoI principle is not ours; the place we
put it and the durability around it are.

The whole thing is closed-form and deterministic - never an LLM call - so it always runs
and you can show the numbers live.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

VARROA_RATE_THRESHOLD = 0.03   # 3 mites / 100 bees (economic injury level)


@dataclass
class Costs:
    """Costs for one condition, in interpretable dollars. Always c_fn >> c_fp >> c_ask."""
    c_fn: float   # cost of MISSING a real problem (a lost colony). BIG.
    c_fp: float   # cost of acting on a healthy hive (wasted/harmful treatment). small.
    c_ask: float  # cost of interrupting the beekeeper. smallest.


# Dollar-interpretable defaults (lost colony $150-300, miticide $10-20, a trip = time).
# Each monitored condition gets its own loss matrix because the stakes differ.
COSTS = {
    "varroa":    Costs(c_fn=150, c_fp=15, c_ask=3),  # lost colony vs needless miticide
    "queenless": Costs(c_fn=120, c_fp=8,  c_ask=3),  # dwindling colony vs needless requeen
    "swarm":     Costs(c_fn=90,  c_fp=5,  c_ask=3),  # lost swarm/honey vs needless trip
}


def voi_gate(p: float, costs: Costs) -> dict:
    """Decide whether to ask the beekeeper, from the belief p = P(real problem).

    Loss matrix (cost incurred; lower is better):
        L(act,  real) = 0       L(act,  fine) = c_fp     (acted on a healthy hive)
        L(hold, real) = c_fn    L(hold, fine) = 0        (missed a real problem)

    Returns the Bayes-optimal autonomous action, the expected value of perfect
    information (EVPI = the residual risk of that action), and whether to ask.
    EVPI is large only when the call is BOTH uncertain AND high-stakes, and collapses
    to ~0 when p is near 0 or 1 - so the gate is quiet at both ends, chatty in the middle.
    """
    p = min(max(float(p), 0.0), 1.0)
    loss_act = (1.0 - p) * costs.c_fp     # risk we acted on a healthy hive
    loss_hold = p * costs.c_fn            # risk we missed a real problem
    if loss_act < loss_hold:
        action, bayes_risk = "act", loss_act
    else:
        action, bayes_risk = "hold", loss_hold
    evpi = bayes_risk                     # perfect info -> the zero-loss action; EVPI = residual risk
    needs_human = evpi > costs.c_ask
    threshold = costs.c_fp / (costs.c_fp + costs.c_fn)   # autonomous act/hold flip point
    return {
        "p": round(p, 3), "action": action, "evpi": round(evpi, 2),
        "c_ask": costs.c_ask, "c_fn": costs.c_fn, "c_fp": costs.c_fp,
        "threshold": round(threshold, 3), "needs_human": bool(needs_human),
        "decision": "ask" if needs_human else ("auto_act" if action == "act" else "auto_hold"),
    }


def explain(gate: dict, condition: str = "varroa") -> str:
    """One plain, natural sentence for the beekeeper (no jargon, no math read aloud)."""
    name = {"varroa": "mites", "queenless": "the queen", "swarm": "swarming"}.get(condition, condition)
    if gate["needs_human"]:
        return (f"This is a close call on {name}, so your judgement is worth more than "
                f"the interruption right now. I'd like you to take a look and decide.")
    if gate["action"] == "act":
        return (f"I'm confident enough about {name} to act without bothering you - the "
                "safe choice here is clear.")
    return (f"Everything about {name} looks calm, so I'm leaving the colony alone and "
            "just keeping watch. No need to involve you.")


def infestation_probability(acoustic_stress: float, vision_rate: float,
                            vision_ran: bool, prior: float = 0.15) -> float:
    """Fuse the two independent sensors into a single belief p = P(infested), in [0,1].

    A simple, calibrated log-odds blend: the acoustic stress and (when it ran) the
    per-bee vision mite rate each shift the prior. Vision is the more direct evidence,
    so it carries more weight. Deterministic - this is the belief the VoI gate consumes.
    """
    def logit(x):
        x = min(max(x, 1e-6), 1 - 1e-6)
        return math.log(x / (1 - x))

    lo = logit(prior)
    a = min(max(float(acoustic_stress or 0.0), 0.0), 1.0)
    lo += 0.6 * (logit(a) - logit(0.5))                # acoustic nudge, centred at 0.5
    if vision_ran:
        k = 1.0 / max(VARROA_RATE_THRESHOLD, 1e-3)
        v = 1.0 / (1.0 + math.exp(-k * (float(vision_rate or 0.0) - VARROA_RATE_THRESHOLD)))
        lo += 1.0 * (logit(v) - logit(0.5))            # vision nudge (stronger weight)
    return 1.0 / (1.0 + math.exp(-lo))


# NOTE (future, do not block on it): the perfect-oracle EVPI above assumes the beekeeper
# is always right. For a rigorous version, model them as an imperfect oracle with
# reliability q and use Expected Value of Sample Information (EVSI), which scales the
# value of asking by roughly (2q - 1) for a symmetric binary oracle.


if __name__ == "__main__":
    # Worked examples from the spec - these are the unit checks (varroa, p* = 0.091).
    for p in (0.85, 0.12, 0.02, 0.01):
        g = voi_gate(p, COSTS["varroa"])
        print(f"p={p:<5} action={g['action']:<4} EVPI=${g['evpi']:<6} "
              f"c_ask=${g['c_ask']} -> {'ASK' if g['needs_human'] else 'AUTO'}")

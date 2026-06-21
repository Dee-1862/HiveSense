"""
The hive brain: ASI:One (asi1-mini) reasoning with a deterministic safety fallback.

Two judgment calls are delegated to the LLM (the human-like part):
  1. should_run_vision(acoustic, history) - is the cheap acoustic reading ambiguous
     enough to spend the expensive tunnel-vision test?
  2. reconcile(acoustic, vision, feedback) - acoustic and vision agree? clash? If they
     clash, set needs_human and write a plain-language reason for the beekeeper.

Everything obvious is handled deterministically; the LLM is only consulted for the
ambiguous middle. If ASI_ONE_API_KEY is unset or the call fails, we fall back to the
deterministic policy, so the fleet always runs - the LLM only makes it smarter.

Set the key:  export ASI_ONE_API_KEY=...   (https://asi1.ai)
"""

import os
import json

ASI1_URL = "https://api.asi1.ai/v1/chat/completions"
ASI1_MODEL = "asi1-mini"


def _chat(system, user):
    """Call asi1-mini and return its text, or None if no key / any failure."""
    key = os.getenv("ASI_ONE_API_KEY")
    if not key:
        return None
    try:
        import requests
        r = requests.post(
            ASI1_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": ASI1_MODEL, "temperature": 0.2,
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": user}]},
            timeout=20,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception:
        return None


def _extract_json(text):
    """Pull the first {...} JSON object out of an LLM reply."""
    if not text:
        return None
    try:
        start, end = text.index("{"), text.rindex("}") + 1
        return json.loads(text[start:end])
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# 1. when to spend the vision test
# --------------------------------------------------------------------------- #
ROUTINE_EVERY = 3  # run a vision spot-check at least this often, even if acoustic is calm


def should_run_vision(acoustic, history):
    sys = ("You are a beekeeping hive monitor. Acoustic sensing is cheap and always on; "
           "the tunnel vision test is more expensive. Run vision when the acoustic reading "
           "is ambiguous or elevated, AND also run a routine spot-check periodically so that "
           "mites visible on bees BEFORE any colony-wide acoustic stress are still caught. "
           "Reply with JSON only: {\"run_vision\": true|false, \"rationale\": \"<short>\"}.")
    usr = f"acoustic={acoustic}; cycles_seen={len(history)}; recent_history={history[-3:] if history else []}"
    out = _extract_json(_chat(sys, usr))
    if out is not None and "run_vision" in out:
        return bool(out["run_vision"]), str(out.get("rationale", "llm"))
    # deterministic fallback: look closer when acoustic is elevated OR on a routine cadence
    if acoustic["label"] in ("stressed", "watch"):
        return True, "fallback: acoustic elevated/ambiguous"
    if len(history) % ROUTINE_EVERY == 0:
        return True, "fallback: routine vision spot-check"
    return False, "fallback: acoustic clear, no routine check due"


# --------------------------------------------------------------------------- #
# 2. reconcile acoustic vs vision (the clash -> human path)
# --------------------------------------------------------------------------- #
def reconcile(acoustic, vision, feedback=None, similar=None):
    """Return {varroa_status, needs_human, reason}.

    acoustic is colony-level stress; vision is per-bee mite presence. They corroborate,
    they do not confirm the same physical event - so a disagreement is informative, not a
    failure, and is the trigger to ask a human.

    `similar` is an optional recall of this hive's most similar past states (from the
    Redis vector memory) - retrieval-augmented context the brain can weigh, e.g. a prior
    look-alike reading that a beekeeper later confirmed was a false alarm.
    """
    sys = ("You fuse two INDEPENDENT estimators of a bee colony's Varroa state: acoustic "
           "colony stress and per-bee vision mite rate. If both indicate a problem -> alert. "
           "If both look fine -> clear. If they DISAGREE, do not guess: set needs_human true "
           "so a beekeeper inspects. Consider any prior human feedback and any recalled "
           "similar past states. Reply JSON only: "
           '{"varroa_status": "clear|watch|alert", "needs_human": true|false, "reason": "<short, for a beekeeper>"}.')
    usr = f"acoustic={acoustic}; vision={vision}; prior_human_feedback={feedback or 'none'}"
    if similar:
        usr += f"; recalled_similar_past_states={similar}"
    out = _extract_json(_chat(sys, usr))
    if out is not None and "varroa_status" in out:
        return {"varroa_status": out["varroa_status"],
                "needs_human": bool(out.get("needs_human", False)),
                "reason": str(out.get("reason", ""))}
    return _reconcile_fallback(acoustic, vision)


def _reconcile_fallback(acoustic, vision):
    a_bad = acoustic["label"] == "stressed"
    a_mid = acoustic["label"] == "watch"
    v_bad = vision["label"] == "infested"
    if a_bad and v_bad:
        return {"varroa_status": "alert", "needs_human": False,
                "reason": "Acoustic stress and visible mites agree: treat this week."}
    if not a_bad and not a_mid and not v_bad:
        return {"varroa_status": "clear", "needs_human": False,
                "reason": "Acoustic calm and no visible mites."}
    if a_bad != v_bad:  # one says problem, the other says fine -> genuine clash
        return {"varroa_status": "watch", "needs_human": True,
                "reason": ("Signals disagree: acoustic="
                           f"{acoustic['label']} but vision={vision['label']}. "
                           "Please inspect and confirm.")}
    return {"varroa_status": "watch", "needs_human": False,
            "reason": "Mild/early signal; keep watching."}


def using_llm():
    return bool(os.getenv("ASI_ONE_API_KEY"))

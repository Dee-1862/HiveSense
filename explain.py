"""
Plain-English explainer for beekeepers.

Turns a technical log line or term (e.g. "5s window - stress 61 - SSD vector pushed")
into simple language a non-technical hive manager understands. Deterministic glossary
first (instant, no API key), with an optional LLM fallback for anything unmatched.

Used by the dashboard: put an "explain this" / "?" control on each log line and call
GET /api/explain?q=<line>.
"""

import os
import re

# Ordered rules: first match wins. Patterns run against the lowercased line.
RULES = [
    (r"set hive:?\s*(\w+).*state\s+(\w+)",
     lambda m: f"Saved hive {m.group(1).upper()}'s overall status as '{m.group(2)}'."),
    (r"(\d+)\s*s window.*stress\s+(\d+)",
     lambda m: f"Listened to {m.group(1)} seconds of hive sound; the colony's stress level is {m.group(2)} out of 100."),
    (r"traffic\s+(\d+)\s*bees/min.*\b(up|down|steady)\b",
     lambda m: f"About {m.group(1)} bees a minute are moving at the entrance, and that's trending {m.group(2)}."),
    (r"frame\s+\d+.*?(\d+)\s*bees.*?(\d+)\s*mites",
     lambda m: f"The camera checked a video frame: {m.group(1)} bees seen, {m.group(2)} with visible mites."),
    (r"treatment wf step\s*(\d+)\s*/\s*(\d+).*approval",
     lambda m: f"A mite treatment plan is waiting for your approval, currently on step {m.group(1)} of {m.group(2)}."),
    (r"fusion confirmed\s*([\d.]+)",
     lambda m: f"Combining the sound and camera evidence, the system is {round(float(m.group(1)) * 100)}% sure."),
    (r"signals within baseline",
     lambda m: "All of this hive's signals look normal, so there is nothing you need to do."),
    (r"pre-?swarm",
     lambda m: "This hive may be about to swarm, which means the old queen would leave with about half the bees, so check it for queen cells soon."),
    (r"wasp pressure high|robbing",
     lambda m: "Wasps or robber bees are crowding this hive's entrance, so it may be getting raided and you should consider narrowing the entrance."),
    (r"awaiting (beekeeper )?approval",
     lambda m: "An action is waiting for you to approve it before it goes ahead."),
    (r"queenless",
     lambda m: "This colony seems to have lost its queen and will likely need a new one introduced."),
    (r"deformed.?wing|\bdwv\b",
     lambda m: "This refers to Deformed Wing Virus, a serious bee disease that is spread by Varroa mites."),
    (r"swarm",
     lambda m: "This is a swarming signal, which means the colony may split and a large group of bees may fly off."),
    (r"varroa",
     lambda m: "Varroa mites are the main parasite that weakens and eventually kills honey bee colonies."),
    (r"ssd vector pushed|vector",
     lambda m: "The system saved this hive's sound fingerprint so it can spot changes over time."),
    (r"mic armed|field copilot|deepgram",
     lambda m: "The voice assistant is on standby and ready to answer questions."),
    (r"redis|blackboard|heartbeat",
     lambda m: "This is an internal note that the monitoring system is running normally, so there is nothing for you to do."),
]

SYSTEM = (
    "You explain beehive monitoring logs to a non-technical beekeeper. Given one log line, "
    "reply with one to three complete, plain sentences. Do not use jargon, dashes, or "
    "bullet fragments. Write it as flowing prose that says what it means for the bees and "
    "whether the beekeeper needs to do anything."
)


def _chat(system, user, max_tokens=160):
    """Generic LLM call (ASI:One / Gemini / Claude). Returns text, or None if no key / failure."""
    try:
        if os.getenv("ASI_ONE_API_KEY"):
            from openai import OpenAI
            c = OpenAI(base_url="https://api.asi1.ai/v1", api_key=os.getenv("ASI_ONE_API_KEY"))
            r = c.chat.completions.create(model="asi1", max_tokens=max_tokens, messages=[
                {"role": "system", "content": system}, {"role": "user", "content": user}])
            return r.choices[0].message.content.strip()
        if os.getenv("GEMINI_API_KEY"):
            from openai import OpenAI
            c = OpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                       api_key=os.getenv("GEMINI_API_KEY"))
            r = c.chat.completions.create(model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                                          max_tokens=max_tokens, messages=[
                {"role": "system", "content": system}, {"role": "user", "content": user}])
            return r.choices[0].message.content.strip()
        if os.getenv("ANTHROPIC_API_KEY"):
            import anthropic
            m = anthropic.Anthropic().messages.create(
                model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest"),
                max_tokens=max_tokens, system=system, messages=[{"role": "user", "content": user}])
            return "".join(b.text for b in m.content if getattr(b, "type", None) == "text").strip()
    except Exception:
        return None
    return None


def _llm_explain(line):
    return _chat(SYSTEM, line, 120)


# ---- agentic advisor: tailored recommendation from a hive's live readings ----
ADVISE_SYS = (
    "You are an experienced beekeeping advisor. Given one colony's current readings, give the "
    "beekeeper specific, practical, prioritised advice in two to four complete sentences. Use plain "
    "language with no jargon, no dashes, and no bullet points. If nothing is wrong, reassure them briefly."
)


def _advise_fallback(p):
    st = str(p.get("status", "")).lower()
    q = str(p.get("queen", "")).lower()
    try:
        mite = float(p.get("mite", 0) or 0)
    except (TypeError, ValueError):
        mite = 0.0
    if "queenless" in q:
        return ("This colony appears to have lost its queen, so introduce a mated queen or a frame of "
                "young eggs within about 72 hours, because without eggs it cannot raise its own.")
    if "swarm" in q or "pre-swarm" in st:
        return ("This colony is showing swarm signs, so inspect it for queen cells within 48 hours and "
                "either add space or make a split so you keep the bees.")
    if st == "crit" or mite > 3:
        return (f"The mite load is about {p.get('mite')} per 100 bees, which is above the treatment line, "
                "so plan a treatment such as oxalic acid this week while brood is low, then re-test in "
                "about two weeks.")
    if st == "watch":
        return ("One signal is drifting, so keep a close eye on this colony and re-check it in about a "
                "week before deciding on any action.")
    return "This colony looks healthy, so simply keep it on your normal inspection schedule."


def advise(p: dict) -> str:
    situation = (f"Hive {p.get('hive')} ({p.get('name')}): overall status {p.get('status')}, "
                 f"mite load {p.get('mite')} per 100 bees, colony stress {p.get('stress')} out of 100, "
                 f"queen status {p.get('queen')}, net entrance flow {p.get('traffic')} bees per cycle.")
    return _chat(ADVISE_SYS, situation, 200) or _advise_fallback(p)


def explain(line: str, use_llm: bool = True) -> str:
    low = (line or "").lower()
    for pat, fn in RULES:
        m = re.search(pat, low)
        if m:
            return fn(m)
    if use_llm:
        ans = _llm_explain(line)
        if ans:
            return ans
    return ("This is a routine status message from the hive monitor. No action is needed unless "
            "it mentions an alert or asks for your approval.")


if __name__ == "__main__":
    for ln in ["SET hive:A3:state crit", "5s window - stress 61 - SSD vector pushed",
               "pre-swarm - inspect for queen cells", "wasp pressure HIGH - robbing risk",
               "traffic 130 bees/min - steady", "frame 4208 - 26 bees - 0 mites"]:
        print(f"{ln}\n  -> {explain(ln, use_llm=False)}\n")

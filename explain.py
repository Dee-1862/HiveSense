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
     lambda m: f"A mite-treatment plan is waiting for your approval (step {m.group(1)} of {m.group(2)})."),
    (r"fusion confirmed\s*([\d.]+)",
     lambda m: f"Combining the sound and camera evidence, the system is {round(float(m.group(1)) * 100)}% sure."),
    (r"signals within baseline",
     lambda m: "All of this hive's signals look normal - nothing to worry about."),
    (r"pre-?swarm",
     lambda m: "This hive may be about to swarm (the old queen leaves with half the bees). Check it for queen cells."),
    (r"wasp pressure high|robbing",
     lambda m: "Wasps or robber bees are crowding this hive's entrance - it may be getting raided."),
    (r"awaiting (beekeeper )?approval",
     lambda m: "An action is waiting for you to approve it."),
    (r"queenless",
     lambda m: "This colony seems to have lost its queen and may need a new one."),
    (r"deformed.?wing|\bdwv\b",
     lambda m: "Deformed Wing Virus - a bee disease spread by Varroa mites."),
    (r"swarm",
     lambda m: "A swarming signal - the colony may split and fly off."),
    (r"varroa",
     lambda m: "Varroa mites - the main parasite that weakens and kills colonies."),
    (r"ssd vector pushed|vector",
     lambda m: "The system saved this hive's sound 'fingerprint' so it can spot changes over time."),
    (r"mic armed|field copilot|deepgram",
     lambda m: "The voice assistant is on standby, ready to listen."),
    (r"redis|blackboard|heartbeat",
     lambda m: "An internal system note that the monitoring service is running - nothing you need to act on."),
]

SYSTEM = (
    "You explain beehive monitoring logs to a non-technical beekeeper. Given one log line, "
    "reply with ONE or TWO short plain-English sentences, no jargon, no numbers-only answers. "
    "Say plainly what it means for the bees and whether they need to do anything."
)


def _llm_explain(line):
    """Optional LLM fallback (ASI:One / Gemini / Claude). Returns None if no key / failure."""
    try:
        if os.getenv("ASI_ONE_API_KEY"):
            from openai import OpenAI
            c = OpenAI(base_url="https://api.asi1.ai/v1", api_key=os.getenv("ASI_ONE_API_KEY"))
            r = c.chat.completions.create(model="asi1", max_tokens=120, messages=[
                {"role": "system", "content": SYSTEM}, {"role": "user", "content": line}])
            return r.choices[0].message.content.strip()
        if os.getenv("GEMINI_API_KEY"):
            from openai import OpenAI
            c = OpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                       api_key=os.getenv("GEMINI_API_KEY"))
            r = c.chat.completions.create(model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                                          max_tokens=120, messages=[
                {"role": "system", "content": SYSTEM}, {"role": "user", "content": line}])
            return r.choices[0].message.content.strip()
        if os.getenv("ANTHROPIC_API_KEY"):
            import anthropic
            m = anthropic.Anthropic().messages.create(
                model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest"),
                max_tokens=120, system=SYSTEM, messages=[{"role": "user", "content": line}])
            return "".join(b.text for b in m.content if getattr(b, "type", None) == "text").strip()
    except Exception:
        return None
    return None


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

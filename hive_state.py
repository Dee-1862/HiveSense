"""
Shared apiary state for the ASI:One agent.

The hive fleet / coordinator writes the latest verdicts to data/verdicts.json; the
ASI:One agent reads them here and turns them into a short status string it can put in
the LLM prompt (or return directly when no LLM is available). This file is the only
coupling between the chat agent and the monitoring fleet - a simple shared store, no
network needed.
"""

import os
import json

ROOT = os.path.dirname(os.path.abspath(__file__))
VERDICTS_FILE = os.path.join(ROOT, "data", "verdicts.json")


def load_verdicts():
    """Return {hive_id: [verdict, ...]} from the shared store, or {} if unavailable."""
    try:
        with open(VERDICTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_verdicts(verdicts):
    """Write the verdicts store (called by the coordinator as verdicts arrive)."""
    os.makedirs(os.path.dirname(VERDICTS_FILE), exist_ok=True)
    with open(VERDICTS_FILE, "w", encoding="utf-8") as f:
        json.dump(verdicts, f, indent=2)


def append_verdict(verdict: dict, max_points: int = 96):
    """Append one live verdict to its hive's rolling history (keeps the 24h seed).

    Loads the existing store, appends to verdict['hive_id'], trims to the last
    `max_points`, and saves. This lets the live fleet extend the history without
    wiping the seeded 24 hours.
    """
    hive = verdict.get("hive_id")
    if not hive:
        return
    verdicts = load_verdicts()
    hist = verdicts.get(hive, [])
    if not isinstance(hist, list):
        hist = [hist]
    hist.append(verdict)
    verdicts[hive] = hist[-max_points:]
    save_verdicts(verdicts)


def apiary_summary(verdicts=None):
    """Plain-text status of every hive, flagging any that need a human inspection."""
    verdicts = load_verdicts() if verdicts is None else verdicts
    if not verdicts:
        return "No live hive data is available yet (the monitoring fleet may be offline)."

    lines, needs = [], []
    for hid, hist in sorted(verdicts.items()):
        v = hist[-1] if isinstance(hist, list) and hist else hist
        if not isinstance(v, dict):
            continue
        flag = ""
        if v.get("needs_human"):
            needs.append(hid)
            flag = f"  [NEEDS INSPECTION: {v.get('reason', '')}]"
        lines.append(
            f"- Hive {hid}: varroa={v.get('varroa_status', '?')}, "
            f"queenless={v.get('queenless_alert', '?')}, swarm={v.get('swarm_alert', '?')}, "
            f"net_traffic={v.get('traffic', '?')}{flag}"
        )

    header = "Current apiary status (live):"
    if needs:
        header += f" {len(needs)} hive(s) need inspection: {', '.join(needs)}."
    return header + "\n" + "\n".join(lines)

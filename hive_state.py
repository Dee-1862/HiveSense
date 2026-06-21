"""
Shared apiary state for the dashboard, fleet and ASI:One agent.

The hive fleet / coordinator writes the latest verdicts here; the dashboard API and
the ASI:One agent read them back. This file is the only coupling between the chat
agent and the monitoring fleet - a simple shared store, no network needed.

The actual storage is now pluggable (see src/store): with USE_REDIS=1 it is backed
by Redis Stack, otherwise by data/verdicts.json. The functions below keep their old
signatures so every existing caller (coordinator, godfather, api_server, asi1_agent)
works unchanged - they just delegate to the selected backend.
"""

import os

from src.store import get_store

ROOT = os.path.dirname(os.path.abspath(__file__))


def load_verdicts():
    """Return {hive_id: [verdict, ...]} from the shared store, or {} if unavailable."""
    return get_store().load_verdicts()


def save_verdicts(verdicts):
    """Write the verdicts store (called by the coordinator as verdicts arrive)."""
    return get_store().save_verdicts(verdicts)


def append_verdict(verdict: dict, max_points: int = 96):
    """Append one live verdict to its hive's rolling history (keeps the 24h seed)."""
    return get_store().append_verdict(verdict, max_points)


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

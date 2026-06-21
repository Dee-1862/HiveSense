"""
The Godfather: apiary-level orchestration logic.

Each hive agent decides about its OWN hive. The godfather looks across ALL hives and
produces the apiary-wide picture no single hive can see: regional Varroa spread,
neighbour robbing (influx at one hive vs outflux next door), and a prioritised action
list for the beekeeper. Pure functions over the verdict store, so the live feed, the
API server, and the ASI:One agent all share one brain.
"""

NEIGHBOR_DIST = 10.0   # metres; closer hives can rob each other
FLOW_THRESHOLD = 50    # net bees/cycle that counts as a real surge or drain


def _latest(verdicts):
    out = {}
    for h, hist in verdicts.items():
        v = hist[-1] if isinstance(hist, list) and hist else hist
        if isinstance(v, dict):
            out[h] = v
    return out


def _dist(p, q):
    if not p or not q or len(p) < 2 or len(q) < 2:
        return float("inf")
    return ((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2) ** 0.5


def apiary_analysis(verdicts: dict) -> dict:
    """Return the apiary-wide picture: counts, emergent patterns, priorities, headline."""
    latest = _latest(verdicts)
    n = len(latest)

    alerts = [h for h, v in latest.items() if v.get("varroa_status") == "alert"]
    watches = [h for h, v in latest.items() if v.get("varroa_status") == "watch"]
    needs_human = [h for h, v in latest.items() if v.get("needs_human")]
    queenless = [h for h, v in latest.items() if v.get("queenless_alert")]
    swarming = [h for h, v in latest.items() if v.get("swarm_alert")]

    # emergent: regional varroa pressure across the yard
    emergent = []
    if len(alerts) + len(watches) >= 2:
        emergent.append(f"Regional Varroa pressure across {sorted(alerts + watches)} - treat the row, not one hive.")

    # emergent: possible robbing between neighbours (influx vs outflux)
    robbing = []
    hids = list(latest)
    for i in range(len(hids)):
        for j in range(i + 1, len(hids)):
            a, b = latest[hids[i]], latest[hids[j]]
            if _dist(a.get("position"), b.get("position")) > NEIGHBOR_DIST:
                continue
            ta, tb = a.get("traffic", 0), b.get("traffic", 0)
            if ta >= FLOW_THRESHOLD and tb <= -FLOW_THRESHOLD:
                robbing.append((hids[j], hids[i]))   # (robbed, robber)
            elif tb >= FLOW_THRESHOLD and ta <= -FLOW_THRESHOLD:
                robbing.append((hids[i], hids[j]))
    for robbed, robber in robbing:
        emergent.append(f"Possible robbing: {robbed} draining while neighbour {robber} surges.")

    # prioritised actions (most urgent first)
    priorities = []
    for h in needs_human:
        priorities.append({"hive": h, "action": "inspect", "why": latest[h].get("reason", "needs inspection")})
    for h in alerts:
        priorities.append({"hive": h, "action": "treat varroa", "why": "mite load over the economic threshold"})
    for h in queenless:
        priorities.append({"hive": h, "action": "requeen", "why": "queenless signature"})
    for h in swarming:
        priorities.append({"hive": h, "action": "swarm control", "why": "pre-swarm signal"})

    parts = []
    if alerts:
        parts.append(f"{len(alerts)} on Varroa alert ({', '.join(sorted(alerts))})")
    if needs_human:
        parts.append(f"{len(needs_human)} need inspection ({', '.join(sorted(needs_human))})")
    if queenless:
        parts.append(f"{len(queenless)} queenless ({', '.join(sorted(queenless))})")
    if swarming:
        parts.append(f"{len(swarming)} swarming ({', '.join(sorted(swarming))})")
    healthy = n - len(set(alerts + watches + needs_human + queenless + swarming))
    headline = (f"Apiary: {n} hives, {healthy} healthy. " + ("; ".join(parts) + "."
                if parts else "All hives nominal.")
                + (f" Top priority: {priorities[0]['hive']} ({priorities[0]['action']})." if priorities else ""))

    return {
        "n_hives": n, "healthy": healthy,
        "alerts": sorted(alerts), "watches": sorted(watches),
        "needs_human": sorted(needs_human), "queenless": sorted(queenless),
        "swarming": sorted(swarming),
        "emergent": emergent, "priorities": priorities, "headline": headline,
    }


if __name__ == "__main__":
    import hive_state
    a = apiary_analysis(hive_state.load_verdicts())
    print(a["headline"])
    for e in a["emergent"]:
        print(" -", e)
    for p in a["priorities"]:
        print(f"   * {p['hive']}: {p['action']} ({p['why']})")

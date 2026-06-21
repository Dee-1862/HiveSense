"""
HiveDoctor demo - the agent that knows when NOT to ask (Value-of-Information gate).

  python demo_hive_doctor.py            # show the VoI decision for every hive
  python demo_hive_doctor.py A3         # one hive, then the approval gate if it asks
  AGENTSPAN_LIVE=1 python demo_hive_doctor.py A3   # run on the live Agentspan engine
                                                   # (after: agentspan server start)

The gate (src/agentspan/voi.py) weighs the value of the beekeeper's input against the
cost of interrupting them, so it stays quiet when confident and asks only on close calls.
When it asks, Agentspan holds the pause durably. Grounded in "Value of Information: A
Framework for Human-Agent Communication" (arXiv 2601.06407, Jan 2026).
"""

import sys

import hive_state
from src.agentspan import hive_doctor as hd


def main():
    args = sys.argv[1:]
    if args:
        plan = hd.run_cli(args[0])
        if plan["decision"] != "ask":
            return  # confident: the agent handled it without us
        run = hd.start(args[0])
        if run["status"] != "awaiting_approval":
            return
        print("\n--- human-in-the-loop gate (Agentspan would hold this durably) ---")
        ans = input("Treat this hive? [y/N] ").strip().lower()
        out = hd.respond(run["id"], approve=ans in ("y", "yes"), note="decided from CLI")
        print("resolved:", out["status"], "->", out.get("result"))
        return

    verdicts = hive_state.load_verdicts()
    if not verdicts:
        print("No verdicts in the store yet. Run:  python seed_apiary.py")
        return
    print(f"HiveDoctor VoI sweep over {len(verdicts)} hives "
          f"(Agentspan {'available' if hd.HAS_AGENTSPAN else 'not installed - gate still runs'}):\n")
    tag = {"ask": "ASK YOU", "auto_act": "ACT  ", "auto_hold": "WATCH"}
    for hive_id in verdicts:
        p = hd.compute_decision(hive_id)
        print(f"[{tag[p['decision']]}] {p['headline']}")


if __name__ == "__main__":
    main()

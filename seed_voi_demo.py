"""
Give the apiary a spread of severities so the Value-of-Information gate visibly does its
job: stay quiet when confident, ask only on close calls.

Each hive's LATEST acoustic/vision reading is set to a designed scenario (the rest of its
24h history is left untouched). Re-runnable and reversible (data/verdicts.json is tracked
in git: `git checkout data/verdicts.json` to undo). This only changes simulated demo data,
not any model.

  python seed_voi_demo.py        # then: python demo_hive_doctor.py   (or open the dashboard)

Expected outcome with the paper's default costs (varroa c_fn=150, c_fp=15, c_ask=3):
  - very calm hives        -> AUTO-HOLD (agent watches, never bothers you)
  - clearly infested hives -> AUTO-ACT  (agent treats on its own, no interruption)
  - genuine close calls    -> ASK YOU   (durable Agentspan approval pause)
"""

import hive_state
from src.agentspan import hive_doctor as hd

# (acoustic_stress, vision_mite_rate, vision_ran) per hive - chosen to span the VoI regimes
SCENARIOS = {
    "A1": (0.01, 0.00, False),   # dead calm            -> auto-hold
    "C1": (0.02, 0.00, False),   # calm                 -> auto-hold
    "B1": (0.85, 0.12, True),    # both sensors high    -> auto-act (clearly infested)
    "A2": (0.80, 0.11, True),    # both sensors high    -> auto-act
    "A3": (0.75, 0.00, True),    # sound says yes, camera says no (disagree) -> ask
    "B2": (0.55, 0.00, False),   # middling sound only  -> ask
    "B3": (0.60, 0.04, True),    # mixed, just over the line -> ask
}


def main():
    verdicts = hive_state.load_verdicts()
    if not verdicts:
        print("No verdicts yet. Run:  python seed_apiary.py")
        return
    for hive_id, (ac, vr, ran) in SCENARIOS.items():
        hist = verdicts.get(hive_id)
        if not hist:
            continue
        latest = dict(hist[-1])
        latest["acoustic_stress"] = ac
        latest["vision_mite_rate"] = vr
        latest["vision_ran"] = ran
        hist[-1] = latest
        verdicts[hive_id] = hist
    hive_state.save_verdicts(verdicts)

    print("Seeded VoI demo scenarios. Decisions now:")
    tag = {"ask": "ASK YOU", "auto_act": "ACT", "auto_hold": "WATCH"}
    for hive_id in SCENARIOS:
        p = hd.compute_decision(hive_id)
        g = p["varroa"]
        print(f"  {hive_id}: p={g['p']:.2f}  EVPI=${g['evpi']:.2f} vs ${g['c_ask']}"
              f"  -> {tag[p['decision']]}")


if __name__ == "__main__":
    main()

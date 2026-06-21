"""
Run the live multi-agent apiary: 7 hive reasoning agents + the Godfather, in ONE Bureau.

Each hive agent reads its realistic per-hive feed (feed.py), runs genuine reasoning
(acoustic -> decide vision -> reconcile -> escalate), and sends a Verdict to the Godfather.
The Godfather appends every verdict to the shared store (data/verdicts.json) and runs the
apiary-wide analysis in turn. Keeping them in one Bureau means the agent-to-agent
messaging is local and robust - NO mailbox/Agentverse needed for the orchestration.

Then, separately:
  - python api_server.py     -> serves /api/status + /api/apiary to the dashboard
  - python asi1_agent.py     -> ASI:One chat (the one agent that goes on Agentverse)

Run:  python seed_apiary.py   (once, lays down 24h history)
      python -m src.agents.run_fleet
Optional: VIT4V_CLIP=/path/to/clip.mkv makes the first hive run the REAL Vit4V model.
"""

import os
from uagents import Bureau
from src.agents.hive_agent import create_hive_agent
from src.agents.coordinator import create_godfather
from src.agents.feed import POSITIONS

VIT4V_CLIP = os.getenv("VIT4V_CLIP")          # if set, hive A1 uses the real vision model
PERIOD = float(os.getenv("HIVE_PERIOD", "8"))  # seconds between each hive's cycles


def main():
    bureau = Bureau(endpoint=["http://127.0.0.1:8003/submit"], port=8003)

    godfather = create_godfather()
    bureau.add(godfather)
    print(f"Godfather: {godfather.address}")

    for i, (code, pos) in enumerate(POSITIONS.items()):
        agent = create_hive_agent(
            hive_id=code,
            seed=f"hivesense_hive_{code}_seed",
            coordinator_address=godfather.address,
            position=pos,
            clip_path=VIT4V_CLIP if i == 0 else None,
            period=PERIOD,
        )
        bureau.add(agent)
        print(f"  hive {code} -> {agent.address}")

    print(f"\n7 hive agents reasoning every {PERIOD:.0f}s; Godfather aggregating. Ctrl+C to stop.")
    bureau.run()


if __name__ == "__main__":
    main()

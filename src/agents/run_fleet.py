"""
Run the 7 reasoning hive agents (one brain per hive) in a single Bureau.

Hive ids reuse the dashboard's tile codes (A1..C1), so each Verdict maps straight onto a
dashboard tile without any frontend change (the frontend upper-cases the hive id to a code).
Run the coordinator separately:  python -m src.agents.run_coordinator

Optional: set VIT4V_CLIP=/path/to/clip.mkv to make ONE hive run the real Vit4V model on a
VD2 clip instead of the stub vision feed (nice for a live demo).
Optional: set ASI_ONE_API_KEY to enable LLM reasoning (otherwise deterministic fallback).
"""

import os
from uagents import Bureau, Agent
from src.agents.hive_agent import create_hive_agent

COORD_SEED = "hivesense_coordinator_seed"
COORDINATOR_ADDRESS = Agent(seed=COORD_SEED).address

# 7 hives, positioned in a 3-row yard; codes match the dashboard tiles.
HIVES = [
    ("A1", [0.0, 0.0]), ("A2", [3.0, 0.0]), ("A3", [6.0, 0.0]),
    ("B1", [0.0, 3.0]), ("B2", [3.0, 3.0]), ("B3", [6.0, 3.0]),
    ("C1", [0.0, 6.0]),
]

VIT4V_CLIP = os.getenv("VIT4V_CLIP")  # if set, the first hive uses the real vision model


def main():
    bureau = Bureau(endpoint=["http://127.0.0.1:8003/submit"], port=8003)
    for i, (code, pos) in enumerate(HIVES):
        agent = create_hive_agent(
            hive_id=code,
            seed=f"hivesense_hive_{code}_seed",
            coordinator_address=COORDINATOR_ADDRESS,
            position=pos,
            clip_path=VIT4V_CLIP if i == 0 else None,
        )
        bureau.add(agent)
        print(f"hive {code} -> {agent.address}")

    print(f"\nCoordinator address: {COORDINATOR_ADDRESS}")
    print(f"Reasoning: {'ASI:One asi1-mini' if os.getenv('ASI_ONE_API_KEY') else 'deterministic fallback (set ASI_ONE_API_KEY for LLM)'}")
    bureau.run()


if __name__ == "__main__":
    main()

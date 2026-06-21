import os
from src.agents.coordinator import create_coordinator

# Deterministic seed
COORD_SEED = "hivesense_coordinator_seed"
# PORT defaults to 8000 (what the dashboard proxies to). If the frontend session is
# already holding 8000 with its mock, run the real coordinator elsewhere: set PORT=8001.
PORT = int(os.getenv("PORT", "8000"))
# Connectivity:
#   AGENT_ENDPOINT=<public url>/submit -> self-hosted mode (for the Agentverse "Agent
#                                         Endpoint URL" form; e.g. an ngrok https tunnel).
#   MAILBOX=1 (default)                -> Agentverse mailbox (no public URL needed).
#   MAILBOX=0                          -> pure local dev (no Agentverse, no 401 noise).
ENDPOINT = os.getenv("AGENT_ENDPOINT")  # e.g. https://xxxx.ngrok-free.app/submit
USE_MAILBOX = os.getenv("MAILBOX", "1") != "0"

def main():
    coordinator_agent = create_coordinator(
        agent_name="hivesense_coordinator",
        seed=COORD_SEED,
        port=PORT,
        mailbox=USE_MAILBOX,
        endpoint=ENDPOINT,
    )

    mode = f"self-hosted endpoint {ENDPOINT}" if ENDPOINT else ("mailbox" if USE_MAILBOX else "local dev")
    print(f"Starting Fleet Coordinator ({mode})...")
    print(f"Coordinator address: {coordinator_agent.address}")
    
    # We run the coordinator. agent.run() handles standard operations including registration if configured.
    coordinator_agent.run()

if __name__ == "__main__":
    main()

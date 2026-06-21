"""
Register the running coordinator's mailbox on Agentverse WITHOUT the website button.

The repeating `401: Could not validate credentials` means the agent's mailbox was never
registered. The Inspector "Connect" button just POSTs your Agentverse API key to the
agent's local /connect endpoint - which can fail silently if the HTTPS inspector page is
blocked from calling http://127.0.0.1 (mixed content). This script does the same POST
directly, so it always works.

Steps:
  1. Get an API key: https://agentverse.ai  ->  profile / API Keys (Mailroom).
  2. Start the coordinator:   python -m src.agents.run_coordinator   (leave it running)
  3. In another terminal:     AGENTVERSE_API_KEY=<key> python -m src.agents.connect_mailbox
After it prints success, the 401 loop in the coordinator stops within a few seconds.
"""

import os
import sys
import requests

CONNECT_URL = os.getenv("AGENT_CONNECT_URL", "http://127.0.0.1:8000/connect")


def main():
    key = os.getenv("AGENTVERSE_API_KEY") or (sys.argv[1] if len(sys.argv) > 1 else None)
    if not key:
        sys.exit("Set AGENTVERSE_API_KEY=<key> (or pass it as the first argument). "
                 "Get one at https://agentverse.ai -> API Keys.")
    # agent_type 'mailbox' tells Agentverse this is a locally-hosted mailbox agent.
    # If the API rejects it, retry with AGENT_TYPE=uagent.
    payload = {"user_token": key, "agent_type": os.getenv("AGENT_TYPE", "mailbox")}
    try:
        r = requests.post(CONNECT_URL, json=payload, timeout=30)
    except requests.exceptions.ConnectionError:
        sys.exit(f"Could not reach {CONNECT_URL}. Is the coordinator running "
                 "(python -m src.agents.run_coordinator)?")
    print("status:", r.status_code)
    print("response:", r.text)
    if r.ok:
        print("\nMailbox registration sent. Watch the coordinator: the 401 loop should stop "
              "and ASI:One can now route chat to it.")


if __name__ == "__main__":
    main()

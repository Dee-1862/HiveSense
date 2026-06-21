"""
HiveSense - HOSTED Agentverse agent (no local mailbox, no 401).

Deploy on Agentverse so it runs on their infra and ASI:One can reach it directly:
  1. agentverse.ai -> Agents -> + New Agent -> Blank Agent (Hosted).
  2. Paste this whole file into the editor.
  3. In the agent's Secrets, add:  ASI_ONE_API_KEY = <your asi1 key>
  4. Click Run. Then use "Chat with Agent" / ASI:One.

Hosted agents have a restricted package set, so this uses only `requests` for the LLM
call (not the openai SDK). Live local hive data can't be read from Agentverse, so a
representative apiary snapshot is embedded; the live dashboard shows the real-time data.
"""

import os
from datetime import datetime
from uuid import uuid4

import requests
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    TextContent,
    chat_protocol_spec,
)

ASI_ONE_API_KEY = os.environ.get("ASI_ONE_API_KEY", "")

# Representative apiary snapshot (hosted agents can't read your local files).
APIARY_SNAPSHOT = (
    "Current apiary snapshot: 7 hives. A3 is on Varroa ALERT (treat this week). "
    "B1 needs inspection (acoustic stress but vision sees no mites - signals disagree). "
    "B2 shows a swarm signal. B3 reads queenless. A1, A2, C1 are healthy."
)

SYSTEM_PROMPT = (
    "You are the HiveSense apiary assistant: an expert on beehive health, Varroa mites, "
    "queen status, swarming, and bee acoustics. Use the apiary snapshot below to answer "
    "questions about the user's hives; for general bee questions, answer from expertise. "
    "Keep replies concise and practical.\n\n" + APIARY_SNAPSHOT
)


def ask_llm(question: str) -> str:
    if not ASI_ONE_API_KEY:
        return ("(No ASI_ONE_API_KEY secret set.) " + APIARY_SNAPSHOT)
    try:
        r = requests.post(
            "https://api.asi1.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {ASI_ONE_API_KEY}",
                     "Content-Type": "application/json"},
            json={"model": "asi1",
                  "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                               {"role": "user", "content": question}],
                  "max_tokens": 2048},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"I could not reach the language model right now. {APIARY_SNAPSHOT} (error: {e})"


agent = Agent(name="hivesense", seed=os.environ.get("AGENT_SEED", "hivesense-hosted-seed-v1"))

protocol = Protocol(spec=chat_protocol_spec)


@protocol.on_message(ChatMessage)
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(sender, ChatAcknowledgement(
        timestamp=datetime.now(), acknowledged_msg_id=msg.msg_id))
    question = "".join(i.text for i in msg.content if isinstance(i, TextContent))
    ctx.logger.info(f"Chat query: {question}")
    answer = ask_llm(question)
    await ctx.send(sender, ChatMessage(
        timestamp=datetime.utcnow(),
        msg_id=uuid4(),
        content=[TextContent(type="text", text=answer),
                 EndSessionContent(type="end-session")],
    ))


@protocol.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    pass


agent.include(protocol, publish_manifest=True)

if __name__ == "__main__":
    agent.run()

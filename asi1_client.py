"""
Local test client for asi1_agent.py (from the Fetch.ai ASI:One guide).

Sends one ChatMessage to the HiveSense agent and prints its reply - lets you test the
agent WITHOUT ASI:One/Agentverse. Run the agent first (python asi1_agent.py), then:
    python asi1_client.py

AI_AGENT_ADDRESS is the address of asi1_agent.py (derived from its seed). If you change
the agent's seed, update this address (run:
  python -c "from uagents import Agent; print(Agent(seed='<seed>').address)").
"""

from datetime import datetime
from uuid import uuid4

from uagents import Agent, Context
from uagents_core.contrib.protocols.chat import (
    ChatMessage, ChatAcknowledgement, TextContent,
)

AI_AGENT_ADDRESS = "agent1qt5wrurzefxsk0y50yaw29awtn5n9fwl6jhqtrth6pzpafufy95ak0kktlf"
QUESTION = "How do I tell if my hive has a Varroa mite problem?"

agent = Agent(
    name="hivesense-test-client",
    seed="hivesense-asi1-client-seed-v1",
    port=8002,
    endpoint=["http://127.0.0.1:8002/submit"],
)


@agent.on_event("startup")
async def send_message(ctx: Context):
    ctx.logger.info(f"Asking the agent: {QUESTION}")
    await ctx.send(AI_AGENT_ADDRESS, ChatMessage(
        timestamp=datetime.now(),
        msg_id=uuid4(),
        content=[TextContent(type="text", text=QUESTION)],
    ))


@agent.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    ctx.logger.info(f"Acknowledged by {sender} for {msg.acknowledged_msg_id}")


@agent.on_message(ChatMessage)
async def handle_reply(ctx: Context, sender: str, msg: ChatMessage):
    for item in msg.content:
        if isinstance(item, TextContent):
            ctx.logger.info(f"Reply from agent:\n{item.text}")


if __name__ == "__main__":
    agent.run()

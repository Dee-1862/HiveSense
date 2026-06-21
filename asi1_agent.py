"""
HiveSense ASI:One agent - canonical Fetch.ai ASI:One example
(https://uagents.fetch.ai/docs/examples/asi-1), upgraded to answer from LIVE hive data.

It pulls the latest verdicts (hive_state.py reads data/verdicts.json, which the fleet
writes) and injects them into the prompt, so "how are my bees?" returns the real apiary
status, not generic advice.

LLM brain (no OpenAI account is ever needed - the OpenAI SDK is just pointed at ASI:One):
  - ASI_ONE_API_KEY set -> replies via ASI:One `asi1`           (https://asi1.ai/developer)
  - else ANTHROPIC_API_KEY set -> replies via Anthropic Claude  (https://console.anthropic.com)
  - else NO key -> still answers, deterministically, straight from the hive data.

Setup:  pip install uagents openai anthropic
        $env:ASI_ONE_API_KEY="<key>"   (or $env:ANTHROPIC_API_KEY="<key>")
        python asi1_agent.py
Then open the inspector link, Connect -> Mailbox, and chat from https://asi1.ai.
"""

import os
from datetime import datetime
from uuid import uuid4

from uagents import Context, Protocol, Agent
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    TextContent,
    chat_protocol_spec,
)

import hive_state
import godfather

# Load keys from a .env file if present (ASI_ONE_API_KEY / GEMINI_API_KEY / etc.),
# so you don't have to set $env: vars every shell. Real shell env vars still win.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

subject_matter = (
    "beehive health, Varroa mites, queen status, swarming, bee acoustics, and the "
    "HiveSense non-invasive apiary monitoring system"
)
BASE_PROMPT = (
    f"You are the HiveSense apiary assistant. You answer questions about {subject_matter}, "
    "and especially about the user's OWN hives using the live status below. When the user "
    "asks how their bees/hives are doing, summarise the live status: call out any hive that "
    "is on alert or needs inspection, and otherwise reassure them. Keep it concise and practical."
)


def _valid(v):
    return v and v != "<YOUR-API-KEY>"


# ---- pick the brain ----
# Auto-detect by which key is set (priority asi1 > gemini > claude), or force one with
# LLM_PROVIDER=asi1|gemini|claude. asi1 and gemini both use the OpenAI-compatible API
# (the OpenAI SDK pointed at their servers - no OpenAI account needed).
def _select_brain():
    forced = os.getenv("LLM_PROVIDER", "").lower()
    order = [forced] if forced else ["asi1", "gemini", "claude"]
    for p in order:
        if p == "asi1" and _valid(os.getenv("ASI_ONE_API_KEY")):
            from openai import OpenAI
            return "asi1", OpenAI(base_url="https://api.asi1.ai/v1",
                                  api_key=os.getenv("ASI_ONE_API_KEY")), "asi1"
        if p == "gemini" and _valid(os.getenv("GEMINI_API_KEY")):
            from openai import OpenAI
            return "gemini", OpenAI(
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                api_key=os.getenv("GEMINI_API_KEY")), os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        if p == "claude" and _valid(os.getenv("ANTHROPIC_API_KEY")):
            import anthropic
            return "claude", anthropic.Anthropic(), os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
    return "none", None, "-"


_provider, _client, _model = _select_brain()


def _deterministic(status: str) -> str:
    note = "" if _provider != "none" else \
        "\n\n(No LLM key set, so this is the raw status. Set ASI_ONE_API_KEY or ANTHROPIC_API_KEY for conversational answers.)"
    return status + note


def generate_reply(question: str, logger=None) -> str:
    verdicts = hive_state.load_verdicts()
    status = hive_state.apiary_summary(verdicts)
    try:
        headline = godfather.apiary_analysis(verdicts)["headline"]
    except Exception:
        headline = ""
    system = f"{BASE_PROMPT}\n\nGODFATHER SUMMARY: {headline}\n\n{status}"
    try:
        if _provider in ("asi1", "gemini"):  # both use the OpenAI-compatible API
            r = _client.chat.completions.create(
                model=_model, max_tokens=2048,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": question}],
            )
            return str(r.choices[0].message.content)
        if _provider == "claude":
            m = _client.messages.create(
                model=_model, max_tokens=1024, system=system,
                messages=[{"role": "user", "content": question}],
            )
            return "".join(b.text for b in m.content if getattr(b, "type", None) == "text")
    except Exception:
        if logger:
            logger.exception(f"LLM call failed (provider={_provider}, model={_model}); "
                             "falling back to raw status")
    return _deterministic(status)


agent = Agent(
    name="hivesense-bee-agent",                      # <-- your unique agent name
    seed="hivesense-asi1-agent-seed-v1-change-me",   # <-- your unique seed phrase
    port=8001,
    mailbox=True,
    publish_agent_details=True,
)

protocol = Protocol(spec=chat_protocol_spec)


@protocol.on_message(ChatMessage)
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(
        sender,
        ChatAcknowledgement(timestamp=datetime.now(), acknowledged_msg_id=msg.msg_id),
    )

    text = "".join(item.text for item in msg.content if isinstance(item, TextContent))
    ctx.logger.info(f"Chat query from {sender}: {text}")

    response = generate_reply(text, logger=ctx.logger)

    await ctx.send(sender, ChatMessage(
        timestamp=datetime.utcnow(),
        msg_id=uuid4(),
        content=[
            TextContent(type="text", text=response),
            EndSessionContent(type="end-session"),
        ],
    ))


@protocol.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    pass


agent.include(protocol, publish_manifest=True)

if __name__ == "__main__":
    print(f"LLM brain: {_provider} (model={_model})")
    print(hive_state.apiary_summary())
    agent.run()

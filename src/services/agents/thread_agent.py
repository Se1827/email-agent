"""Thread summarizer agent — condenses long email threads for context.

Only invoked for threads with >5 messages. Uses a single LLM call to produce
a structured summary: key points, unresolved items, and whose move it is.
"""

from __future__ import annotations

import logging

from src.llm import client as llm
from src.services.agents.context import SharedAgentContext

log = logging.getLogger(__name__)

_THREAD_SYSTEM = """\
You are an email thread summarizer. Given an email thread summary, produce a
concise structured summary.

Respond ONLY with a JSON object (no markdown):
{
  "key_points": ["point 1", "point 2"],
  "unresolved_items": ["item 1"],
  "whose_move": "sender|recipient|unclear",
  "one_line_summary": "Brief summary of the thread state"
}
"""

_THREAD_USER = """\
Thread summary:
{thread_context}

Latest email from: {sender}
Subject: {subject}
"""


async def run_thread_agent(ctx: SharedAgentContext) -> None:
    """Summarize the thread if it has substantial history."""
    thread_ctx = ""
    if ctx.memory and ctx.memory.thread_summary:
        thread_ctx = ctx.memory.thread_summary

    if not thread_ctx or len(thread_ctx) < 200:
        ctx.record_agent("thread_agent", llm_calls=0)
        return

    try:
        user_msg = _THREAD_USER.format(
            thread_context=thread_ctx[:2000],
            sender=ctx.email.sender,
            subject=ctx.email.subject,
        )

        raw = await llm.chat(
            messages=[
                {"role": "system", "content": _THREAD_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.1,
            max_tokens=300,
        )

        import json
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1])
        data = json.loads(text)

        # Enrich the memory findings with thread summary
        if ctx.memory:
            ctx.memory.thread_summary = data.get("one_line_summary", thread_ctx[:200])
            ctx.memory.thread_unresolved = data.get("unresolved_items", [])
            ctx.memory.whose_move = data.get("whose_move", "unclear")

        ctx.record_agent("thread_agent", llm_calls=1)
        log.info("thread_agent_complete", extra={
            "email_id": ctx.email.id,
            "key_points": len(data.get("key_points", [])),
            "unresolved": len(data.get("unresolved_items", [])),
        })

    except Exception as exc:
        ctx.record_error("thread_agent", str(exc))
        ctx.record_agent("thread_agent", llm_calls=1)
        log.warning("thread_agent_failed", extra={"error": str(exc)})

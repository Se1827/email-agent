"""Memory agent — enriches context with sender profile, preferences, and history.

Runs FIRST in the AI-Rich pipeline so all downstream agents (classification,
draft) have access to personalization data without extra LLM calls.
Zero LLM calls — pure database lookups.
"""

from __future__ import annotations

import logging

from src.services.agents.context import MemoryFindings, SharedAgentContext
from src.services.memory import get_sender_profile, get_preferences
from src.services.search import search_similar_emails, get_thread_context

log = logging.getLogger(__name__)


async def run_memory_agent(ctx: SharedAgentContext) -> None:
    """Enrich the shared context with memory and personalization data."""
    email = ctx.email

    # ── Sender profile ────────────────────────────────────────────────
    profile = get_sender_profile(email.sender)

    # ── User preferences ──────────────────────────────────────────────
    prefs = get_preferences()
    pref_strings = [f"{p.pref_type}: {p.pref_value}" for p in prefs]

    # ── Similar past emails ───────────────────────────────────────────
    query = f"{email.subject} {email.body[:200]}"
    similar = search_similar_emails(query, limit=3)

    # ── Thread context ────────────────────────────────────────────────
    thread_ctx = ""
    if email.thread_id:
        thread_ctx = get_thread_context(email.thread_id)

    # ── Build findings ────────────────────────────────────────────────
    findings = MemoryFindings(
        sender_profile=profile,
        user_preferences=pref_strings,
        similar_emails=similar,
        thread_summary=thread_ctx,
    )

    ctx.memory = findings
    ctx.record_agent("memory_agent", llm_calls=0)

    log.info(
        "memory_agent_complete",
        extra={
            "email_id": email.id,
            "has_profile": profile is not None,
            "pref_count": len(pref_strings),
            "similar_count": len(similar),
            "has_thread_ctx": bool(thread_ctx),
        },
    )

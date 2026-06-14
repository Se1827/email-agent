"""Classification agent — enriched classification with multi-agent context.

This agent receives the SharedAgentContext (which already contains the
calendar agent's findings) and produces a richer classification than the
Classic single-pass classifier. It has access to conflict details, free
slots, and a pre-computed availability verdict.
"""

from __future__ import annotations

import json
import logging

from src.llm import client as llm
from src.llm.prompts import RICH_CLASSIFY_SYSTEM, RICH_CLASSIFY_USER
from src.models.email import Classification
from src.services.agents.context import SharedAgentContext
from src.services.pii import PrivacyGateway
from src.storage import safe_store_pii_mappings

log = logging.getLogger(__name__)


async def run_classification_agent(ctx: SharedAgentContext) -> None:
    """Classify the email using the enriched multi-agent context.

    The classification prompt includes the calendar agent's availability
    summary so the LLM has deterministic ground truth to reason about.
    """
    email = ctx.email
    privacy = PrivacyGateway()

    # ── Build calendar context from agent findings ─────────────────────
    cal_findings = ctx.calendar
    calendar_block = ""
    if cal_findings.availability_summary:
        calendar_block = f"--- Calendar Agent Report ---\n{cal_findings.availability_summary}"
        if cal_findings.conflicts:
            conflict_lines = [f'  • CONFLICT: "{c.event.title}" ({c.reason})' for c in cal_findings.conflicts]
            calendar_block += "\n" + "\n".join(conflict_lines)
        if cal_findings.free_slots:
            slot_lines = [f"  • FREE: {s.start.strftime('%H:%M')}–{s.end.strftime('%H:%M')} ({s.duration_minutes} min)" for s in cal_findings.free_slots[:3]]
            calendar_block += "\nAlternative free slots:\n" + "\n".join(slot_lines)

    # ── Build memory context from agent findings ─────────────────────────
    memory_block = ""
    if ctx.memory:
        mem = ctx.memory
        parts = []
        if mem.sender_profile:
            sp = mem.sender_profile
            parts.append(f"Sender: {sp.display_name or sp.email_address} "
                         f"(relationship: {sp.relationship}, "
                         f"avg priority: {sp.avg_priority}, "
                         f"interactions: {sp.interaction_count}"
                         f"{', VIP' if sp.is_vip else ''})")
        if mem.user_preferences:
            parts.append("Your standing instructions:\n" +
                         "\n".join(f"  - {p}" for p in mem.user_preferences[:5]))
        if mem.similar_emails:
            parts.append("Similar past emails:\n" +
                         "\n".join(f"  - {s['summary'][:80]}" for s in mem.similar_emails[:3]))
        if mem.thread_summary:
            parts.append(f"Thread context: {mem.thread_summary[:200]}")
        if parts:
            memory_block = "\n--- Memory Agent Report ---\n" + "\n".join(parts)

    user_msg = RICH_CLASSIFY_USER.format(
        sender=privacy.mask_text(email.sender).text,
        recipients=privacy.mask_text(", ".join(email.recipients)).text,
        timestamp=email.timestamp.isoformat(),
        subject=privacy.mask_text(email.subject).text,
        body=privacy.mask_text(email.body).text,
        calendar_report=privacy.mask_text(calendar_block + memory_block).text,
    )

    raw = await llm.chat(
        messages=[
            {"role": "system", "content": RICH_CLASSIFY_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.1,
    )

    parsed = _parse_classification(raw)

    # ── Build explanation factors from deterministic sources ────────────
    factors: list[str] = []
    if ctx.memory and ctx.memory.sender_profile:
        sp = ctx.memory.sender_profile
        if sp.is_vip:
            factors.append("sender is VIP")
        if sp.relationship != "unknown":
            factors.append(f"sender is {sp.relationship}")

    if cal_findings.conflicts:
        conflict_titles = ", ".join(
            f'"{c.event.title}"' for c in cal_findings.conflicts
        )
        parsed.reasoning = (
            f"{parsed.reasoning} — "
            f"You are NOT available at the proposed time: "
            f"conflict with {conflict_titles}"
        )
        factors.append(f"conflict with {conflict_titles}")
        parsed.conflicting_event_id = cal_findings.conflicts[0].event.id
    elif cal_findings.resolved_date:
        parsed.reasoning = (
            f"{parsed.reasoning} — "
            f"You ARE available at the proposed time."
        )
        factors.append("available at proposed time")

    if ctx.memory and ctx.memory.thread_unresolved:
        factors.append(f"{len(ctx.memory.thread_unresolved)} unresolved item(s) in thread")

    parsed.explanation_factors = factors

    ctx.classification = parsed
    safe_store_pii_mappings(email.id, "rich_classification", privacy.mappings)
    ctx.record_agent("classification_agent")

    log.info(
        "classification_agent_complete",
        extra={
            "email_id": email.id,
            "priority": parsed.priority.value,
            "category": parsed.category.value,
            "explanation_factors": factors,
        },
    )


def _parse_classification(raw: str) -> Classification:
    """Parse the LLM's JSON output into a Classification model."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1])
    data = json.loads(text)
    return Classification.model_validate(data)

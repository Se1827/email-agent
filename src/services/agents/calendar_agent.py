"""Calendar agent — pulls availability on demand via tool calls.

Unlike Classic Mode (which dumps all upcoming events into the prompt),
this agent actively queries the calendar for the specific dates mentioned
in the email. It uses the deterministic ``conflicts.py`` module for the
actual arithmetic, but wraps it with LLM reasoning for ambiguous cases.
"""

from __future__ import annotations

import logging
from datetime import datetime

from src.llm.date_resolver import resolve_proposed_datetime
from src.services.agents.context import CalendarFindings, SharedAgentContext
from src.services.email_utils import strip_quoted_text, filter_relevant_events
from src.services.conflicts import find_conflicts, find_free_slots, wall_clock

log = logging.getLogger(__name__)


async def run_calendar_agent(ctx: SharedAgentContext) -> None:
    """Enrich the shared context with calendar availability findings.

    Steps:
    1. Use the LLM date resolver to extract proposed date/time
    2. Find conflicts against the extracted date
    3. Find free slots on the same day as alternatives
    4. Write findings to ctx.calendar
    """
    email = ctx.email
    clean_body = strip_quoted_text(email.body)

    # ── Step 1: Resolve proposed date via LLM ──────────────────────────
    resolved = await resolve_proposed_datetime(
        email.subject, clean_body, email.timestamp,
    )

    findings = CalendarFindings()

    if resolved:
        findings.resolved_date = resolved.date
        findings.resolved_time = resolved.time
        findings.is_all_day = resolved.is_all_day

        # Exclude events auto-created from THIS email to avoid self-conflicts
        non_self_events = [
            ev for ev in ctx.calendar_events
            if ev.source_email_id != email.id
        ]

        # ── Step 2: Find conflicts ─────────────────────────────────────
        conflicts = find_conflicts(
            resolved.start,
            resolved.end,
            non_self_events,
            candidate_is_all_day=resolved.is_all_day,
        )
        findings.conflicts = conflicts

        # ── Step 3: Find free slots on the same day ────────────────────
        if conflicts:
            free = find_free_slots(resolved.date, non_self_events)
            findings.free_slots = free

        # ── Step 4: Build a human-readable availability summary ────────
        # Check if this meeting is already on the calendar from this email
        already_scheduled = any(
            ev.source_email_id == email.id for ev in ctx.calendar_events
        )
        if conflicts:
            conflict_names = ", ".join(f'"{c.event.title}"' for c in conflicts)
            slot_info = ""
            if free:
                slot_strs = [
                    f"{s.start.strftime('%H:%M')}–{s.end.strftime('%H:%M')}"
                    for s in free[:3]
                ]
                slot_info = f" Free alternatives: {', '.join(slot_strs)}."
            findings.availability_summary = (
                f"NOT available at the proposed time. "
                f"Conflicts with: {conflict_names}.{slot_info}"
            )
        elif already_scheduled:
            findings.availability_summary = (
                f"Available at the proposed time "
                f"({resolved.start.strftime('%A, %b %d')} "
                f"{'all day' if resolved.is_all_day else resolved.start.strftime('%H:%M')}). "
                f"This meeting is already on your calendar."
            )
        else:
            findings.availability_summary = (
                f"Available at the proposed time "
                f"({resolved.start.strftime('%A, %b %d')} "
                f"{'all day' if resolved.is_all_day else resolved.start.strftime('%H:%M')})."
            )

        log.info(
            "calendar_agent_complete",
            extra={
                "email_id": email.id,
                "resolved_date": resolved.date.strftime("%Y-%m-%d"),
                "conflict_count": len(conflicts),
                "free_slot_count": len(findings.free_slots),
            },
        )
    else:
        # No date proposed — check for generally relevant events
        relevant = filter_relevant_events(email, ctx.calendar_events)
        if relevant:
            findings.availability_summary = (
                f"{len(relevant)} related calendar events found but no specific "
                f"time proposed in the email."
            )
        else:
            findings.availability_summary = (
                "No scheduling context — no dates proposed and no related events."
            )

        log.info(
            "calendar_agent_no_date",
            extra={"email_id": email.id},
        )

    ctx.calendar = findings
    ctx.record_agent("calendar_agent", llm_calls=1 if resolved else 0)

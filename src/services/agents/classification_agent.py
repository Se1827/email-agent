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
            conflict_lines = []
            for c in cal_findings.conflicts:
                conflict_lines.append(
                    f"  • CONFLICT: \"{c.event.title}\" ({c.reason})"
                )
            calendar_block += "\n" + "\n".join(conflict_lines)

        if cal_findings.free_slots:
            slot_lines = []
            for s in cal_findings.free_slots[:3]:
                slot_lines.append(
                    f"  • FREE: {s.start.strftime('%H:%M')}–{s.end.strftime('%H:%M')} "
                    f"({s.duration_minutes} min)"
                )
            calendar_block += "\nAlternative free slots:\n" + "\n".join(slot_lines)

    user_msg = RICH_CLASSIFY_USER.format(
        sender=privacy.mask_text(email.sender).text,
        recipients=privacy.mask_text(", ".join(email.recipients)).text,
        timestamp=email.timestamp.isoformat(),
        subject=privacy.mask_text(email.subject).text,
        body=privacy.mask_text(email.body).text,
        calendar_report=privacy.mask_text(calendar_block).text,
    )

    raw = await llm.chat(
        messages=[
            {"role": "system", "content": RICH_CLASSIFY_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.1,
    )

    parsed = _parse_classification(raw)

    # ── Append deterministic availability to reasoning ─────────────────
    if cal_findings.conflicts:
        conflict_titles = ", ".join(
            f'"{c.event.title}"' for c in cal_findings.conflicts
        )
        parsed.reasoning = (
            f"{parsed.reasoning} — "
            f"You are NOT available at the proposed time: "
            f"conflict with {conflict_titles}"
        )
    elif cal_findings.resolved_date:
        parsed.reasoning = (
            f"{parsed.reasoning} — "
            f"You ARE available at the proposed time."
        )

    ctx.classification = parsed
    safe_store_pii_mappings(email.id, "rich_classification", privacy.mappings)
    ctx.record_agent("classification_agent")

    log.info(
        "classification_agent_complete",
        extra={
            "email_id": email.id,
            "priority": parsed.priority.value,
            "category": parsed.category.value,
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

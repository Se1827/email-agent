"""Draft reply service — generates context-aware email replies via LLM."""

from __future__ import annotations

import logging

from src.llm import client as llm
from src.llm.prompts import DRAFT_SYSTEM, DRAFT_USER
from src.models.email import (
    CalendarEvent,
    Classification,
    DraftReply,
    Email,
)
from src.services.calendar import format_calendar_context
from src.services.pii import redact

log = logging.getLogger(__name__)


async def draft_reply(
    email: Email,
    classification: Classification,
    calendar_events: list[CalendarEvent] | None = None,
) -> DraftReply:
    """Generate a reply draft for the given email.

    The generated text is run through the PII redactor before being returned.
    """
    cal_ctx = format_calendar_context(calendar_events or [])

    user_msg = DRAFT_USER.format(
        sender=email.sender,
        subject=email.subject,
        timestamp=email.timestamp.isoformat(),
        body=email.body,
        priority=classification.priority.value,
        category=classification.category.value,
        calendar_context=cal_ctx,
    )

    raw = await llm.chat(
        messages=[
            {"role": "system", "content": DRAFT_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.4,
    )

    # Redact any PII the model might have echoed back.
    result = redact(raw.strip())

    draft = DraftReply(
        body=result.text,
        tone="professional",
        pii_redacted=result.was_redacted,
        redacted_types=result.found_types,
    )

    log.info(
        "draft_generated",
        extra={
            "email_id": email.id,
            "pii_redacted": draft.pii_redacted,
        },
    )
    return draft

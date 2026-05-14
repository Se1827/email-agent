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
from src.services.pii import PrivacyGateway, redact

log = logging.getLogger(__name__)


async def draft_reply(
    email: Email,
    classification: Classification,
    calendar_events: list[CalendarEvent] | None = None,
) -> DraftReply:
    """Generate a reply draft for the given email.

    The original email is masked before it reaches the LLM. If the model uses
    semantic placeholders in its answer, only those known local values are
    rehydrated before user review.
    """
    privacy = PrivacyGateway()
    cal_ctx = format_calendar_context(calendar_events or [])

    user_msg = DRAFT_USER.format(
        sender=privacy.mask_text(email.sender).text,
        subject=privacy.mask_text(email.subject).text,
        timestamp=email.timestamp.isoformat(),
        body=privacy.mask_text(email.body).text,
        priority=classification.priority.value,
        category=classification.category.value,
        calendar_context=privacy.mask_text(cal_ctx).text,
    )

    raw = await llm.chat(
        messages=[
            {"role": "system", "content": DRAFT_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.4,
    )

    rehydrated = privacy.rehydrate_text(raw.strip())
    result = _redact_new_pii(rehydrated, allowed_values={m.original for m in privacy.mappings})
    pii_types = sorted({_pii_type(mapping.entity_type) for mapping in privacy.mappings} | set(result.found_types))

    draft = DraftReply(
        body=result.text,
        tone="professional",
        pii_redacted=result.was_redacted,
        redacted_types=pii_types,
    )

    log.info(
        "draft_generated",
        extra={
            "email_id": email.id,
            "pii_redacted": draft.pii_redacted,
        },
    )
    return draft


def _redact_new_pii(text: str, *, allowed_values: set[str]):
    """Mask hallucinated PII while allowing values restored from the email."""
    result = redact(text)
    for mapping in result.mappings:
        if mapping.original in allowed_values:
            result.text = result.text.replace(mapping.token, mapping.original)
    result.mappings = [
        mapping for mapping in result.mappings if mapping.original not in allowed_values
    ]
    result.found_types = sorted({_pii_type(mapping.entity_type) for mapping in result.mappings})
    return result


def _pii_type(entity_type: str) -> str:
    return "ssn" if entity_type == "US_SSN" else entity_type.lower()

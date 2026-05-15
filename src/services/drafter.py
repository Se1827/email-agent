"""Draft reply service — generates context-aware email replies via LLM."""

from __future__ import annotations

import logging
from datetime import timedelta

from src.llm import client as llm
from src.llm.prompts import (
    DRAFT_QUALITY_PARAMS,
    DRAFT_SYSTEM,
    DRAFT_USER_TEMPLATES,
)
from src.models.email import (
    CalendarEvent,
    Classification,
    DraftReply,
    Email,
)
from src.services.classifier import (
    filter_relevant_events,
    _format_relevant_context,
    _strip_quoted_text,
    _extract_dates_from_text,
    _extract_time_from_text,
)
from src.services.pii import PrivacyGateway, redact
from src.storage import safe_store_pii_mappings

log = logging.getLogger(__name__)


async def draft_reply(
    email: Email,
    classification: Classification,
    calendar_events: list[CalendarEvent] | None = None,
    *,
    quality: str = "balanced",
) -> DraftReply:
    """Generate a reply draft for the given email."""
    privacy = PrivacyGateway()

    relevant_events = filter_relevant_events(email, calendar_events or [])

    # Extract the time the sender is proposing so the LLM gets an explicit
    # CONFLICT / free label rather than having to guess from raw event data.
    clean_body = _strip_quoted_text(email.body)
    text = f"{email.subject} {clean_body}"
    cand_dates = _extract_dates_from_text(text, email.timestamp)
    cand_time  = _extract_time_from_text(text)

    if cand_dates and cand_time:
        cand_start = cand_dates[0].replace(hour=cand_time[0], minute=cand_time[1])
        cand_end   = cand_start + timedelta(hours=1)
    elif cand_dates:
        cand_start, cand_end = cand_dates[0], None
    else:
        cand_start = cand_end = None

    cal_ctx = _format_relevant_context(relevant_events, cand_start, cand_end)

    quality = quality if quality in DRAFT_USER_TEMPLATES else "balanced"
    template = DRAFT_USER_TEMPLATES[quality]
    temperature, max_tokens = DRAFT_QUALITY_PARAMS[quality]

    user_msg = template.format(
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
        temperature=temperature,
        max_tokens=max_tokens,
    )

    rehydrated = privacy.rehydrate_text(raw.strip())
    result = _redact_new_pii(rehydrated, allowed_values={m.original for m in privacy.mappings})
    pii_types = sorted({_pii_type(mapping.entity_type) for mapping in privacy.mappings} | set(result.found_types))

    draft = DraftReply(
        body=result.text,
        tone="professional",
        quality=quality,
        pii_redacted=result.was_redacted,
        redacted_types=pii_types,
    )
    safe_store_pii_mappings(email.id, "draft", privacy.mappings)

    log.info(
        "draft_generated",
        extra={
            "email_id": email.id,
            "quality": quality,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "relevant_events": len(relevant_events),
            "pii_redacted": draft.pii_redacted,
            "conflict_detected": cand_start is not None and any(
                "[CONFLICT" in line for line in cal_ctx.splitlines()
            ),
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
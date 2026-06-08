"""Draft reply service — generates context-aware email replies via LLM."""

from __future__ import annotations

import logging

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
from src.services.classifier import _strip_quoted_text
from src.services.pii import PrivacyGateway, redact
from src.storage import (
    safe_store_pii_mappings,
    get_sender_tone,
)

log = logging.getLogger(__name__)


def _extract_availability(reasoning: str) -> str:
    """Extract the availability verdict from classifier reasoning.

    The classifier always appends one of:
      '... — You are NOT available at the proposed time: conflict with "X"'
      '... — You ARE available at the proposed time.'

    Returns a direct, unambiguous instruction for the drafter LLM.
    """
    if not reasoning:
        return ""

    if "NOT available" in reasoning:
        # Extract the conflict event name if present
        if 'conflict with "' in reasoning:
            event_name = reasoning.split('conflict with "')[1].rstrip('"')
            return (
                f'\n\n*** MANDATORY: You are NOT available. '
                f'You have a conflict with "{event_name}". '
                f'DECLINE the proposed time and ask for an alternative. ***'
            )
        return (
            '\n\n*** MANDATORY: You are NOT available. '
            'DECLINE the proposed time. You have a prior commitment. '
            'Ask the sender to suggest an alternative time. ***'
        )

    if "ARE available" in reasoning:
        return (
            '\n\n*** MANDATORY: You ARE available. '
            'ACCEPT the proposed time. Confirm you are free '
            'and look forward to the meeting/call. ***'
        )

    return ""


async def draft_reply(
    email: Email,
    classification: Classification,
    calendar_events: list[CalendarEvent] | None = None,
    *,
    quality: str = "balanced",
) -> DraftReply:
    """Generate a reply draft for the given email.

    Availability is derived from the classifier's reasoning (which already
    checked the calendar). The drafter does NOT independently resolve dates
    or check the calendar — it trusts the classifier's verdict.
    """
    privacy = PrivacyGateway()

    quality = quality if quality in DRAFT_USER_TEMPLATES else "balanced"
    if "manager" in email.sender.lower():
        sender_tone = "concise"
    elif "hr" in email.sender.lower():
        sender_tone = "professional"
    elif "client" in email.sender.lower():
        sender_tone = "friendly"
    else:
        sender_tone = get_sender_tone(email.sender)
    template = DRAFT_USER_TEMPLATES[quality]
    temperature, max_tokens = DRAFT_QUALITY_PARAMS[quality]

    # Split body: latest message vs quoted thread
    latest_body = _strip_quoted_text(email.body)
    full_body = email.body
    thread_part = full_body[len(latest_body):].strip()
    thread_context_block = ""
    if thread_part:
        thread_context_block = (
            "--- Thread history (for context only, do NOT mimic) ---\n"
            + thread_part
        )

    # Extract availability from classifier and inject as a hard instruction
    availability = _extract_availability(classification.reasoning or "")

    user_msg = template.format(
        sender=privacy.mask_text(email.sender).text,
        subject=privacy.mask_text(email.subject).text,
        timestamp=email.timestamp.isoformat(),
        latest_body=privacy.mask_text(latest_body).text,
        thread_context=privacy.mask_text(thread_context_block).text,
        priority=classification.priority.value,
        category=classification.category.value,
        tone=sender_tone,
        availability_instruction=availability,
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
            "availability": availability[:80] if availability else "none",
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

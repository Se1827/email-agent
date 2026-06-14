"""Draft reply service — generates context-aware email replies via LLM."""

from __future__ import annotations

import logging

from src.llm import client as llm
from src.llm.prompts import (
    DRAFT_QUALITY_PARAMS,
    DRAFT_SYSTEM,
    DRAFT_USER_TEMPLATES,
    COMPOSE_SYSTEM,
    COMPOSE_USER_TEMPLATES,
)
from src.models.email import (
    CalendarEvent,
    Classification,
    DraftReply,
    Email,
)
from src.services.classifier import _strip_quoted_text
from src.services.pii import PrivacyGateway, redact
from src.storage import safe_store_pii_mappings

log = logging.getLogger(__name__)


def _extract_availability(reasoning: str) -> str:
    """Extract the availability verdict from classifier reasoning.

    The classifier always appends one of:
      '... — You are NOT available at the proposed time: conflict with "X"'
      '... — You ARE available at the proposed time.'
      '... — This meeting is already on your calendar.'

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

    if "already on your calendar" in reasoning:
        return (
            '\n\n*** MANDATORY: You ARE available and this meeting is already '
            'on your calendar. ACCEPT the proposed time. Confirm you are free '
            'and look forward to the meeting/call. ***'
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

    Note: ``calendar_events`` is accepted for API compatibility with AI-Rich
    mode (which uses the orchestrator to provide calendar context directly).
    In Classic mode, it is intentionally unused — this is NOT a bug.
    """
    privacy = PrivacyGateway()

    quality = quality if quality in DRAFT_USER_TEMPLATES else "balanced"
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

    # ── Reschedule Draft Generation ────────────────────────────────────
    # Generate a reschedule draft when there is a calendar conflict
    conflict_event = None
    if calendar_events:
        if classification.conflicting_event_id:
            conflict_event = next((e for e in calendar_events if e.id == classification.conflicting_event_id), None)
        
        # Dynamically check if our own auto-event conflicts with another event if not found
        if not conflict_event:
            my_event = next((e for e in calendar_events if e.source_email_id == email.id or e.id == f"auto-{email.id}"), None)
            if my_event:
                my_s = my_event.start.replace(tzinfo=None)
                my_e = my_event.end.replace(tzinfo=None)
                for ev in calendar_events:
                    if ev.id != my_event.id:
                        ev_s = ev.start.replace(tzinfo=None)
                        ev_e = ev.end.replace(tzinfo=None)
                        if ev_s < my_e and ev_e > my_s:
                            conflict_event = ev
                            break

    if conflict_event:
        # Determine priority of the conflict event
        conflict_priority = conflict_event.priority or "normal"
        priority_scale = {"critical": 4, "high": 3, "normal": 2, "low": 1}
        new_p = priority_scale.get(classification.priority.value, 0)
        old_p = priority_scale.get(conflict_priority, 2)

        resched_type = "override" if new_p > old_p else "yield"
        
        if resched_type == "override":
            recipient = conflict_event.attendees[0] if conflict_event.attendees else "team"
            # Exclude user's own email from attendees if possible
            from src.config import get_settings
            cfg = get_settings()
            user_email = cfg.imap_user
            if len(conflict_event.attendees) > 1 and user_email:
                other_attendees = [a for a in conflict_event.attendees if a.lower() != user_email.lower()]
                if other_attendees:
                    recipient = other_attendees[0]

            resched_sys = (
                "You are an email assistant. Write a short, polite email to request "
                "rescheduling a meeting because of an urgent, unavoidable conflict. "
                "Keep it extremely professional, courteous, and concise. "
                "Do NOT include any subject line, signature, or header block — just the email body itself."
            )
            resched_user = (
                f"We need to reschedule the following meeting:\n"
                f"Meeting Title: {conflict_event.title}\n"
                f"Reason: A higher-priority issue/meeting ('{email.subject}') has created a conflict.\n"
                f"Write a polite reschedule request email to {recipient}."
            )
            subject = f"Reschedule request: {conflict_event.title}"
            event_id = conflict_event.id
            event_title = conflict_event.title
        else:
            recipient = email.sender
            resched_sys = (
                "You are an email assistant. Write a short, polite email to request "
                "rescheduling a meeting because of a scheduling conflict with an existing higher-priority commitment. "
                "Keep it extremely professional, courteous, and concise. "
                "Do NOT include any subject line, signature, or header block — just the email body itself."
            )
            resched_user = (
                f"We need to reschedule the meeting proposed in this email ('{email.subject}') "
                f"because it conflicts with an existing higher-priority commitment.\n"
                f"Write a polite email to {recipient} asking to reschedule."
            )
            subject = f"Reschedule request: {email.subject}"
            event_id = f"auto-{email.id}"
            # Find current event title if any
            sender_name = email.sender.split("@")[0].replace(".", " ").title()
            event_title = f"Meeting: {sender_name} — {email.subject[:40]}"

        try:
            resched_raw = await llm.chat(
                messages=[
                    {"role": "system", "content": resched_sys},
                    {"role": "user", "content": resched_user},
                ],
                temperature=temperature,
                max_tokens=200,
            )
            resched_body = resched_raw.strip()
            draft.conflict_reschedule_draft = {
                "type": resched_type,
                "event_id": event_id,
                "event_title": event_title,
                "recipient": recipient,
                "subject": subject,
                "body": resched_body,
            }
            log.info("reschedule_draft_generated", extra={"event_id": event_id, "type": resched_type})
        except Exception as exc:
            log.warning("Failed to generate reschedule draft via LLM", exc_info=exc)

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


async def ai_compose(prompt: str, quality: str = "balanced") -> str:
    """Generate a brand new email draft from a user prompt."""
    quality = quality if quality in COMPOSE_USER_TEMPLATES else "balanced"
    template = COMPOSE_USER_TEMPLATES[quality]
    temperature, max_tokens = DRAFT_QUALITY_PARAMS[quality]

    user_msg = template.format(prompt=prompt)

    raw = await llm.chat(
        messages=[
            {"role": "system", "content": COMPOSE_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )

    log.info(
        "ai_compose_generated",
        extra={
            "quality": quality,
            "prompt_length": len(prompt),
        },
    )
    return raw.strip()
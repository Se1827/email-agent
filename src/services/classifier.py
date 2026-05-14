"""Email classification service — assigns priority and category via LLM."""

from __future__ import annotations

import json
import logging

from src.llm import client as llm
from src.llm.prompts import CLASSIFY_SYSTEM, CLASSIFY_USER
from src.models.email import CalendarEvent, Classification, Email
from src.services.calendar import format_calendar_context
from src.services.pii import PrivacyGateway

log = logging.getLogger(__name__)


async def classify(
    email: Email,
    calendar_events: list[CalendarEvent] | None = None,
) -> Classification:
    """Classify an email by priority and category.

    Sends the email contents (plus optional calendar context) to the LLM
    and parses the structured JSON response into a ``Classification``.
    """
    privacy = PrivacyGateway()
    cal_ctx = format_calendar_context(calendar_events or [])

    user_msg = CLASSIFY_USER.format(
        sender=privacy.mask_text(email.sender).text,
        recipients=privacy.mask_text(", ".join(email.recipients)).text,
        timestamp=email.timestamp.isoformat(),
        subject=privacy.mask_text(email.subject).text,
        body=privacy.mask_text(email.body).text,
        calendar_context=privacy.mask_text(cal_ctx).text,
    )

    raw = await llm.chat(
        messages=[
            {"role": "system", "content": CLASSIFY_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.1,
    )

    parsed = _parse_classification(raw)
    log.info(
        "classified",
        extra={
            "email_id": email.id,
            "priority": parsed.priority.value,
            "category": parsed.category.value,
            "pii_masked": bool(privacy.mappings),
            "pii_types": sorted({mapping.entity_type.lower() for mapping in privacy.mappings}),
        },
    )
    return parsed


def _parse_classification(raw: str) -> Classification:
    """Parse the LLM's JSON output into a Classification model.

    Handles minor formatting issues like markdown code fences.
    """
    text = raw.strip()
    if text.startswith("```"):
        # Strip ```json ... ``` wrappers if the model adds them.
        lines = text.splitlines()
        text = "\n".join(lines[1:-1])

    data = json.loads(text)
    return Classification.model_validate(data)

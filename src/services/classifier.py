"""Email classification service — assigns priority and category via LLM."""

from __future__ import annotations

import json
import logging

from src.llm import client as llm
from src.llm.prompts import CLASSIFY_SYSTEM, CLASSIFY_USER
from src.models.email import CalendarEvent, Classification, Email
from src.services.calendar import format_calendar_context

log = logging.getLogger(__name__)


async def classify(
    email: Email,
    calendar_events: list[CalendarEvent] | None = None,
) -> Classification:
    """Classify an email by priority and category.

    Sends the email contents (plus optional calendar context) to the LLM
    and parses the structured JSON response into a ``Classification``.
    """
    cal_ctx = format_calendar_context(calendar_events or [])

    user_msg = CLASSIFY_USER.format(
        sender=email.sender,
        recipients=", ".join(email.recipients),
        timestamp=email.timestamp.isoformat(),
        subject=email.subject,
        body=email.body,
        calendar_context=cal_ctx,
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

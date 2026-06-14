"""LLM-based date/time resolver for email scheduling context.

Replaces fragile regex date extraction with a focused LLM call that
reliably handles 'tomorrow', 'next week', '21st', 'May 19 4pm', etc.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.llm import client as llm

log = logging.getLogger(__name__)


@dataclass
class ResolvedDate:
    """Result of LLM date resolution."""
    date: datetime
    time: tuple[int, int] | None
    is_all_day: bool
    summary: str

    @property
    def start(self) -> datetime:
        if self.time:
            return self.date.replace(hour=self.time[0], minute=self.time[1])
        return self.date

    @property
    def end(self) -> datetime:
        if self.time:
            return self.start + timedelta(hours=1)
        return self.date.replace(hour=23, minute=59)


_SYSTEM = """\
You extract proposed meeting/event dates from emails.
Given the email and the reference date, determine if a specific date or time \
is being proposed for a meeting, call, event, deadline, or action item.

RULES:
- "tomorrow" = reference date + 1 day
- "next week" = the coming Monday after reference date
- "by next week" / "before next week" = the coming Monday
- "end of week" / "by Friday" = the coming Friday
- "day after tomorrow" = reference date + 2 days
- Day names ("Wednesday") = the next occurrence of that day after reference
- Bare ordinals ("21st") = that day of the current month (next month if past)
- Explicit dates like "May 19", "19th May", "2026-05-19" = that date
- Times like "4pm", "16:00", "4:30 PM" = specific time on the resolved date
- Phrases like "ASAP", "urgent", "at your earliest" with no date = use \
reference date + 1 day
- If NO meeting/call/event/deadline/task is being proposed (e.g. newsletters, \
FYI updates, thank-you notes), return has_proposed_date: false
- Only look at the LATEST message, ignore quoted reply chains

Return ONLY valid JSON (no markdown fences, no extra text):
{"has_proposed_date": true/false, "date": "YYYY-MM-DD"/null, "time": "HH:MM"/null, "is_all_day": true/false, "summary": "brief description"/null}\
"""

_USER = """\
Reference date: {ref_date} ({day_name})

Subject: {subject}

Body:
{body}\
"""


async def resolve_proposed_datetime(
    subject: str,
    body: str,
    email_timestamp: datetime,
) -> ResolvedDate | None:
    """Use LLM to extract a proposed date/time from an email.

    Returns None if the email doesn't propose any meeting/event date.
    """
    try:
        from src.services.pii import PrivacyGateway
        privacy = PrivacyGateway()
        subject = privacy.mask_text(subject).text
        body = privacy.mask_text(body).text
    except Exception as exc:
        log.warning("Failed to mask PII in date resolver", exc_info=exc)

    # Use email timestamp as reference (converted to local/naive to keep relative comparisons simple)
    ref = email_timestamp.astimezone() if email_timestamp.tzinfo else email_timestamp
    ref = ref.replace(second=0, microsecond=0, tzinfo=None)

    user_msg = _USER.format(
        ref_date=ref.strftime("%Y-%m-%d"),
        day_name=ref.strftime("%A"),
        subject=subject,
        body=body[:800],
    )

    try:
        raw = await llm.chat(
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
            max_tokens=200,
        )

        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1])

        data = json.loads(text)

        if not data.get("has_proposed_date") or not data.get("date"):
            log.info("date_resolved_none", extra={"subject": subject[:60]})
            return None

        resolved_date = datetime.strptime(data["date"], "%Y-%m-%d")

        time_tuple = None
        if data.get("time"):
            parts = data["time"].split(":")
            time_tuple = (int(parts[0]), int(parts[1]))

        is_all_day = data.get("is_all_day", time_tuple is None)
        summary = data.get("summary") or ""

        log.info(
            "date_resolved",
            extra={
                "date": data["date"],
                "time": data.get("time"),
                "is_all_day": is_all_day,
                "summary": summary,
            },
        )

        return ResolvedDate(
            date=resolved_date,
            time=time_tuple,
            is_all_day=is_all_day,
            summary=summary,
        )

    except Exception as exc:
        log.warning("date_resolution_failed", extra={"error": str(exc)})
        return None

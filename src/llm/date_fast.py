"""Fast regex + dateutil date resolver — no LLM calls.

Classic Mode uses this as the *primary* date resolution path. It tries
well-known patterns (ordinals, day names, relative phrases, ISO dates)
using regex and ``python-dateutil``. Returns a ``ResolvedDate`` on success
or ``None`` to signal "fall back to the LLM resolver."

AI-Rich Mode skips this module entirely and always uses the LLM resolver
for maximum accuracy on ambiguous inputs.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.llm.date_resolver import ResolvedDate

log = logging.getLogger(__name__)


# ── Month and day maps ─────────────────────────────────────────────────────

_MONTH_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

_DAY_NAMES = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def resolve_fast(
    subject: str,
    body: str,
    email_timestamp: datetime,
) -> ResolvedDate | None:
    """Try to extract a proposed date/time from the email using regex only.

    Returns None if no confident extraction can be made (caller should
    fall back to the LLM resolver).
    """
    ref = datetime.now().replace(second=0, microsecond=0)
    text = f"{subject} {body}".lower()

    # ── Strip quoted reply chains ──────────────────────────────────────
    text = _strip_quoted(text)

    # ── Check if this looks like a scheduling email at all ─────────────
    if not _has_scheduling_intent(text):
        return None

    resolved_date = _extract_date(text, ref)
    if resolved_date is None:
        return None

    time_tuple = _extract_time(text)

    if time_tuple:
        is_all_day = False
        summary = f"Proposed: {resolved_date.strftime('%Y-%m-%d')} at {time_tuple[0]:02d}:{time_tuple[1]:02d}"
    else:
        is_all_day = True
        summary = f"Proposed: {resolved_date.strftime('%Y-%m-%d')} (all day)"

    from src.llm.date_resolver import ResolvedDate
    result = ResolvedDate(
        date=resolved_date,
        time=time_tuple,
        is_all_day=is_all_day,
        summary=summary,
    )

    log.info(
        "date_resolved_fast",
        extra={
            "date": resolved_date.strftime("%Y-%m-%d"),
            "time": f"{time_tuple[0]:02d}:{time_tuple[1]:02d}" if time_tuple else None,
            "is_all_day": is_all_day,
        },
    )
    return result


# ── Scheduling intent detection ────────────────────────────────────────────

_SCHEDULING_RE = re.compile(
    r"\b("
    r"meeting|meet|call|sync|standup|demo|review|retro|planning|"
    r"deadline|appointment|schedule|calendar|"
    r"available|availability|free|busy|"
    r"today|tomorrow|tonight|day after tomorrow|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"asap|urgent|earliest"
    r")\b",
    re.IGNORECASE,
)


def _has_scheduling_intent(text: str) -> bool:
    """Quick check: does this text look like it proposes a time/meeting?"""
    return bool(_SCHEDULING_RE.search(text))


# ── Date extraction ────────────────────────────────────────────────────────

def _extract_date(text: str, ref: datetime) -> datetime | None:
    """Extract the first proposed date from text. Returns None if ambiguous."""

    # Relative phrases (highest confidence)
    if re.search(r"\btoday\b", text):
        return ref.replace(hour=0, minute=0, second=0, microsecond=0)

    if re.search(r"\btomorrow\b", text):
        return (ref + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    if re.search(r"\bday after tomorrow\b", text):
        return (ref + timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)

    # ISO dates (YYYY-MM-DD)
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # "Month Day" patterns: "May 19", "June 21st"
    month_pattern = "|".join(_MONTH_MAP.keys())
    m = re.search(
        rf"\b({month_pattern})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b",
        text,
    )
    if m:
        month = _MONTH_MAP[m.group(1)]
        day = int(m.group(2))
        try:
            return datetime(ref.year, month, day)
        except ValueError:
            pass

    # "Day Month" patterns: "19th May", "21 June"
    m = re.search(
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({month_pattern})\b",
        text,
    )
    if m:
        day = int(m.group(1))
        month = _MONTH_MAP[m.group(2)]
        try:
            return datetime(ref.year, month, day)
        except ValueError:
            pass

    # Day names: "next Wednesday", "on Friday"
    for name, weekday in _DAY_NAMES.items():
        if re.search(rf"\b{name}\b", text):
            days_ahead = (weekday - ref.weekday()) % 7 or 7
            return (ref + timedelta(days=days_ahead)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

    # Bare ordinals with no month: "the 19th", "on the 21st"
    m = re.search(r"\b(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)\b", text)
    if m:
        day = int(m.group(1))
        if 1 <= day <= 31:
            try:
                candidate = datetime(ref.year, ref.month, day)
                if candidate.date() < ref.date():
                    next_month = ref.month + 1 if ref.month < 12 else 1
                    next_year = ref.year if ref.month < 12 else ref.year + 1
                    candidate = datetime(next_year, next_month, day)
                return candidate
            except ValueError:
                pass

    return None


# ── Time extraction ────────────────────────────────────────────────────────

def _extract_time(text: str) -> tuple[int, int] | None:
    """Extract a time reference like '4pm', '4:30pm', '16:00' from text."""
    # 12-hour format: "4pm", "4:30 AM"
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        if m.group(3) == "pm" and hour != 12:
            hour += 12
        elif m.group(3) == "am" and hour == 12:
            hour = 0
        return (hour, minute)

    # 24-hour format: "16:00"
    m = re.search(r"\b(\d{1,2}):(\d{2})\b", text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return (hour, minute)

    return None


# ── Quote stripping ────────────────────────────────────────────────────────

def _strip_quoted(text: str) -> str:
    """Remove quoted reply chains that contain stale dates."""
    separators = [
        r"^-{3,}\s*original\s+message\s*-{3,}",
        r"^on\s+\w+,\s+\d{1,2}/\d{1,2}/\d{2,4}\s+at\s+",
        r"^on\s+\w+,\s+\w+\s+\d{1,2},\s+\d{4}\s+at\s+",
        r"^>",
        r"^sent from \[",
    ]
    lines = text.splitlines()
    clean_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        is_quote = False
        for sep in separators:
            if re.match(sep, stripped, re.IGNORECASE):
                is_quote = True
                break
        if is_quote:
            break
        clean_lines.append(line)
    return "\n".join(clean_lines)

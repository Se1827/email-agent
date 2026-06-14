"""Daily digest — AI-generated summary of the day's email priorities.

Provides a scheduled, pre-computed email digest with:
  - Per-email urgency cards with deadline term highlighting
  - Actionable suggestions (add to calendar / create action)
  - Themes, nudges, calendar timeline, productivity tips
  - User memory & preferences woven into the LLM context
  - Configurable via user preferences (wake time, auto-classify)
  - Smart "all clear" state when inbox is clean
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from src.llm import client as llm
from src.services.actions import get_action_items

log = logging.getLogger(__name__)

# ── Default digest configuration ──────────────────────────────────────────

_DEFAULT_DIGEST_CONFIG = {
    "enabled": True,
    "wake_time": "08:00",
    "auto_classify": True,
}


def get_digest_config() -> dict[str, Any]:
    """Read digest configuration from user preferences."""
    try:
        from src.services.memory import get_preferences
        prefs = get_preferences("digest_config")
        if prefs:
            config = dict(_DEFAULT_DIGEST_CONFIG)
            for p in prefs:
                key = p.pref_key
                val = p.pref_value
                if key in ("enabled", "auto_classify"):
                    config[key] = val.lower() in ("true", "1", "yes")
                else:
                    config[key] = val
            return config
    except Exception:
        log.exception("get_digest_config_failed")
    return dict(_DEFAULT_DIGEST_CONFIG)


def save_digest_config(config: dict[str, Any]) -> None:
    """Persist digest configuration as user preferences."""
    try:
        from src.services.memory import store_preference
        for key, value in config.items():
            if key in _DEFAULT_DIGEST_CONFIG:
                store_preference("digest_config", key, str(value))
    except Exception:
        log.exception("save_digest_config_failed")


# ── Memory / Personalization context ──────────────────────────────────────


def _get_user_context() -> str:
    """Build a personalization block from memory for the LLM prompt."""
    parts: list[str] = []
    try:
        from src.services.memory import (
            get_preferences,
            get_scheduling_constraints,
            get_vip_senders,
        )
        # VIP senders
        vips = get_vip_senders()
        if vips:
            parts.append(f"VIP senders (prioritize): {', '.join(vips[:10])}")

        # Standing instructions (personalization prefs)
        prefs = get_preferences("standing_instruction")
        if prefs:
            instructions = [p.pref_value for p in prefs[:5]]
            parts.append("User instructions: " + "; ".join(instructions))

        # Scheduling constraints
        constraints = get_scheduling_constraints()
        if constraints:
            parts.append("Scheduling: " + "; ".join(constraints[:3]))

    except Exception:
        log.debug("user_context_fetch_failed", exc_info=True)

    return "\n".join(parts) if parts else ""


# ── Time helpers ──────────────────────────────────────────────────────────


def _time_greeting() -> str:
    """Return a time-appropriate greeting."""
    hour = datetime.now().hour
    if hour < 12:
        return "Good morning"
    if hour < 17:
        return "Good afternoon"
    return "Good evening"


def _human_time_since(iso_ts: str) -> str:
    """Convert an ISO timestamp to a human-readable relative time."""
    try:
        ts = datetime.fromisoformat(iso_ts)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - ts
        hours = delta.total_seconds() / 3600
        if hours < 1:
            return f"{max(1, int(delta.total_seconds() / 60))}m ago"
        if hours < 24:
            return f"{int(hours)}h ago"
        days = int(hours / 24)
        if days == 1:
            return "yesterday"
        if days < 7:
            return f"{days}d ago"
        return ts.strftime("%b %d")
    except (ValueError, TypeError):
        return ""


def _is_within_window(iso_ts: str, days: int = 0) -> bool:
    """Check if a timestamp falls within the lookback window.

    days=0 means last 24h (today), days=1 means last 48h, etc.
    """
    try:
        ts = datetime.fromisoformat(iso_ts)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (now - ts) < timedelta(hours=24 * (days + 1))
    except (ValueError, TypeError):
        return False


# ── Deadline term extraction (regex — NO LLM) ────────────────────────────
#
# These patterns target ACTIONABLE deadline language in the email body.
# We explicitly strip forwarded-email headers first to avoid false
# positives on "On Mon Jun 16 at 10:30 AM, Alice wrote:".

_FORWARDED_HEADER_RE = re.compile(
    r"(?:^|\n)-{2,}\s*Forwarded message\s*-{2,}.*?(?=\n\n|\Z)"
    r"|(?:^|\n)On\s+.{10,80}\s+wrote:\s*$"
    r"|(?:^|\n)From:\s+.+$"
    r"|(?:^|\n)Sent:\s+.+$"
    r"|(?:^|\n)Date:\s+.+$"
    r"|(?:^|\n)Subject:\s+.+$"
    r"|(?:^|\n)To:\s+.+$",
    re.MULTILINE | re.IGNORECASE,
)

_DEADLINE_PATTERNS = [
    # "by/before/due + specific date/day"
    r"\b(?:by|before|due|deadline)\s+(?:end\s+of\s+day|EOD|COB|end\s+of\s+week|"
    r"(?:mon|tues|wednes|thurs|fri|satur|sun)day|tomorrow|tonight|today|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\.?\s+\d{1,2}(?:st|nd|rd|th)?|"
    r"\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*|"
    r"\d{1,2}[\/\-]\d{1,2}(?:[\/\-]\d{2,4})?|"
    r"next\s+(?:week|month|monday|tuesday|wednesday|thursday|friday))",
    # Urgency keywords (standalone)
    r"\b(?:urgent(?:ly)?|asap|immediately|right\s+away|time[- ]sensitive)\b",
    # "respond/submit/send by X"
    r"\b(?:respond|reply|submit|send|complete|finish|deliver)\s+by\s+\S+(?:\s+\S+)?",
    # "due date/deadline: X"
    r"\b(?:due\s+date|deadline)\s*(?::|is)?\s*\S+(?:\s+\S+){0,3}",
    # Acronyms
    r"\bEOD\b|\bCOB\b|\bASAP\b",
]
_DEADLINE_RE = re.compile("|".join(_DEADLINE_PATTERNS), re.IGNORECASE)


def extract_deadline_terms(text: str) -> list[str]:
    """Extract deadline-related phrases from email text.

    Strips forwarded-email headers first to avoid matching
    timestamps like "On Mon Jun 16 at 10:30 AM".
    """
    if not text:
        return []
    # Strip forwarded/reply headers before extraction
    clean = _FORWARDED_HEADER_RE.sub("", text)
    matches = _DEADLINE_RE.findall(clean)
    # Deduplicate and clean
    seen: set[str] = set()
    result = []
    for m in matches:
        m_clean = m.strip().strip(".,;:")
        if m_clean and m_clean.lower() not in seen and len(m_clean) > 2:
            seen.add(m_clean.lower())
            result.append(m_clean)
    return result[:5]


# ── Extract meeting date from classification reasoning ────────────────

_DATE_EXTRACT_RE = re.compile(
    r"(?:(?:mon|tues|wednes|thurs|fri|satur|sun)day,?\s+)?"
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?"
    r"|\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?"
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"(?:\s+\d{4})?"
    r"|\d{1,2}[\/\-]\d{1,2}(?:[\/\-]\d{2,4})?",
    re.IGNORECASE,
)


def _extract_date_from_reasoning(reasoning: str) -> str | None:
    """Try to extract a meeting date from classification reasoning text.

    Returns an ISO date string if found, else None.
    """
    if not reasoning:
        return None
    match = _DATE_EXTRACT_RE.search(reasoning)
    if not match:
        return None
    date_str = match.group(0).strip()
    # Try to parse it
    from dateutil import parser as dateparser
    try:
        dt = dateparser.parse(date_str, fuzzy=True)
        if dt:
            # Default to 10:00 AM if no time
            if dt.hour == 0 and dt.minute == 0:
                dt = dt.replace(hour=10, minute=0)
            return dt.isoformat()
    except (ValueError, TypeError):
        pass
    return None


# ── LLM System Prompt ────────────────────────────────────────────────────

_DIGEST_SYSTEM = """\
You are an email productivity assistant generating a rich daily digest.
Given pending emails (with body previews), action items, calendar events, \
and user context, produce a structured digest that helps the user \
never miss a deadline.

Respond ONLY with JSON (no markdown fences, no extra text):
{{
  "urgency_score": <0-10 integer. 0=inbox zero, 10=critical overload>,
  "one_line": "<crisp 1-sentence TL;DR of the day>",
  "email_cards": [
    {{
      "id": "<email_id>",
      "subject": "...",
      "sender": "...",
      "preview": "<first ~120 chars of the email body, clean>",
      "urgency": "critical|high|normal|low",
      "deadline_terms": ["by Friday EOD", "before the meeting"],
      "suggested_actions": [
        {{"type": "calendar", "label": "Friday EOD — Report deadline"}},
        {{"type": "action", "label": "Submit quarterly report"}}
      ],
      "time_since": "<relative time like '3h ago' or 'yesterday'>"
    }}
  ],
  "themes": [
    {{"theme": "<topic>", "count": <N>, "summary": "<1-line>"}}
  ],
  "nudges": [
    {{"text": "<actionable nudge>", "type": "overdue|stale_draft|vip|reminder"}}
  ],
  "calendar_today": [
    {{"time": "<HH:MM>", "title": "...", "id": "<event_id>"}}
  ],
  "tip": "<contextual productivity tip>"
}}

RULES:
- email_cards: Create a card for EVERY email provided. Rank by urgency \
(critical/high first, then unread).
- deadline_terms: Extract phrases indicating deadlines from the email body. \
Be specific (e.g., "by Friday EOD"). Do NOT extract timestamps from \
forwarded/reply headers ("On Mon at 10:30 AM Alice wrote" is NOT a deadline).
- suggested_actions: Suggest concrete calendar events or action items. \
Only suggest if truly relevant.
- preview: Clean first ~120 characters of the email body. No HTML tags.
- themes: group emails by topic/project, max 6.
- nudges: flag overdue actions, unanswered high-priority emails (>24h), \
stale drafts. Mention VIP senders by name if applicable.
- calendar_today: all events for today sorted by time.
- urgency_score: based on deadline proximity, unread count, overdue actions.
- If given user context, respect VIP senders and standing instructions.\
"""


async def generate_daily_digest(
    emails: list[dict[str, Any]],
    calendar_events: list[dict[str, Any]] | None = None,
    *,
    user_name: str | None = None,
    lookback_days: int = 0,
    existing_event_emails: set[str] | None = None,
    existing_action_emails: set[str] | None = None,
) -> dict[str, Any]:
    """Generate a daily digest with rich email cards.

    lookback_days: 0 = today (24h), 1 = past 2 days, 2 = past 3 days.
    existing_event_emails: email IDs that already have calendar events.
    existing_action_emails: email IDs that already have action items.
    """
    pending_actions = get_action_items(status="pending")
    now = datetime.now(timezone.utc)

    # ── Filter emails within the lookback window ───────────────────────
    window_emails = [
        e for e in emails
        if _is_within_window(e.get("timestamp", ""), lookback_days)
    ]
    # If no emails in window, still consider unread ones
    actionable_emails = window_emails or [
        e for e in emails
        if not e.get("is_read", True)
    ]

    # ── Compute derived stats (over ALL emails for accuracy) ───────────
    high_priority_count = sum(
        1 for e in emails
        if e.get("priority") in ("critical", "high")
    )
    unread_count = sum(1 for e in emails if not e.get("is_read", True))
    stale_drafts = [
        e for e in emails
        if e.get("has_draft") and not e.get("draft_sent")
    ]
    overdue_actions = []
    for a in pending_actions:
        if a.get("due_date"):
            try:
                due = datetime.fromisoformat(a["due_date"])
                if due.tzinfo is None:
                    due = due.replace(tzinfo=timezone.utc)
                if due < now:
                    hours_overdue = (now - due).total_seconds() / 3600
                    overdue_actions.append({
                        "description": a["description"],
                        "hours_overdue": round(hours_overdue),
                    })
            except (ValueError, TypeError):
                pass

    greeting_name = f", {user_name}" if user_name else ""
    base_greeting = f"{_time_greeting()}{greeting_name}!"
    config = get_digest_config()

    # ── "All clear" short-circuit ──────────────────────────────────────
    if (
        len(actionable_emails) == 0
        and len(overdue_actions) == 0
        and len(stale_drafts) == 0
    ):
        return _build_all_clear_digest(
            base_greeting, calendar_events or [], len(emails),
        )

    # ── Build email context (only actionable emails) ───────────────────
    email_lines = []
    for e in actionable_emails:
        age = _human_time_since(e.get("timestamp", ""))
        flags = []
        if e.get("priority") in ("critical", "high"):
            flags.append("⚠️" + e.get("priority", "").upper())
        if e.get("has_draft"):
            flags.append("DRAFT")
        if not e.get("is_read", True):
            flags.append("UNREAD")
        flag_str = f" [{', '.join(flags)}]" if flags else ""

        preview = (e.get("body_preview") or "")[:200].replace("\n", " ").strip()
        terms = extract_deadline_terms(preview)
        term_hint = f" DEADLINES_FOUND=[{', '.join(terms)}]" if terms else ""

        email_lines.append(
            f"- id={e.get('id', '?')} | {e.get('subject', 'No subject')} "
            f"from {e.get('sender', 'unknown')}{flag_str} ({age})"
            f"{term_hint}"
            f"\n  PREVIEW: {preview or '(no preview)'}"
        )

    action_lines = []
    for a in pending_actions[:10]:
        due = a.get("due_date", "no due date")
        overdue_flag = ""
        if a.get("due_date"):
            try:
                d = datetime.fromisoformat(a["due_date"])
                if d.tzinfo is None:
                    d = d.replace(tzinfo=timezone.utc)
                if d < now:
                    overdue_flag = " ⚠️OVERDUE"
            except (ValueError, TypeError):
                pass
        action_lines.append(f"- {a['description']} (due: {due}){overdue_flag}")

    cal_lines = []
    if calendar_events:
        for ev in calendar_events[:15]:
            time_str = ev.get("time", ev.get("start", "?"))
            cal_lines.append(
                f"- {time_str} — {ev.get('title', '?')} (id={ev.get('id', '?')})"
            )

    # ── Personalization context from memory ────────────────────────────
    user_ctx = _get_user_context()
    user_ctx_block = (
        f"\n\nUSER CONTEXT:\n{user_ctx}" if user_ctx else ""
    )

    prompt = (
        f"Today: {datetime.now().strftime('%A, %B %d, %Y %I:%M %p')}\n\n"
        f"STATS: {len(emails)} total emails, {len(actionable_emails)} need attention, "
        f"{unread_count} unread, {high_priority_count} high priority, "
        f"{len(stale_drafts)} stale drafts, {len(overdue_actions)} overdue actions\n\n"
        f"Actionable emails ({len(actionable_emails)}):\n"
        + "\n".join(email_lines or ["(none)"])
        + f"\n\nPending actions ({len(pending_actions)}):\n"
        + "\n".join(action_lines or ["(none)"])
        + f"\n\nToday's calendar ({len(cal_lines)}):\n"
        + "\n".join(cal_lines or ["(no events)"])
        + user_ctx_block
    )

    try:
        raw = await llm.chat(
            messages=[
                {"role": "system", "content": _DIGEST_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=1500,
        )

        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1])

        result = json.loads(text)
        result["greeting"] = base_greeting
        result.setdefault("urgency_score", 5)
        result.setdefault(
            "one_line",
            f"You have {len(actionable_emails)} emails needing attention.",
        )
        result.setdefault("email_cards", [])
        result.setdefault("themes", [])
        result.setdefault("nudges", [])
        result.setdefault("calendar_today", [])
        result.setdefault("tip", "")
        # Backward compat
        if not result["email_cards"] and result.get("priority_emails"):
            result["email_cards"] = _convert_priority_to_cards(
                result["priority_emails"], actionable_emails
            )

        # ── Enrich cards with reasoning, deadlines, meeting actions ─────
        _evt_emails = existing_event_emails or set()
        _act_emails = existing_action_emails or set()
        email_map = {e.get("id"): e for e in actionable_emails}

        for card in result["email_cards"]:
            eid = card.get("id")
            if eid and eid in email_map:
                e = email_map[eid]
                preview = (e.get("body_preview") or "")[:200]
                if not card.get("deadline_terms"):
                    card["deadline_terms"] = extract_deadline_terms(preview)
                if not card.get("time_since"):
                    card["time_since"] = _human_time_since(
                        e.get("timestamp", "")
                    )
                # Classification reasoning
                if e.get("reasoning") and not card.get("reasoning"):
                    card["reasoning"] = e["reasoning"]
                if e.get("category") and not card.get("category"):
                    card["category"] = e["category"]
                # Thread count
                if e.get("thread_count"):
                    card["thread_count"] = e["thread_count"]
                # Already-exists flags
                has_event = eid in _evt_emails
                has_action = eid in _act_emails
                card["has_existing_event"] = has_event
                card["has_existing_action"] = has_action

                # Build suggested_actions for meeting emails
                cat = e.get("category", "")
                if cat == "meeting" and not card.get("suggested_actions"):
                    # Try to extract a date from the reasoning
                    meeting_date = _extract_date_from_reasoning(
                        e.get("reasoning", "")
                    )
                    if has_event:
                        card["suggested_actions"] = [
                            {"type": "calendar",
                             "label": "Already in calendar ✓",
                             "already_done": True},
                        ]
                    else:
                        card["suggested_actions"] = [
                            {"type": "calendar",
                             "label": f"Add meeting to calendar",
                             "date": meeting_date},
                        ]
                    if has_action:
                        card["suggested_actions"].append(
                            {"type": "action",
                             "label": "Action already created ✓",
                             "already_done": True}
                        )
                    else:
                        card["suggested_actions"].append(
                            {"type": "action",
                             "label": "Create follow-up action"}
                        )
                # Mark non-meeting existing items too
                elif card.get("suggested_actions"):
                    for sa in card["suggested_actions"]:
                        if sa["type"] == "calendar" and has_event:
                            sa["label"] = "Already in calendar ✓"
                            sa["already_done"] = True
                        if sa["type"] == "action" and has_action:
                            sa["label"] = "Action already created ✓"
                            sa["already_done"] = True

            card.setdefault("deadline_terms", [])
            card.setdefault("suggested_actions", [])
            card.setdefault("time_since", "")
            card.setdefault("preview", "")
            card.setdefault("reasoning", "")
            card.setdefault("category", "")
            card.setdefault("has_existing_event", False)
            card.setdefault("has_existing_action", False)

        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        result["auto_classified"] = config.get("auto_classify", False)
        result["emails_in_digest"] = len(actionable_emails)
        result["total_emails"] = len(emails)
        result["lookback_days"] = lookback_days

        log.info(
            "digest_generated",
            extra={
                "urgency": result["urgency_score"],
                "card_count": len(result["email_cards"]),
                "window_emails": len(window_emails),
                "actionable": len(actionable_emails),
            },
        )
        return result

    except Exception:
        log.exception("digest_generation_failed")
        return _build_deterministic_digest(
            actionable_emails, calendar_events or [], pending_actions,
            overdue_actions, stale_drafts, base_greeting,
            total_emails=len(emails),
        )


def _build_all_clear_digest(
    greeting: str,
    calendar_events: list[dict[str, Any]],
    total_emails: int,
) -> dict[str, Any]:
    """Return a celebratory digest when there's nothing to act on."""
    cal_today = []
    for ev in calendar_events[:10]:
        cal_today.append({
            "time": ev.get("time", ev.get("start", "?")),
            "title": ev.get("title", "?"),
            "id": ev.get("id"),
        })

    return {
        "greeting": greeting,
        "urgency_score": 0,
        "one_line": "You're all caught up — no pending emails or overdue tasks!",
        "email_cards": [],
        "themes": [],
        "nudges": [],
        "calendar_today": cal_today,
        "tip": (
            "Great job staying on top of things! "
            "Use this time to review stale drafts or plan ahead."
            if total_emails > 0
            else "Your inbox is empty. Enjoy the peace! ☀️"
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "auto_classified": False,
        "emails_in_digest": 0,
        "total_emails": total_emails,
        "all_clear": True,
    }


def _convert_priority_to_cards(
    priority_emails: list[dict],
    all_emails: list[dict],
) -> list[dict]:
    """Convert old-style priority_emails to email_cards format."""
    email_map = {e.get("id"): e for e in all_emails}
    cards = []
    for pe in priority_emails:
        eid = pe.get("id")
        e = email_map.get(eid, {}) if eid else {}
        preview = (e.get("body_preview") or "")[:120]
        cards.append({
            "id": eid,
            "subject": pe.get("subject", ""),
            "sender": pe.get("sender", ""),
            "preview": preview,
            "urgency": pe.get("priority", "normal"),
            "deadline_terms": extract_deadline_terms(preview),
            "suggested_actions": [],
            "time_since": _human_time_since(e.get("timestamp", "")),
        })
    return cards


def _build_deterministic_digest(
    emails: list[dict[str, Any]],
    calendar_events: list[dict[str, Any]],
    pending_actions: list[dict[str, Any]],
    overdue_actions: list[dict[str, Any]],
    stale_drafts: list[dict[str, Any]],
    greeting: str,
    *,
    total_emails: int = 0,
) -> dict[str, Any]:
    """Build a useful digest purely from data when LLM is unavailable."""
    high_emails = [
        e for e in emails
        if e.get("priority") in ("critical", "high")
    ]
    urgency = min(10, len(high_emails) * 2 + len(overdue_actions) * 3)

    # Build email cards — ALL actionable emails, ranked by urgency
    ranked = sorted(
        emails,
        key=lambda e: (
            0 if e.get("priority") == "critical" else
            1 if e.get("priority") == "high" else
            2 if not e.get("is_read", True) else 3
        ),
    )
    email_cards = []
    for e in ranked:
        preview = (e.get("body_preview") or "")[:120]
        cat = e.get("category", "unknown")
        # Auto-suggest actions for meetings
        actions = []
        if cat == "meeting":
            actions = [
                {"type": "calendar",
                 "label": f"Add meeting: {e.get('subject', 'Meeting')}"},
                {"type": "action",
                 "label": f"Prepare for: {e.get('subject', 'Meeting')}"},
            ]
        email_cards.append({
            "id": e.get("id"),
            "subject": e.get("subject", "No subject"),
            "sender": e.get("sender", "unknown"),
            "preview": preview,
            "urgency": e.get("priority", "normal"),
            "category": cat,
            "reasoning": e.get("reasoning", ""),
            "deadline_terms": extract_deadline_terms(preview),
            "suggested_actions": actions,
            "time_since": _human_time_since(e.get("timestamp", "")),
        })

    # Themes
    cat_counts: dict[str, int] = {}
    for e in emails:
        cat = e.get("category", "general")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
    themes = [
        {"theme": cat.replace("-", " ").title(), "count": count,
         "summary": f"{count} emails"}
        for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1])[:6]
    ]

    # Nudges
    nudges = []
    for oa in overdue_actions[:3]:
        nudges.append({
            "text": f"Overdue: {oa['description']} ({oa['hours_overdue']}h overdue)",
            "type": "overdue",
        })
    for sd in stale_drafts[:2]:
        nudges.append({
            "text": f"Draft unsent for \"{sd.get('subject', '?')}\"",
            "type": "stale_draft",
        })

    # Calendar
    cal_today = []
    for ev in calendar_events[:10]:
        cal_today.append({
            "time": ev.get("time", ev.get("start", "?")),
            "title": ev.get("title", "?"),
            "id": ev.get("id"),
        })

    unread = sum(1 for e in emails if not e.get("is_read", True))
    one_line = (
        f"You have {len(emails)} emails"
        + (f" ({unread} unread)" if unread else "")
        + (f", {len(high_emails)} high priority" if high_emails else "")
        + (f", and {len(overdue_actions)} overdue action(s)"
           if overdue_actions else "")
        + "."
    )

    tip = ""
    if stale_drafts:
        tip = (f"You have {len(stale_drafts)} draft(s) sitting unsent. "
               "Send or discard them to keep your inbox clean.")
    elif overdue_actions:
        tip = (f"You have {len(overdue_actions)} overdue action item(s). "
               "Tackle them first to clear your plate.")
    elif len(emails) > 20:
        tip = "Classify your emails in bulk using 'Classify All' to triage."

    return {
        "greeting": greeting,
        "urgency_score": urgency,
        "one_line": one_line,
        "email_cards": email_cards,
        "themes": themes,
        "nudges": nudges,
        "calendar_today": cal_today,
        "tip": tip,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "auto_classified": False,
        "emails_in_digest": len(emails),
        "total_emails": total_emails or len(emails),
    }

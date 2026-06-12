"""Draft agent — context-aware reply generation for AI-Rich mode.

This agent receives the full SharedAgentContext (with calendar findings,
classification, conflict details, and free slot suggestions) to produce
a higher-quality draft than the single-pass Classic drafter.
"""

from __future__ import annotations

import logging

from src.llm import client as llm
from src.llm.prompts import RICH_DRAFT_SYSTEM, RICH_DRAFT_USER
from src.models.email import DraftReply
from src.services.agents.context import SharedAgentContext
from src.services.classifier import _strip_quoted_text
from src.services.pii import PrivacyGateway, redact
from src.storage import safe_store_pii_mappings

log = logging.getLogger(__name__)


async def run_draft_agent(ctx: SharedAgentContext, *, quality: str = "balanced") -> None:
    """Generate a draft reply using the full orchestrated context.

    The prompt is richer than Classic mode's — it includes:
    - The calendar agent's availability verdict
    - Specific conflict details and free slot suggestions
    - The classification agent's reasoning
    """
    email = ctx.email
    classification = ctx.classification
    privacy = PrivacyGateway()

    if classification is None:
        ctx.record_error("draft_agent", "No classification available — skipping draft")
        return

    # ── Build body sections ────────────────────────────────────────────
    latest_body = _strip_quoted_text(email.body)
    full_body = email.body
    thread_part = full_body[len(latest_body):].strip()
    thread_context_block = ""
    if thread_part:
        thread_context_block = (
            "--- Thread history (for context only, do NOT mimic) ---\n"
            + thread_part
        )

    # ── Build calendar context from agent findings ─────────────────────
    cal = ctx.calendar
    calendar_instruction = ""
    if cal.conflicts:
        conflict_names = ", ".join(f'"{c.event.title}"' for c in cal.conflicts)
        slot_suggestion = ""
        if cal.free_slots:
            slot_strs = [
                f"{s.start.strftime('%H:%M')}–{s.end.strftime('%H:%M')}"
                for s in cal.free_slots[:3]
            ]
            slot_suggestion = f" Suggest alternatives: {', '.join(slot_strs)}."
        calendar_instruction = (
            f"\n\n*** MANDATORY: You are NOT available. "
            f"You have conflicts with {conflict_names}. "
            f"DECLINE the proposed time and ask for an alternative.{slot_suggestion} ***"
        )
    elif cal.resolved_date:
        calendar_instruction = (
            "\n\n*** MANDATORY: You ARE available. "
            "ACCEPT the proposed time. Confirm you are free "
            "and look forward to the meeting/call. ***"
        )

    user_msg = RICH_DRAFT_USER.format(
        sender=privacy.mask_text(email.sender).text,
        subject=privacy.mask_text(email.subject).text,
        timestamp=email.timestamp.isoformat(),
        latest_body=privacy.mask_text(latest_body).text,
        thread_context=privacy.mask_text(thread_context_block).text,
        priority=classification.priority.value,
        category=classification.category.value,
        classification_reasoning=classification.reasoning or "",
        calendar_instruction=calendar_instruction,
        availability_summary=cal.availability_summary,
    )

    # ── Quality parameters ─────────────────────────────────────────────
    quality_params = {
        "quick": (0.3, 400),
        "balanced": (0.4, 700),
        "thorough": (0.5, 1200),
    }
    temperature, max_tokens = quality_params.get(quality, (0.4, 700))

    raw = await llm.chat(
        messages=[
            {"role": "system", "content": RICH_DRAFT_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )

    # ── Rehydrate and redact ───────────────────────────────────────────
    rehydrated = privacy.rehydrate_text(raw.strip())
    result = _redact_new_pii(rehydrated, allowed_values={m.original for m in privacy.mappings})
    pii_types = sorted(
        {_pii_type(m.entity_type) for m in privacy.mappings} | set(result.found_types)
    )

    draft = DraftReply(
        body=result.text,
        tone="professional",
        quality=quality,
        pii_redacted=result.was_redacted,
        redacted_types=pii_types,
    )

    ctx.draft = draft
    safe_store_pii_mappings(email.id, "rich_draft", privacy.mappings)
    ctx.record_agent("draft_agent")

    log.info(
        "draft_agent_complete",
        extra={
            "email_id": email.id,
            "quality": quality,
            "calendar_instruction_len": len(calendar_instruction),
        },
    )


def _redact_new_pii(text: str, *, allowed_values: set[str]):
    """Mask hallucinated PII while allowing values restored from the email."""
    result = redact(text)
    for mapping in result.mappings:
        if mapping.original in allowed_values:
            result.text = result.text.replace(mapping.token, mapping.original)
    result.mappings = [
        mapping for mapping in result.mappings if mapping.original not in allowed_values
    ]
    result.found_types = sorted({_pii_type(m.entity_type) for m in result.mappings})
    return result


def _pii_type(entity_type: str) -> str:
    return "ssn" if entity_type == "US_SSN" else entity_type.lower()

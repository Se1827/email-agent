"""AI-Rich orchestrator — supervisor-driven multi-agent pipeline.

This is the entry point for AI-Rich mode. It:
1. Asks the supervisor agent to decide which specialists to invoke
2. Dispatches to each specialist in order, passing the shared context
3. Returns the same (Classification, ResolvedDate) tuple as Classic mode

On any failure, it falls back to Classic mode for resilient degradation.
"""

from __future__ import annotations

import logging
from datetime import datetime

from src.llm.date_resolver import ResolvedDate
from src.models.email import CalendarEvent, Classification, DraftReply, Email
from src.services.agents.context import AgentType, SharedAgentContext
from src.services.agents.supervisor import run_supervisor
from src.services.agents.memory_agent import run_memory_agent
from src.services.agents.thread_agent import run_thread_agent
from src.services.agents.calendar_agent import run_calendar_agent
from src.services.agents.classification_agent import run_classification_agent
from src.services.agents.draft_agent import run_draft_agent

log = logging.getLogger(__name__)


async def orchestrate_classify(
    email: Email,
    calendar_events: list[CalendarEvent] | None = None,
) -> tuple[Classification, ResolvedDate | None]:
    """AI-Rich classification: supervisor → agents → Classification.

    Returns the same type as ``classifier.classify()`` for API compatibility.
    Falls back to Classic mode on orchestration failure.
    """
    try:
        ctx = SharedAgentContext(
            email=email,
            calendar_events=calendar_events or [],
        )

        # ── Step 0: Memory agent (always runs first, zero LLM calls) ──
        try:
            await run_memory_agent(ctx)
        except Exception as exc:
            ctx.record_error("memory_agent", str(exc))

        # ── Step 1: Supervisor triage ──────────────────────────────────
        plan = await run_supervisor(email)
        ctx.plan = plan
        ctx.record_agent("supervisor")

        # ── Step 2: Execute agent pipeline ─────────────────────────────
        agent_dispatch = {
            AgentType.CALENDAR: run_calendar_agent,
            AgentType.CLASSIFICATION: run_classification_agent,
            AgentType.THREAD: run_thread_agent,
        }

        for step in plan.steps:
            if step.agent in (AgentType.DRAFT, AgentType.MEMORY):
                continue  # Draft handled separately; memory already ran
            handler = agent_dispatch.get(step.agent)
            if handler:
                try:
                    await handler(ctx)
                except Exception as exc:
                    ctx.record_error(step.agent.value, str(exc))
                    log.warning(
                        f"agent_{step.agent.value}_failed",
                        extra={"error": str(exc), "email_id": email.id},
                    )

        # ── Ensure classification was produced ─────────────────────────
        if ctx.classification is None:
            log.info("orchestrator_force_classification", extra={"email_id": email.id})
            await run_classification_agent(ctx)

        # ── Build resolved date from calendar findings ─────────────────
        resolved_date = None
        if ctx.calendar.resolved_date:
            resolved_date = ResolvedDate(
                date=ctx.calendar.resolved_date,
                time=ctx.calendar.resolved_time,
                is_all_day=ctx.calendar.is_all_day,
                summary=ctx.calendar.availability_summary,
            )

        log.info(
            "orchestrate_classify_complete",
            extra={
                "email_id": email.id,
                "agents_executed": ctx.agents_executed,
                "total_llm_calls": ctx.total_llm_calls,
                "errors": ctx.errors,
                "priority": ctx.classification.priority.value if ctx.classification else None,
            },
        )

        return ctx.classification, resolved_date

    except Exception as exc:
        log.error(
            "orchestrator_fallback_to_classic",
            extra={"error": str(exc), "email_id": email.id},
        )
        from src.services import classifier
        return await classifier.classify(email, calendar_events, ai_mode="classic")


async def orchestrate_draft(
    email: Email,
    classification: Classification,
    calendar_events: list[CalendarEvent] | None = None,
    *,
    quality: str = "balanced",
) -> DraftReply:
    """AI-Rich drafting: builds context from classification, runs draft agent.

    Returns the same DraftReply type as ``drafter.draft_reply()``
    for API compatibility. Falls back to Classic on failure.
    """
    try:
        ctx = SharedAgentContext(
            email=email,
            calendar_events=calendar_events or [],
        )
        ctx.classification = classification

        # ── Memory agent (for tone matching and context) ───────────────
        try:
            await run_memory_agent(ctx)
        except Exception:
            pass

        # ── Run calendar agent to get availability context ─────────────
        await run_calendar_agent(ctx)

        # ── Run draft agent ────────────────────────────────────────────
        await run_draft_agent(ctx, quality=quality)

        if ctx.draft is None:
            raise RuntimeError("Draft agent produced no output")

        log.info(
            "orchestrate_draft_complete",
            extra={
                "email_id": email.id,
                "agents_executed": ctx.agents_executed,
                "total_llm_calls": ctx.total_llm_calls,
                "quality": quality,
            },
        )

        return ctx.draft

    except Exception as exc:
        log.error(
            "orchestrator_draft_fallback_to_classic",
            extra={"error": str(exc), "email_id": email.id},
        )
        from src.services import drafter
        return await drafter.draft_reply(
            email, classification,
            calendar_events=calendar_events,
            quality=quality,
        )

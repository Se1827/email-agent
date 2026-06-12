"""Shared context and data models for AI-Rich multi-agent orchestration.

The SharedAgentContext is the accumulator that gets passed between agents.
Each agent enriches it with its findings, and the final agent (usually
the drafter) consumes the full context to produce the output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from src.models.email import CalendarEvent, Classification, DraftReply, Email
from src.services.conflicts import ConflictResult, TimeSlot


class AgentType(str, Enum):
    """The specialist agents available in AI-Rich mode."""
    CALENDAR = "calendar"
    CLASSIFICATION = "classification"
    DRAFT = "draft"


@dataclass
class AgentStep:
    """A single step in the supervisor's plan."""
    agent: AgentType
    reason: str  # Why the supervisor chose this agent


@dataclass
class AgentPlan:
    """The supervisor's triage output: an ordered list of agents to invoke."""
    steps: list[AgentStep]
    email_summary: str
    triage_reasoning: str

    @property
    def agent_sequence(self) -> list[AgentType]:
        return [step.agent for step in self.steps]


@dataclass
class CalendarFindings:
    """Output from the calendar agent."""
    resolved_date: datetime | None = None
    resolved_time: tuple[int, int] | None = None
    is_all_day: bool = False
    conflicts: list[ConflictResult] = field(default_factory=list)
    free_slots: list[TimeSlot] = field(default_factory=list)
    availability_summary: str = ""


@dataclass
class SharedAgentContext:
    """The accumulator passed between agents in AI-Rich mode.

    Each agent reads what previous agents have discovered, adds its own
    findings, and passes the enriched context forward.
    """
    # ── Input (set once at the start) ──────────────────────────────────
    email: Email
    calendar_events: list[CalendarEvent] = field(default_factory=list)
    plan: AgentPlan | None = None

    # ── Calendar agent output ──────────────────────────────────────────
    calendar: CalendarFindings = field(default_factory=CalendarFindings)

    # ── Classification agent output ────────────────────────────────────
    classification: Classification | None = None

    # ── Draft agent output ─────────────────────────────────────────────
    draft: DraftReply | None = None

    # ── Agent execution metadata ───────────────────────────────────────
    agents_executed: list[str] = field(default_factory=list)
    total_llm_calls: int = 0
    errors: list[str] = field(default_factory=list)

    def record_agent(self, agent_name: str, llm_calls: int = 1) -> None:
        """Track which agents ran and how many LLM calls were made."""
        self.agents_executed.append(agent_name)
        self.total_llm_calls += llm_calls

    def record_error(self, agent_name: str, error: str) -> None:
        """Record a non-fatal agent error."""
        self.errors.append(f"{agent_name}: {error}")

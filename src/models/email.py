"""Pydantic data models for emails, classifications, drafts, and calendar events."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Priority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class Category(str, Enum):
    MEETING = "meeting"
    DEADLINE = "deadline"
    INFO = "info"
    ACTION_REQUIRED = "action-required"
    SPAM = "spam"


# ---------------------------------------------------------------------------
# Core models
# ---------------------------------------------------------------------------

class Email(BaseModel):
    id: str
    sender: str
    recipients: list[str]
    subject: str
    body: str
    timestamp: datetime
    thread_id: Optional[str] = None

    # Populated after classification.
    classification: Optional[Classification] = None
    # Populated after draft generation.
    draft_reply: Optional[DraftReply] = None


class Classification(BaseModel):
    priority: Priority
    category: Category
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""


class DraftReply(BaseModel):
    body: str
    tone: str = "professional"
    pii_redacted: bool = False
    redacted_types: list[str] = Field(default_factory=list)


class CalendarEvent(BaseModel):
    title: str
    start: datetime
    end: datetime
    attendees: list[str] = Field(default_factory=list)


# Rebuild Email so the forward references resolve.
Email.model_rebuild()

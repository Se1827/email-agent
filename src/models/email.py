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
class DraftQuality(str, Enum):
    QUICK = "quick"
    BALANCED = "balanced"
    THOROUGH = "thorough"
# ---------------------------------------------------------------------------
# Core models
# ---------------------------------------------------------------------------
class Attachment(BaseModel):
    """Metadata for a single email attachment."""
    filename: str
    content_type: str = "application/octet-stream"
    size: int = 0  # bytes
    # Relative path under data/attachments/ (filled after save to disk).
    stored_path: Optional[str] = None
class Email(BaseModel):
    # Format: {account_id}:{mailbox}:{uidvalidity}:{uid}
    id: str
    uid: Optional[int] = None
    uidvalidity: Optional[int] = None
    inbox: Optional[str] = None
    account_id: Optional[str] = None
    sender: str
    recipients: list[str]
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    subject: str
    body: str
    html_body: Optional[str] = None
    timestamp: datetime
    thread_id: Optional[str] = None
    # RFC-2822 threading headers.
    message_id: Optional[str] = None
    in_reply_to: Optional[str] = None
    references: list[str] = Field(default_factory=list)
    # Sent flag — True for emails sent from this client.
    is_sent: bool = False
    # UI state.
    is_read: bool = False
    is_starred: bool = False
    labels: list[str] = Field(default_factory=list)
    attachments: list[Attachment] = Field(default_factory=list)
    # Populated after classification.
    classification: Optional[Classification] = None
    # Populated after draft generation.
    draft_reply: Optional[DraftReply] = None
    # Internal UI/debug hint: db, source, source+cache, or source-updated.
    storage_origin: Optional[str] = None
class Classification(BaseModel):
    priority: Priority
    category: Category
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""
    explanation_factors: list[str] = Field(default_factory=list)
    # e.g. ["sender is VIP", "deadline mentioned", "related meeting tomorrow"]
class DraftReply(BaseModel):
    body: str                    # primary draft (backward compat)
    alternatives: list[str] = Field(default_factory=list)  # 0-2 alternative drafts
    tone: str = "professional"
    quality: str = "balanced"
    pii_redacted: bool = False
    redacted_types: list[str] = Field(default_factory=list)
class CalendarEvent(BaseModel):
    id: Optional[str] = None
    title: str
    start: datetime
    end: datetime
    description: str = ""
    location: str = ""
    color: str = ""
    attendees: list[str] = Field(default_factory=list)
    account_id: Optional[str] = None
    is_all_day: bool = False
    recurrence: Optional[str] = None
class Notification(BaseModel):
    id: str
    type: str  # "deadline", "meeting_soon", "urgent_email", "ai_insight"
    title: str
    message: str
    severity: str  # "critical", "warning", "info"
    related_id: Optional[str] = None  # email_id or event_id
    related_type: Optional[str] = None  # "email" or "event"
    timestamp: datetime
    is_read: bool = False
class DashboardStats(BaseModel):
    total_emails: int = 0
    unread_count: int = 0
    classified_count: int = 0
    starred_count: int = 0
    priority_breakdown: dict[str, int] = Field(default_factory=dict)
    category_breakdown: dict[str, int] = Field(default_factory=dict)
    accounts: list[dict] = Field(default_factory=list)
    upcoming_events: list[dict] = Field(default_factory=list)
    notifications: list[dict] = Field(default_factory=list)
    recent_activity: list[dict] = Field(default_factory=list)
    storage_stats: dict = Field(default_factory=dict)
class AccountConfig(BaseModel):
    id: str
    name: str
    email: str
    provider: str = "imap"  # gmail, outlook, imap
    imap_host: str = ""
    imap_port: int = 993
    imap_user: str = ""
    imap_pass: str = ""
    imap_mailbox: str = "INBOX"
    imap_use_ssl: bool = True
    # SMTP settings for sending mail.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""    # falls back to imap_user / email
    smtp_pass: str = ""    # falls back to imap_pass
    smtp_use_ssl: bool = False   # direct SSL (port 465)
    smtp_use_tls: bool = True    # STARTTLS (port 587)
    color: str = "#3b82f6"
    is_active: bool = True
class SyncState(BaseModel):
    account_id: str
    mailbox: str
    uidvalidity: int
    last_uid: int
    highestmodseq: int = 0
    updated_at: datetime = Field(default_factory=datetime.utcnow)
# Rebuild Email so the forward references resolve.
Email.model_rebuild()

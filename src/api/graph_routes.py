"""src/api/graph_routes.py — Microsoft Graph plugin routes.

Registers as a FastAPI APIRouter and is mounted in src/api/app.py.
All routes work in mock mode (GRAPH_MOCK=true) with zero Azure credentials.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.connectors.graph import graph, IS_MOCK

router = APIRouter(prefix="/graph", tags=["Microsoft Graph"])


# ── Request models ─────────────────────────────────────────────────────────────

class SendMailRequest(BaseModel):
    to: str
    subject: str
    body: str
    reply_to_id: Optional[str] = None


class CreateEventRequest(BaseModel):
    subject: str
    start_iso: str
    end_iso: str
    body: Optional[str] = ""
    attendees: Optional[list[str]] = []


class TeamsNotifyRequest(BaseModel):
    channel_id: str
    message: str


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/status")
def graph_status() -> dict:
    """Returns connector mode (mock / live) and config hints."""
    return {
        "mode": "mock" if IS_MOCK else "live",
        "user_email": graph.__class__.__module__,  # non-sensitive
        "tip": (
            "Running in mock mode — set GRAPH_MOCK=false + Azure creds in .env to go live."
            if IS_MOCK
            else "Connected to Microsoft Graph (live mode)."
        ),
    }


# ── Mail endpoints ─────────────────────────────────────────────────────────────

@router.get("/mail/inbox")
def graph_inbox(top: int = 20) -> dict:
    """Fetch inbox messages from Microsoft Graph (or mock)."""
    try:
        raw = graph.list_messages(top=top)
        return {
            "count": len(raw),
            "source": "mock" if IS_MOCK else "microsoft_graph",
            "messages": [graph.to_agent_email(m) for m in raw],
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Graph API error: {exc}") from exc


@router.get("/mail/{message_id}")
def graph_get_message(message_id: str) -> dict:
    """Get a single mail message with full body."""
    try:
        return graph.to_agent_email(graph.get_message(message_id))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/mail/send")
def graph_send_mail(req: SendMailRequest) -> dict:
    """Send or reply to an email via Microsoft Graph."""
    try:
        result = graph.send_message(req.to, req.subject, req.body, req.reply_to_id)
        return {"status": "ok", "detail": result}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/mail/{message_id}/attachments")
def graph_list_attachments(message_id: str) -> dict:
    """List attachments for a mail message."""
    try:
        attachments = graph.list_attachments(message_id)
        return {"count": len(attachments), "attachments": attachments}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ── Calendar endpoints ─────────────────────────────────────────────────────────

@router.get("/calendar/today")
def graph_calendar_today() -> dict:
    """Return today's calendar events from Microsoft Graph."""
    try:
        events = graph.list_events(days_ahead=1)
        return {"count": len(events), "events": events}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/calendar/events")
def graph_create_event(req: CreateEventRequest) -> dict:
    """Create a calendar event in Microsoft Graph."""
    try:
        ev = graph.create_event(
            req.subject, req.start_iso, req.end_iso,
            req.body or "", req.attendees or [],
        )
        return {"status": "created", "event": ev}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/calendar/auto-block")
def graph_auto_block(message_id: str, deadline_iso: str) -> dict:
    """Detect conflicts and auto-create a calendar block before the deadline."""
    try:
        result = graph.auto_block(message_id, deadline_iso)
        return {
            "status": "created",
            "event": result["event"],
            "conflicts": result["conflicts"],
            "message": (
                f"Blocked calendar 1h before deadline. "
                f"Conflicts: {result['conflicts'] or 'none'}"
            ),
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ── Teams endpoints ───────────────────────────────────────────────────────────

@router.post("/teams/notify")
def graph_teams_notify(req: TeamsNotifyRequest) -> dict:
    """Send a Teams message via Microsoft Graph."""
    try:
        result = graph.notify_teams(req.channel_id, req.message)
        return {"status": "sent", "detail": result}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ── Presence endpoint ─────────────────────────────────────────────────────────

@router.get("/presence/{user_email}")
def graph_presence(user_email: str) -> dict:
    """Get Teams presence for a user (Available / Busy / Away etc.)."""
    try:
        return graph.get_presence(user_email)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

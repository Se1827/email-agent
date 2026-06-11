"""src/api/graph_routes.py — Microsoft Graph plugin routes.

Registers as a FastAPI APIRouter and is mounted in src/api/app.py.
All routes work in mock mode (GRAPH_MOCK=true) with zero Azure credentials.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.connectors.graph import graph, IS_MOCK
from src.llm.client import chat
from src.llm.prompts import CLASSIFY_SYSTEM, CLASSIFY_USER, DRAFT_SYSTEM, DRAFT_USER_TEMPLATES, DRAFT_QUALITY_PARAMS

router = APIRouter(tags=["Microsoft Graph"])



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


# ── Config models ─────────────────────────────────────────────────────────────

class GraphConfig(BaseModel):
    graph_mock: bool
    tenant_id: str
    client_id: str
    client_secret: str
    user_email: str


# ── Status and Config ─────────────────────────────────────────────────────────

@router.get("/config")
def graph_get_config() -> dict:
    """Returns the current Microsoft Graph API configuration."""
    from src.config import get_settings
    import os
    from dotenv import dotenv_values
    env_vars = dotenv_values(get_settings().data_dir.parent / ".env")
    return {
        "graph_mock": env_vars.get("GRAPH_MOCK", "true").lower() == "true",
        "tenant_id": env_vars.get("AZURE_TENANT_ID", ""),
        "client_id": env_vars.get("AZURE_CLIENT_ID", ""),
        "client_secret": env_vars.get("AZURE_CLIENT_SECRET", ""),
        "user_email": env_vars.get("GRAPH_USER_EMAIL", ""),
    }

@router.post("/config")
def graph_update_config(config: GraphConfig) -> dict:
    """Updates the Microsoft Graph API configuration in .env."""
    from src.config import get_settings
    from dotenv import set_key
    env_path = get_settings().data_dir.parent / ".env"
    
    # Ensure .env exists
    if not env_path.exists():
        env_path.touch()
        
    set_key(env_path, "GRAPH_MOCK", "true" if config.graph_mock else "false")
    set_key(env_path, "AZURE_TENANT_ID", config.tenant_id)
    set_key(env_path, "AZURE_CLIENT_ID", config.client_id)
    set_key(env_path, "AZURE_CLIENT_SECRET", config.client_secret)
    set_key(env_path, "GRAPH_USER_EMAIL", config.user_email)
    
    # Dynamically update the module variables in GraphConnector
    import src.connectors.graph as graph_module
    graph_module.IS_MOCK = config.graph_mock
    graph_module.TENANT_ID = config.tenant_id
    graph_module.CLIENT_ID = config.client_id
    graph_module.CLIENT_SECRET = config.client_secret
    graph_module.USER_EMAIL = config.user_email
    
    return {"status": "ok", "message": "Graph configuration updated."}


@router.get("/status")
def graph_status() -> dict:
    """Returns connector mode (mock / live) and config hints."""
    from src.connectors.graph import USER_EMAIL, IS_MOCK, _get_token, GraphAuthRequired
    if IS_MOCK:
        return {
            "mode": "mock",
            "user_email": USER_EMAIL,
            "tip": "Running in mock mode — set GRAPH_MOCK=false + Azure creds in .env to go live.",
        }
    
    try:
        _get_token(auto_login=False)
        return {
            "mode": "live",
            "user_email": USER_EMAIL,
            "tip": "Connected to Microsoft Graph (live mode).",
        }
    except GraphAuthRequired:
        return {
            "mode": "offline",
            "user_email": USER_EMAIL,
            "tip": "Microsoft Graph is disconnected. Run `python src/connectors/graph.py --login` to reconnect.",
        }
    except Exception as e:
        return {
            "mode": "error",
            "user_email": USER_EMAIL,
            "tip": f"Error checking Graph status: {e}",
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


@router.get("/mail/thread/{conversation_id}")
def graph_get_thread(conversation_id: str) -> dict:
    """Get all mail messages in a conversation thread."""
    try:
        raw = graph.list_thread_messages(conversation_id)
        return {
            "count": len(raw),
            "messages": [graph.to_agent_email(m) for m in raw],
        }
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
def graph_calendar_today(days_ahead: int = 30) -> dict:
    """Return upcoming calendar events from Microsoft Graph (default 30 days)."""
    try:
        events = graph.list_events(days_ahead=days_ahead)
        return {"count": len(events), "events": events}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Graph API error: {exc}") from exc


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
# ── Contacts endpoint ────────────────────────────────────────────────────────

@router.get("/contacts")
def graph_contacts(top: int = 20) -> dict:
    """Return contacts from Microsoft Graph (or mock)."""
    try:
        return {"count": top, "contacts": graph.list_contacts(top=top)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

# ── Users endpoint ────────────────────────────────────────────────────────

@router.get("/users/me")
def graph_user_profile() -> dict:
    """Return the authenticated user's profile."""
    try:
        return graph.get_user_profile()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

# ── Groups endpoint ────────────────────────────────────────────────────────

@router.get("/groups")
def graph_groups(top: int = 20) -> dict:
    """Return groups the user belongs to."""
    try:
        return {"count": top, "groups": graph.list_groups(top=top)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

# ── Drive items endpoint ────────────────────────────────────────────────────

@router.get("/drive/items")
def graph_drive_items(top: int = 20) -> dict:
    """Return OneDrive items (files/folders)."""
    try:
        return {"count": top, "items": graph.list_drive_items(top=top)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ── AI endpoints ─────────────────────────────────────────────────────────────

class GraphClassifyRequest(BaseModel):
    message_id: str


class GraphDraftRequest(BaseModel):
    message_id: str
    quality: str = "balanced"   # quick | balanced | thorough


@router.post("/mail/classify")
async def graph_classify_mail(req: GraphClassifyRequest) -> dict:
    """Classify a Graph mail message using the LLM."""
    try:
        raw = graph.get_message(req.message_id)
        msg = graph.to_agent_email(raw)
        user_prompt = CLASSIFY_USER.format(
            sender=msg.get("sender", ""),
            recipients=msg.get("to", ""),
            timestamp=msg.get("timestamp", ""),
            subject=msg.get("subject", ""),
            body=(msg.get("body") or msg.get("snippet") or "")[:3000],
            calendar_context="",
        )
        reply = await chat(
            [{"role": "system", "content": CLASSIFY_SYSTEM},
             {"role": "user",   "content": user_prompt}],
            temperature=0.2,
            max_tokens=300,
        )
        classification = json.loads(reply.strip())
        return {"message_id": req.message_id, "classification": classification}
    except json.JSONDecodeError:
        return {"message_id": req.message_id, "classification": {"raw": reply}}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/mail/draft-reply")
async def graph_draft_reply(req: GraphDraftRequest) -> dict:
    """Draft an AI reply for a Graph mail message."""
    try:
        raw = graph.get_message(req.message_id)
        msg = graph.to_agent_email(raw)
        quality = req.quality if req.quality in DRAFT_USER_TEMPLATES else "balanced"
        temperature, max_tokens = DRAFT_QUALITY_PARAMS[quality]
        user_prompt = DRAFT_USER_TEMPLATES[quality].format(
            sender=msg.get("sender", ""),
            subject=msg.get("subject", ""),
            timestamp=msg.get("timestamp", ""),
            latest_body=(msg.get("body") or msg.get("snippet") or "")[:3000],
            thread_context="",
            priority="normal",
            category="info",
            availability_instruction="",
        )
        draft = await chat(
            [{"role": "system", "content": DRAFT_SYSTEM},
             {"role": "user",   "content": user_prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return {"message_id": req.message_id, "draft": draft.strip()}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/mail/summarize")
async def graph_summarize_mail(req: GraphClassifyRequest) -> dict:
    """Return a 2-3 sentence AI summary of a Graph mail message."""
    try:
        raw = graph.get_message(req.message_id)
        msg = graph.to_agent_email(raw)
        body = (msg.get("body") or msg.get("snippet") or "")[:3000]
        summary = await chat(
            [{"role": "system", "content": "You are an email summarizer. Summarize the email in 2-3 concise sentences. Output only the summary text, no labels."},
             {"role": "user",   "content": f"Subject: {msg.get('subject','')}\n\n{body}"}],
            temperature=0.3,
            max_tokens=200,
        )
        return {"message_id": req.message_id, "summary": summary.strip()}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/mail/add-to-calendar")
async def graph_add_to_calendar(req: GraphClassifyRequest) -> dict:
    """Use AI to extract meeting details from an email and create a calendar event."""
    from datetime import timezone
    try:
        raw = graph.get_message(req.message_id)
        msg = graph.to_agent_email(raw)
        body = (msg.get("body") or msg.get("snippet") or "")[:3000]
        subject = msg.get("subject", "")
        sender = msg.get("sender", "")

        # Today's date for reference
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        extraction_prompt = f"""Today is {today}. Extract meeting/event details from the email below.
Return ONLY valid JSON with these fields:
{{
  "title": "meeting title",
  "date": "YYYY-MM-DD",
  "start_time": "HH:MM",
  "end_time": "HH:MM",
  "attendees": ["email1", "email2"],
  "description": "brief description",
  "found": true
}}
If no meeting details found, return {{"found": false}}.
"tomorrow afternoon" means 14:00-15:00 the next day.
"tomorrow morning" means 09:00-10:00 the next day.

Email subject: {subject}
From: {sender}
Body: {body}"""

        reply = await chat(
            [{"role": "system", "content": "You are a calendar assistant. Extract meeting details and return JSON only."},
             {"role": "user",   "content": extraction_prompt}],
            temperature=0.1,
            max_tokens=300,
        )

        # Parse JSON (strip markdown fences if present)
        clean = reply.strip().strip("```json").strip("```").strip()
        details = json.loads(clean)

        if not details.get("found"):
            return {"status": "no_meeting_found", "message": "No meeting details found in this email."}

        # Build ISO datetimes
        date = details.get("date", today)
        start_time = details.get("start_time", "14:00")
        end_time   = details.get("end_time",   "15:00")
        start_iso  = f"{date}T{start_time}:00"
        end_iso    = f"{date}T{end_time}:00"
        title      = details.get("title") or subject or "Meeting"
        attendees  = details.get("attendees") or [sender]
        description = details.get("description", f"Meeting scheduled from email: {subject}")

        event = graph.create_event(title, start_iso, end_iso, description, attendees)
        return {
            "status": "created",
            "event_id": event.get("id"),
            "title": title,
            "start": start_iso,
            "end": end_iso,
            "attendees": attendees,
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="AI could not parse meeting details")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


class CreateFromTextRequest(BaseModel):
    subject: str
    body: str
    recipient: str


@router.post("/calendar/create-from-text")
async def graph_create_from_text(req: CreateFromTextRequest) -> dict:
    """Use AI to extract meeting details from sent email text and create a calendar event."""
    from datetime import timezone
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        extraction_prompt = f"""Today is {today}. Extract meeting/event details from this sent email.
Return ONLY valid JSON with these fields:
{{
  "title": "meeting title",
  "date": "YYYY-MM-DD",
  "start_time": "HH:MM",
  "end_time": "HH:MM",
  "attendees": ["email1"],
  "description": "brief description",
  "found": true
}}
If no meeting/scheduling intent or details found in the email, return {{"found": false}}.
"tomorrow afternoon" means 14:00-15:00 the next day.
"tomorrow morning" means 09:00-10:00 the next day.

Email subject: {req.subject}
Recipient: {req.recipient}
Body: {req.body}"""

        reply = await chat(
            [{"role": "system", "content": "You are a calendar assistant. Extract meeting details from text and return JSON only."},
             {"role": "user",   "content": extraction_prompt}],
            temperature=0.1,
            max_tokens=300,
        )

        clean = reply.strip().strip("```json").strip("```").strip()
        details = json.loads(clean)

        if not details.get("found"):
            return {"status": "no_meeting_found"}

        date = details.get("date", today)
        start_time = details.get("start_time", "14:00")
        end_time   = details.get("end_time",   "15:00")
        start_iso  = f"{date}T{start_time}:00Z"
        end_iso    = f"{date}T{end_time}:00Z"
        title      = details.get("title") or req.subject or "Meeting"
        attendees  = details.get("attendees") or [req.recipient]
        description = details.get("description", f"Auto-scheduled from sent email: {req.subject}")

        event = graph.create_event(title, start_iso, end_iso, description, attendees)
        return {
            "status": "created",
            "event_id": event.get("id"),
            "title": title,
            "start": start_iso,
            "end": end_iso,
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

"""
src/connectors/graph.py
Microsoft Graph connector – sits alongside imap.py and mock.py.

MOCK MODE  (default, GRAPH_MOCK=true): works right now, zero Azure needed.
LIVE MODE:  set GRAPH_MOCK=false + fill Azure creds in .env.
            First run will open a browser login for your KIIT account (device code flow).
            Token is cached in .graph_token_cache.json so you only log in once.
"""
from __future__ import annotations

import os
import uuid
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────────
IS_MOCK       = os.getenv("GRAPH_MOCK", "true").lower() == "true"
TENANT_ID     = os.getenv("AZURE_TENANT_ID",     "mock-tenant")
CLIENT_ID     = os.getenv("AZURE_CLIENT_ID",     "mock-client")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "mock-secret")
USER_EMAIL    = os.getenv("GRAPH_USER_EMAIL",    "23053333@kiit.ac.in")
GRAPH_BASE    = "https://graph.microsoft.com/v1.0"
TOKEN_CACHE   = Path(__file__).parent.parent.parent / ".graph_token_cache.json"

SCOPES = [
    "https://graph.microsoft.com/Mail.Read",
    "https://graph.microsoft.com/Mail.Send",
    "https://graph.microsoft.com/Calendars.Read",
    "https://graph.microsoft.com/User.Read",
    "offline_access",
]

# ── Mock data (realistic Graph API shape) ──────────────────────────────────────
_now = datetime.now(timezone.utc)

_MOCK_MESSAGES = [
    {
        "id": "graph-msg-001",
        "subject": "Re: Hackathon submission deadline",
        "bodyPreview": "Panel needs prototype + 2-min video by 5 PM today.",
        "body": {
            "contentType": "html",
            "content": (
                "<p>Hi,</p><p>The judging panel needs the final prototype link and a "
                "2-minute video by <b>5:00 PM today</b>. Please confirm receipt.</p>"
                "<p>Best,<br>Rahul</p>"
            ),
        },
        "from": {"emailAddress": {"name": "Rahul Sharma", "address": "rahul.sharma@kiit.ac.in"}},
        "toRecipients": [{"emailAddress": {"name": "You", "address": USER_EMAIL}}],
        "receivedDateTime": (_now - timedelta(hours=1)).isoformat() + "Z",
        "isRead": False,
        "importance": "high",
        "hasAttachments": True,
        "conversationId": "conv-001",
        "categories": [],
    },
    {
        "id": "graph-msg-002",
        "subject": "Q3 Review – Action Required",
        "bodyPreview": "Please review deck and share inputs by Friday EOW.",
        "body": {
            "contentType": "html",
            "content": (
                "<p>Hi Team,</p><p>Please review the attached Q3 deck and share "
                "your inputs by <b>Friday EOW</b>.</p><p>Thanks,<br>Priya</p>"
            ),
        },
        "from": {"emailAddress": {"name": "Priya Menon", "address": "priya.menon@kiit.ac.in"}},
        "toRecipients": [{"emailAddress": {"name": "You", "address": USER_EMAIL}}],
        "receivedDateTime": (_now - timedelta(hours=3)).isoformat() + "Z",
        "isRead": False,
        "importance": "normal",
        "hasAttachments": True,
        "conversationId": "conv-002",
        "categories": [],
    },
]

_MOCK_EVENTS = [
    {
        "id": "evt-001",
        "subject": "Team Standup",
        "start": {
            "dateTime": _now.replace(hour=16, minute=0, second=0, microsecond=0).isoformat(),
            "timeZone": "UTC",
        },
        "end": {
            "dateTime": _now.replace(hour=16, minute=30, second=0, microsecond=0).isoformat(),
            "timeZone": "UTC",
        },
        "isOnlineMeeting": True,
        "onlineMeetingUrl": "https://teams.microsoft.com/mock-standup",
        "bodyPreview": "Daily sync",
        "attendees": [],
    },
]

_MOCK_ATTACHMENTS: dict[str, list] = {
    "graph-msg-001": [
        {
            "id": "att-001",
            "name": "hackathon_brief_v3.pdf",
            "contentType": "application/pdf",
            "size": 204800,
        }
    ],
}


# ── Auth helper (live mode – device code flow) ─────────────────────────────────

def _load_cached_token() -> dict | None:
    if TOKEN_CACHE.exists():
        try:
            return json.loads(TOKEN_CACHE.read_text())
        except Exception:
            return None
    return None


def _save_token(token_data: dict) -> None:
    TOKEN_CACHE.write_text(json.dumps(token_data))


def _is_token_expired(token_data: dict) -> bool:
    expires_at = token_data.get("expires_at", 0)
    return datetime.utcnow().timestamp() >= expires_at - 60


def _refresh_token(token_data: dict) -> dict:
    import httpx
    resp = httpx.post(
        f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token",
        data={
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": token_data["refresh_token"],
            "scope": " ".join(SCOPES),
        },
        timeout=10,
    )
    resp.raise_for_status()
    new_token = resp.json()
    new_token["expires_at"] = datetime.utcnow().timestamp() + new_token.get("expires_in", 3600)
    _save_token(new_token)
    return new_token


def _device_code_login() -> dict:
    """Prompt user to sign in via browser (device code flow)."""
    import httpx

    # Step 1: get device code
    resp = httpx.post(
        f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/devicecode",
        data={
            "client_id": CLIENT_ID,
            "scope": " ".join(SCOPES),
        },
        timeout=10,
    )
    resp.raise_for_status()
    device_data = resp.json()

    print("\n" + "="*60)
    print("MICROSOFT LOGIN REQUIRED")
    print("="*60)
    print(f"\n1. Open this URL in your browser:\n   {device_data['verification_uri']}")
    print(f"\n2. Enter this code: {device_data['user_code']}")
    print("\n3. Sign in with your KIIT account (23053333@kiit.ac.in)")
    print("\nWaiting for you to sign in...")
    print("="*60 + "\n")

    # Step 2: poll for token
    interval = device_data.get("interval", 5)
    expires_in = device_data.get("expires_in", 900)
    import time
    start = time.time()

    while time.time() - start < expires_in:
        time.sleep(interval)
        poll = httpx.post(
            f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "client_id": CLIENT_ID,
                "device_code": device_data["device_code"],
            },
            timeout=10,
        )
        poll_data = poll.json()
        if "access_token" in poll_data:
            poll_data["expires_at"] = datetime.utcnow().timestamp() + poll_data.get("expires_in", 3600)
            _save_token(poll_data)
            print("✅ Signed in successfully!\n")
            return poll_data
        elif poll_data.get("error") == "authorization_pending":
            continue
        else:
            raise Exception(f"Login failed: {poll_data.get('error_description', poll_data)}")

    raise Exception("Login timed out. Please restart and try again.")


def _get_token() -> str:
    """Get a valid access token, using cache / refresh / device code as needed."""
    token_data = _load_cached_token()

    if token_data is None:
        token_data = _device_code_login()
    elif _is_token_expired(token_data):
        try:
            token_data = _refresh_token(token_data)
        except Exception:
            token_data = _device_code_login()

    return token_data["access_token"]


def _headers() -> dict:
    return {"Authorization": f"Bearer {_get_token()}", "Content-Type": "application/json"}


# ── GraphConnector class ───────────────────────────────────────────────────────

class GraphConnector:
    """Microsoft Graph connector. Same pattern as imap.py / mock.py."""

    # ── Mail ──────────────────────────────────────────────────────────────────

    def list_messages(self, top: int = 20) -> list[dict]:
        if IS_MOCK:
            return _MOCK_MESSAGES[:top]
        import httpx
        resp = httpx.get(
            f"{GRAPH_BASE}/me/mailFolders/inbox/messages",
            headers=_headers(),
            params={
                "$top": top,
                "$orderby": "receivedDateTime desc",
                "$select": (
                    "id,subject,bodyPreview,body,from,toRecipients,"
                    "receivedDateTime,isRead,importance,hasAttachments,conversationId"
                ),
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("value", [])

    def get_message(self, msg_id: str) -> dict:
        if IS_MOCK:
            return next((m for m in _MOCK_MESSAGES if m["id"] == msg_id), _MOCK_MESSAGES[0])
        import httpx
        resp = httpx.get(f"{GRAPH_BASE}/me/messages/{msg_id}", headers=_headers(), timeout=10)
        resp.raise_for_status()
        return resp.json()

    def send_message(self, to: str, subject: str, body_html: str, reply_to_id: str | None = None) -> dict:
        if IS_MOCK:
            return {
                "id": f"sent-{uuid.uuid4().hex[:8]}",
                "status": "sent",
                "to": to,
                "subject": subject,
                "sentAt": datetime.utcnow().isoformat() + "Z",
                "mock": True,
            }
        import httpx, json as _json
        if reply_to_id:
            url = f"{GRAPH_BASE}/me/messages/{reply_to_id}/reply"
            payload = {"comment": body_html}
        else:
            url = f"{GRAPH_BASE}/me/sendMail"
            payload = {
                "message": {
                    "subject": subject,
                    "body": {"contentType": "html", "content": body_html},
                    "toRecipients": [{"emailAddress": {"address": to}}],
                },
                "saveToSentItems": True,
            }
        resp = httpx.post(url, headers=_headers(), content=_json.dumps(payload), timeout=15)
        resp.raise_for_status()
        return {"status": "sent", "to": to, "subject": subject}

    def list_attachments(self, msg_id: str) -> list[dict]:
        if IS_MOCK:
            return _MOCK_ATTACHMENTS.get(msg_id, [])
        import httpx
        resp = httpx.get(
            f"{GRAPH_BASE}/me/messages/{msg_id}/attachments",
            headers=_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("value", [])

    # ── Calendar ──────────────────────────────────────────────────────────────

    def list_events(self, days_ahead: int = 1) -> list[dict]:
        if IS_MOCK:
            return _MOCK_EVENTS
        import httpx
        now = datetime.utcnow()
        resp = httpx.get(
            f"{GRAPH_BASE}/me/calendarView",
            headers=_headers(),
            params={
                "startDateTime": now.isoformat() + "Z",
                "endDateTime": (now + timedelta(days=days_ahead)).isoformat() + "Z",
                "$orderby": "start/dateTime",
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("value", [])

    def create_event(self, subject: str, start_iso: str, end_iso: str, body: str = "", attendees: list[str] | None = None) -> dict:
        if IS_MOCK:
            return {
                "id": f"evt-{uuid.uuid4().hex[:8]}",
                "subject": subject,
                "start": {"dateTime": start_iso, "timeZone": "UTC"},
                "end": {"dateTime": end_iso, "timeZone": "UTC"},
                "mock": True,
            }
        import httpx, json as _json
        payload: dict = {
            "subject": subject,
            "body": {"contentType": "text", "content": body},
            "start": {"dateTime": start_iso, "timeZone": "UTC"},
            "end": {"dateTime": end_iso, "timeZone": "UTC"},
        }
        if attendees:
            payload["attendees"] = [
                {"emailAddress": {"address": a}, "type": "required"} for a in attendees
            ]
        resp = httpx.post(f"{GRAPH_BASE}/me/events", headers=_headers(), content=_json.dumps(payload), timeout=10)
        resp.raise_for_status()
        return resp.json()

    def detect_conflicts(self, deadline_iso: str) -> list[str]:
        deadline = datetime.fromisoformat(deadline_iso)
        conflicts = []
        for ev in self.list_events():
            ev_start = datetime.fromisoformat(ev["start"]["dateTime"])
            ev_end = datetime.fromisoformat(ev["end"]["dateTime"])
            if ev_start <= deadline <= ev_end:
                conflicts.append(ev.get("subject", "Unknown Event"))
        return conflicts

    def auto_block(self, msg_id: str, deadline_iso: str) -> dict:
        deadline = datetime.fromisoformat(deadline_iso)
        conflicts = self.detect_conflicts(deadline_iso)
        event = self.create_event(
            subject=f"⏰ MailMind deadline – {msg_id}",
            start_iso=(deadline - timedelta(hours=1)).isoformat(),
            end_iso=deadline_iso,
            body="Auto-created by MailMind agent based on detected email deadline.",
        )
        return {"event": event, "conflicts": conflicts}

    # ── Teams ─────────────────────────────────────────────────────────────────

    def notify_teams(self, channel_id: str, message: str) -> dict:
        if IS_MOCK:
            return {
                "id": f"teams-{uuid.uuid4().hex[:8]}",
                "mock": True,
                "message": message,
                "ts": datetime.utcnow().isoformat() + "Z",
            }
        import httpx, json as _json
        resp = httpx.post(
            f"{GRAPH_BASE}/teams/{channel_id}/messages",
            headers=_headers(),
            content=_json.dumps({"body": {"content": message}}),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def get_presence(self, email: str) -> dict:
        if IS_MOCK:
            return {"id": email, "availability": "Available", "activity": "Available", "mock": True}
        import httpx
        resp = httpx.get(f"{GRAPH_BASE}/users/{email}/presence", headers=_headers(), timeout=10)
        resp.raise_for_status()
        return resp.json()

    # ── Conversion helper ─────────────────────────────────────────────────────

    def to_agent_email(self, m: dict) -> dict:
        sender_obj = m.get("from", {}).get("emailAddress", {})
        body_obj = m.get("body", {})
        return {
            "id": m["id"],
            "subject": m.get("subject", "(no subject)"),
            "sender": sender_obj.get("name", sender_obj.get("address", "")),
            "sender_email": sender_obj.get("address", ""),
            "body": body_obj.get("content", m.get("bodyPreview", "")),
            "timestamp": m.get("receivedDateTime", ""),
            "is_read": m.get("isRead", True),
            "importance": m.get("importance", "normal"),
            "has_attachments": m.get("hasAttachments", False),
            "conversation_id": m.get("conversationId", ""),
            "source": "microsoft_graph",
            "classification": None,
            "draft_reply": None,
        }


# Module-level singleton
graph = GraphConnector()


if __name__ == "__main__":
    print("Running smoke test...\n")
    msgs = graph.list_messages()
    print(f"Emails ({len(msgs)}):")
    for m in msgs:
        c = graph.to_agent_email(m)
        print(f"  [{c['importance'].upper()}] {c['subject']} — from {c['sender']}")
    print("\n✅ Test passed")

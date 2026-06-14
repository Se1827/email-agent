"""
src/connectors/graph.py
Microsoft Graph connector â€“ sits alongside imap.py and mock.py.

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
import shutil

# â”€â”€ Configuration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
IS_MOCK       = os.getenv("GRAPH_MOCK", "true").lower() == "true"
TENANT_ID     = os.getenv("AZURE_TENANT_ID",     "mock-tenant")
CLIENT_ID     = os.getenv("AZURE_CLIENT_ID",     "mock-client")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "mock-secret")
USER_EMAIL    = os.getenv("GRAPH_USER_EMAIL",    "you@example.com")
GRAPH_BASE    = "https://graph.microsoft.com/v1.0"
TOKEN_CACHE   = Path(__file__).parent.parent.parent / ".graph_token_cache.json"

SCOPES = [
    "https://graph.microsoft.com/Contacts.Read",
    "https://graph.microsoft.com/Mail.Read",
    "https://graph.microsoft.com/Mail.Send",
    "https://graph.microsoft.com/Calendars.ReadWrite",
    "https://graph.microsoft.com/User.Read",
    "https://graph.microsoft.com/Files.Read",
    "offline_access",
]

class GraphAuthRequired(Exception):
    pass


# â”€â”€ Mock data â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_now = datetime.now(timezone.utc)

_MOCK_MESSAGES = [
    {
        "id": "graph-msg-001",
        "subject": "Re: Hackathon submission deadline",
        "bodyPreview": "Panel needs prototype + 2-min video by 5 PM today.",
        "body": {
            "contentType": "html",
            "content": "<p>Hi,</p><p>The judging panel needs the final prototype link and a 2-minute video by <b>5:00 PM today</b>.</p>",
        },
        "from": {"emailAddress": {"name": "Rahul Sharma", "address": "rahul@example.com"}},
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
        "subject": "Q3 Review â€“ Action Required",
        "bodyPreview": "Please review deck and share inputs by Friday EOW.",
        "body": {
            "contentType": "html",
            "content": "<p>Hi Team,</p><p>Please review the attached Q3 deck and share your inputs by <b>Friday EOW</b>.</p>",
        },
        "from": {"emailAddress": {"name": "Priya Menon", "address": "priya@example.com"}},
        "toRecipients": [{"emailAddress": {"name": "You", "address": USER_EMAIL}}],
        "receivedDateTime": (_now - timedelta(hours=3)).isoformat() + "Z",
        "isRead": False,
        "importance": "normal",
        "hasAttachments": True,
        "conversationId": "conv-002",
        "categories": [],
    },
]

_MOCK_CONTACTS = [
    {
        "id": "contact-001",
        "displayName": "Alice Example",
        "emailAddresses": [{"address": "alice@example.com", "name": "Alice Example"}],
        "mobilePhone": "+1-555-0100",
    },
    {
        "id": "contact-002",
        "displayName": "Bob Example",
        "emailAddresses": [{"address": "bob@example.com", "name": "Bob Example"}],
        "mobilePhone": "+1-555-0101",
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


_MOCK_ATTACHMENTS = {
    "graph-msg-001": [
        {
            "id": "att-001",
            "name": "hackathon_brief_v3.pdf",
            "contentType": "application/pdf",
            "size": 204800,
        }
    ],
}


_MOCK_GROUPS = [
    {"id": "group-001", "displayName": "Engineering", "mail": "eng@example.com"},
    {"id": "group-002", "displayName": "HR", "mail": "hr@example.com"},
]

_MOCK_DRIVE_ITEMS = [
    {"id": "file-001", "name": "ProjectPlan.docx", "size": 102400, "folder": False},
    {"id": "folder-001", "name": "Shared", "folder": True},
]


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
            "refresh_token": token_data["refresh_token"],
            "scope": " ".join(SCOPES),
        },
        timeout=30,
    )
    resp.raise_for_status()
    new_token = resp.json()
    new_token["expires_at"] = datetime.utcnow().timestamp() + new_token.get("expires_in", 3600)
    _save_token(new_token)
    return new_token


def _device_code_login() -> dict:
    """Prompt user to sign in via browser (device code flow)."""
    import httpx
    import time

    # Step 1: get device code
    resp = httpx.post(
        f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/devicecode",
        data={
            "client_id": CLIENT_ID,
            "scope": " ".join(SCOPES),
        },
        timeout=60,
    )
    resp.raise_for_status()
    device_data = resp.json()

    print("\n" + "="*60, flush=True)
    print("MICROSOFT LOGIN REQUIRED", flush=True)
    print("="*60, flush=True)
    print(f"\n1. Open this URL in your browser:\n   {device_data.get('verification_uri', 'https://microsoft.com/devicelogin')}", flush=True)
    print(f"\n2. Enter this code: {device_data['user_code']}", flush=True)
    print(f"\n3. Sign in with your Microsoft account", flush=True)
    print("\nWaiting for you to sign in...", flush=True)
    print("="*60 + "\n", flush=True)

    # Step 2: poll for token
    interval = device_data.get("interval", 5)
    expires_in = device_data.get("expires_in", 900)
    start = time.time()

    while time.time() - start < expires_in:
        time.sleep(interval)
        try:
            with httpx.Client(timeout=httpx.Timeout(60.0, connect=30.0)) as client:
                poll = client.post(
                    f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token",
                    data={
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                        "client_id": CLIENT_ID,
                        "device_code": device_data["device_code"],
                    },
                )
            poll_data = poll.json()
        except httpx.TimeoutException:
            continue

        if "access_token" in poll_data:
            poll_data["expires_at"] = datetime.utcnow().timestamp() + poll_data.get("expires_in", 3600)
            _save_token(poll_data)
            print("Signed in successfully!\n")
            return poll_data
        elif poll_data.get("error") == "authorization_pending":
            continue
        else:
            raise Exception(f"Login failed: {poll_data.get('error_description', poll_data)}")

    raise Exception("Login timed out. Please restart and try again.")


def _get_token(auto_login: bool = False) -> str:
    """Get a valid access token, using cache / refresh / device code as needed."""
    token_data = _load_cached_token()

    if token_data is None:
        if auto_login:
            token_data = _device_code_login()
        else:
            raise GraphAuthRequired("Microsoft Graph is not authenticated. Please log in.")
    elif _is_token_expired(token_data):
        try:
            token_data = _refresh_token(token_data)
        except Exception:
            if auto_login:
                token_data = _device_code_login()
            else:
                raise GraphAuthRequired("Microsoft Graph token expired and refresh failed. Please log in.")

    return token_data["access_token"]


def _headers() -> dict:
    return {"Authorization": f"Bearer {_get_token(auto_login=False)}", "Content-Type": "application/json"}


# â”€â”€ GraphConnector class â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class GraphConnector:
    """Microsoft Graph connector. Same pattern as imap.py / mock.py."""

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
                    "id,internetMessageId,subject,bodyPreview,body,from,toRecipients,"
                    "receivedDateTime,isRead,importance,hasAttachments,conversationId"
                ),
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("value", [])

    def list_all_messages(self) -> list[dict]:
        """Retrieve all messages from the inbox, handling pagination.

        Returns the complete list of messages available to the authenticated user.
        """
        if IS_MOCK:
            return _MOCK_MESSAGES
        import httpx
        messages: list[dict] = []
        url = f"{GRAPH_BASE}/me/mailFolders/inbox/messages"
        params = {
            "$top": 100,
            "$select": (
                "id,internetMessageId,subject,bodyPreview,body,from,toRecipients,receivedDateTime," 
                "isRead,importance,hasAttachments,conversationId"
            ),
        }
        while url:
            resp = httpx.get(url, headers=_headers(), params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            messages.extend(data.get("value", []))
            # The nextLink already contains all query params, so clear params for subsequent calls
            url = data.get("@odata.nextLink")
            params = None
        return messages

    def get_access_token(self) -> str:
        """Public method to obtain a cached access token, refreshing if needed."""
        return _get_token()

    def persist_credentials(self, destination: str) -> None:
        """Copy the token cache to the given destination.

        Parameters
        ----------
        destination: str
            Path (file or directory) where the token cache should be saved.
            If a directory is given, the cache file is written inside it with its
            original name.
        """
        dest_path = Path(destination)
        if dest_path.is_dir():
            dest_path = dest_path / TOKEN_CACHE.name
        shutil.copy2(TOKEN_CACHE, dest_path)
        print(f"Credentials persisted to {dest_path}")

    def list_contacts(self, top: int = 20) -> list[dict]:
        """Return a list of contacts (mock or real)."""
        if IS_MOCK:
            return _MOCK_CONTACTS[:top]
        import httpx
        resp = httpx.get(
            f"{GRAPH_BASE}/me/contacts",
            headers=_headers(),
            params={"$top": top},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("value", [])

    def get_user_profile(self) -> dict:
        """Return the authenticated user's profile info."""
        if IS_MOCK:
            return {"displayName": "Mock User", "mail": USER_EMAIL, "id": "user-001"}
        import httpx
        resp = httpx.get(f"{GRAPH_BASE}/me", headers=_headers(), timeout=30)
        resp.raise_for_status()
        return resp.json()

    def list_groups(self, top: int = 20) -> list[dict]:
        """Return a list of groups (mock or real)."""
        if IS_MOCK:
            return _MOCK_GROUPS[:top]
        import httpx
        resp = httpx.get(
            f"{GRAPH_BASE}/me/memberOf",
            headers=_headers(),
            params={"$top": top},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("value", [])

    def list_drive_items(self, top: int = 20) -> list[dict]:
        """Return a list of OneDrive items (mock or real)."""
        if IS_MOCK:
            return _MOCK_DRIVE_ITEMS[:top]
        import httpx
        resp = httpx.get(
            f"{GRAPH_BASE}/me/drive/root/children",
            headers=_headers(),
            params={"$top": top},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("value", [])

    def get_message(self, msg_id: str) -> dict:
        """Fetch a single mail message by ID."""
        if IS_MOCK:
            return next((m for m in _MOCK_MESSAGES if m["id"] == msg_id), _MOCK_MESSAGES[0])
        import httpx
        resp = httpx.get(f"{GRAPH_BASE}/me/mailFolders/inbox/messages/{msg_id}", headers=_headers(), timeout=30)
        resp.raise_for_status()
        return resp.json()

    def list_thread_messages(self, conversation_id: str) -> list[dict]:
        """Fetch all messages in a conversation thread (both sent and received) by conversation ID."""
        if IS_MOCK:
            return [m for m in _MOCK_MESSAGES if m.get("conversationId") == conversation_id]
        import httpx
        resp = httpx.get(
            f"{GRAPH_BASE}/me/messages",
            headers=_headers(),
            params={
                "$filter": f"conversationId eq '{conversation_id}'",
                "$select": (
                    "id,internetMessageId,subject,bodyPreview,body,from,toRecipients,"
                    "receivedDateTime,isRead,importance,hasAttachments,conversationId"
                ),
            },
            timeout=30,
        )
        resp.raise_for_status()
        value = resp.json().get("value", [])
        try:
            value.sort(key=lambda x: x.get("receivedDateTime", ""))
        except Exception:
            pass
        return value


    def send_message(self, to: str | list[str], subject: str, body_html: str, reply_to_id: str | None = None, cc: list[str] | None = None, bcc: list[str] | None = None) -> dict:
        if IS_MOCK:
            return {
                "id": f"sent-{uuid.uuid4().hex[:8]}",
                "status": "sent",
                "to": to,
                "subject": subject,
                "sentAt": datetime.utcnow().isoformat() + "Z",
                "mock": True,
            }
        import httpx
        import json as _json
        
        to_list = [to] if isinstance(to, str) else to
        cc_list = cc or []
        bcc_list = bcc or []
        
        if reply_to_id:
            url = f"{GRAPH_BASE}/me/messages/{reply_to_id}/replyAll"
            payload = {
                "comment": body_html
            }
        else:
            url = f"{GRAPH_BASE}/me/sendMail"
            payload = {
                "message": {
                    "subject": subject,
                    "body": {"contentType": "html", "content": body_html},
                    "toRecipients": [{"emailAddress": {"address": t}} for t in to_list if t],
                    "ccRecipients": [{"emailAddress": {"address": c}} for c in cc_list if c],
                    "bccRecipients": [{"emailAddress": {"address": b}} for b in bcc_list if b],
                },
                "saveToSentItems": True,
            }
        resp = httpx.post(url, headers=_headers(), content=_json.dumps(payload), timeout=30)
        resp.raise_for_status()
        return {"status": "sent", "to": to_list, "subject": subject}

    def list_attachments(self, msg_id: str) -> list[dict]:
        if IS_MOCK:
            return _MOCK_ATTACHMENTS.get(msg_id, [])
        import httpx
        resp = httpx.get(
            f"{GRAPH_BASE}/me/mailFolders/inbox/messages/{msg_id}/attachments",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("value", [])

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
            timeout=30,
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
        import httpx
        import json as _json
        payload: dict = {
            "subject": subject,
            "body": {"contentType": "text", "content": body},
            "start": {"dateTime": start_iso, "timeZone": "UTC"},
            "end": {"dateTime": end_iso, "timeZone": "UTC"},
        }
        if attendees:
            payload["attendees"] = [
                {"emailAddress": {"address": a}, "type": "required"} for a in attendees if a and a.strip()
            ]
        resp = httpx.post(f"{GRAPH_BASE}/me/events", headers=_headers(), content=_json.dumps(payload), timeout=30)
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
            subject=f"Deadline â€“ {msg_id}",
            start_iso=(deadline - timedelta(hours=1)).isoformat(),
            end_iso=deadline_iso,
            body="Auto-created by Pluemail agent based on detected email deadline.",
        )
        return {"event": event, "conflicts": conflicts}

    def get_presence(self, email: str) -> dict:
        if IS_MOCK:
            return {"id": email, "availability": "Available", "activity": "Available", "mock": True}
        import httpx
        resp = httpx.get(f"{GRAPH_BASE}/users/{email}/presence", headers=_headers(), timeout=30)
        resp.raise_for_status()
        return resp.json()

    def to_agent_email(self, m: dict) -> dict:
        import re
        sender_obj = m.get("from", {}).get("emailAddress", {})
        body_obj = m.get("body", {})
        raw_body = body_obj.get("content", m.get("bodyPreview", ""))
        content_type = body_obj.get("contentType", "text").lower()
        # Strip HTML tags for plain-text preview/AI use
        if content_type == "html":
            # Replace paragraph and line break tags with newlines
            text = re.sub(r"(?i)<br\s*/?>", "\n", raw_body)
            text = re.sub(r"(?i)</p>", "\n\n", text)
            text = re.sub(r"(?i)</div>", "\n", text)
            # Strip other HTML tags
            text = re.sub(r"<[^>]+>", "", text)
            # Clean up horizontal whitespace but preserve newlines
            lines = []
            for line in text.splitlines():
                cleaned_line = re.sub(r"[ \t]+", " ", line).strip()
                lines.append(cleaned_line)
            plain_body = "\n".join(lines).strip()
            # Collapse more than two consecutive newlines
            plain_body = re.sub(r"\n{3,}", "\n\n", plain_body)
            # Decode HTML entities (&nbsp; &lt; &gt; etc.)
            import html as _html
            plain_body = _html.unescape(plain_body)
        else:
            plain_body = raw_body

        # Parse nested messages from quoted text
        sub_messages = []
        remaining = plain_body
        current_sender = sender_obj.get("address", sender_obj.get("name", ""))
        current_time = m.get("receivedDateTime", "")
        
        while remaining:
            # Look for the next quote header
            match = re.search(r"(?im)^On\s+[A-Za-z]{3},\s+\d+\s+[A-Za-z]{3}\s+\d{4}.*?wrote:", remaining)
            if not match:
                match = re.search(r"(?im)^On\s+[A-Za-z]{3,10},\s+[A-Za-z]{3,10}\s+\d+.*?,?\s+.*?\s+wrote:", remaining)
            
            if match:
                start, end = match.span()
                msg_body = remaining[:start].strip()
                if msg_body:
                    sub_messages.append({
                        "sender": current_sender,
                        "body": msg_body,
                        "timestamp": current_time,
                    })
                
                header = match.group(0)
                next_sender = ""
                email_match = re.search(r"<([^>]+)>", header)
                if email_match:
                    next_sender = email_match.group(1)
                else:
                    name_match = re.search(r"On\s+[^,]+,\s+([^,<>]+)", header)
                    if name_match:
                        next_sender = name_match.group(1).strip()
                    else:
                        next_sender = "Previous Sender"
                
                current_sender = next_sender
                current_time = ""
                remaining = remaining[end:].strip()
            else:
                if remaining.strip():
                    sub_messages.append({
                        "sender": current_sender,
                        "body": remaining.strip(),
                        "timestamp": current_time,
                    })
                break

        return {
            "id": m["id"],
            "subject": m.get("subject", "(no subject)"),
            "sender": sender_obj.get("address", sender_obj.get("name", "")),
            "recipients": [r.get("emailAddress", {}).get("address", "") for r in m.get("toRecipients", [])],
            "body": plain_body,           # plain text for AI/classification
            "html_body": raw_body if content_type == "html" else None,  # HTML for rendering
            "snippet": m.get("bodyPreview", plain_body[:120]),
            "timestamp": m.get("receivedDateTime", ""),
            "thread_id": m.get("conversationId", ""),
            "message_id": m.get("internetMessageId"),
            "is_read": m.get("isRead", True),
            "is_starred": False,
            "labels": m.get("categories", []),
            "importance": m.get("importance", "normal"),
            "has_attachments": m.get("hasAttachments", False),
            "source": "microsoft_graph",
            "classification": None,
            "draft_reply": None,
            "sub_messages": sub_messages if len(sub_messages) > 1 else [],
        }


# Module-level singleton
graph = GraphConnector()


if __name__ == "__main__":
    import sys
    if "--login" in sys.argv:
        print("Initiating manual Microsoft Graph login...")
        _device_code_login()
    else:
        print("Running smoke test...\n")
        # For the smoke test to work if not logged in, we must force auto_login
        _get_token(auto_login=True)
        msgs = graph.list_messages()
        print(f"Emails ({len(msgs)}):")
        for m in msgs:
            c = graph.to_agent_email(m)
            print(f"  [{c['importance'].upper()}] {c['subject']} -- from {c['sender']}")
        print("\nTest passed")

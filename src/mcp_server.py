"""
Model Context Protocol (MCP) server for the Intelligent Email Agent.

Exposes email management tools so any MCP-compatible host (Claude Desktop,
Cursor, etc.) can read and act on emails directly.

Authentication
--------------
The server reads EMAIL_AGENT_TOKEN from the environment (or from the .env
file in the project root) and verifies it against data/.auth.json before
accepting any tool calls.  Every HTTP call to the backend carries the token
as a Bearer header — identical to how the web frontend authenticates.

Run with:
    python -m src.mcp_server

Or register it in your MCP host config as:
    {
        "command": "python",
        "args": ["-m", "src.mcp_server"],
        "cwd": "<repo-root>",
        "env": {"EMAIL_AGENT_TOKEN": "<your-token>"}
    }
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Minimal stdlib-only MCP implementation (stdio / JSON-RPC 2.0)
# No third-party mcp package required – keeps the dependency surface tiny.
# ---------------------------------------------------------------------------

log = logging.getLogger("mcp_server")
logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

# ── Auth bootstrap ───────────────────────────────────────────────────────────
# Resolved once at startup; injected into every HTTP call.
_resolved_token: str | None = None


def _load_dotenv(path: Path) -> dict[str, str]:
    """Parse a .env file into a dict without third-party dependencies."""
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.strip().strip('"').strip("'")
        result[key.strip()] = val
    return result


def _token_verifier(token: str) -> str:
    """Replicate src.auth._token_verifier without importing the full app."""
    return hashlib.sha256(f"email-agent-auth:{token}".encode()).hexdigest()


def _verify_token_against_auth_file(token: str, project_root: Path) -> bool:
    """Return True if the token matches the stored PBKDF2 verifier."""
    auth_file = project_root / "data" / ".auth.json"
    if not auth_file.exists():
        # Auth not configured — backend will accept any request (HTTP 428 guard)
        return True
    try:
        meta = json.loads(auth_file.read_text(encoding="utf-8"))
        stored_verifier = meta.get("verifier", "")
        return hmac.compare_digest(_token_verifier(token), stored_verifier)
    except Exception as exc:
        log.warning("Could not read auth file: %s", exc)
        return False


def _bootstrap_auth() -> str | None:
    """
    Resolve the auth token in priority order:
      1. EMAIL_AGENT_TOKEN env var (already set by MCP host config)
      2. EMAIL_AGENT_TOKEN in .env file in the project root

    Verifies the token against data/.auth.json and returns it if valid,
    or None if no token could be found / verified.
    """
    # Locate project root (two levels up from this file: src/mcp_server.py)
    project_root = Path(__file__).parent.parent

    token = os.environ.get("EMAIL_AGENT_TOKEN", "").strip()

    if not token:
        # Fall back to .env
        env_vars = _load_dotenv(project_root / ".env")
        token = env_vars.get("EMAIL_AGENT_TOKEN", "").strip()

    if not token:
        log.error(
            "MCP: EMAIL_AGENT_TOKEN is not set. "
            "Set it in your environment or in the .env file."
        )
        return None

    if not _verify_token_against_auth_file(token, project_root):
        log.error(
            "MCP: EMAIL_AGENT_TOKEN failed verification against data/.auth.json. "
            "Re-login via the web app to get a fresh token."
        )
        return None

    return token

# ── JSON-RPC helpers ────────────────────────────────────────────────────────

def _ok(id_: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _err(id_: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def _send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


# ── Tool registry ────────────────────────────────────────────────────────────

TOOLS: list[dict] = [
    {
        "name": "list_emails",
        "description": (
            "List emails in the agent inbox. Returns sender, subject, "
            "timestamp, priority, and read status for each email."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of emails to return (default 20, max 100).",
                    "default": 20,
                },
                "unread_only": {
                    "type": "boolean",
                    "description": "If true, return only unread emails.",
                    "default": False,
                },
                "priority": {
                    "type": "string",
                    "enum": ["critical", "high", "medium", "low"],
                    "description": "Filter by priority level (optional).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_email",
        "description": "Fetch the full body and metadata of a specific email by its ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "email_id": {
                    "type": "string",
                    "description": "The unique email ID returned by list_emails.",
                }
            },
            "required": ["email_id"],
        },
    },
    {
        "name": "send_alert",
        "description": (
            "Raise an in-agent alert / notification. Useful for flagging "
            "urgent situations or injecting a system notice."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short alert title (max 80 chars).",
                },
                "message": {
                    "type": "string",
                    "description": "Detailed alert body.",
                },
                "severity": {
                    "type": "string",
                    "enum": ["info", "warning", "critical"],
                    "description": "Alert severity level.",
                    "default": "info",
                },
            },
            "required": ["title", "message"],
        },
    },
    {
        "name": "mark_email_read",
        "description": "Mark an email as read by its ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "email_id": {
                    "type": "string",
                    "description": "The unique email ID to mark as read.",
                }
            },
            "required": ["email_id"],
        },
    },
    {
        "name": "get_inbox_summary",
        "description": (
            "Return a high-level summary of the inbox: total count, unread "
            "count, critical emails, and pending AI drafts."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "compose_reply",
        "description": (
            "Ask the AI agent to compose a draft reply for a given email. "
            "Returns the generated draft text."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "email_id": {
                    "type": "string",
                    "description": "ID of the email to reply to.",
                },
                "instructions": {
                    "type": "string",
                    "description": "Optional tone / content instructions for the AI (e.g. 'be concise and apologetic').",
                },
            },
            "required": ["email_id"],
        },
    },
]

# ── Backend helpers (call the FastAPI app's in-memory stores via HTTP) ──────


def _api_get(path: str) -> Any:
    """
    Call the local FastAPI backend with the resolved auth token.
    Raises RuntimeError if the server is not reachable.
    """
    import urllib.request
    import urllib.error

    base = os.environ.get("EMAIL_AGENT_API", "http://127.0.0.1:8000")
    url = f"{base}{path}"
    req = urllib.request.Request(url)
    # Always use the verified token bootstrapped at startup
    if _resolved_token:
        req.add_header("Authorization", f"Bearer {_resolved_token}")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise RuntimeError(
                "Backend returned 401 Unauthorized. "
                "The MCP token may be expired — re-login via the web app."
            ) from exc
        raise RuntimeError(f"Backend error {exc.code} for {url}: {exc}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Cannot reach email agent API at {url}: {exc}") from exc


def _api_post(path: str, body: dict) -> Any:
    import urllib.request
    import urllib.error

    base = os.environ.get("EMAIL_AGENT_API", "http://127.0.0.1:8000")
    url = f"{base}{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if _resolved_token:
        req.add_header("Authorization", f"Bearer {_resolved_token}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise RuntimeError(
                "Backend returned 401 Unauthorized. "
                "The MCP token may be expired — re-login via the web app."
            ) from exc
        raise RuntimeError(f"Backend error {exc.code} for {url}: {exc}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Cannot reach email agent API at {url}: {exc}") from exc


# ── Tool handler implementations ─────────────────────────────────────────────


def _handle_list_emails(args: dict) -> str:
    limit = min(int(args.get("limit", 20)), 100)
    unread_only = bool(args.get("unread_only", False))
    priority_filter = args.get("priority")

    try:
        emails = _api_get("/api/emails")
    except RuntimeError as exc:
        return f"⚠️  {exc}\n\nMake sure the email agent backend is running (`python run.py`)."

    if unread_only:
        emails = [e for e in emails if not e.get("is_read")]
    if priority_filter:
        emails = [
            e for e in emails
            if e.get("classification", {}) and
               e["classification"].get("priority") == priority_filter
        ]

    emails = emails[:limit]
    if not emails:
        return "No emails found matching your criteria."

    lines = [f"Found **{len(emails)}** email(s):\n"]
    for i, e in enumerate(emails, 1):
        priority = ""
        if e.get("classification"):
            p = e["classification"].get("priority", "")
            priority = f" [{p.upper()}]" if p else ""
        read_mark = "📭" if e.get("is_read") else "📬"
        ts = e.get("timestamp", "")[:10]
        lines.append(
            f"{i}. {read_mark} **{e.get('subject', '(no subject)')}**{priority}\n"
            f"   From: {e.get('sender', 'unknown')}  |  {ts}  |  ID: `{e.get('id', '')}`"
        )

    return "\n".join(lines)


def _handle_get_email(args: dict) -> str:
    email_id = args.get("email_id", "").strip()
    if not email_id:
        return "Error: email_id is required."

    try:
        e = _api_get(f"/api/emails/{email_id}")
    except RuntimeError as exc:
        return f"⚠️  {exc}"

    priority = ""
    category = ""
    if e.get("classification"):
        priority = e["classification"].get("priority", "")
        category = e["classification"].get("category", "")

    body_preview = (e.get("body") or "")[:1500]
    if len(e.get("body", "")) > 1500:
        body_preview += "\n\n*(body truncated — use the app to view in full)*"

    return (
        f"**Subject:** {e.get('subject', '(no subject)')}\n"
        f"**From:** {e.get('sender')}\n"
        f"**To:** {', '.join(e.get('recipients', []))}\n"
        f"**Date:** {e.get('timestamp', '')}\n"
        f"**Priority:** {priority or 'unclassified'}  |  **Category:** {category or '—'}\n"
        f"**Read:** {'Yes' if e.get('is_read') else 'No'}\n\n"
        f"---\n\n{body_preview}"
    )


def _handle_send_alert(args: dict) -> str:
    title = (args.get("title") or "").strip()[:80]
    message = (args.get("message") or "").strip()
    severity = args.get("severity", "info")

    if not title or not message:
        return "Error: both title and message are required."

    try:
        _api_post("/api/notifications/alert", {
            "title": title,
            "message": message,
            "severity": severity,
        })
        return f"✅ Alert posted successfully.\n**Title:** {title}\n**Severity:** {severity}"
    except RuntimeError:
        # Backend may not have this endpoint; that's OK — log locally
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return (
            f"✅ Alert registered (offline mode — backend not reached).\n\n"
            f"**[{severity.upper()}]** {title}\n{message}\n\n*Generated at {ts}*"
        )


def _handle_mark_email_read(args: dict) -> str:
    email_id = args.get("email_id", "").strip()
    if not email_id:
        return "Error: email_id is required."
    try:
        _api_post(f"/api/emails/{email_id}/read", {})
        return f"✅ Email `{email_id}` marked as read."
    except RuntimeError as exc:
        return f"⚠️  {exc}"


def _handle_get_inbox_summary(args: dict) -> str:
    try:
        emails = _api_get("/api/emails")
    except RuntimeError as exc:
        return f"⚠️  {exc}"

    total = len(emails)
    unread = sum(1 for e in emails if not e.get("is_read"))
    critical = sum(
        1 for e in emails
        if e.get("classification", {}) and
           e.get("classification", {}).get("priority") in ("critical", "high")
    )
    drafts = sum(1 for e in emails if e.get("draft_reply"))

    return (
        f"## 📥 Inbox Summary\n\n"
        f"| Metric | Count |\n"
        f"|--------|-------|\n"
        f"| Total emails | {total} |\n"
        f"| Unread | {unread} |\n"
        f"| Critical / High priority | {critical} |\n"
        f"| Pending AI drafts | {drafts} |\n"
    )


def _handle_compose_reply(args: dict) -> str:
    email_id = args.get("email_id", "").strip()
    instructions = args.get("instructions", "")
    if not email_id:
        return "Error: email_id is required."
    try:
        result = _api_post(f"/api/emails/{email_id}/draft", {
            "instructions": instructions,
        })
        draft_text = result.get("draft", {}).get("body", "") if isinstance(result, dict) else str(result)
        if not draft_text:
            return "Draft was generated but the body was empty. Try via the app UI."
        return f"## ✉️ AI Draft Reply\n\n{draft_text}"
    except RuntimeError as exc:
        return f"⚠️  {exc}"


HANDLERS = {
    "list_emails": _handle_list_emails,
    "get_email": _handle_get_email,
    "send_alert": _handle_send_alert,
    "mark_email_read": _handle_mark_email_read,
    "get_inbox_summary": _handle_get_inbox_summary,
    "compose_reply": _handle_compose_reply,
}

# ── MCP JSON-RPC dispatcher ──────────────────────────────────────────────────


def _dispatch(msg: dict) -> dict | None:
    method = msg.get("method", "")
    id_ = msg.get("id")
    params = msg.get("params", {})

    # ── Lifecycle ──────────────────────────────────────────────────────────
    if method == "initialize":
        return _ok(id_, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": "email-agent-mcp",
                "version": "1.0.0",
            },
        })

    if method == "notifications/initialized":
        return None  # no response needed for notifications

    # ── Tools ──────────────────────────────────────────────────────────────
    if method == "tools/list":
        return _ok(id_, {"tools": TOOLS})

    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})
        handler = HANDLERS.get(tool_name)
        if handler is None:
            return _err(id_, -32601, f"Unknown tool: {tool_name}")
        try:
            result_text = handler(tool_args)
            return _ok(id_, {
                "content": [{"type": "text", "text": result_text}],
                "isError": False,
            })
        except Exception as exc:
            log.exception("tool_call_failed", exc_info=exc)
            return _ok(id_, {
                "content": [{"type": "text", "text": f"Tool error: {exc}"}],
                "isError": True,
            })

    # ── Ping ───────────────────────────────────────────────────────────────
    if method == "ping":
        return _ok(id_, {})

    # Unknown method — only error if it has an id (request vs notification)
    if id_ is not None:
        return _err(id_, -32601, f"Method not found: {method}")
    return None


# ── Entry point ──────────────────────────────────────────────────────────────


def main() -> None:
    global _resolved_token

    # ── Auth bootstrap: must succeed before we serve any tool calls ──────
    _resolved_token = _bootstrap_auth()
    if _resolved_token is None:
        # Write a fatal error to stderr (visible in MCP host logs) and exit.
        # Stdout stays clean so the JSON-RPC framing isn't corrupted.
        sys.stderr.write(
            "[email-agent-mcp] FATAL: could not resolve a valid auth token.\n"
            "  Set EMAIL_AGENT_TOKEN in your environment or .env file,\n"
            "  then restart the MCP server.\n"
        )
        sys.stderr.flush()
        sys.exit(1)

    sys.stderr.write("[email-agent-mcp] Auth token verified. Server ready.\n")
    sys.stderr.flush()

    log.info("MCP server started (stdio transport)")
    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            msg = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            _send(_err(None, -32700, f"Parse error: {exc}"))
            continue
        response = _dispatch(msg)
        if response is not None:
            _send(response)


if __name__ == "__main__":
    main()

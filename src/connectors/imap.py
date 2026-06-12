"""IMAP email connector — fetches real emails from an IMAP mailbox.

Works with any standard IMAP server (Gmail, Outlook, Yahoo, Fastmail,
self-hosted, etc.) — the same settings you would put into Thunderbird.
"""

from __future__ import annotations

import email
import email.header
import email.utils
import hashlib
import imaplib
import logging
from datetime import datetime, timezone
from email.message import Message

from src.models.email import Email

log = logging.getLogger(__name__)


def _decode_header(raw: str | None) -> str:
    """Decode an RFC 2047 encoded header into a plain string."""
    if not raw:
        return ""
    parts = email.header.decode_header(raw)
    decoded: list[str] = []
    for fragment, charset in parts:
        if isinstance(fragment, bytes):
            decoded.append(fragment.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(fragment)
    return " ".join(decoded)


def _extract_body(msg: Message) -> str:
    """Walk a MIME message and return the best plain-text body."""
    # Prefer text/plain, fall back to text/html stripped of tags.
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in disposition:
                continue
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        # No text/plain found, try text/html as a last resort.
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    return ""


def _parse_recipients(msg: Message) -> list[str]:
    """Extract all To/Cc addresses."""
    addrs: list[str] = []
    for header in ("To", "Cc"):
        raw = msg.get_all(header) or []
        for value in raw:
            parsed = email.utils.getaddresses([value])
            addrs.extend(addr for _, addr in parsed if addr)
    return addrs


def _parse_date(msg: Message) -> datetime:
    """Parse the Date header into a timezone-aware datetime."""
    raw = msg.get("Date", "")
    parsed = email.utils.parsedate_to_datetime(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _stable_id(msg_id: str | None, subject: str, date: str) -> str:
    """Generate a short stable ID from the Message-ID or a hash fallback."""
    raw = msg_id or f"{subject}-{date}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def get_uidvalidity(conn: imaplib.IMAP4) -> int | None:
    """Extract UIDVALIDITY from the IMAP connection after select()."""
    status, responses = conn.response("UIDVALIDITY")
    if status == "OK" and responses and responses[0]:
        try:
            return int(responses[0])
        except (ValueError, TypeError):
            pass
    return None


def get_highestmodseq(conn: imaplib.IMAP4) -> int | None:
    """Extract HIGHESTMODSEQ from the IMAP connection after select()."""
    status, responses = conn.response("HIGHESTMODSEQ")
    if status == "OK" and responses and responses[0]:
        try:
            return int(responses[0])
        except (ValueError, TypeError):
            pass
    return None


def sync_mailbox(
    account_id: str,
    host: str,
    port: int,
    username: str,
    password: str,
    *,
    mailbox: str = "INBOX",
    use_ssl: bool = True,
    inbox: str | None = None,
    last_uid: int = 0,
    highestmodseq: int = 0,
    uidvalidity: int | None = None,
) -> tuple[list[Email], int, int, int, list[tuple[int, list[str]]]]:
    """Connect to an IMAP server and fetch new emails incrementally.
    
    Returns:
        (emails, new_last_uid, new_highestmodseq, new_uidvalidity, flag_updates)
    """
    klass = imaplib.IMAP4_SSL if use_ssl else imaplib.IMAP4
    log.info("imap_connect", extra={"host": host, "user": username, "mailbox": mailbox})

    conn = klass(host, port)
    try:
        conn.login(username, password)
        
        # Capabilities often change after login (e.g. CONDSTORE becomes available)
        conn.capability()
        
        caps = [c.decode('ascii').upper() for c in conn.capabilities]
        if "ENABLE" in caps:
            try:
                conn._simple_command("ENABLE", "CONDSTORE")
            except Exception:
                pass

        _select_status, _select_data = conn.select(mailbox, readonly=True)

        current_uidvalidity = get_uidvalidity(conn) or 0
        current_highestmodseq = get_highestmodseq(conn) or 0
        
        # If UIDVALIDITY changed, we must fetch from scratch
        if uidvalidity is not None and current_uidvalidity != uidvalidity:
            log.warning("uidvalidity_changed", extra={"old": uidvalidity, "new": current_uidvalidity})
            last_uid = 0
            highestmodseq = 0

        if last_uid == 0:
            # First sync: only grab the most recent N
            _status, data = conn.uid("search", "ALL")
            all_uids_str = data[0].split() if data and data[0] else []
            new_uids = all_uids_str[-50:]  # Limit to 50
        else:
            try:
                _status, data = conn.uid("search", "UID", f"{last_uid + 1}:*")
                if _status != "OK":
                    raise ValueError("search failed")
                new_uids = data[0].split() if data and data[0] else []
            except Exception:
                # Fallback for servers that mis-parse UID ranges (e.g., Elektrine)
                _status, data = conn.uid("search", "ALL")
                all_uids_str = data[0].split() if data and data[0] else []
                new_uids = []
                for uid_bytes in all_uids_str:
                    try:
                        uid_int = int(uid_bytes.decode('ascii'))
                        if uid_int > last_uid:
                            new_uids.append(uid_bytes)
                    except ValueError:
                        pass
        emails: list[Email] = []
        
        new_last_uid = last_uid
        
        if new_uids:
            uid_set = b",".join(new_uids).decode('ascii')
            _status, msg_data = conn.uid("fetch", uid_set, "(UID RFC822)")
            
            import re
            messages_by_uid: dict[int, bytes] = {}
            i = 0
            while i < len(msg_data):
                item = msg_data[i]
                if isinstance(item, tuple):
                    header_line = item[0].decode('ascii', errors='ignore')
                    m = re.search(r'UID\s+(\d+)', header_line, re.IGNORECASE)
                    if m:
                        messages_by_uid[int(m.group(1))] = item[1]
                    i += 1
                else:
                    i += 1

            for uid_int, raw_bytes in messages_by_uid.items():
                new_last_uid = max(new_last_uid, uid_int)
                msg = email.message_from_bytes(raw_bytes)

                sender_pairs = email.utils.getaddresses([msg.get("From", "")])
                sender = sender_pairs[0][1] if sender_pairs else "unknown"

                subject = _decode_header(msg.get("Subject"))
                date = _parse_date(msg)
                body = _extract_body(msg)
                recipients = _parse_recipients(msg)

                # Extract CC addresses
                cc_addrs: list[str] = []
                for cc_hdr in (msg.get_all("Cc") or []):
                    parsed = email.utils.getaddresses([cc_hdr])
                    cc_addrs.extend(addr for _, addr in parsed if addr)

                raw_msg_id = msg.get("Message-ID", "").strip()
                raw_in_reply_to = msg.get("In-Reply-To", "").strip() or None
                raw_references_hdr = msg.get("References", "")
                ref_list = raw_references_hdr.split() if raw_references_hdr else []

                thread_id = (
                    ref_list[0] if ref_list
                    else raw_in_reply_to
                    or raw_msg_id
                    or None
                )

                uid = uid_int
                # id format: account_id:mailbox:uidvalidity:uid
                stable_id = f"{account_id}:{mailbox}:{current_uidvalidity}:{uid}"

                emails.append(Email(
                    id=stable_id,
                    uid=uid,
                    uidvalidity=current_uidvalidity,
                    inbox=inbox,
                    sender=sender,
                    recipients=recipients,
                    cc=cc_addrs,
                    subject=subject,
                    body=body[:5000],
                    timestamp=date,
                    thread_id=thread_id,
                    message_id=raw_msg_id or None,
                    in_reply_to=raw_in_reply_to,
                    references=ref_list,
                ))

        flag_updates: list[tuple[int, list[str]]] = []

        if highestmodseq > 0 and current_highestmodseq > highestmodseq:
            try:
                _status, data = conn.uid("fetch", "1:*", f"(FLAGS) (CHANGEDSINCE {highestmodseq})")
                if data and data[0]:
                    for item in data:
                        if isinstance(item, tuple):
                            item_str = item[0].decode('ascii', errors='ignore')
                        elif isinstance(item, bytes):
                            item_str = item.decode('ascii', errors='ignore')
                        else:
                            continue
                        
                        import re
                        uid_match = re.search(r'UID\s+(\d+)', item_str, re.IGNORECASE)
                        flags_match = re.search(r'FLAGS\s+\((.*?)\)', item_str, re.IGNORECASE)
                        
                        if uid_match and flags_match:
                            f_uid = int(uid_match.group(1))
                            flags = flags_match.group(1).split()
                            flag_updates.append((f_uid, flags))
            except Exception as e:
                log.warning("condstore_fetch_failed", extra={"error": str(e)})
        elif current_highestmodseq == 0 and last_uid > 0:
            # Fallback for servers without CONDSTORE (like Elektrine)
            # Fetch flags for the last ~100 messages
            fetch_start = max(1, new_last_uid - 100)
            if new_last_uid >= fetch_start:
                try:
                    _status, data = conn.uid("fetch", f"{fetch_start}:{new_last_uid}", "(FLAGS)")
                    if data and data[0]:
                        for item in data:
                            if isinstance(item, tuple):
                                item_str = item[0].decode('ascii', errors='ignore')
                            elif isinstance(item, bytes):
                                item_str = item.decode('ascii', errors='ignore')
                            else:
                                continue
                            import re
                            uid_match = re.search(r'UID\s+(\d+)', item_str, re.IGNORECASE)
                            flags_match = re.search(r'FLAGS\s+\((.*?)\)', item_str, re.IGNORECASE)
                            
                            if uid_match and flags_match:
                                f_uid = int(uid_match.group(1))
                                flags = flags_match.group(1).split()
                                flag_updates.append((f_uid, flags))
                except Exception as e:
                    log.warning("fallback_flag_fetch_failed", extra={"error": str(e)})

        log.info("imap_synced", extra={"count": len(emails), "new_last_uid": new_last_uid, "flags": len(flag_updates)})
        return emails, new_last_uid, current_highestmodseq, current_uidvalidity, flag_updates

    finally:
        try:
            conn.logout()
        except Exception:
            pass


import socket
import time

def idle_loop(
    host: str,
    port: int,
    username: str,
    password: str,
    *,
    mailbox: str = "INBOX",
    use_ssl: bool = True,
    callback = None,
) -> None:
    """Connect to an IMAP server and wait for push notifications.
    
    Calls `callback()` whenever a notification is received.
    """
    klass = imaplib.IMAP4_SSL if use_ssl else imaplib.IMAP4
    while True:
        try:
            conn = klass(host, port)
            conn.login(username, password)
            conn.select(mailbox, readonly=True)
            conn.socket().settimeout(29 * 60)
            
            while True:
                # Send IDLE command
                tag = conn._new_tag()
                conn.send(b"%s IDLE\r\n" % tag)
                
                # Wait for the continuation response (+)
                line = conn.readline()
                if not line.startswith(b"+"):
                    break
                    
                # Block until we receive a line from the server (push notification)
                try:
                    line = conn.readline()
                except socket.timeout:
                    line = b""  # timed out, just re-issue IDLE
                
                # As soon as we receive something, break out of IDLE
                conn.send(b"DONE\r\n")
                
                # Read until the tagged completion response
                while True:
                    resp = conn.readline()
                    if resp.startswith(tag) or not resp:
                        break
                
                # Trigger the callback
                if line and callback:
                    try:
                        callback()
                    except Exception as e:
                        log.error("idle_callback_error", extra={"error": str(e)})
                        
        except Exception as e:
            log.error("idle_loop_error", extra={"error": str(e), "user": username})
        finally:
            try:
                conn.logout()
            except Exception:
                pass
        
        time.sleep(15)

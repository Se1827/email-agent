"""Small CLI for inspecting and wiping local email-agent storage."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.storage import (  # noqa: E402
    delete_all_storage_records,
    delete_email_records,
    decrypt_payload,
    init_storage,
    storage_configured,
    storage_stats,
)

try:
    import psycopg
except Exception:  # pragma: no cover - dependency is required only for browse.
    psycopg = None


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage encrypted email-agent storage.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create storage tables/extensions if configured.")
    sub.add_parser("stats", help="Show current storage usage counts.")
    sub.add_parser("wipe-all", help="Delete all encrypted/vector storage rows.")

    browse = sub.add_parser("browse", help="Browse encrypted_records with decrypted payloads.")
    browse.add_argument("--limit", type=int, default=20, help="Maximum rows to show.")
    browse.add_argument("--type", dest="record_type", help="Filter by record_type.")
    browse.add_argument("--email-id", help="Filter by email_id.")
    browse.add_argument("--raw", action="store_true", help="Print full payload JSON.")

    wipe_email = sub.add_parser("wipe-email", help="Delete storage rows for one email.")
    wipe_email.add_argument("email_id", help="Email id to remove from storage.")

    args = parser.parse_args()

    if not storage_configured():
        print("Storage is not configured. Set STORAGE_ENABLED=true, DATABASE_URL, and STORAGE_ENCRYPTION_KEY.")
        return 2

    if args.command == "init":
        init_storage()
        print("Storage initialized.")
        return 0

    if args.command == "stats":
        print(storage_stats())
        return 0

    if args.command == "browse":
        browse_records(
            limit=args.limit,
            record_type=args.record_type,
            email_id=args.email_id,
            raw=args.raw,
        )
        return 0

    if args.command == "wipe-email":
        print(delete_email_records(args.email_id))
        return 0

    if args.command == "wipe-all":
        confrimation = True if input("Confirm: y/N: ").lower() == 'y' else False
        if confrimation:
            print("<<Deleting>>\n")
            print(delete_all_storage_records())
        else: print("Cancelled!\n")
        return 0

    return 1


def browse_records(
    *,
    limit: int,
    record_type: str | None = None,
    email_id: str | None = None,
    raw: bool = False,
) -> None:
    """Run a friendly decrypted version of SELECT * FROM encrypted_records."""
    if psycopg is None:
        raise RuntimeError("psycopg[binary] is required to browse storage.")

    where = []
    params: list[object] = []
    if record_type:
        where.append("record_type = %s")
        params.append(record_type)
    if email_id:
        where.append("email_id = %s")
        params.append(email_id)

    sql = """
        SELECT
            id, record_type, record_id, email_id, thread_id, source,
            occurred_at, metadata, ciphertext, created_at, updated_at
        FROM encrypted_records
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY occurred_at DESC LIMIT %s"
    params.append(max(1, limit))

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    key = os.environ["STORAGE_ENCRYPTION_KEY"]
    for row in rows:
        (
            row_id,
            row_type,
            row_record_id,
            row_email_id,
            row_thread_id,
            row_source,
            occurred_at,
            metadata,
            ciphertext,
            created_at,
            updated_at,
        ) = row
        payload = decrypt_payload(ciphertext, key)
        shown_payload = payload if raw else _payload_preview(payload)
        print(
            json.dumps(
                {
                    "id": str(row_id),
                    "record_type": row_type,
                    "record_id": row_record_id,
                    "email_id": row_email_id,
                    "thread_id": row_thread_id,
                    "source": row_source,
                    "occurred_at": occurred_at.isoformat(),
                    "metadata": metadata,
                    "payload": shown_payload,
                    "created_at": created_at.isoformat(),
                    "updated_at": updated_at.isoformat(),
                },
                indent=2,
                default=str,
            )
        )

    print(f"Rows: {len(rows)}")


def _payload_preview(payload: dict) -> dict:
    text_limit = 300
    preview = {}
    for key, value in payload.items():
        if isinstance(value, str) and len(value) > text_limit:
            preview[key] = value[:text_limit] + "...[truncated]"
        elif isinstance(value, list) and len(value) > 5:
            preview[key] = [*value[:5], f"...[{len(value) - 5} more]"]
        elif isinstance(value, dict):
            preview[key] = _payload_preview(value)
        else:
            preview[key] = value
    return preview


if __name__ == "__main__":
    raise SystemExit(main())

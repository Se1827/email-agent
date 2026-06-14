"""Password-derived authentication and encrypted local data files."""

from __future__ import annotations

import base64
import contextlib
import contextvars
import hashlib
import hmac
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request

from src.config import PROJECT_ROOT

AUTH_FILE = PROJECT_ROOT / "data" / ".auth.json"
ENCRYPTED_PREFIX = b"EMAIL_AGENT_ENCRYPTED_JSON_V1\n"
PBKDF2_ITERATIONS = 260_000

_auth_token: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "email_agent_auth_token",
    default=None,
)


class AuthError(RuntimeError):
    """Raised when encrypted data cannot be read in the current auth context."""


def auth_configured() -> bool:
    return AUTH_FILE.exists()


def load_auth_metadata() -> dict[str, Any] | None:
    if not AUTH_FILE.exists():
        return None
    try:
        return json.loads(AUTH_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AuthError("Authentication metadata is unreadable") from exc


def auth_status(request: Request | None = None) -> dict[str, Any]:
    metadata = load_auth_metadata()
    authenticated = False
    if metadata is not None and request is not None:
        try:
            token = extract_request_token(request)
            authenticated = bool(token and verify_token(token))
        except HTTPException:
            authenticated = False
    return {
        "configured": metadata is not None,
        "authenticated": authenticated,
        "display_name": metadata.get("display_name") if metadata else "",
    }


def register_user(display_name: str, password: str) -> dict[str, str]:
    display_name = display_name.strip()
    if not display_name:
        raise HTTPException(status_code=422, detail="Display name is required")
    _validate_password(password)
    if AUTH_FILE.exists():
        raise HTTPException(status_code=409, detail="Authentication is already configured")

    salt = os.urandom(16)
    token = derive_token(password, salt)
    metadata = {
        "version": 1,
        "display_name": display_name,
        "salt": _b64encode(salt),
        "verifier": _token_verifier(token),
        "kdf": "pbkdf2_sha256",
        "iterations": PBKDF2_ITERATIONS,
    }
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUTH_FILE.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    with use_auth_token(token):
        encrypt_plain_json_files(PROJECT_ROOT / "data")

    return {"token": token, "display_name": display_name}


def login_user(password: str) -> dict[str, str]:
    metadata = load_auth_metadata()
    if metadata is None:
        raise HTTPException(status_code=404, detail="Authentication is not configured")
    token = derive_token(password, _b64decode(metadata["salt"]))
    if not hmac.compare_digest(_token_verifier(token), metadata.get("verifier", "")):
        raise HTTPException(status_code=401, detail="Invalid password")
    return {"token": token, "display_name": metadata.get("display_name", "")}


def derive_token(password: str, salt: bytes) -> str:
    raw = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
        dklen=32,
    )
    return _b64encode(raw)


def verify_token(token: str) -> bool:
    metadata = load_auth_metadata()
    if metadata is None:
        return False
    return hmac.compare_digest(_token_verifier(token), metadata.get("verifier", ""))


def extract_request_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    token = request.query_params.get("auth_token")
    return token.strip() if token else None


def require_request_auth(request: Request) -> str:
    token = extract_request_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication token")
    if not verify_token(token):
        raise HTTPException(status_code=401, detail="Invalid authentication token")
    return token


@contextlib.contextmanager
def use_auth_token(token: str) -> Iterator[None]:
    ctx_token = _auth_token.set(token)
    try:
        yield
    finally:
        _auth_token.reset(ctx_token)


def get_current_token() -> str | None:
    return _auth_token.get()


def read_json_file(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    raw = path.read_bytes()
    if raw.startswith(ENCRYPTED_PREFIX):
        return json.loads(_decrypt_bytes(raw[len(ENCRYPTED_PREFIX):]).decode("utf-8"))
    return json.loads(raw.decode("utf-8"))


def write_json_file(path: Path, data: Any, *, indent: int = 4) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(data, indent=indent, default=str) + "\n").encode("utf-8")
    if auth_configured():
        path.write_bytes(ENCRYPTED_PREFIX + _encrypt_bytes(raw))
    else:
        path.write_bytes(raw)


def encrypt_plain_json_files(data_dir: Path) -> list[str]:
    encrypted: list[str] = []
    if not data_dir.exists():
        return encrypted
    for path in data_dir.rglob("*.json"):
        if path == AUTH_FILE or path.name.startswith("."):
            continue
        raw = path.read_bytes()
        if raw.startswith(ENCRYPTED_PREFIX):
            continue
        try:
            json.loads(raw.decode("utf-8"))
        except Exception:
            continue
        path.write_bytes(ENCRYPTED_PREFIX + _encrypt_bytes(raw))
        encrypted.append(str(path.relative_to(data_dir)))
    return encrypted


def _encrypt_bytes(data: bytes) -> bytes:
    return Fernet(_fernet_key()).encrypt(data)


def _decrypt_bytes(data: bytes) -> bytes:
    try:
        return Fernet(_fernet_key()).decrypt(data)
    except InvalidToken as exc:
        raise AuthError("Encrypted data cannot be decrypted with the current token") from exc


def _fernet_key() -> bytes:
    token = get_current_token()
    if not token:
        if auth_configured():
            raise AuthError("Encrypted data access requires authentication")
        raise AuthError("No authentication token is available")
    return base64.urlsafe_b64encode(_b64decode(token))


def _token_verifier(token: str) -> str:
    return hashlib.sha256(f"email-agent-auth:{token}".encode("utf-8")).hexdigest()


def _validate_password(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii")


def _b64decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data.encode("ascii"))

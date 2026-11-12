"""Encryption helpers for stored third-party API credentials.

Credentials are encrypted at rest with Fernet (AES-128-CBC + HMAC). Plaintext
values are only ever materialised inside the backend process when an outbound
request is built; they are never returned by the API.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _fernet_key() -> bytes:
    configured = (settings.encryption_key or "").strip()
    if configured:
        return configured.encode("utf-8")
    # Deterministic development fallback: derives a valid Fernet key from the
    # application secret. Production deployments must set ENCRYPTION_KEY.
    digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet() -> Fernet:
    return Fernet(_fernet_key())


def encrypt_json(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return _fernet().encrypt(raw.encode("utf-8")).decode("ascii")


def decrypt_json(token: str | None) -> dict[str, Any]:
    if not token:
        return {}
    try:
        raw = _fernet().decrypt(token.encode("ascii"))
    except (InvalidToken, ValueError):
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * max(4, len(value) - 4)}{value[-2:]}"


def redact(credentials: dict[str, Any]) -> dict[str, str]:
    """Return a browser-safe view of a credential bag (masked values only)."""
    return {key: mask_secret(str(value)) for key, value in credentials.items() if value}

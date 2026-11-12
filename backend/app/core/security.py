"""Password hashing, JWT sessions and TOTP helpers."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import pyotp

from app.core.config import settings

PASSWORD_MIN_LENGTH = 10
_PASSWORD_RE = re.compile(r"[A-Za-z]")


class TokenError(Exception):
    """Raised when a bearer token is missing, malformed, expired or revoked."""


def hash_password(password: str) -> str:
    raw = password.encode("utf-8")[:72]
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


def validate_password_strength(password: str) -> list[str]:
    problems: list[str] = []
    if len(password) < PASSWORD_MIN_LENGTH:
        problems.append(f"Password must be at least {PASSWORD_MIN_LENGTH} characters long")
    if not _PASSWORD_RE.search(password):
        problems.append("Password must contain at least one letter")
    if not re.search(r"\d", password):
        problems.append("Password must contain at least one digit")
    return problems


def create_access_token(user_id: str, token_version: int = 0) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=settings.access_token_ttl_minutes)
    payload = {
        "sub": user_id,
        "ver": token_version,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "iss": "kuhhan",
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, expires


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
            issuer="kuhhan",
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Session expired, please sign in again") from exc
    except jwt.PyJWTError as exc:
        raise TokenError("Invalid authentication token") from exc


def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=settings.app_name)


def verify_totp(secret: str, code: str) -> bool:
    if not secret or not code:
        return False
    cleaned = code.strip().replace(" ", "")
    if not cleaned.isdigit():
        return False
    return pyotp.TOTP(secret).verify(cleaned, valid_window=1)

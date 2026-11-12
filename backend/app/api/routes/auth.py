"""Authentication: login, session inspection, password and 2FA management."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_user
from app.api.serializers import user_dict
from app.core.audit import record_audit
from app.core.ratelimit import login_limiter
from app.core.security import (
    create_access_token,
    hash_password,
    new_totp_secret,
    totp_uri,
    validate_password_strength,
    verify_password,
    verify_totp,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import LoginRequest, PasswordChange, TotpCode

router = APIRouter(prefix="/auth", tags=["Authentication"])

MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 15


@router.post("/login")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    email = payload.email.strip().lower()
    throttle_key = f"{client_ip(request) or 'unknown'}:{email}"
    if not login_limiter.hit(throttle_key):
        record_audit(
            db,
            action="auth.login",
            entity_type="user",
            outcome="blocked",
            ip_address=client_ip(request),
            user_agent=request.headers.get("user-agent"),
            detail={"email": email, "reason": "rate_limited"},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many sign-in attempts. Please wait a minute and try again.",
        )

    user = db.scalar(select(User).where(func.lower(User.email) == email))
    now = datetime.now(timezone.utc)
    if user is None or not verify_password(payload.password, user.password_hash):
        if user is not None:
            user.failed_login_count += 1
            if user.failed_login_count >= MAX_FAILED_LOGINS:
                user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
                user.failed_login_count = 0
        record_audit(
            db,
            action="auth.login",
            entity_type="user",
            entity_id=user.id if user else None,
            outcome="failure",
            ip_address=client_ip(request),
            user_agent=request.headers.get("user-agent"),
            detail={"email": email},
        )
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account is disabled")

    locked_until = user.locked_until
    if locked_until is not None and locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    if locked_until and locked_until > now:
        raise HTTPException(
            status_code=423,
            detail=f"Account temporarily locked until {locked_until.strftime('%H:%M UTC')}",
        )

    if user.totp_enabled:
        if not payload.totp_code:
            raise HTTPException(status_code=401, detail="totp_required")
        if not verify_totp(user.totp_secret or "", payload.totp_code):
            user.failed_login_count += 1
            db.commit()
            raise HTTPException(status_code=401, detail="Invalid two-factor code")

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    token, expires_at = create_access_token(user.id, user.token_version)
    record_audit(
        db,
        action="auth.login",
        entity_type="user",
        entity_id=user.id,
        user=user,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    login_limiter.reset(throttle_key)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at,
        "user": user_dict(user),
    }


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return user_dict(user)


@router.post("/logout")
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    user.token_version += 1
    record_audit(db, action="auth.logout", entity_type="user", entity_id=user.id, user=user)
    db.commit()
    return {"message": "Signed out of all sessions"}


@router.post("/change-password")
def change_password(
    payload: PasswordChange,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    problems = validate_password_strength(payload.new_password)
    if problems:
        raise HTTPException(status_code=422, detail="; ".join(problems))
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=422, detail="New password must be different")
    user.password_hash = hash_password(payload.new_password)
    user.token_version += 1
    record_audit(
        db,
        action="auth.change_password",
        entity_type="user",
        entity_id=user.id,
        user=user,
        ip_address=client_ip(request),
    )
    db.commit()
    token, expires_at = create_access_token(user.id, user.token_version)
    return {"message": "Password updated", "access_token": token, "expires_at": expires_at}


@router.post("/2fa/setup")
def setup_2fa(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    secret = new_totp_secret()
    user.totp_secret = secret
    user.totp_enabled = False
    db.commit()
    return {
        "secret": secret,
        "otpauth_uri": totp_uri(secret, user.email),
        "message": "Scan the URI with an authenticator app, then confirm a code to enable 2FA.",
    }


@router.post("/2fa/enable")
def enable_2fa(
    payload: TotpCode, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    if not user.totp_secret:
        raise HTTPException(status_code=400, detail="Start the 2FA setup first")
    if not verify_totp(user.totp_secret, payload.code):
        raise HTTPException(status_code=400, detail="Invalid authenticator code")
    user.totp_enabled = True
    user.token_version += 1
    record_audit(db, action="auth.2fa_enabled", entity_type="user", entity_id=user.id, user=user)
    db.commit()
    return {"totp_enabled": True, "message": "Two-factor authentication enabled"}


@router.post("/2fa/disable")
def disable_2fa(
    payload: TotpCode, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    if not user.totp_enabled:
        return {"totp_enabled": False, "message": "Two-factor authentication is already disabled"}
    if not verify_totp(user.totp_secret or "", payload.code):
        raise HTTPException(status_code=400, detail="Invalid authenticator code")
    user.totp_enabled = False
    user.totp_secret = None
    record_audit(db, action="auth.2fa_disabled", entity_type="user", entity_id=user.id, user=user)
    db.commit()
    return {"totp_enabled": False, "message": "Two-factor authentication disabled"}

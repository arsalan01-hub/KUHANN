"""Shared API dependencies: authentication, authorisation and pagination."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import TokenError, decode_access_token
from app.db.session import get_db
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account unavailable")
    if int(payload.get("ver", 0)) != int(user.token_version):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session revoked, please sign in again"
        )
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Account temporarily locked")

    request.state.user = user
    return user


def require_permission(*codes: str) -> Callable[[User], User]:
    """Dependency factory: the caller must hold at least one of ``codes``."""

    def _dependency(user: User = Depends(get_current_user)) -> User:
        if any(user.has_permission(code) for code in codes):
            return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing permission: {' or '.join(codes)}",
        )

    return _dependency


class Pagination:
    def __init__(
        self,
        page: int = Query(1, ge=1, le=10_000),
        page_size: int = Query(25, ge=1, le=200),
    ) -> None:
        self.page = page
        self.page_size = page_size
        self.offset = (page - 1) * page_size


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None

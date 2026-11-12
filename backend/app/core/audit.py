"""Audit trail helper — every privileged mutation is recorded."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.system import AuditLog
from app.models.user import User


def record_audit(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    user: User | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    outcome: str = "success",
    detail: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        ip_address=ip_address,
        user_agent=(user_agent or "")[:300] or None,
        outcome=outcome,
        detail=detail or {},
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    return entry

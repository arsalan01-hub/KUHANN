"""Notifications and saved-search monitoring."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.search import SavedSearch
from app.models.system import Notification
from app.models.user import User
from app.services import search_engine


def notify(
    db: Session,
    *,
    title: str,
    body: str = "",
    level: str = "info",
    category: str = "system",
    user_id: str | None = None,
    link: str | None = None,
    payload: dict[str, Any] | None = None,
) -> Notification:
    entry = Notification(
        user_id=user_id,
        title=title[:200],
        body=body,
        level=level,
        category=category,
        link=link,
        payload=payload or {},
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    db.flush()
    return entry


def notify_permission_holders(
    db: Session,
    permission: str,
    *,
    title: str,
    body: str = "",
    level: str = "warning",
    category: str = "system",
    link: str | None = None,
    payload: dict[str, Any] | None = None,
) -> int:
    users = db.scalars(select(User).where(User.is_active.is_(True))).all()
    count = 0
    for user in users:
        if user.has_permission(permission):
            notify(
                db,
                user_id=user.id,
                title=title,
                body=body,
                level=level,
                category=category,
                link=link,
                payload=payload,
            )
            count += 1
    return count


def run_saved_search(
    db: Session, saved: SavedSearch, *, since: datetime | None = None
) -> dict[str, Any]:
    """Evaluate a saved search against collected listings and notify on matches."""
    now = datetime.now(timezone.utc)
    since = since or saved.last_run_at or (now - timedelta(days=1))
    filters = dict(saved.filters or {})
    filters.pop("added_since_days", None)
    conditions = search_engine.build_conditions(filters, source_ids=saved.source_ids or [])
    from app.models.listing import Listing  # local import keeps module graph simple

    from sqlalchemy import func, select as sa_select

    stmt = (
        sa_select(Listing)
        .where(*conditions, Listing.first_discovered_at > since)
        .order_by(Listing.first_discovered_at.desc())
        .limit(20)
    )
    matches = list(db.scalars(stmt).all())
    total_matches = db.scalar(
        sa_select(func.count())
        .select_from(Listing)
        .where(*conditions, Listing.first_discovered_at > since)
    ) or 0

    if matches and saved.notify:
        lines = [
            f"• {item.manufacturer or 'Truck'} {item.model or ''} "
            f"({item.year or 'n/a'}) — {round(float(item.price_eur)) if item.price_eur else 'n/a'} EUR"
            for item in matches[:5]
        ]
        notify(
            db,
            user_id=saved.user_id,
            title=f"{total_matches} new match(es) for “{saved.name}”",
            body="\n".join(lines),
            level="success",
            category="saved_search",
            link=f"/saved-searches",
            payload={"saved_search_id": saved.id, "matches": total_matches},
        )

    saved.last_run_at = now
    saved.last_match_count = int(total_matches)
    saved.total_matches = int(saved.total_matches or 0) + int(total_matches)
    db.flush()
    return {"saved_search_id": saved.id, "name": saved.name, "matches": int(total_matches)}

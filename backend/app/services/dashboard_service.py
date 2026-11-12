"""Dashboard aggregates and price analytics.

Every number is produced by an aggregate query over the live database — there
are no hard-coded statistics.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.api import ApiIntegration
from app.models.listing import DuplicateCandidate, Listing
from app.models.search import SavedSearch, SearchHistory
from app.models.source import DiscoveryRun, WebsiteSource
from app.models.system import JobRun, Notification
from app.models.user import User
from app.services.settings_service import get_setting


def _scalar(db: Session, stmt) -> int:
    return int(db.scalar(stmt) or 0)


def overview(db: Session, *, user_id: str | None = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    window_days = int(get_setting(db, "monitoring.new_listing_window_days", 7) or 7)
    new_since = now - timedelta(days=window_days)
    week_ago = now - timedelta(days=7)

    totals = {
        "listings_total": _scalar(db, select(func.count(Listing.id))),
        "listings_active": _scalar(
            db, select(func.count(Listing.id)).where(Listing.listing_status == "active")
        ),
        "listings_new": _scalar(
            db, select(func.count(Listing.id)).where(Listing.first_discovered_at >= new_since)
        ),
        "listings_price_changed": _scalar(
            db, select(func.count(Listing.id)).where(Listing.last_price_change_at >= week_ago)
        ),
        "listings_flagged": _scalar(
            db,
            select(func.count(Listing.id)).where(
                Listing.risk_score >= int(get_setting(db, "risk.flag_threshold", 45) or 45)
            ),
        ),
        "duplicates_open": _scalar(
            db, select(func.count(DuplicateCandidate.id)).where(DuplicateCandidate.status == "open")
        ),
        "sources_total": _scalar(db, select(func.count(WebsiteSource.id))),
        "sources_active": _scalar(
            db,
            select(func.count(WebsiteSource.id)).where(
                WebsiteSource.status.in_(("approved", "active"))
            ),
        ),
        "sources_pending": _scalar(
            db,
            select(func.count(WebsiteSource.id)).where(
                WebsiteSource.status.in_(
                    ("newly_discovered", "under_investigation", "needs_review")
                )
            ),
        ),
        "connectors_failing": _scalar(
            db,
            select(func.count(WebsiteSource.id)).where(
                WebsiteSource.last_run_status == "failed"
            ),
        ),
        "apis_total": _scalar(db, select(func.count(ApiIntegration.id))),
        "apis_active": _scalar(
            db,
            select(func.count(ApiIntegration.id)).where(ApiIntegration.status == "active"),
        ),
        "discovery_runs": _scalar(db, select(func.count(DiscoveryRun.id))),
        "discovered_websites": _scalar(
            db,
            select(func.count(WebsiteSource.id)).where(WebsiteSource.discovery_provider != "manual"),
        ),
        "saved_searches": _scalar(db, select(func.count(SavedSearch.id))),
        "users": _scalar(db, select(func.count(User.id)).where(User.is_active.is_(True))),
        "prices_tracked": _scalar(db, select(func.count(Listing.id)).where(Listing.price.is_not(None))),
    }

    # Chart: listings discovered per day (last 14 days).
    day = func.date_trunc("day", Listing.first_discovered_at)
    rows = db.execute(
        select(day.label("day"), func.count(Listing.id))
        .where(Listing.first_discovered_at >= now - timedelta(days=14))
        .group_by(day)
        .order_by(day)
    ).all()
    listings_by_day = [
        {"date": (r[0].date().isoformat() if r[0] else ""), "count": int(r[1])} for r in rows
    ]

    # Chart: average asking price per manufacturer (top 8 by volume).
    rows = db.execute(
        select(
            Listing.manufacturer,
            func.count(Listing.id).label("count"),
            func.avg(Listing.price_eur),
        )
        .where(Listing.manufacturer.is_not(None), Listing.price_eur.is_not(None))
        .group_by(Listing.manufacturer)
        .order_by(func.count(Listing.id).desc())
        .limit(8)
    ).all()
    price_by_manufacturer = [
        {"manufacturer": r[0], "count": int(r[1]), "avg_price_eur": round(float(r[2]), 2)}
        for r in rows
        if r[2] is not None
    ]

    rows = db.execute(
        select(Listing.country, func.count(Listing.id))
        .where(Listing.country.is_not(None))
        .group_by(Listing.country)
        .order_by(func.count(Listing.id).desc())
        .limit(10)
    ).all()
    listings_by_country = [{"country": r[0], "count": int(r[1])} for r in rows]

    rows = db.execute(
        select(WebsiteSource.status, func.count(WebsiteSource.id))
        .group_by(WebsiteSource.status)
        .order_by(func.count(WebsiteSource.id).desc())
    ).all()
    sources_by_status = [{"status": r[0], "count": int(r[1])} for r in rows]

    recent_price_changes = db.scalars(
        select(Listing)
        .where(Listing.last_price_change_at.is_not(None))
        .order_by(Listing.last_price_change_at.desc())
        .limit(6)
    ).all()

    recent_searches = db.scalars(
        select(SearchHistory).order_by(SearchHistory.created_at.desc()).limit(6)
    ).all()

    recent_notifications = db.scalars(
        select(Notification)
        .where((Notification.user_id == user_id) | (Notification.user_id.is_(None)))
        .order_by(Notification.created_at.desc())
        .limit(6)
    ).all()

    recent_jobs = db.scalars(select(JobRun).order_by(JobRun.started_at.desc()).limit(6)).all()

    avg_price = db.scalar(
        select(func.avg(Listing.price_eur)).where(Listing.price_eur.is_not(None))
    )
    totals["average_price_eur"] = round(float(avg_price), 2) if avg_price is not None else None

    return {
        "totals": totals,
        "charts": {
            "listings_by_day": listings_by_day,
            "price_by_manufacturer": price_by_manufacturer,
            "listings_by_country": listings_by_country,
            "sources_by_status": sources_by_status,
        },
        "recent": {
            "price_changes": recent_price_changes,
            "searches": recent_searches,
            "notifications": recent_notifications,
            "jobs": recent_jobs,
        },
        "generated_at": now,
    }

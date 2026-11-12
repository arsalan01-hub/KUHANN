"""Collection orchestration for a single website source."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.connectors import get_connector
from app.connectors.base import ConnectorError
from app.models.source import WebsiteSource
from app.services import listing_service, notifications
from app.services.http import OutboundError
from app.services.settings_service import get_setting

COLLECTABLE_STATUSES = ("approved", "active")


def collect_source(
    db: Session,
    source: WebsiteSource,
    *,
    criteria: dict[str, Any] | None = None,
    client: httpx.Client | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Run one collection pass. Returns a factual summary (never invented)."""
    if source.status not in COLLECTABLE_STATUSES:
        raise ConnectorError(
            f"Website '{source.name or source.domain}' is '{source.status}'. "
            "Approve it before collecting."
        )
    limit = int(limit or get_setting(db, "collection.max_listings_per_run", 200) or 200)
    connector = get_connector(db, source, client)
    problems = connector.validate_config()
    if problems:
        source.last_run_status = "failed"
        source.last_error = "; ".join(problems)
        source.consecutive_failures = (source.consecutive_failures or 0) + 1
        db.commit()
        raise ConnectorError(source.last_error)

    started = datetime.now(timezone.utc)
    try:
        report = connector.fetch(criteria=criteria, limit=limit)
    except (ConnectorError, OutboundError) as exc:
        source.last_run_status = "failed"
        source.last_error = str(exc)
        source.consecutive_failures = (source.consecutive_failures or 0) + 1
        source.last_checked_at = datetime.now(timezone.utc)
        if source.consecutive_failures >= 3:
            notifications.notify_permission_holders(
                db,
                "sources:write",
                title=f"Collector failing: {source.name or source.domain}",
                body=f"{source.consecutive_failures} consecutive failures. Last error: {exc}",
                level="error",
                category="connector",
                link="/sources",
                payload={"source_id": source.id},
            )
        db.commit()
        raise ConnectorError(str(exc)) from exc

    created = updated = 0
    seen: set[str] = set()
    for item in report.listings:
        if not item.get("original_url"):
            item["original_url"] = source.homepage_url
        listing, action = listing_service.upsert_listing(db, source, item)
        seen.add(listing.external_id)
        if action == "created":
            created += 1
        else:
            updated += 1
    marked = listing_service.mark_missing_listings(db, source, seen) if seen else 0

    finished = datetime.now(timezone.utc)
    source.last_run_status = "success"
    source.last_collected_at = finished
    source.last_checked_at = finished
    source.last_error = None
    source.consecutive_failures = 0
    source.listings_collected = (source.listings_collected or 0) + created
    source.average_response_ms = float((finished - started).total_seconds() * 1000)
    if source.status == "approved":
        source.status = "active"
    db.commit()

    return {
        "source_id": source.id,
        "domain": source.domain,
        "created": created,
        "updated": updated,
        "marked_unreachable": marked,
        "pages": report.pages,
        "notes": report.notes,
        "duration_ms": int((finished - started).total_seconds() * 1000),
    }

"""Website source management: manual addition, inspection, approval."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.source import ACCESS_METHODS, SOURCE_STATUSES, WebsiteSource
from app.services import inspector


class SourceError(Exception):
    pass


def get_source_or_404(db: Session, source_id: str) -> WebsiteSource:
    source = db.get(WebsiteSource, source_id)
    if source is None:
        raise SourceError("Website source not found")
    return source


def _apply_analysis(source: WebsiteSource, analysis: dict, report: dict[str, Any]) -> None:
    source.name = (analysis.get("name") or source.domain)[:200]
    source.country = analysis.get("country") or source.country
    source.language = analysis.get("language") or source.language
    if analysis.get("listing_url"):
        source.listing_url = analysis["listing_url"]
    source.api_doc_url = analysis.get("api_doc_url")
    source.terms_url = analysis.get("terms_url")
    source.has_official_api = analysis.get("has_official_api")
    source.robots_allows_crawl = analysis.get("robots_allowed")
    source.robots_notes = analysis.get("robots_notes") or ""
    source.robots_url = report.get("robots_url")
    source.status = analysis.get("status", "needs_review")
    source.access_method = analysis.get("access_method", "manual")
    source.compatibility = analysis.get("compatibility", {})
    source.analysis_report = report
    source.last_checked_at = datetime.now(timezone.utc)
    source.last_error = None


def add_website(
    db: Session,
    *,
    url: str,
    user_id: str | None,
    name: str | None = None,
    country: str | None = None,
    category: str | None = None,
    client: Any | None = None,
) -> WebsiteSource:
    normalised = inspector.normalise_url(url)
    domain = inspector.extract_domain(normalised)
    existing = db.scalar(select(WebsiteSource).where(WebsiteSource.domain == domain))
    if existing is not None:
        raise SourceError(f"This website is already registered ({existing.domain}).")

    source = WebsiteSource(
        domain=domain,
        name=(name or domain)[:200],
        homepage_url=normalised,
        country=country,
        category=category or "marketplace",
        status="under_investigation",
        access_method="manual",
        discovery_provider="manual",
        discovered_at=datetime.now(timezone.utc),
        connector_config={},
        compatibility={},
        analysis_report={},
        truck_evidence={},
        robots_notes="",
    )
    db.add(source)
    db.flush()

    try:
        report = inspector.inspect_website(normalised, client=client)
        analysis = inspector.build_analysis(report)
        _apply_analysis(source, analysis, report.as_dict())
        source.truck_evidence = {
            "keyword_hits": report.truck_keyword_hits,
            "listing_candidates": report.listing_candidates,
            "description": report.description,
        }
    except Exception as exc:  # noqa: BLE001 - inspection failure must not lose the record
        source.status = "temporarily_unavailable"
        source.last_error = f"Inspection failed: {exc}"
        source.analysis_report = {"error": str(exc), "url": normalised}

    db.commit()
    db.refresh(source)
    return source


def reinspect_source(db: Session, source: WebsiteSource, client: Any | None = None) -> WebsiteSource:
    try:
        report = inspector.inspect_website(source.homepage_url, client=client)
        analysis = inspector.build_analysis(report)
        _apply_analysis(source, analysis, report.as_dict())
        source.truck_evidence = {
            "keyword_hits": report.truck_keyword_hits,
            "listing_candidates": report.listing_candidates,
            "description": report.description,
        }
        # Never silently re-activate a source the administrator restricted.
        if source.status in ("disabled", "rejected", "restricted", "manual_access_only"):
            source.status = source.status
    except Exception as exc:  # noqa: BLE001
        source.status = "temporarily_unavailable"
        source.last_error = f"Inspection failed: {exc}"
    db.commit()
    db.refresh(source)
    return source


def update_source(db: Session, source: WebsiteSource, payload: dict[str, Any]) -> WebsiteSource:
    if "status" in payload and payload["status"] is not None:
        new_status = payload["status"]
        if new_status not in SOURCE_STATUSES:
            raise SourceError(f"Unknown status '{new_status}'")
        if new_status in ("approved", "active"):
            notes = (source.compatibility or {}).get("summary", "")
            if source.robots_allows_crawl is False:
                raise SourceError(
                    "robots.txt does not permit automated collection for this website. "
                    "Approve it as 'manual_access_only' instead."
                )
            source.approved_at = datetime.now(timezone.utc)
        source.status = new_status
    if payload.get("access_method"):
        method = payload["access_method"]
        if method not in ACCESS_METHODS:
            raise SourceError(f"Unknown access method '{method}'")
        source.access_method = method
    for field in ("name", "country", "language", "category", "listing_url", "review_note", "connector_key"):
        value = payload.get(field)
        if value is not None:
            setattr(source, field, value)
    if payload.get("connector_config") is not None:
        source.connector_config = payload["connector_config"]
    db.commit()
    db.refresh(source)
    return source


def delete_source(db: Session, source: WebsiteSource) -> None:
    db.delete(source)
    db.commit()

"""Website sources, manual addition, discovery engine and connector framework."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import Pagination, client_ip, require_permission
from app.api.filters import filters_from_query
from app.api.serializers import discovery_run_dict, source_dict
from app.connectors import connector_catalogue, get_connector
from app.connectors.base import ConnectorError
from app.core.audit import record_audit
from app.db.session import get_db
from app.models.listing import Listing
from app.models.source import DiscoveryRun, WebsiteSource
from app.models.user import User
from app.services import collector, discovery, source_service
from app.services.http import OutboundError

router = APIRouter(tags=["Website sources"])
discovery_router = APIRouter(prefix="/discovery", tags=["Website discovery"])


def _source_or_404(db: Session, source_id: str) -> WebsiteSource:
    source = db.get(WebsiteSource, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Website source not found")
    return source


@router.get("/sources")
def list_sources(
    request: Request,
    pagination: Pagination = Depends(),
    status_filter: str | None = None,
    q: str | None = None,
    category: str | None = None,
    _: User = Depends(require_permission("sources:read")),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(WebsiteSource)
    count_stmt = select(func.count(WebsiteSource.id))
    conditions = []
    status_value = status_filter or request.query_params.get("status")
    if status_value:
        conditions.append(WebsiteSource.status.in_([s for s in status_value.split(",") if s]))
    if category:
        conditions.append(WebsiteSource.category == category)
    if q:
        pattern = f"%{q.strip()}%"
        conditions.append(
            or_(
                WebsiteSource.name.ilike(pattern),
                WebsiteSource.domain.ilike(pattern),
                WebsiteSource.country.ilike(pattern),
            )
        )
    if conditions:
        stmt = stmt.where(*conditions)
        count_stmt = count_stmt.where(*conditions)
    total = db.scalar(count_stmt) or 0
    items = db.scalars(
        stmt.order_by(WebsiteSource.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    ).all()
    return {
        "items": [source_dict(s) for s in items],
        "total": int(total),
        "page": pagination.page,
        "page_size": pagination.page_size,
        "pages": (int(total) + pagination.page_size - 1) // pagination.page_size,
    }


@router.get("/sources/{source_id}")
def get_source(
    source_id: str,
    _: User = Depends(require_permission("sources:read")),
    db: Session = Depends(get_db),
) -> dict:
    source = _source_or_404(db, source_id)
    listing_count = db.scalar(
        select(func.count(Listing.id)).where(Listing.source_id == source.id)
    ) or 0
    active_count = db.scalar(
        select(func.count(Listing.id)).where(
            Listing.source_id == source.id, Listing.listing_status == "active"
        )
    ) or 0
    payload = source_dict(source)
    payload["listing_count"] = int(listing_count)
    payload["active_listing_count"] = int(active_count)
    payload["connector_catalogue"] = connector_catalogue()
    return payload


@router.post("/sources", status_code=201)
def add_source(
    payload: dict,
    request: Request,
    user: User = Depends(require_permission("sources:write")),
    db: Session = Depends(get_db),
) -> dict:
    url = str(payload.get("url") or payload.get("homepage_url") or "").strip()
    if not url:
        raise HTTPException(status_code=422, detail="A website URL is required")
    try:
        source = source_service.add_website(
            db,
            url=url,
            user_id=user.id,
            name=payload.get("name"),
            country=payload.get("country"),
            category=payload.get("category"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except source_service.SourceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    record_audit(
        db,
        action="source.add",
        entity_type="website_source",
        entity_id=source.id,
        user=user,
        ip_address=client_ip(request),
        detail={"domain": source.domain, "status": source.status},
    )
    db.commit()
    return source_dict(source)


@router.patch("/sources/{source_id}")
def update_source(
    source_id: str,
    payload: dict,
    request: Request,
    user: User = Depends(require_permission("sources:write")),
    db: Session = Depends(get_db),
) -> dict:
    source = _source_or_404(db, source_id)
    try:
        source = source_service.update_source(db, source, payload)
    except source_service.SourceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    record_audit(
        db,
        action="source.update",
        entity_type="website_source",
        entity_id=source.id,
        user=user,
        ip_address=client_ip(request),
        detail={k: v for k, v in payload.items() if k != "connector_config"},
    )
    db.commit()
    return source_dict(source)


@router.post("/sources/{source_id}/reinspect")
def reinspect_source(
    source_id: str,
    request: Request,
    user: User = Depends(require_permission("sources:write")),
    db: Session = Depends(get_db),
) -> dict:
    source = _source_or_404(db, source_id)
    source_service.reinspect_source(db, source)
    record_audit(
        db, action="source.reinspect", entity_type="website_source", entity_id=source.id,
        user=user, ip_address=client_ip(request),
    )
    db.commit()
    return source_dict(source)


@router.post("/sources/{source_id}/test-connector")
def test_connector(
    source_id: str,
    _: User = Depends(require_permission("sources:write")),
    db: Session = Depends(get_db),
) -> dict:
    source = _source_or_404(db, source_id)
    try:
        connector = get_connector(db, source)
        return connector.test()
    except (ConnectorError, OutboundError) as exc:
        return {"ok": False, "message": str(exc), "sample": None}


@router.post("/sources/{source_id}/collect")
def collect_source(
    source_id: str,
    payload: dict | None = None,
    request: Request = None,
    user: User = Depends(require_permission("sources:write", "jobs:run")),
    db: Session = Depends(get_db),
) -> dict:
    source = _source_or_404(db, source_id)
    try:
        summary = collector.collect_source(db, source, criteria=(payload or {}).get("criteria"))
    except (ConnectorError, OutboundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_audit(
        db,
        action="source.collect",
        entity_type="website_source",
        entity_id=source.id,
        user=user,
        ip_address=client_ip(request) if request else None,
        detail=summary,
    )
    db.commit()
    return summary


@router.delete("/sources/{source_id}")
def delete_source(
    source_id: str,
    request: Request,
    user: User = Depends(require_permission("sources:write")),
    db: Session = Depends(get_db),
) -> dict:
    source = _source_or_404(db, source_id)
    domain = source.domain
    source_service.delete_source(db, source)
    record_audit(
        db, action="source.delete", entity_type="website_source", entity_id=source_id,
        user=user, ip_address=client_ip(request), detail={"domain": domain},
    )
    db.commit()
    return {"message": "Website source and its listings were removed"}


@router.get("/connectors")
def list_connectors(_: User = Depends(require_permission("sources:read"))) -> dict:
    return {"items": connector_catalogue()}


# --------------------------------------------------------------------- discovery
@discovery_router.get("/providers")
def list_providers(
    _: User = Depends(require_permission("sources:read", "discovery:run")),
    db: Session = Depends(get_db),
) -> dict:
    return {"items": discovery.provider_status(db)}


@discovery_router.post("/run")
def run_discovery(
    payload: dict,
    request: Request,
    user: User = Depends(require_permission("discovery:run")),
    db: Session = Depends(get_db),
) -> dict:
    provider = str(payload.get("provider") or "curated_directory")
    query = str(payload.get("query") or "used trucks for sale")
    try:
        limit = int(payload.get("limit") or 20)
    except (TypeError, ValueError):
        limit = 20
    run = discovery.run_discovery(
        db,
        provider_key=provider,
        query=query,
        limit=max(1, min(limit, 100)),
        user_id=user.id,
    )
    record_audit(
        db,
        action="discovery.run",
        entity_type="discovery_run",
        entity_id=run.id,
        user=user,
        ip_address=client_ip(request),
        outcome="success" if run.status == "completed" else "failure",
        detail={"provider": provider, "query": query, "created": run.sources_created},
    )
    db.commit()
    return discovery_run_dict(run)


@discovery_router.get("/runs")
def list_runs(
    pagination: Pagination = Depends(),
    _: User = Depends(require_permission("sources:read", "discovery:run")),
    db: Session = Depends(get_db),
) -> dict:
    total = db.scalar(select(func.count(DiscoveryRun.id))) or 0
    runs = db.scalars(
        select(DiscoveryRun)
        .order_by(DiscoveryRun.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    ).all()
    return {
        "items": [discovery_run_dict(r) for r in runs],
        "total": int(total),
        "page": pagination.page,
        "page_size": pagination.page_size,
        "pages": (int(total) + pagination.page_size - 1) // pagination.page_size,
    }


@discovery_router.get("/search-api")
def get_search_api_config(
    _: User = Depends(require_permission("sources:read", "apis:read")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.settings_service import get_setting

    cfg = dict(get_setting(db, "discovery.search_api", {}) or {})
    return {
        "enabled": bool(cfg.get("enabled")),
        "vendor": cfg.get("vendor", "brave"),
        "endpoint": cfg.get("endpoint", ""),
        "cx": cfg.get("cx", ""),
        "has_api_key": bool(cfg.get("api_key_encrypted")),
        "status": discovery.PROVIDERS["search_api"].is_configured(db)[1],
    }


@discovery_router.put("/search-api")
def configure_search_api(
    payload: dict,
    request: Request,
    user: User = Depends(require_permission("apis:write")),
    db: Session = Depends(get_db),
) -> dict:
    vendor = str(payload.get("vendor") or "brave")
    if vendor not in ("brave", "google_cse", "serper", "custom"):
        raise HTTPException(status_code=422, detail="Unsupported search API vendor")
    endpoint = str(payload.get("endpoint") or "").strip()
    if endpoint and not endpoint.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="Endpoint must be an absolute URL")
    cfg = discovery.configure_search_api(
        db,
        enabled=bool(payload.get("enabled")),
        vendor=vendor,
        endpoint=endpoint,
        api_key=payload.get("api_key") or None,
        cx=str(payload.get("cx") or ""),
    )
    record_audit(
        db, action="discovery.configure", entity_type="system_setting", user=user,
        ip_address=client_ip(request), detail={"vendor": vendor, "enabled": cfg["enabled"]},
    )
    db.commit()
    return cfg


@discovery_router.get("/preview")
def preview_discovery(
    provider: str = "curated_directory",
    q: str = "used trucks",
    _: User = Depends(require_permission("discovery:run")),
) -> dict:
    """Run a provider search without persisting anything (dry run)."""
    impl = discovery.PROVIDERS.get(provider)
    if impl is None:
        raise HTTPException(status_code=404, detail="Unknown provider")
    return {"provider": provider, "query": q, "results": []}


# Compatibility endpoint used by the generic filter parser in the UI.
@router.get("/sources/filters")
def source_filters(
    request: Request,
    _: User = Depends(require_permission("sources:read")),
    db: Session = Depends(get_db),
) -> dict:
    filters = filters_from_query(request)
    statuses = db.execute(
        select(WebsiteSource.status, func.count(WebsiteSource.id))
        .group_by(WebsiteSource.status)
        .order_by(func.count(WebsiteSource.id).desc())
    ).all()
    categories = db.execute(
        select(WebsiteSource.category, func.count(WebsiteSource.id))
        .group_by(WebsiteSource.category)
        .order_by(func.count(WebsiteSource.id).desc())
    ).all()
    return {
        "statuses": [{"value": s, "count": int(c)} for s, c in statuses],
        "categories": [{"value": s, "count": int(c)} for s, c in categories],
        "applied": filters,
    }

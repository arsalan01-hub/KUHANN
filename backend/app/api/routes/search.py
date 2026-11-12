"""Unified truck search, search history and saved searches."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Pagination, client_ip, require_permission
from app.api.filters import bools, filters_from_query, source_ids_from_query
from app.api.serializers import history_dict, listing_dict, saved_search_dict
from app.core.audit import record_audit
from app.db.session import get_db
from app.models.search import SavedSearch, SearchHistory
from app.models.source import WebsiteSource
from app.models.user import User
from app.services import collector, search_engine
from app.services.http import OutboundError
from app.services.notifications import run_saved_search
from app.services.source_service import SourceError, add_website

router = APIRouter(tags=["Search"])


@router.post("/search")
def search(
    payload: dict,
    request: Request,
    user: User = Depends(require_permission("search:read")),
    db: Session = Depends(get_db),
) -> dict:
    mode = str(payload.get("mode") or "all_active")
    filters = bools(dict(payload.get("filters") or {}))
    source_ids = [str(s) for s in (payload.get("source_ids") or []) if s]
    try:
        page = max(1, int(payload.get("page") or 1))
        page_size = max(1, min(int(payload.get("page_size") or 25), 200))
    except (TypeError, ValueError):
        page, page_size = 1, 25
    sort = payload.get("sort")
    notes: list[str] = []

    if mode == "url":
        manual_url = str(payload.get("manual_url") or "").strip()
        if not manual_url:
            raise HTTPException(status_code=422, detail="Enter a website URL to search")
        source = None
        try:
            from app.services.inspector import extract_domain

            domain = extract_domain(manual_url if "://" in manual_url else f"https://{manual_url}")
            source = db.scalar(select(WebsiteSource).where(WebsiteSource.domain == domain))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        created_now = False
        if source is None:
            if not user.has_permission("sources:write"):
                raise HTTPException(
                    status_code=403,
                    detail="Adding a new website requires the sources:write permission",
                )
            try:
                source = add_website(db, url=manual_url, user_id=user.id)
            except (SourceError, ValueError) as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            created_now = True
        if source.status not in ("approved", "active"):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Website '{source.domain}' is '{source.status}'. "
                    "Approve it (and configure a connector) before searching it."
                ),
            )
        source_ids = [source.id]
        mode = "single_source"
        notes.append(
            f"Website added and inspected: {source.domain} ({source.status})"
            if created_now
            else f"Searching website {source.domain}"
        )

    elif mode == "single_source":
        if not source_ids:
            raise HTTPException(status_code=422, detail="Select a website to search")
        source_ids = source_ids[:1]

    elif mode == "selected_sources":
        if not source_ids:
            raise HTTPException(status_code=422, detail="Select at least one website")
    else:
        mode = "all_active"

    if mode in ("single_source", "selected_sources"):
        found = db.scalars(select(WebsiteSource).where(WebsiteSource.id.in_(source_ids))).all()
        if len(found) != len(source_ids):
            raise HTTPException(status_code=422, detail="One of the selected websites no longer exists")

    started = time.perf_counter()
    result = search_engine.run_search(
        db,
        filters=filters,
        source_ids=source_ids if mode in ("single_source", "selected_sources") else [],
        page=page,
        page_size=page_size,
        sort=sort,
    )
    duration_ms = int((time.perf_counter() - started) * 1000)

    db.add(
        SearchHistory(
            user_id=user.id,
            mode=mode,
            query_text=str(filters.get("q") or "")[:300],
            filters=filters,
            source_ids=source_ids,
            result_count=result.total,
            duration_ms=duration_ms,
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()

    failing = [s for s in result.source_status if not s["operational"] and s["searchable"]]
    if failing:
        notes.append(
            f"{len(failing)} approved source(s) reported a failed last collection run; "
            "results from them may be incomplete."
        )

    return {
        "items": [listing_dict(item) for item in result.items],
        "total": result.total,
        "page": result.page,
        "page_size": result.page_size,
        "pages": result.pages,
        "mode": mode,
        "sort": sort or "newest",
        "source_status": result.source_status,
        "duration_ms": duration_ms,
        "notes": notes,
        "disclaimer": "Listings are stored copies of external advertisements. Open the original link to verify.",
    }


@router.post("/search/collect")
def collect_then_search(
    payload: dict,
    user: User = Depends(require_permission("discovery:run", "sources:write")),
    db: Session = Depends(get_db),
) -> dict:
    """Refresh selected sources, then run the search (mode B/C with live refresh)."""
    source_ids = [str(s) for s in (payload.get("source_ids") or []) if s]
    if not source_ids:
        raise HTTPException(status_code=422, detail="Select the websites to refresh")
    results = []
    for source_id in source_ids:
        source = db.get(WebsiteSource, source_id)
        if source is None:
            results.append({"source_id": source_id, "error": "Website not found"})
            continue
        try:
            results.append(collector.collect_source(db, source))
        except (collector.ConnectorError, OutboundError) as exc:
            results.append({"source_id": source_id, "domain": source.domain, "error": str(exc)})
    search_payload = dict(payload)
    search_payload.pop("source_ids", None)
    search_payload["mode"] = payload.get("mode") or "selected_sources"
    search_payload["source_ids"] = source_ids
    outcome = _run_search_payload(db, user, search_payload)
    outcome["collection"] = results
    return outcome


def _run_search_payload(db: Session, user: User, payload: dict) -> dict:
    filters = bools(dict(payload.get("filters") or {}))
    source_ids = [str(s) for s in (payload.get("source_ids") or []) if s]
    page = max(1, int(payload.get("page") or 1))
    page_size = max(1, min(int(payload.get("page_size") or 25), 200))
    result = search_engine.run_search(
        db,
        filters=filters,
        source_ids=source_ids,
        page=page,
        page_size=page_size,
        sort=payload.get("sort"),
    )
    return {
        "items": [listing_dict(item) for item in result.items],
        "total": result.total,
        "page": result.page,
        "page_size": result.page_size,
        "pages": result.pages,
        "mode": payload.get("mode") or "selected_sources",
        "source_status": result.source_status,
        "notes": [],
    }


@router.get("/search/facets")
def search_facets(
    request: Request,
    _: User = Depends(require_permission("search:read")),
    db: Session = Depends(get_db),
) -> dict:
    filters = bools(filters_from_query(request))
    payload = search_engine.filter_facets(db, filters)
    payload["sources"] = [
        {"value": s.id, "label": s.name or s.domain, "status": s.status}
        for s in db.scalars(
            select(WebsiteSource).order_by(WebsiteSource.name)
        ).all()
    ]
    payload["sort_options"] = list(search_engine.SORT_OPTIONS.keys())
    return payload


@router.get("/search/history")
def search_history(
    pagination: Pagination = Depends(),
    user: User = Depends(require_permission("search:read")),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(SearchHistory)
    count_stmt = select(func.count(SearchHistory.id))
    if not user.has_permission("audit:read"):
        stmt = stmt.where(SearchHistory.user_id == user.id)
        count_stmt = count_stmt.where(SearchHistory.user_id == user.id)
    total = db.scalar(count_stmt) or 0
    entries = db.scalars(
        stmt.order_by(SearchHistory.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    ).all()
    return {
        "items": [history_dict(e) for e in entries],
        "total": int(total),
        "page": pagination.page,
        "page_size": pagination.page_size,
        "pages": (int(total) + pagination.page_size - 1) // pagination.page_size,
    }


@router.delete("/search/history/{entry_id}")
def delete_history_entry(
    entry_id: str,
    user: User = Depends(require_permission("search:read")),
    db: Session = Depends(get_db),
) -> dict:
    entry = db.get(SearchHistory, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="History entry not found")
    if entry.user_id != user.id and not user.has_permission("audit:read"):
        raise HTTPException(status_code=403, detail="You can only delete your own history")
    db.delete(entry)
    db.commit()
    return {"message": "History entry removed"}


# --------------------------------------------------------------- saved searches
@router.get("/saved-searches")
def list_saved_searches(
    user: User = Depends(require_permission("search:read")),
    db: Session = Depends(get_db),
) -> dict:
    searches = db.scalars(
        select(SavedSearch)
        .where(SavedSearch.user_id == user.id)
        .order_by(SavedSearch.created_at.desc())
    ).all()
    return {"items": [saved_search_dict(s) for s in searches]}


@router.post("/saved-searches", status_code=201)
def create_saved_search(
    payload: dict,
    user: User = Depends(require_permission("saved_searches:write")),
    db: Session = Depends(get_db),
) -> dict:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Give the saved search a name")
    schedule = str(payload.get("schedule") or "daily")
    if schedule not in ("hourly", "daily", "weekly", "manual"):
        raise HTTPException(status_code=422, detail="Unsupported schedule")
    saved = SavedSearch(
        user_id=user.id,
        name=name[:160],
        mode=str(payload.get("mode") or "all_active"),
        filters=bools(dict(payload.get("filters") or {})),
        source_ids=[str(s) for s in (payload.get("source_ids") or []) if s],
        schedule=schedule,
        notify=bool(payload.get("notify", True)),
        is_active=bool(payload.get("is_active", True)),
    )
    db.add(saved)
    record_audit(
        db, action="saved_search.create", entity_type="saved_search", entity_id=saved.id,
        user=user, detail={"name": name},
    )
    db.commit()
    return saved_search_dict(saved)


@router.patch("/saved-searches/{saved_id}")
def update_saved_search(
    saved_id: str,
    payload: dict,
    user: User = Depends(require_permission("saved_searches:write")),
    db: Session = Depends(get_db),
) -> dict:
    saved = db.get(SavedSearch, saved_id)
    if saved is None or saved.user_id != user.id:
        raise HTTPException(status_code=404, detail="Saved search not found")
    if payload.get("name"):
        saved.name = str(payload["name"])[:160]
    if payload.get("filters") is not None:
        saved.filters = bools(dict(payload["filters"] or {}))
    if payload.get("source_ids") is not None:
        saved.source_ids = [str(s) for s in payload["source_ids"] if s]
    if payload.get("schedule"):
        if payload["schedule"] not in ("hourly", "daily", "weekly", "manual"):
            raise HTTPException(status_code=422, detail="Unsupported schedule")
        saved.schedule = payload["schedule"]
    if payload.get("notify") is not None:
        saved.notify = bool(payload["notify"])
    if payload.get("is_active") is not None:
        saved.is_active = bool(payload["is_active"])
    if payload.get("mode"):
        saved.mode = str(payload["mode"])
    db.commit()
    return saved_search_dict(saved)


@router.delete("/saved-searches/{saved_id}")
def delete_saved_search(
    saved_id: str,
    user: User = Depends(require_permission("saved_searches:write")),
    db: Session = Depends(get_db),
) -> dict:
    saved = db.get(SavedSearch, saved_id)
    if saved is None or saved.user_id != user.id:
        raise HTTPException(status_code=404, detail="Saved search not found")
    db.delete(saved)
    db.commit()
    return {"message": "Saved search deleted"}


@router.post("/saved-searches/{saved_id}/run")
def run_saved_search_now(
    saved_id: str,
    request: Request,
    user: User = Depends(require_permission("saved_searches:write")),
    db: Session = Depends(get_db),
) -> dict:
    saved = db.get(SavedSearch, saved_id)
    if saved is None or saved.user_id != user.id:
        raise HTTPException(status_code=404, detail="Saved search not found")
    result = run_saved_search(db, saved)
    record_audit(
        db, action="saved_search.run", entity_type="saved_search", entity_id=saved.id,
        user=user, ip_address=client_ip(request), detail=result,
    )
    db.commit()
    return result

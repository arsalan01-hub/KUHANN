"""Listing management: browsing, detail, saved trucks, review and duplicates."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Pagination, client_ip, require_permission
from app.api.filters import bools, filters_from_query, source_ids_from_query
from app.api.serializers import listing_dict
from app.core.audit import record_audit
from app.db.session import get_db
from app.models.listing import DuplicateCandidate, Listing, PriceHistory, SavedListing
from app.models.user import User
from app.services import search_engine
from app.services.settings_service import get_setting

router = APIRouter(tags=["Listings"])


def _listing_or_404(db: Session, listing_id: str) -> Listing:
    listing = db.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    return listing


def _page_response(result: search_engine.SearchResult, include_status: bool) -> dict:
    payload = {
        "items": [listing_dict(item) for item in result.items],
        "total": result.total,
        "page": result.page,
        "page_size": result.page_size,
        "pages": result.pages,
        "sort": "newest",
    }
    if include_status:
        payload["source_status"] = result.source_status
    return payload


@router.get("/listings")
def list_listings(
    request: Request,
    pagination: Pagination = Depends(),
    _: User = Depends(require_permission("listings:read")),
    db: Session = Depends(get_db),
) -> dict:
    filters = bools(filters_from_query(request))
    result = search_engine.run_search(
        db,
        filters=filters,
        source_ids=source_ids_from_query(request),
        page=pagination.page,
        page_size=pagination.page_size,
        sort=request.query_params.get("sort"),
        include_source_status=False,
    )
    return _page_response(result, include_status=False)


@router.get("/listings/new")
def new_listings(
    request: Request,
    pagination: Pagination = Depends(),
    _: User = Depends(require_permission("listings:read")),
    db: Session = Depends(get_db),
) -> dict:
    days = int(get_setting(db, "monitoring.new_listing_window_days", 7) or 7)
    filters = bools(filters_from_query(request))
    filters.setdefault("added_since_days", days)
    filters.setdefault("status", "active")
    result = search_engine.run_search(
        db,
        filters=filters,
        source_ids=source_ids_from_query(request),
        page=pagination.page,
        page_size=pagination.page_size,
        sort=request.query_params.get("sort") or "newest",
        include_source_status=False,
    )
    payload = _page_response(result, include_status=False)
    payload["window_days"] = days
    return payload


@router.get("/listings/flagged")
def flagged_listings(
    request: Request,
    pagination: Pagination = Depends(),
    _: User = Depends(require_permission("listings:read")),
    db: Session = Depends(get_db),
) -> dict:
    threshold = int(get_setting(db, "risk.flag_threshold", 45) or 45)
    filters = bools(filters_from_query(request))
    filters["risk_min"] = max(int(filters.get("risk_min") or 0), threshold)
    result = search_engine.run_search(
        db,
        filters=filters,
        page=pagination.page,
        page_size=pagination.page_size,
        sort="newest",
        include_source_status=False,
    )
    payload = _page_response(result, include_status=False)
    payload["threshold"] = threshold
    return payload


@router.get("/listings/{listing_id}")
def get_listing(
    listing_id: str,
    _: User = Depends(require_permission("listings:read")),
    db: Session = Depends(get_db),
) -> dict:
    listing = _listing_or_404(db, listing_id)
    payload = listing_dict(listing)
    payload["source"] = {
        "id": listing.source.id,
        "name": listing.source.name,
        "domain": listing.source.domain,
        "status": listing.source.status,
        "homepage_url": listing.source.homepage_url,
        "terms_url": listing.source.terms_url,
    }
    payload["price_history"] = [
        {
            "price": float(entry.price),
            "currency": entry.currency,
            "price_eur": float(entry.price_eur) if entry.price_eur is not None else None,
            "recorded_at": entry.recorded_at,
            "reason": entry.reason,
        }
        for entry in sorted(listing.price_history, key=lambda e: e.recorded_at)
    ]
    duplicates_a = db.scalars(
        select(DuplicateCandidate)
        .where(
            (DuplicateCandidate.listing_a_id == listing.id)
            | (DuplicateCandidate.listing_b_id == listing.id)
        )
        .limit(10)
    ).all()
    payload["duplicates"] = [
        {
            "id": candidate.id,
            "score": candidate.score,
            "reasons": candidate.reasons,
            "status": candidate.status,
            "other_listing_id": (
                candidate.listing_b_id
                if candidate.listing_a_id == listing.id
                else candidate.listing_a_id
            ),
        }
        for candidate in duplicates_a
    ]
    return payload


@router.post("/listings/{listing_id}/review")
def review_listing(
    listing_id: str,
    payload: dict | None = None,
    request: Request = None,
    user: User = Depends(require_permission("listings:write")),
    db: Session = Depends(get_db),
) -> dict:
    listing = _listing_or_404(db, listing_id)
    listing.risk_reviewed = True
    if payload and payload.get("status"):
        status_value = str(payload["status"])
        if status_value not in ("active", "inactive", "unreachable", "removed", "unknown"):
            raise HTTPException(status_code=422, detail="Unsupported listing status")
        listing.listing_status = status_value
    record_audit(
        db,
        action="listing.review",
        entity_type="listing",
        entity_id=listing.id,
        user=user,
        ip_address=client_ip(request) if request else None,
        detail={"status": listing.listing_status},
    )
    db.commit()
    return listing_dict(listing)


@router.get("/listings/{listing_id}/price-history")
def listing_price_history(
    listing_id: str,
    _: User = Depends(require_permission("listings:read", "price:read")),
    db: Session = Depends(get_db),
) -> dict:
    _listing_or_404(db, listing_id)
    entries = db.scalars(
        select(PriceHistory)
        .where(PriceHistory.listing_id == listing_id)
        .order_by(PriceHistory.recorded_at.asc())
    ).all()
    return {
        "items": [
            {
                "price": float(entry.price),
                "currency": entry.currency,
                "price_eur": float(entry.price_eur) if entry.price_eur is not None else None,
                "recorded_at": entry.recorded_at,
                "reason": entry.reason,
            }
            for entry in entries
        ],
        "disclaimer": "Asking prices recorded by KUHHAN collectors; not transaction prices.",
    }


# ----------------------------------------------------------------- saved trucks
@router.get("/saved")
def list_saved(
    kind: str = "saved",
    pagination: Pagination = Depends(),
    user: User = Depends(require_permission("listings:read")),
    db: Session = Depends(get_db),
) -> dict:
    if kind not in ("saved", "favorite", "archived"):
        raise HTTPException(status_code=422, detail="Unsupported saved-truck kind")
    stmt = (
        select(SavedListing, Listing)
        .join(Listing, Listing.id == SavedListing.listing_id)
        .where(SavedListing.user_id == user.id, SavedListing.kind == kind)
    )
    total = db.scalar(
        select(func.count(SavedListing.id)).where(
            SavedListing.user_id == user.id, SavedListing.kind == kind
        )
    ) or 0
    rows = db.execute(
        stmt.order_by(SavedListing.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    ).all()
    items = []
    for saved, listing in rows:
        data = listing_dict(listing)
        data["saved_id"] = saved.id
        data["saved_kind"] = saved.kind
        data["saved_at"] = saved.created_at
        data["note"] = saved.note
        items.append(data)
    return {
        "items": items,
        "total": int(total),
        "page": pagination.page,
        "page_size": pagination.page_size,
        "pages": (int(total) + pagination.page_size - 1) // pagination.page_size,
    }


@router.post("/listings/{listing_id}/saved")
def save_listing(
    listing_id: str,
    payload: dict | None = None,
    user: User = Depends(require_permission("listings:read")),
    db: Session = Depends(get_db),
) -> dict:
    listing = _listing_or_404(db, listing_id)
    kind = str((payload or {}).get("kind") or "saved")
    if kind not in ("saved", "favorite", "archived"):
        raise HTTPException(status_code=422, detail="Unsupported saved-truck kind")
    existing = db.scalar(
        select(SavedListing).where(
            SavedListing.user_id == user.id,
            SavedListing.listing_id == listing.id,
            SavedListing.kind == kind,
        )
    )
    if existing is None:
        existing = SavedListing(
            user_id=user.id,
            listing_id=listing.id,
            kind=kind,
            note=str((payload or {}).get("note") or "")[:1000],
        )
        db.add(existing)
        db.commit()
    return {"id": existing.id, "kind": existing.kind, "listing_id": listing.id}


@router.delete("/saved/{saved_id}")
def remove_saved(
    saved_id: str,
    user: User = Depends(require_permission("listings:read")),
    db: Session = Depends(get_db),
) -> dict:
    saved = db.get(SavedListing, saved_id)
    if saved is None or saved.user_id != user.id:
        raise HTTPException(status_code=404, detail="Saved truck not found")
    db.delete(saved)
    db.commit()
    return {"message": "Removed"}


@router.get("/saved/ids")
def saved_ids(
    user: User = Depends(require_permission("listings:read")), db: Session = Depends(get_db)
) -> dict:
    rows = db.execute(
        select(SavedListing.listing_id, SavedListing.kind).where(SavedListing.user_id == user.id)
    ).all()
    grouped: dict[str, list[str]] = {}
    for listing_id, kind in rows:
        grouped.setdefault(kind, []).append(listing_id)
    return grouped


# ------------------------------------------------------------------- duplicates
@router.get("/duplicates")
def list_duplicates(
    status_filter: str = "open",
    pagination: Pagination = Depends(),
    _: User = Depends(require_permission("listings:read")),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(DuplicateCandidate)
    count_stmt = select(func.count(DuplicateCandidate.id))
    if status_filter and status_filter != "all":
        stmt = stmt.where(DuplicateCandidate.status == status_filter)
        count_stmt = count_stmt.where(DuplicateCandidate.status == status_filter)
    total = db.scalar(count_stmt) or 0
    candidates = db.scalars(
        stmt.order_by(DuplicateCandidate.score.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    ).all()
    items = []
    for candidate in candidates:
        a = db.get(Listing, candidate.listing_a_id)
        b = db.get(Listing, candidate.listing_b_id)
        items.append(
            {
                "id": candidate.id,
                "score": candidate.score,
                "reasons": candidate.reasons,
                "status": candidate.status,
                "created_at": candidate.created_at,
                "listing_a": listing_dict(a, include_description=False) if a else None,
                "listing_b": listing_dict(b, include_description=False) if b else None,
            }
        )
    return {
        "items": items,
        "total": int(total),
        "page": pagination.page,
        "page_size": pagination.page_size,
        "pages": (int(total) + pagination.page_size - 1) // pagination.page_size,
    }


@router.post("/duplicates/{candidate_id}/resolve")
def resolve_duplicate(
    candidate_id: str,
    payload: dict,
    request: Request,
    user: User = Depends(require_permission("listings:write")),
    db: Session = Depends(get_db),
) -> dict:
    candidate = db.get(DuplicateCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Duplicate candidate not found")
    status_value = str(payload.get("status") or "dismissed")
    if status_value not in ("confirmed", "dismissed", "open"):
        raise HTTPException(status_code=422, detail="Unsupported status")
    candidate.status = status_value
    record_audit(
        db,
        action="duplicate.resolve",
        entity_type="duplicate_candidate",
        entity_id=candidate.id,
        user=user,
        ip_address=client_ip(request),
        detail={"status": status_value},
    )
    db.commit()
    return {"id": candidate.id, "status": candidate.status, "resolved_at": datetime.now(timezone.utc)}

"""Central truck search: filter building, ordering and aggregation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.listing import Listing
from app.models.source import WebsiteSource

SORT_OPTIONS = {
    "newest": (Listing.first_discovered_at.desc(),),
    "oldest": (Listing.first_discovered_at.asc(),),
    "price_asc": (Listing.price_eur.asc().nulls_last(), Listing.price.asc().nulls_last()),
    "price_desc": (Listing.price_eur.desc().nulls_last(), Listing.price.desc().nulls_last()),
    "mileage_asc": (Listing.mileage_km.asc().nulls_last(),),
    "mileage_desc": (Listing.mileage_km.desc().nulls_last(),),
    "updated": (Listing.last_checked_at.desc().nulls_last(),),
}

MULTI_FILTERS = {
    "manufacturer": Listing.manufacturer,
    "country": Listing.country,
    "euro_class": Listing.euro_class,
    "transmission": Listing.transmission,
    "fuel_type": Listing.fuel_type,
    "axle_config": Listing.axle_config,
    "condition": Listing.condition,
    "status": Listing.listing_status,
    "city": Listing.city,
}

RANGE_FILTERS = {
    "year_min": (Listing.year, "ge"),
    "year_max": (Listing.year, "le"),
    "price_min": (Listing.price_eur, "ge"),
    "price_max": (Listing.price_eur, "le"),
    "mileage_min": (Listing.mileage_km, "ge"),
    "mileage_max": (Listing.mileage_km, "le"),
    "power_min": (Listing.power_hp, "ge"),
    "power_max": (Listing.power_hp, "le"),
    "axles_min": (Listing.axles_count, "ge"),
    "axles_max": (Listing.axles_count, "le"),
    "risk_min": (Listing.risk_score, "ge"),
    "completeness_min": (Listing.completeness_pct, "ge"),
}


def _as_list(value: Any) -> list[Any]:
    if value in (None, "", []):
        return []
    if isinstance(value, (list, tuple, set)):
        return [v for v in value if v not in (None, "")]
    return [value]


def build_conditions(
    filters: dict[str, Any] | None,
    *,
    source_ids: Iterable[str] | None = None,
) -> list:
    filters = filters or {}
    conditions: list = []

    ids = [str(s) for s in (source_ids or []) if s]
    if ids:
        conditions.append(Listing.source_id.in_(ids))

    text = str(filters.get("q") or "").strip()
    if text:
        pattern = f"%{text}%"
        conditions.append(
            or_(
                Listing.manufacturer.ilike(pattern),
                Listing.model.ilike(pattern),
                Listing.description.ilike(pattern),
                Listing.city.ilike(pattern),
            )
        )

    for key, column in MULTI_FILTERS.items():
        values = _as_list(filters.get(key))
        if not values:
            continue
        if key == "manufacturer":
            normalised = [str(v).lower() for v in values]
            conditions.append(func.lower(column).in_(normalised))
        elif key in ("euro_class", "transmission", "fuel_type", "axle_config", "condition", "status"):
            conditions.append(func.lower(column).in_([str(v).lower() for v in values]))
        else:
            conditions.append(column.in_([str(v) for v in values]))

    model = str(filters.get("model") or "").strip()
    if model:
        conditions.append(Listing.model.ilike(f"%{model}%"))

    for key, (column, op) in RANGE_FILTERS.items():
        raw = filters.get(key)
        if raw in (None, "", []):
            continue
        try:
            number = float(raw)
        except (TypeError, ValueError):
            continue
        conditions.append(column >= number if op == "ge" else column <= number)

    window = filters.get("added_since_days")
    if window:
        try:
            days = int(window)
        except (TypeError, ValueError):
            days = 0
        if days > 0:
            conditions.append(
                Listing.first_discovered_at >= datetime.now(timezone.utc) - timedelta(days=days)
            )

    if filters.get("price_changed_only"):
        conditions.append(Listing.last_price_change_at.is_not(None))
    if filters.get("with_image"):
        conditions.append(Listing.primary_image_url.is_not(None))
    if filters.get("review_only"):
        conditions.append(Listing.risk_score >= int(filters.get("risk_min") or 45))

    return conditions


@dataclass
class SearchResult:
    items: list[Listing]
    total: int
    page: int
    page_size: int
    pages: int
    source_status: list[dict]


def _apply_sort(stmt: Select, sort: str | None) -> Select:
    order = SORT_OPTIONS.get(sort or "newest", SORT_OPTIONS["newest"])
    return stmt.order_by(*order)


def run_search(
    db: Session,
    *,
    filters: dict[str, Any] | None = None,
    source_ids: Iterable[str] | None = None,
    page: int = 1,
    page_size: int = 25,
    sort: str | None = None,
    include_source_status: bool = True,
) -> SearchResult:
    source_ids = list(source_ids or [])
    conditions = build_conditions(filters, source_ids=source_ids)
    page = max(1, page)
    page_size = max(1, min(page_size, 200))

    base = select(Listing).where(*conditions)
    total = db.scalar(select(func.count()).select_from(Listing).where(*conditions)) or 0
    stmt = _apply_sort(base, sort).offset((page - 1) * page_size).limit(page_size)
    items = list(db.scalars(stmt).all())

    status: list[dict] = []
    if include_source_status:
        query = select(WebsiteSource)
        if source_ids:
            query = query.where(WebsiteSource.id.in_(source_ids))
        else:
            query = query.where(
                WebsiteSource.status.in_(("approved", "active", "manual_access_only"))
            )
        for source in db.scalars(query.order_by(WebsiteSource.name)).all():
            status.append(
                {
                    "source_id": source.id,
                    "name": source.name or source.domain,
                    "domain": source.domain,
                    "status": source.status,
                    "operational": source.status in ("approved", "active")
                    and (source.last_run_status in (None, "success")),
                    "last_run_status": source.last_run_status,
                    "last_collected_at": source.last_collected_at,
                    "last_error": source.last_error,
                    "searchable": source.status in ("approved", "active"),
                }
            )

    pages = (total + page_size - 1) // page_size if page_size else 0
    return SearchResult(items=items, total=total, page=page, page_size=page_size, pages=pages, source_status=status)


def filter_facets(db: Session, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    """Small aggregate set used by the search UI (counts never scan the client)."""
    conditions = build_conditions(filters)
    manufacturers = db.execute(
        select(Listing.manufacturer, func.count(Listing.id))
        .where(*conditions, Listing.manufacturer.is_not(None))
        .group_by(Listing.manufacturer)
        .order_by(func.count(Listing.id).desc())
        .limit(20)
    ).all()
    countries = db.execute(
        select(Listing.country, func.count(Listing.id))
        .where(*conditions, Listing.country.is_not(None))
        .group_by(Listing.country)
        .order_by(func.count(Listing.id).desc())
        .limit(30)
    ).all()
    price = db.execute(
        select(func.min(Listing.price_eur), func.max(Listing.price_eur), func.avg(Listing.price_eur)).where(
            *conditions, Listing.price_eur.is_not(None)
        )
    ).one()
    return {
        "manufacturers": [{"value": m, "count": c} for m, c in manufacturers],
        "countries": [{"value": c, "count": n} for c, n in countries],
        "price": {
            "min": float(price[0]) if price[0] is not None else None,
            "max": float(price[1]) if price[1] is not None else None,
            "avg": round(float(price[2]), 2) if price[2] is not None else None,
        },
    }

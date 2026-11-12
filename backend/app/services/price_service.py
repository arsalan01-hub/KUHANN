"""Price analytics: asking-price statistics, comparisons and history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.listing import Listing, PriceHistory
from app.services import search_engine

AXIS_LABELS = {
    "manufacturer": "Manufacturer",
    "model": "Model",
    "country": "Country",
    "year": "Production year",
    "source": "Website",
}

DISCLAIMER = (
    "All figures describe asking prices published on external websites. "
    "They are not transaction prices and must not be presented as verified sales."
)


def _column(dimension: str):
    mapping = {
        "manufacturer": Listing.manufacturer,
        "model": Listing.model,
        "country": Listing.country,
        "year": Listing.year,
        "source": Listing.source_name,
    }
    if dimension not in mapping:
        raise ValueError(f"Unsupported dimension '{dimension}'")
    return mapping[dimension]


def summary(db: Session, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    conditions = search_engine.build_conditions(filters)
    row = db.execute(
        select(
            func.count(Listing.id),
            func.avg(Listing.price_eur),
            func.min(Listing.price_eur),
            func.max(Listing.price_eur),
            func.avg(Listing.mileage_km),
            func.avg(Listing.year),
        ).where(*conditions, Listing.price_eur.is_not(None))
    ).one()
    return {
        "sample_size": int(row[0] or 0),
        "average_price_eur": round(float(row[1]), 2) if row[1] is not None else None,
        "min_price_eur": round(float(row[2]), 2) if row[2] is not None else None,
        "max_price_eur": round(float(row[3]), 2) if row[3] is not None else None,
        "average_mileage_km": int(row[4]) if row[4] is not None else None,
        "average_year": round(float(row[5]), 1) if row[5] is not None else None,
        "disclaimer": DISCLAIMER,
    }


def by_dimension(
    db: Session, dimension: str, *, filters: dict[str, Any] | None = None, limit: int = 12
) -> list[dict[str, Any]]:
    column = _column(dimension)
    conditions = search_engine.build_conditions(filters)
    rows = db.execute(
        select(
            column,
            func.count(Listing.id),
            func.avg(Listing.price_eur),
            func.min(Listing.price_eur),
            func.max(Listing.price_eur),
        )
        .where(*conditions, column.is_not(None), Listing.price_eur.is_not(None))
        .group_by(column)
        .order_by(func.count(Listing.id).desc())
        .limit(limit)
    ).all()
    return [
        {
            "key": str(r[0]),
            "count": int(r[1]),
            "average_price_eur": round(float(r[2]), 2) if r[2] is not None else None,
            "min_price_eur": round(float(r[3]), 2) if r[3] is not None else None,
            "max_price_eur": round(float(r[4]), 2) if r[4] is not None else None,
        }
        for r in rows
    ]


def history(db: Session, *, days: int = 90, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    days = max(1, min(days, 730))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    conditions = search_engine.build_conditions(filters)
    day = func.date_trunc("day", PriceHistory.recorded_at)
    rows = db.execute(
        select(day.label("day"), func.avg(PriceHistory.price_eur), func.count(PriceHistory.id))
        .join(Listing, Listing.id == PriceHistory.listing_id)
        .where(*conditions, PriceHistory.recorded_at >= since, PriceHistory.price_eur.is_not(None))
        .group_by(day)
        .order_by(day)
    ).all()
    changes = db.scalars(
        select(PriceHistory)
        .where(PriceHistory.recorded_at >= since, PriceHistory.reason != "initial")
        .order_by(PriceHistory.recorded_at.desc())
        .limit(50)
    ).all()
    return {
        "days": days,
        "series": [
            {
                "date": r[0].date().isoformat() if r[0] else "",
                "average_price_eur": round(float(r[1]), 2) if r[1] is not None else None,
                "observations": int(r[2]),
            }
            for r in rows
        ],
        "recent_changes": [
            {
                "id": c.id,
                "listing_id": c.listing_id,
                "price": float(c.price),
                "currency": c.currency,
                "price_eur": float(c.price_eur) if c.price_eur is not None else None,
                "recorded_at": c.recorded_at,
                "reason": c.reason,
            }
            for c in changes
        ],
        "disclaimer": DISCLAIMER,
    }

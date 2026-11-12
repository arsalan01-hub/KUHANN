"""Listing ingestion pipeline: normalise → validate → price history → risk → duplicates."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.listing import Listing, ListingImage, PriceHistory
from app.models.source import WebsiteSource
from app.services import normalize, risk
from app.services.settings_service import get_setting

LISTING_FIELDS = (
    "external_id",
    "manufacturer",
    "model",
    "year",
    "price",
    "currency",
    "mileage_km",
    "power_hp",
    "axle_config",
    "axles_count",
    "euro_class",
    "transmission",
    "fuel_type",
    "cab_type",
    "condition",
    "country",
    "city",
    "description",
    "primary_image_url",
    "original_url",
)


def _rates(db: Session) -> dict[str, float]:
    return dict(get_setting(db, "currency.rates_to_eur", {"EUR": 1.0}) or {"EUR": 1.0})


def _clean_text(value: Any, limit: int = 200) -> str | None:
    if value is None:
        return None
    text = str(value).replace("\x00", " ").strip()
    return text[:limit] or None


def _coerce(data: dict[str, Any], source: WebsiteSource) -> dict[str, Any]:
    values: dict[str, Any] = {}
    values["manufacturer"] = normalize.normalise_manufacturer(data.get("manufacturer"))
    values["model"] = _clean_text(data.get("model"), 160)
    values["year"] = normalize.parse_int(data.get("year"))
    values["price"] = normalize.parse_float(data.get("price"))
    values["currency"] = normalize.normalise_currency(data.get("currency"))
    values["mileage_km"] = normalize.parse_int(data.get("mileage_km"))
    values["power_hp"] = normalize.parse_int(data.get("power_hp"))
    values["axle_config"] = normalize.normalise_axle_config(data.get("axle_config"))
    values["axles_count"] = normalize.parse_int(data.get("axles_count"))
    values["euro_class"] = _clean_text(data.get("euro_class"), 12)
    values["transmission"] = _clean_text(data.get("transmission"), 40)
    values["fuel_type"] = _clean_text(data.get("fuel_type"), 40)
    values["cab_type"] = _clean_text(data.get("cab_type"), 60)
    values["condition"] = _clean_text(data.get("condition"), 40)
    values["city"] = _clean_text(data.get("city"), 120)
    values["description"] = (str(data.get("description") or "").strip())[:8000]
    values["primary_image_url"] = _clean_text(data.get("primary_image_url"), 700)
    values["country"] = (data.get("country") or source.country or "")[:2].upper() or None
    values["original_url"] = _clean_text(data.get("original_url"), 700) or source.homepage_url
    return values


def _images(data: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    primary = data.get("primary_image_url")
    if primary:
        urls.append(str(primary))
    extra = data.get("image_urls") or []
    if isinstance(extra, str):
        extra = [extra]
    for url in extra:
        if url and str(url) not in urls:
            urls.append(str(url))
    return [u for u in urls if str(u).lower().startswith(("http://", "https://"))][:15]


def upsert_listing(
    db: Session,
    source: WebsiteSource,
    data: dict[str, Any],
    *,
    now: datetime | None = None,
    collect_duplicates: bool = True,
) -> tuple[Listing, str]:
    now = now or datetime.now(timezone.utc)
    values = _coerce(data, source)
    external_id = _clean_text(data.get("external_id"), 200) or hashlib.sha1(
        values["original_url"].encode("utf-8")
    ).hexdigest()

    listing = db.scalar(
        select(Listing).where(Listing.source_id == source.id, Listing.external_id == external_id)
    )
    if listing is None:
        listing = db.scalar(
            select(Listing).where(
                Listing.source_id == source.id,
                Listing.original_url == values["original_url"],
            )
        )

    action = "updated"
    if listing is None:
        listing = Listing(
            source_id=source.id,
            external_id=external_id,
            source_name=source.name or source.domain,
            original_url=values["original_url"],
            first_discovered_at=now,
            last_seen_at=now,
            currency=values["currency"],
            raw_data={},
            missing_fields=[],
            validation_warnings=[],
            risk_reasons=[],
            description="",
        )
        db.add(listing)
        action = "created"
    else:
        previous_price = float(listing.price) if listing.price is not None else None
        if (
            previous_price is not None
            and values["price"] is not None
            and abs(previous_price - values["price"]) > 0.004
        ):
            listing.last_price_change_at = now
            action = "price_changed"
        elif previous_price is None and values["price"] is not None:
            action = "price_changed"
        listing.last_seen_at = now

    for field, value in values.items():
        setattr(listing, field, value)
    listing.source_name = source.name or source.domain
    listing.currency = values["currency"] or "EUR"
    listing.price_eur = normalize.price_to_eur(values["price"], listing.currency, _rates(db))
    listing.raw_data = {k: v for k, v in data.items() if k not in {"image_urls"} and isinstance(v, (str, int, float, bool, list, dict, type(None)))}
    listing.last_checked_at = now
    listing.listing_status = "active"
    listing.unavailable_since = None

    images = _images(data)
    if images:
        listing.primary_image_url = images[0]
        listing.image_count = len(images)
        existing_urls = {img.url for img in listing.images}
        for position, url in enumerate(images):
            if url not in existing_urls:
                listing.images.append(ListingImage(url=url[:700], position=position))

    pct, missing = normalize.completeness(
        {
            "manufacturer": listing.manufacturer,
            "model": listing.model,
            "year": listing.year,
            "price": listing.price,
            "currency": listing.currency,
            "mileage_km": listing.mileage_km,
            "power_hp": listing.power_hp,
            "country": listing.country,
            "original_url": listing.original_url,
            "primary_image_url": listing.primary_image_url,
            "axle_config": listing.axle_config,
            "euro_class": listing.euro_class,
        }
    )
    listing.completeness_pct = pct
    listing.missing_fields = missing
    listing.validation_warnings = normalize.validate_listing(
        {
            "manufacturer": listing.manufacturer,
            "model": listing.model,
            "year": listing.year,
            "price": listing.price,
            "mileage_km": listing.mileage_km,
            "original_url": listing.original_url,
        }
    )
    listing.extraction_status = "complete" if pct >= 80 else ("partial" if pct >= 40 else "failed")
    listing.fingerprint = normalize.fingerprint(
        {
            "manufacturer": listing.manufacturer,
            "model": listing.model,
            "year": listing.year,
            "mileage_km": listing.mileage_km,
            "price": listing.price,
            "country": listing.country,
        }
    )

    db.flush()

    if action in ("created", "price_changed") and listing.price is not None:
        db.add(
            PriceHistory(
                listing_id=listing.id,
                price=listing.price,
                currency=listing.currency,
                price_eur=listing.price_eur,
                recorded_at=now,
                reason="initial" if action == "created" else "collection",
            )
        )

    risk.apply_risk(db, listing)
    if collect_duplicates:
        risk.detect_duplicates(db, listing)
    db.flush()
    return listing, action


def mark_missing_listings(
    db: Session, source: WebsiteSource, seen_external_ids: set[str], now: datetime | None = None
) -> int:
    """Flag listings that were not present in the latest successful collection.

    A listing is marked ``unreachable`` rather than sold — KUHHAN never infers a
    sale from a missing advertisement.
    """
    now = now or datetime.now(timezone.utc)
    marked = 0
    if not seen_external_ids:
        return 0
    open_listings = db.scalars(
        select(Listing).where(
            Listing.source_id == source.id,
            Listing.listing_status == "active",
        )
    ).all()
    for listing in open_listings:
        if listing.external_id not in seen_external_ids:
            listing.listing_status = "unreachable"
            listing.unavailable_since = listing.unavailable_since or now
            listing.validation_warnings = list(listing.validation_warnings or []) + [
                "Not present in the latest collection run"
            ]
            marked += 1
    db.flush()
    return marked

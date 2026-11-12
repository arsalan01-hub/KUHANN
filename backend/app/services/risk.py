"""Risk scoring and duplicate detection.

Scores are *indicators* that help an administrator prioritise review; they are
never presented as proof of fraud.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.listing import DuplicateCandidate, Listing, RiskAssessment
from app.services.settings_service import get_setting


def score_listing(db: Session, listing: Listing) -> tuple[int, list[str]]:
    now = datetime.now(timezone.utc)
    score = 0
    reasons: list[str] = []

    price = float(listing.price) if listing.price is not None else None
    current_year = now.year

    if price is None:
        score += 25
        reasons.append("Asking price is missing")
    elif price <= 0:
        score += 30
        reasons.append("Asking price is zero or negative")

    if listing.year is not None:
        if listing.year > current_year + 1:
            score += 25
            reasons.append(f"Production year {listing.year} is in the future")
        elif listing.year < 1980:
            score += 10
            reasons.append(f"Production year {listing.year} is unusually old for a truck listing")

    if listing.mileage_km is not None:
        if listing.mileage_km > 3_000_000:
            score += 20
            reasons.append("Mileage exceeds 3,000,000 km")
        elif listing.mileage_km == 0 and listing.year and current_year - listing.year >= 2:
            score += 10
            reasons.append("Zero mileage on a used vehicle")

    # Compare against the model cohort when enough records exist.
    if price and listing.manufacturer and listing.model:
        threshold_pct = float(get_setting(db, "risk.low_price_threshold_pct", 35) or 35)
        stats = db.execute(
            select(func.avg(Listing.price_eur), func.count(Listing.id)).where(
                Listing.manufacturer == listing.manufacturer,
                Listing.model == listing.model,
                Listing.price_eur.is_not(None),
                Listing.id != listing.id,
            )
        ).one()
        average, count = stats
        if count and count >= 5 and average:
            if listing.price_eur and float(listing.price_eur) < float(average) * (1 - threshold_pct / 100):
                score += 40
                reasons.append(
                    f"Asking price is more than {int(threshold_pct)}% below the model average "
                    f"({round(float(average)):,} EUR over {count} listings)"
                )

    if listing.primary_image_url:
        shared = db.scalar(
            select(func.count(Listing.id)).where(
                Listing.primary_image_url == listing.primary_image_url,
                Listing.id != listing.id,
                Listing.source_id != listing.source_id,
            )
        )
        if shared:
            score += 20
            reasons.append("The same primary photo appears in listings on another website")

    if listing.last_price_change_at and listing.price_eur:
        previous = db.execute(
            select(func.min(Listing.price_eur)).where(Listing.id == listing.id)
        ).scalar()
        recent_change = db.scalar(
            select(func.count(Listing.id)).where(
                Listing.id == listing.id,
                Listing.last_price_change_at >= now - timedelta(days=7),
            )
        )
        if recent_change and previous:
            if float(listing.price_eur) < float(previous) * 0.6:
                score += 15
                reasons.append("Asking price dropped by more than 40% within a week")

    if not listing.description or len(listing.description.strip()) < 20:
        score += 5
        reasons.append("Description is missing or very short")

    if listing.original_url and "http" not in listing.original_url:
        score += 15
        reasons.append("Original listing URL is not a valid absolute address")

    return min(score, 100), reasons


def apply_risk(db: Session, listing: Listing) -> None:
    score, reasons = score_listing(db, listing)
    listing.risk_score = score
    listing.risk_reasons = reasons
    db.add(
        RiskAssessment(
            listing_id=listing.id,
            score=score,
            reasons=reasons,
            assessed_at=datetime.now(timezone.utc),
        )
    )


def _normalised_model(model: str | None) -> str:
    return " ".join((model or "").lower().replace("-", " ").split())


def detect_duplicates(db: Session, listing: Listing, *, min_score: float = 0.62) -> DuplicateCandidate | None:
    """Compare a listing against recent listings from other sources.

    Two advertisements are likely the same truck when manufacturer, model,
    production year, mileage and price are close. The candidate is stored for
    administrator review; listings are never merged automatically.
    """
    if not listing.manufacturer or not listing.model:
        return None
    candidates = db.scalars(
        select(Listing)
        .where(
            Listing.id != listing.id,
            Listing.source_id != listing.source_id,
            Listing.manufacturer == listing.manufacturer,
            Listing.first_discovered_at >= datetime.now(timezone.utc) - timedelta(days=180),
        )
        .limit(200)
    ).all()

    best: tuple[float, Listing, list[str]] | None = None
    for other in candidates:
        if _normalised_model(other.model) != _normalised_model(listing.model):
            continue
        score = 0.0
        reasons: list[str] = []
        if other.year and listing.year:
            if other.year == listing.year:
                score += 0.25
                reasons.append("Same production year")
            elif abs(other.year - listing.year) == 1:
                score += 0.1
                reasons.append("Production year differs by one")
            else:
                continue
        if other.mileage_km is not None and listing.mileage_km is not None:
            diff = abs(other.mileage_km - listing.mileage_km)
            if diff <= max(2000, listing.mileage_km * 0.02):
                score += 0.3
                reasons.append("Mileage within 2%")
            elif diff <= listing.mileage_km * 0.1:
                score += 0.15
                reasons.append("Mileage within 10%")
        if other.price_eur is not None and listing.price_eur is not None:
            a, b = float(other.price_eur), float(listing.price_eur)
            if a > 0 and b > 0:
                diff_pct = abs(a - b) / max(a, b)
                if diff_pct <= 0.1:
                    score += 0.3
                    reasons.append("Asking price within 10%")
                elif diff_pct <= 0.25:
                    score += 0.12
                    reasons.append("Asking price within 25%")
        if other.primary_image_url and other.primary_image_url == listing.primary_image_url:
            score += 0.35
            reasons.append("Identical primary photo")
        if other.country and listing.country and other.country == listing.country:
            score += 0.05
            reasons.append("Same country")

        if score >= min_score and (best is None or score > best[0]):
            best = (score, other, reasons)

    if best is None:
        return None
    score, other, reasons = best
    existing = db.scalar(
        select(DuplicateCandidate).where(
            ((DuplicateCandidate.listing_a_id == listing.id) & (DuplicateCandidate.listing_b_id == other.id))
            | ((DuplicateCandidate.listing_a_id == other.id) & (DuplicateCandidate.listing_b_id == listing.id))
        )
    )
    if existing is not None:
        return existing
    candidate = DuplicateCandidate(
        listing_a_id=listing.id,
        listing_b_id=other.id,
        score=round(score, 2),
        reasons=reasons,
        status="open",
    )
    db.add(candidate)
    return candidate


def listing_quality(listing: Listing) -> dict[str, Any]:
    return {
        "completeness_pct": listing.completeness_pct,
        "missing_fields": listing.missing_fields or [],
        "validation_warnings": listing.validation_warnings or [],
        "risk_score": listing.risk_score,
        "risk_reasons": listing.risk_reasons or [],
    }

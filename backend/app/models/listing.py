"""Collected external truck listings, images, price history and data quality."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, uuid_pk

LISTING_STATUSES = ("active", "inactive", "unreachable", "removed", "unknown")
EXTRACTION_STATUSES = ("complete", "partial", "failed")


class Listing(Base, TimestampMixin):
    __tablename__ = "listings"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_listings_source_external"),
        Index("ix_listings_manufacturer_model", "manufacturer", "model"),
        Index("ix_listings_price", "price"),
        Index("ix_listings_year", "year"),
        Index("ix_listings_status_discovered", "listing_status", "first_discovered_at"),
    )

    id: Mapped[str] = uuid_pk()
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("website_sources.id", ondelete="CASCADE"), index=True
    )
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    source_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    original_url: Mapped[str] = mapped_column(String(700), index=True, nullable=False)

    manufacturer: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    model: Mapped[str | None] = mapped_column(String(160), index=True, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    price_eur: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    mileage_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    power_hp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    axle_config: Mapped[str | None] = mapped_column(String(20), nullable=True)
    axles_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    euro_class: Mapped[str | None] = mapped_column(String(12), nullable=True)
    transmission: Mapped[str | None] = mapped_column(String(40), nullable=True)
    fuel_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    cab_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    condition: Mapped[str | None] = mapped_column(String(40), nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), index=True, nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    primary_image_url: Mapped[str | None] = mapped_column(String(700), nullable=True)
    image_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    listing_status: Mapped[str] = mapped_column(
        String(20), default="active", index=True, nullable=False
    )
    extraction_status: Mapped[str] = mapped_column(String(20), default="partial", nullable=False)
    completeness_pct: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    missing_fields: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    validation_warnings: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    risk_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    risk_reasons: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    risk_reviewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    fingerprint: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    first_discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_price_change_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    unavailable_since: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    source: Mapped["WebsiteSource"] = relationship(back_populates="listings")  # noqa: F821
    images: Mapped[list["ListingImage"]] = relationship(
        back_populates="listing", cascade="all, delete-orphan", lazy="selectin"
    )
    price_history: Mapped[list["PriceHistory"]] = relationship(
        back_populates="listing", cascade="all, delete-orphan"
    )


class ListingImage(Base):
    __tablename__ = "listing_images"

    id: Mapped[str] = uuid_pk()
    listing_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("listings.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(String(700), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    listing: Mapped[Listing] = relationship(back_populates="images")


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (Index("ix_price_history_listing_time", "listing_id", "recorded_at"),)

    id: Mapped[str] = uuid_pk()
    listing_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("listings.id", ondelete="CASCADE"), index=True
    )
    price: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    price_eur: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(40), default="collection", nullable=False)

    listing: Mapped[Listing] = relationship(back_populates="price_history")


class SavedListing(Base, TimestampMixin):
    __tablename__ = "saved_listings"
    __table_args__ = (
        UniqueConstraint("user_id", "listing_id", "kind", name="uq_saved_listings_user_listing"),
    )

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    listing_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("listings.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20), default="saved", nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)


class DuplicateCandidate(Base, TimestampMixin):
    __tablename__ = "duplicate_candidates"
    __table_args__ = (
        UniqueConstraint("listing_a_id", "listing_b_id", name="uq_duplicate_candidates_pair"),
    )

    id: Mapped[str] = uuid_pk()
    listing_a_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("listings.id", ondelete="CASCADE"), index=True
    )
    listing_b_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("listings.id", ondelete="CASCADE"), index=True
    )
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    reasons: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True, nullable=False)


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

    id: Mapped[str] = uuid_pk()
    listing_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("listings.id", ondelete="CASCADE"), index=True
    )
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reasons: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

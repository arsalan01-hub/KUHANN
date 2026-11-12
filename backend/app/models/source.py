"""Website sources and website-discovery records."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, uuid_pk

# Discovery / approval lifecycle. A discovered website is never searched until an
# administrator approves it and a permitted access method is confirmed.
SOURCE_STATUSES = (
    "newly_discovered",
    "under_investigation",
    "needs_review",
    "approved",
    "active",
    "manual_access_only",
    "restricted",
    "unsupported",
    "temporarily_unavailable",
    "disabled",
    "rejected",
)

ACCESS_METHODS = ("api", "feed", "html", "manual")


class WebsiteSource(Base, TimestampMixin):
    __tablename__ = "website_sources"

    id: Mapped[str] = uuid_pk()
    domain: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    homepage_url: Mapped[str] = mapped_column(String(500), nullable=False)
    listing_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    category: Mapped[str] = mapped_column(String(60), default="marketplace", nullable=False)

    status: Mapped[str] = mapped_column(
        String(40), default="newly_discovered", index=True, nullable=False
    )
    access_method: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    connector_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    connector_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Evidence gathered by the inspector; nothing here is assumed.
    robots_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    robots_allows_crawl: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    robots_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    terms_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    api_doc_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    has_official_api: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    truck_evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    compatibility: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    analysis_report: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    discovery_provider: Mapped[str] = mapped_column(String(60), default="manual", nullable=False)
    discovery_query: Mapped[str | None] = mapped_column(String(300), nullable=True)
    discovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    review_note: Mapped[str] = mapped_column(Text, default="", nullable=False)

    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_collected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_run_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    listings_collected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    average_response_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    listings: Mapped[list["Listing"]] = relationship(  # noqa: F821
        back_populates="source", cascade="all, delete-orphan"
    )


class DiscoveryRun(Base, TimestampMixin):
    __tablename__ = "discovery_runs"

    id: Mapped[str] = uuid_pk()
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    query: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="running", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    results_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sources_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicates_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    provider_configured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    triggered_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class DiscoveryHit(Base, TimestampMixin):
    """Raw candidate returned by a discovery provider, before promotion."""

    __tablename__ = "discovery_hits"

    id: Mapped[str] = uuid_pk()
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("discovery_runs.id", ondelete="CASCADE"), index=True
    )
    domain: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    snippet: Mapped[str] = mapped_column(Text, default="", nullable=False)
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    already_known: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    run: Mapped[DiscoveryRun] = relationship()

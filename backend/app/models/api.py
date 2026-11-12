"""Configurable API integrations, field mappings and synchronisation logs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, uuid_pk

AUTH_TYPES = ("none", "api_key", "bearer", "basic", "oauth2_client_credentials", "custom_headers")
HTTP_METHODS = ("GET", "POST", "PUT", "PATCH")
PAGINATION_TYPES = ("none", "page", "offset", "cursor")
API_STATUSES = ("draft", "active", "disabled")

# Fields a mapped external record may populate. Anything else is rejected, which
# keeps the mapping layer declarative and free of arbitrary code execution.
KUHHAAN_FIELDS = (
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
    "image_urls",
    "original_url",
    "listed_at",
)

TRANSFORMS = ("none", "strip", "int", "float", "upper", "lower", "date", "bool", "title")


class ApiIntegration(Base, TimestampMixin):
    __tablename__ = "api_integrations"

    id: Mapped[str] = uuid_pk()
    name: Mapped[str] = mapped_column(String(160), unique=True, index=True, nullable=False)
    provider_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    purpose: Mapped[str] = mapped_column(String(40), default="listings", nullable=False)

    website_source_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("website_sources.id", ondelete="SET NULL"), nullable=True
    )

    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    endpoint_path: Mapped[str] = mapped_column(String(500), default="/", nullable=False)
    api_version: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    http_method: Mapped[str] = mapped_column(String(10), default="GET", nullable=False)
    auth_type: Mapped[str] = mapped_column(String(40), default="none", nullable=False)
    header_name: Mapped[str] = mapped_column(String(80), default="X-API-Key", nullable=False)
    custom_headers: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    query_params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    body_template: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    # Fernet ciphertext of the credential bag. Never serialised to clients.
    credentials_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    pagination_type: Mapped[str] = mapped_column(String(20), default="page", nullable=False)
    page_parameter: Mapped[str] = mapped_column(String(60), default="page", nullable=False)
    page_size_parameter: Mapped[str] = mapped_column(String(60), default="limit", nullable=False)
    page_size: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    max_pages: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    records_path: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    response_format: Mapped[str] = mapped_column(String(20), default="json", nullable=False)

    status: Mapped[str] = mapped_column(String(20), default="draft", index=True, nullable=False)
    doc_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_test_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_response_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_response_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    requests_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_synced: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    mappings: Mapped[list["ApiFieldMapping"]] = relationship(
        back_populates="api", cascade="all, delete-orphan", lazy="selectin"
    )
    sync_logs: Mapped[list["ApiSyncLog"]] = relationship(
        back_populates="api", cascade="all, delete-orphan"
    )


class ApiFieldMapping(Base):
    __tablename__ = "api_field_mappings"
    __table_args__ = (
        UniqueConstraint("api_id", "external_field", name="uq_api_field_mappings_api_id"),
    )

    id: Mapped[str] = uuid_pk()
    api_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("api_integrations.id", ondelete="CASCADE"), index=True
    )
    external_field: Mapped[str] = mapped_column(String(200), nullable=False)
    kuhhan_field: Mapped[str] = mapped_column(String(60), nullable=False)
    transform: Mapped[str] = mapped_column(String(20), default="none", nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_value: Mapped[str | None] = mapped_column(String(200), nullable=True)

    api: Mapped[ApiIntegration] = relationship(back_populates="mappings")


class ApiSyncLog(Base, TimestampMixin):
    __tablename__ = "api_sync_logs"

    id: Mapped[str] = uuid_pk()
    api_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("api_integrations.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    records_fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    request_url: Mapped[str | None] = mapped_column(String(700), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    api: Mapped[ApiIntegration] = relationship(back_populates="sync_logs")

"""Notifications, background jobs, audit trail, settings and backups."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, uuid_pk

JOB_STATUSES = ("running", "success", "failed", "skipped")


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    level: Mapped[str] = mapped_column(String(20), default="info", nullable=False)
    category: Mapped[str] = mapped_column(String(40), default="system", index=True, nullable=False)
    link: Mapped[str | None] = mapped_column(String(300), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class JobSchedule(Base, TimestampMixin):
    __tablename__ = "job_schedules"

    id: Mapped[str] = uuid_pk()
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    job_type: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, default=3600, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, nullable=True
    )


class JobRun(Base, TimestampMixin):
    __tablename__ = "job_runs"

    id: Mapped[str] = uuid_pk()
    job_type: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    schedule_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("job_schedules.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="running", index=True, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    triggered_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    trigger: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    user_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    outcome: Mapped[str] = mapped_column(String(20), default="success", nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    description: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


class Backup(Base):
    __tablename__ = "backups"

    id: Mapped[str] = uuid_pk()
    filename: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    method: Mapped[str] = mapped_column(String(20), default="pg_dump", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="completed", nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    table_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

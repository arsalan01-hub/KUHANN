"""Saved searches and search history."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, uuid_pk

SEARCH_MODES = ("all_active", "selected_sources", "single_source", "url")


class SavedSearch(Base, TimestampMixin):
    __tablename__ = "saved_searches"

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    mode: Mapped[str] = mapped_column(String(30), default="all_active", nullable=False)
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    source_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    schedule: Mapped[str] = mapped_column(String(20), default="daily", nullable=False)
    notify: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_match_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_matches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class SearchHistory(Base, TimestampMixin):
    __tablename__ = "search_history"

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    mode: Mapped[str] = mapped_column(String(30), default="all_active", nullable=False)
    query_text: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    source_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    result_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

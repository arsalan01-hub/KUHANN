"""Background job registry and scheduler tick.

Jobs are plain functions that receive a SQLAlchemy session and their schedule
configuration. The worker process (``python -m app.worker``) drives them, so
monitoring and collection continue while no browser is open.
"""

from __future__ import annotations

import traceback
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.listing import Listing, PriceHistory
from app.models.search import SavedSearch, SearchHistory
from app.models.source import WebsiteSource
from app.models.system import JobRun, JobSchedule, SystemSetting
from app.services import backup_service, collector, discovery, notifications, risk
from app.services.collector import COLLECTABLE_STATUSES
from app.services.http import OutboundError
from app.services.settings_service import get_setting

DEFAULT_DISCOVERY_QUERIES = (
    "used trucks for sale europe marketplace",
    "truck dealer lithuania used trucks",
    "used lorry sales poland",
    "second hand trucks netherlands dealer",
)


# --------------------------------------------------------------------- handlers
def _job_discover_websites(db: Session, config: dict[str, Any], job: JobRun) -> dict[str, Any]:
    provider_key = config.get("provider") or (
        "search_api" if discovery.PROVIDERS["search_api"].is_configured(db)[0] else "curated_directory"
    )
    queries = config.get("queries") or list(DEFAULT_DISCOVERY_QUERIES)
    limit = int(config.get("limit") or 15)
    created = 0
    runs: list[dict[str, Any]] = []
    for query in queries:
        run = discovery.run_discovery(
            db, provider_key=provider_key, query=str(query), limit=limit, user_id=None
        )
        created += run.sources_created
        runs.append(
            {
                "query": query,
                "status": run.status,
                "found": run.results_found,
                "created": run.sources_created,
                "message": run.message,
            }
        )
    if created:
        notifications.notify_permission_holders(
            db,
            "sources:write",
            title=f"{created} new website(s) discovered",
            body="Review the new sources in Website Discovery before approving collection.",
            level="info",
            category="discovery",
            link="/discovery",
        )
    return {
        "message": f"{created} new source(s) discovered across {len(queries)} queries",
        "provider": provider_key,
        "runs": runs,
    }


def _job_collect_source(db: Session, config: dict[str, Any], job: JobRun) -> dict[str, Any]:
    source_id = config.get("source_id")
    if not source_id:
        raise ValueError("collect_source requires a source_id")
    source = db.get(WebsiteSource, source_id)
    if source is None:
        raise ValueError("Website source not found")
    summary = collector.collect_source(db, source)
    return {"message": f"Collected {source.domain}", "summary": summary}


def _job_collect_all(db: Session, config: dict[str, Any], job: JobRun) -> dict[str, Any]:
    sources = db.scalars(
        select(WebsiteSource).where(WebsiteSource.status.in_(COLLECTABLE_STATUSES))
    ).all()
    results = []
    failures = 0
    for source in sources:
        if not (source.connector_key or source.access_method in ("api", "feed", "html")):
            continue
        try:
            results.append(collector.collect_source(db, source))
        except (collector.ConnectorError, OutboundError) as exc:
            failures += 1
            results.append({"source_id": source.id, "domain": source.domain, "error": str(exc)})
    created = sum(item.get("created", 0) for item in results if isinstance(item, dict))
    return {
        "message": f"{len(results)} source(s) attempted, {created} new listing(s), {failures} failure(s)",
        "results": results,
    }


def _job_run_saved_searches(db: Session, config: dict[str, Any], job: JobRun) -> dict[str, Any]:
    searches = db.scalars(
        select(SavedSearch).where(SavedSearch.is_active.is_(True))
    ).all()
    results = [notifications.run_saved_search(db, saved) for saved in searches]
    matches = sum(item["matches"] for item in results)
    return {
        "message": f"{len(results)} saved search(es) evaluated, {matches} match(es)",
        "results": results,
    }


def _job_refresh_risk(db: Session, config: dict[str, Any], job: JobRun) -> dict[str, Any]:
    limit = int(config.get("limit") or 500)
    listings = db.scalars(
        select(Listing)
        .where(Listing.first_discovered_at >= datetime.now(timezone.utc) - timedelta(days=60))
        .order_by(Listing.first_discovered_at.desc())
        .limit(limit)
    ).all()
    flagged = 0
    threshold = int(get_setting(db, "risk.flag_threshold", 45) or 45)
    for listing in listings:
        risk.apply_risk(db, listing)
        if listing.risk_score >= threshold:
            flagged += 1
    return {"message": f"{len(listings)} listing(s) re-scored, {flagged} flagged", "flagged": flagged}


def _job_database_backup(db: Session, config: dict[str, Any], job: JobRun) -> dict[str, Any]:
    record = backup_service.create_backup(db)
    if record.status == "failed":
        raise backup_service.BackupError(record.message)
    return {
        "message": f"Backup {record.filename} ({record.method}) verified",
        "backup_id": record.id,
        "size_bytes": record.size_bytes,
    }


def _job_retention_cleanup(db: Session, config: dict[str, Any], job: JobRun) -> dict[str, Any]:
    removed_backups = backup_service.prune_backups(db)
    history_cutoff = datetime.now(timezone.utc) - timedelta(days=180)
    old_history = db.scalar(
        select(func.count(SearchHistory.id)).where(SearchHistory.created_at < history_cutoff)
    ) or 0
    db.query(SearchHistory).filter(SearchHistory.created_at < history_cutoff).delete(
        synchronize_session=False
    )
    job_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    db.query(JobRun).filter(JobRun.started_at < job_cutoff).delete(synchronize_session=False)
    keep_ids = db.scalars(
        select(PriceHistory.id)
        .where(PriceHistory.recorded_at < datetime.now(timezone.utc) - timedelta(days=365 * 3))
        .limit(1000)
    ).all()
    if keep_ids:
        db.query(PriceHistory).filter(PriceHistory.id.in_(keep_ids)).delete(synchronize_session=False)
    db.commit()
    return {
        "message": f"{removed_backups} backup(s) pruned, {old_history} search history row(s) removed",
        "removed_backups": removed_backups,
        "removed_history": int(old_history),
    }


def _job_purge_settings_cache(db: Session, config: dict[str, Any], job: JobRun) -> dict[str, Any]:
    db.query(SystemSetting).filter(SystemSetting.key == "runtime.cache").delete(
        synchronize_session=False
    )
    db.commit()
    return {"message": "Runtime cache cleared"}


JOB_TYPES: dict[str, dict[str, Any]] = {
    "discover_websites": {
        "label": "Discover new websites",
        "handler": _job_discover_websites,
        "description": "Searches configured discovery providers for new European truck websites.",
    },
    "collect_source": {
        "label": "Collect one source",
        "handler": _job_collect_source,
        "description": "Runs the connector for a single approved website.",
    },
    "collect_all": {
        "label": "Collect all approved sources",
        "handler": _job_collect_all,
        "description": "Refreshes listings from every approved and active website.",
    },
    "run_saved_searches": {
        "label": "Run saved searches",
        "handler": _job_run_saved_searches,
        "description": "Evaluates saved searches and raises notifications for new matches.",
    },
    "refresh_risk": {
        "label": "Refresh risk scores",
        "handler": _job_refresh_risk,
        "description": "Re-scores recently collected listings for price and data anomalies.",
    },
    "database_backup": {
        "label": "Database backup",
        "handler": _job_database_backup,
        "description": "Creates and verifies a database backup.",
    },
    "retention_cleanup": {
        "label": "Retention cleanup",
        "handler": _job_retention_cleanup,
        "description": "Prunes old backups, search history and job logs.",
    },
    "purge_cache": {
        "label": "Clear runtime cache",
        "handler": _job_purge_settings_cache,
        "description": "Clears cached runtime values.",
    },
}


def job_catalogue() -> list[dict[str, Any]]:
    return [
        {"job_type": key, "label": meta["label"], "description": meta["description"]}
        for key, meta in JOB_TYPES.items()
    ]


def run_job(
    db: Session,
    job_type: str,
    *,
    config: dict[str, Any] | None = None,
    user_id: str | None = None,
    trigger: str = "manual",
    schedule_id: str | None = None,
) -> JobRun:
    meta = JOB_TYPES.get(job_type)
    run = JobRun(
        job_type=job_type,
        schedule_id=schedule_id,
        status="running",
        started_at=datetime.now(timezone.utc),
        triggered_by=user_id,
        trigger=trigger,
        detail={},
        message="",
    )
    db.add(run)
    db.flush()
    if meta is None:
        run.status = "failed"
        run.message = f"Unknown job type '{job_type}'"
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        return run

    try:
        result = meta["handler"](db, config or {}, run)
        run.status = "success"
        run.message = str(result.get("message", ""))[:1000]
        run.detail = result
    except Exception as exc:  # noqa: BLE001 - jobs must never crash the worker
        db.rollback()
        run.status = "failed"
        run.message = f"{exc.__class__.__name__}: {exc}"[:1000]
        run.detail = {"traceback": traceback.format_exc()[-4000:]}
    finally:
        run.finished_at = datetime.now(timezone.utc)
        if run.started_at:
            started = run.started_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            run.duration_ms = int((run.finished_at - started).total_seconds() * 1000)
        db.commit()
    return run


def due_schedules(db: Session, *, now: datetime | None = None) -> list[JobSchedule]:
    now = now or datetime.now(timezone.utc)
    return list(
        db.scalars(
            select(JobSchedule)
            .where(
                JobSchedule.enabled.is_(True),
                (JobSchedule.next_run_at.is_(None)) | (JobSchedule.next_run_at <= now),
            )
            .order_by(JobSchedule.next_run_at.asc().nulls_first())
        ).all()
    )


def tick(db: Session, *, now: datetime | None = None, limit: int = 5) -> list[JobRun]:
    now = now or datetime.now(timezone.utc)
    executed: list[JobRun] = []
    for schedule in due_schedules(db, now=now)[:limit]:
        run = run_job(
            db,
            schedule.job_type,
            config=dict(schedule.config or {}),
            trigger="schedule",
            schedule_id=schedule.id,
        )
        schedule.last_run_at = now
        schedule.last_status = run.status
        schedule.last_message = run.message
        schedule.next_run_at = now + timedelta(seconds=max(30, schedule.interval_seconds))
        db.commit()
        executed.append(run)
    return executed


def ensure_default_schedules(db: Session) -> None:
    now = datetime.now(timezone.utc)
    defaults = [
        ("Discovery: daily website search", "discover_websites", 86400, {"limit": 15}),
        ("Collection: hourly refresh", "collect_all", 3600, {}),
        ("Monitoring: saved searches", "run_saved_searches", 3600, {}),
        ("Quality: risk re-scoring", "refresh_risk", 86400, {"limit": 500}),
        ("Operations: nightly backup", "database_backup", 86400, {}),
        ("Operations: weekly cleanup", "retention_cleanup", 604800, {}),
    ]
    for name, job_type, interval, config in defaults:
        existing = db.scalar(select(JobSchedule).where(JobSchedule.name == name))
        if existing is None:
            db.add(
                JobSchedule(
                    name=name,
                    job_type=job_type,
                    interval_seconds=interval,
                    enabled=True,
                    config=config,
                    next_run_at=now + timedelta(seconds=interval),
                )
            )
    db.flush()

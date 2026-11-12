"""Dashboard, notifications, audit, jobs, health, settings, backups and prices."""

from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.deps import Pagination, client_ip, require_permission
from app.api.filters import bools, filters_from_query
from app.api.serializers import (
    audit_dict,
    backup_dict,
    job_run_dict,
    job_schedule_dict,
    notification_dict,
)
from app.core.audit import record_audit
from app.core.config import settings as app_settings
from app.db.session import get_db
from app.models.api import ApiIntegration
from app.models.source import WebsiteSource
from app.models.system import AuditLog, Backup, JobRun, JobSchedule, Notification, SystemSetting
from app.models.user import User
from app.services import backup_service, dashboard_service, jobs, price_service
from app.services.settings_service import (
    DEFAULTS,
    SETTING_DESCRIPTIONS,
    get_setting,
    set_setting,
)

router = APIRouter(tags=["System"])


@router.get("/dashboard")
def dashboard(
    user: User = Depends(require_permission("dashboard:read")), db: Session = Depends(get_db)
) -> dict:
    payload = dashboard_service.overview(db, user_id=user.id)
    payload["recent"]["price_changes"] = [
        {
            "id": item.id,
            "title": f"{item.manufacturer or ''} {item.model or ''}".strip() or "Listing",
            "price": float(item.price) if item.price is not None else None,
            "currency": item.currency,
            "price_eur": float(item.price_eur) if item.price_eur is not None else None,
            "changed_at": item.last_price_change_at,
            "source_name": item.source_name,
        }
        for item in payload["recent"]["price_changes"]
    ]
    payload["recent"]["searches"] = [
        {
            "id": item.id,
            "query_text": item.query_text,
            "mode": item.mode,
            "result_count": item.result_count,
            "created_at": item.created_at,
            "duration_ms": item.duration_ms,
        }
        for item in payload["recent"]["searches"]
    ]
    payload["recent"]["notifications"] = [
        notification_dict(item) for item in payload["recent"]["notifications"]
    ]
    payload["recent"]["jobs"] = [job_run_dict(item) for item in payload["recent"]["jobs"]]
    unread = db.scalar(
        select(func.count(Notification.id)).where(
            Notification.read_at.is_(None),
            (Notification.user_id == user.id) | (Notification.user_id.is_(None)),
        )
    ) or 0
    payload["unread_notifications"] = int(unread)
    return payload


# ----------------------------------------------------------------- notifications
@router.get("/notifications")
def list_notifications(
    unread_only: bool = False,
    pagination: Pagination = Depends(),
    user: User = Depends(require_permission("notifications:read")),
    db: Session = Depends(get_db),
) -> dict:
    conditions = [(Notification.user_id == user.id) | (Notification.user_id.is_(None))]
    if unread_only:
        conditions.append(Notification.read_at.is_(None))
    total = db.scalar(select(func.count(Notification.id)).where(*conditions)) or 0
    items = db.scalars(
        select(Notification)
        .where(*conditions)
        .order_by(Notification.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    ).all()
    return {
        "items": [notification_dict(i) for i in items],
        "total": int(total),
        "page": pagination.page,
        "page_size": pagination.page_size,
        "pages": (int(total) + pagination.page_size - 1) // pagination.page_size,
    }


@router.post("/notifications/{notification_id}/read")
def mark_read(
    notification_id: str,
    user: User = Depends(require_permission("notifications:read")),
    db: Session = Depends(get_db),
) -> dict:
    entry = db.get(Notification, notification_id)
    if entry is None or (entry.user_id not in (None, user.id)):
        raise HTTPException(status_code=404, detail="Notification not found")
    entry.read_at = datetime.now(timezone.utc)
    db.commit()
    return {"message": "Marked as read"}


@router.post("/notifications/read-all")
def mark_all_read(
    user: User = Depends(require_permission("notifications:read")),
    db: Session = Depends(get_db),
) -> dict:
    now = datetime.now(timezone.utc)
    updated = db.query(Notification).filter(
        Notification.read_at.is_(None),
        ((Notification.user_id == user.id) | (Notification.user_id.is_(None))),
    ).update({Notification.read_at: now}, synchronize_session=False)
    db.commit()
    return {"message": f"{updated} notification(s) marked as read"}


# ------------------------------------------------------------------------ audit
@router.get("/audit")
def list_audit(
    action: str | None = None,
    entity_type: str | None = None,
    outcome: str | None = None,
    pagination: Pagination = Depends(),
    _: User = Depends(require_permission("audit:read")),
    db: Session = Depends(get_db),
) -> dict:
    conditions = []
    if action:
        conditions.append(AuditLog.action.ilike(f"%{action}%"))
    if entity_type:
        conditions.append(AuditLog.entity_type == entity_type)
    if outcome:
        conditions.append(AuditLog.outcome == outcome)
    total = db.scalar(select(func.count(AuditLog.id)).where(*conditions)) or 0
    items = db.scalars(
        select(AuditLog)
        .where(*conditions)
        .order_by(desc(AuditLog.created_at))
        .offset(pagination.offset)
        .limit(pagination.page_size)
    ).all()
    return {
        "items": [audit_dict(i) for i in items],
        "total": int(total),
        "page": pagination.page,
        "page_size": pagination.page_size,
        "pages": (int(total) + pagination.page_size - 1) // pagination.page_size,
    }


# ------------------------------------------------------------------------- jobs
@router.get("/jobs/types")
def job_types(_: User = Depends(require_permission("jobs:read"))) -> dict:
    return {"items": jobs.job_catalogue()}


@router.get("/jobs/runs")
def job_runs(
    status_filter: str | None = None,
    job_type: str | None = None,
    pagination: Pagination = Depends(),
    _: User = Depends(require_permission("jobs:read")),
    db: Session = Depends(get_db),
) -> dict:
    conditions = []
    if status_filter:
        conditions.append(JobRun.status == status_filter)
    if job_type:
        conditions.append(JobRun.job_type == job_type)
    total = db.scalar(select(func.count(JobRun.id)).where(*conditions)) or 0
    items = db.scalars(
        select(JobRun)
        .where(*conditions)
        .order_by(JobRun.started_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    ).all()
    return {
        "items": [job_run_dict(i) for i in items],
        "total": int(total),
        "page": pagination.page,
        "page_size": pagination.page_size,
        "pages": (int(total) + pagination.page_size - 1) // pagination.page_size,
    }


@router.post("/jobs/run")
def trigger_job(
    payload: dict,
    request: Request,
    user: User = Depends(require_permission("jobs:run")),
    db: Session = Depends(get_db),
) -> dict:
    job_type = str(payload.get("job_type") or "")
    if job_type not in jobs.JOB_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown job type '{job_type}'")
    run = jobs.run_job(db, job_type, config=payload.get("config") or {}, user_id=user.id)
    record_audit(
        db,
        action="job.run",
        entity_type="job_run",
        entity_id=run.id,
        user=user,
        ip_address=client_ip(request),
        outcome="success" if run.status == "success" else "failure",
        detail={"job_type": job_type, "status": run.status},
    )
    db.commit()
    return job_run_dict(run)


@router.get("/jobs/schedules")
def list_schedules(
    _: User = Depends(require_permission("jobs:read")), db: Session = Depends(get_db)
) -> dict:
    schedules = db.scalars(select(JobSchedule).order_by(JobSchedule.name)).all()
    return {"items": [job_schedule_dict(s) for s in schedules]}


@router.patch("/jobs/schedules/{schedule_id}")
def update_schedule(
    schedule_id: str,
    payload: dict,
    request: Request,
    user: User = Depends(require_permission("jobs:run")),
    db: Session = Depends(get_db),
) -> dict:
    schedule = db.get(JobSchedule, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if payload.get("enabled") is not None:
        schedule.enabled = bool(payload["enabled"])
    if payload.get("interval_seconds") is not None:
        try:
            interval = int(payload["interval_seconds"])
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="Interval must be a number") from exc
        if interval < 60:
            raise HTTPException(status_code=422, detail="Minimum interval is 60 seconds")
        schedule.interval_seconds = interval
        schedule.next_run_at = datetime.now(timezone.utc) + timedelta(seconds=interval)
    if payload.get("config") is not None:
        if not isinstance(payload["config"], dict):
            raise HTTPException(status_code=422, detail="Config must be an object")
        schedule.config = payload["config"]
    record_audit(
        db, action="job.schedule.update", entity_type="job_schedule", entity_id=schedule.id,
        user=user, ip_address=client_ip(request), detail=payload,
    )
    db.commit()
    return job_schedule_dict(schedule)


# ------------------------------------------------------------------------ health
@router.get("/system/health")
def system_health(
    _: User = Depends(require_permission("health:read")), db: Session = Depends(get_db)
) -> dict:
    now = datetime.now(timezone.utc)
    database: dict = {"ok": False}
    try:
        database = backup_service.database_health(db)
    except Exception as exc:  # noqa: BLE001
        database = {"ok": False, "error": str(exc)}

    heartbeat = None
    row = db.get(SystemSetting, "runtime.worker_heartbeat")
    if row is not None and isinstance(row.value, dict):
        heartbeat = row.value
    worker_ok = False
    if heartbeat and heartbeat.get("last_tick"):
        try:
            last = datetime.fromisoformat(str(heartbeat["last_tick"]))
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            worker_ok = (now - last).total_seconds() < max(120, app_settings.worker_poll_seconds * 4)
        except ValueError:
            worker_ok = False

    failing_sources = db.scalars(
        select(WebsiteSource).where(WebsiteSource.last_run_status == "failed").limit(20)
    ).all()
    failing_apis = db.scalars(
        select(ApiIntegration).where(ApiIntegration.last_test_status == "failed").limit(20)
    ).all()
    stuck_jobs = db.scalars(
        select(JobRun).where(JobRun.status == "running", JobRun.started_at < now - timedelta(hours=2))
    ).all()

    usage = shutil.disk_usage(str(Path(app_settings.backup_dir).anchor or "/"))
    backup_count = db.scalar(select(func.count(Backup.id))) or 0
    last_backup = db.scalar(select(Backup).order_by(Backup.created_at.desc()).limit(1))

    return {
        "status": "ok" if database.get("ok") and worker_ok else "degraded",
        "time": now,
        "database": database,
        "worker": {"ok": worker_ok, "heartbeat": heartbeat},
        "disk": {
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "free_percent": round(usage.free / usage.total * 100, 1) if usage.total else None,
        },
        "connectors": {
            "failing": [
                {"id": s.id, "domain": s.domain, "last_error": s.last_error,
                 "consecutive_failures": s.consecutive_failures}
                for s in failing_sources
            ]
        },
        "apis": {
            "failing": [
                {"id": a.id, "name": a.name, "last_error": a.last_error} for a in failing_apis
            ]
        },
        "jobs": {
            "stuck": [job_run_dict(j) for j in stuck_jobs],
            "last_runs": [
                job_run_dict(j)
                for j in db.scalars(select(JobRun).order_by(JobRun.started_at.desc()).limit(5)).all()
            ],
        },
        "backups": {
            "count": int(backup_count),
            "last": backup_dict(last_backup) if last_backup else None,
        },
        "version": "1.0.0",
    }


# ---------------------------------------------------------------------- settings
@router.get("/settings")
def list_settings(
    _: User = Depends(require_permission("settings:read")), db: Session = Depends(get_db)
) -> dict:
    rows = {row.key: row for row in db.scalars(select(SystemSetting)).all()}
    items = []
    for key, default in DEFAULTS.items():
        row = rows.get(key)
        value = row.value if row is not None else default
        if key == "discovery.search_api" and isinstance(value, dict):
            value = {k: v for k, v in value.items() if k != "api_key_encrypted"} | {
                "has_api_key": bool((row.value if row else default).get("api_key_encrypted"))
            }
        items.append(
            {
                "key": key,
                "value": value,
                "default": default if not isinstance(default, dict) else None,
                "description": SETTING_DESCRIPTIONS.get(key, ""),
                "updated_at": row.updated_at if row else None,
            }
        )
    return {
        "items": items,
        "environment": {
            "instance": app_settings.app_name,
            "environment": app_settings.environment,
            "preview_mode": app_settings.preview_mode,
            "login_rate_limit": app_settings.login_rate_limit,
            "token_ttl_minutes": app_settings.access_token_ttl_minutes,
            "outbound_timeout_seconds": app_settings.outbound_timeout_seconds,
            "allow_private_outbound": app_settings.allow_private_outbound,
            "backup_dir": app_settings.backup_dir,
        },
    }


@router.put("/settings/{key}")
def update_setting(
    key: str,
    payload: dict,
    request: Request,
    user: User = Depends(require_permission("settings:write")),
    db: Session = Depends(get_db),
) -> dict:
    if key not in DEFAULTS:
        raise HTTPException(status_code=404, detail="Unknown setting")
    if "value" not in payload:
        raise HTTPException(status_code=422, detail="Provide a value")
    value = payload["value"]
    default = DEFAULTS[key]
    if isinstance(default, int) and not isinstance(default, bool):
        try:
            value = int(value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="This setting must be a number") from exc
    if isinstance(default, dict) and not isinstance(value, dict):
        raise HTTPException(status_code=422, detail="This setting must be an object")
    if key == "discovery.search_api" and isinstance(value, dict):
        existing = dict(get_setting(db, "discovery.search_api", {}) or {})
        existing.update({k: v for k, v in value.items() if k != "api_key_encrypted"})
        value = existing
    set_setting(db, key, value, user_id=user.id)
    record_audit(
        db, action="setting.update", entity_type="system_setting", entity_id=key, user=user,
        ip_address=client_ip(request), detail={"key": key},
    )
    db.commit()
    return {"key": key, "value": value}


# ----------------------------------------------------------------------- backups
@router.get("/backups")
def list_backups(
    pagination: Pagination = Depends(),
    _: User = Depends(require_permission("backups:read")),
    db: Session = Depends(get_db),
) -> dict:
    total = db.scalar(select(func.count(Backup.id))) or 0
    items = db.scalars(
        select(Backup).order_by(Backup.created_at.desc())
        .offset(pagination.offset).limit(pagination.page_size)
    ).all()
    return {
        "items": [backup_dict(i) for i in items],
        "total": int(total),
        "page": pagination.page,
        "page_size": pagination.page_size,
        "pages": (int(total) + pagination.page_size - 1) // pagination.page_size,
        "directory": str(backup_service.backup_directory(db)),
        "recovery_steps": backup_service.RECOVERY_STEPS,
    }


@router.post("/backups", status_code=201)
def create_backup(
    request: Request,
    user: User = Depends(require_permission("backups:write")),
    db: Session = Depends(get_db),
) -> dict:
    record = backup_service.create_backup(db, user_id=user.id)
    record_audit(
        db,
        action="backup.create",
        entity_type="backup",
        entity_id=record.id,
        user=user,
        ip_address=client_ip(request),
        outcome="success" if record.status != "failed" else "failure",
        detail={"filename": record.filename, "status": record.status},
    )
    db.commit()
    if record.status == "failed":
        raise HTTPException(status_code=500, detail=record.message)
    return backup_dict(record)


@router.post("/backups/{backup_id}/verify")
def verify_backup(
    backup_id: str,
    request: Request,
    user: User = Depends(require_permission("backups:read")),
    db: Session = Depends(get_db),
) -> dict:
    record = db.get(Backup, backup_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Backup not found")
    path = backup_service.backup_directory(db) / record.filename
    try:
        result = backup_service.verify_backup(path)
    except backup_service.BackupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record.verified_at = datetime.now(timezone.utc)
    record.status = "verified" if result["ok"] else "failed"
    record_audit(
        db, action="backup.verify", entity_type="backup", entity_id=record.id, user=user,
        ip_address=client_ip(request), detail=result,
    )
    db.commit()
    return {**backup_dict(record), "verification": result}


@router.post("/backups/prune")
def prune_backups(
    request: Request,
    user: User = Depends(require_permission("backups:write")),
    db: Session = Depends(get_db),
) -> dict:
    removed = backup_service.prune_backups(db)
    record_audit(
        db, action="backup.prune", entity_type="backup", user=user,
        ip_address=client_ip(request), detail={"removed": removed},
    )
    db.commit()
    return {"message": f"{removed} backup(s) removed"}


# ----------------------------------------------------------------------- prices
@router.get("/price/summary")
def price_summary(
    request: Request,
    _: User = Depends(require_permission("price:read")),
    db: Session = Depends(get_db),
) -> dict:
    filters = bools(filters_from_query(request))
    payload = price_service.summary(db, filters)
    payload["by_dimension"] = {
        key: price_service.by_dimension(db, key, filters=filters, limit=8)
        for key in ("manufacturer", "country", "year")
    }
    return payload


@router.get("/price/by/{dimension}")
def price_by_dimension(
    dimension: str,
    request: Request,
    _: User = Depends(require_permission("price:read")),
    db: Session = Depends(get_db),
) -> dict:
    filters = bools(filters_from_query(request))
    try:
        items = price_service.by_dimension(db, dimension, filters=filters)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"dimension": dimension, "items": items, "disclaimer": price_service.DISCLAIMER}


@router.get("/price/history")
def price_history(
    days: int = 90,
    request: Request = None,
    _: User = Depends(require_permission("price:read")),
    db: Session = Depends(get_db),
) -> dict:
    filters = bools(filters_from_query(request)) if request else {}
    return price_service.history(db, days=days, filters=filters)


@router.get("/settings/options")
def settings_options(_: User = Depends(require_permission("settings:read"))) -> dict:
    return {
        "currencies": list(DEFAULTS["currency.rates_to_eur"].keys()),
        "sorts": ["newest", "oldest", "price_asc", "price_desc", "mileage_asc", "mileage_desc"],
        "source_statuses": [
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
        ],
    }

"""Backup and recovery service.

Primary method is ``pg_dump`` when the client binary is installed (production).
When it is unavailable — for example in the slim development image — KUHHAN
writes a full logical JSON dump instead, which it verifies by reading back.
Both methods are checksummed and recorded; a backup is never overwritten.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import Base
from app.models.system import Backup
from app.services.settings_service import get_setting


class BackupError(Exception):
    pass


def backup_directory(db: Session | None = None) -> Path:
    configured = ""
    if db is not None:
        configured = str(get_setting(db, "backup.directory", "") or "")
    directory = Path(configured or settings.backup_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pg_dump(db: Session, target: Path) -> bool:
    binary = shutil.which("pg_dump")
    if not binary:
        return False
    url = settings.database_url
    # psycopg URL → libpq connection string arguments
    from urllib.parse import unquote, urlparse

    parsed = urlparse(url.replace("postgresql+psycopg://", "postgresql://"))
    env = os.environ.copy()
    env["PGPASSWORD"] = unquote(parsed.password or "")
    command = [
        binary,
        "--no-owner",
        "--no-privileges",
        "--format=plain",
        "--host",
        parsed.hostname or "localhost",
        "--port",
        str(parsed.port or 5432),
        "--username",
        unquote(parsed.username or "postgres"),
        "--file",
        str(target),
        unquote((parsed.path or "/").lstrip("/")),
    ]
    completed = subprocess.run(command, env=env, capture_output=True, text=True, timeout=900)
    if completed.returncode != 0:
        target.unlink(missing_ok=True)
        raise BackupError(f"pg_dump failed: {completed.stderr.strip()[:500]}")
    return True


def _json_dump(db: Session, target: Path) -> tuple[int, int]:
    tables = list(Base.metadata.sorted_tables)
    rows_total = 0
    payload: dict[str, Any] = {
        "format": "kuhhan-logical-json",
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "tables": {},
    }
    for table in tables:
        rows = db.execute(select(table)).mappings().all()
        serialised = []
        for row in rows:
            serialised.append({key: _json_value(value) for key, value in row.items()})
        payload["tables"][table.name] = serialised
        rows_total += len(serialised)
    with gzip.open(target, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, default=str)
    return len(tables), rows_total


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime,)):
        return value.isoformat()
    from decimal import Decimal

    if isinstance(value, Decimal):
        return float(value)
    return value


def verify_backup(path: Path) -> dict[str, Any]:
    """Read the artefact back and report what it actually contains."""
    if not path.exists():
        raise BackupError("Backup file not found")
    suffix = path.suffix.lower()
    if suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
        tables = payload.get("tables") or {}
        return {
            "ok": True,
            "format": payload.get("format", "unknown"),
            "table_count": len(tables),
            "row_count": sum(len(rows) for rows in tables.values()),
        }
    content = path.read_text(encoding="utf-8", errors="replace")
    statements = content.count(";")
    ok = "PostgreSQL database dump" in content or content.lstrip().startswith("--")
    return {"ok": ok, "format": "pg_dump", "table_count": content.count("CREATE TABLE"), "row_count": statements}


def create_backup(db: Session, *, user_id: str | None = None) -> Backup:
    directory = backup_directory(db)
    # Microseconds keep two runs in the same second from colliding; an existing
    # file is still never overwritten (checked below).
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    used_pg_dump = shutil.which("pg_dump") is not None
    filename = f"kuhhan-{stamp}." + ("sql" if used_pg_dump else "json.gz")
    target = directory / filename
    if target.exists():
        raise BackupError("A backup with this timestamp already exists; refusing to overwrite")

    record = Backup(
        filename=filename,
        method="pg_dump" if used_pg_dump else "logical_json",
        status="running",
        created_at=datetime.now(timezone.utc),
        created_by=user_id,
        size_bytes=0,
        table_count=0,
        row_count=0,
        message="",
    )
    db.add(record)
    db.flush()

    try:
        if used_pg_dump:
            _pg_dump(db, target)
            record.table_count = 0
            record.row_count = 0
        else:
            tables, rows = _json_dump(db, target)
            record.table_count = tables
            record.row_count = rows
        verification = verify_backup(target)
        record.size_bytes = target.stat().st_size
        record.checksum_sha256 = _checksum(target)
        record.status = "verified" if verification["ok"] else "failed"
        record.verified_at = datetime.now(timezone.utc)
        record.message = (
            f"{record.method} backup completed and read back successfully "
            f"({verification.get('table_count')} tables)"
        )
        if not verification["ok"]:
            record.status = "failed"
            record.message = "Backup file could not be read back"
    except (BackupError, OSError, subprocess.SubprocessError) as exc:
        record.status = "failed"
        record.message = str(exc)[:500]
        target.unlink(missing_ok=True)
    db.commit()
    return record


def prune_backups(db: Session, *, retention_days: int | None = None) -> int:
    retention = int(retention_days or get_setting(db, "backup.retention_days", 14) or 14)
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention)
    directory = backup_directory(db)
    removed = 0
    for record in db.scalars(select(Backup).where(Backup.created_at < cutoff)).all():
        path = directory / record.filename
        if path.exists():
            path.unlink()
            removed += 1
        db.delete(record)
    db.commit()
    return removed


def database_health(db: Session) -> dict[str, Any]:
    db.execute(text("SELECT 1"))
    tables = []
    for table in Base.metadata.sorted_tables:
        count = db.scalar(select(func.count()).select_from(table)) or 0
        tables.append({"table": table.name, "rows": int(count)})
    return {"ok": True, "table_count": len(tables), "tables": tables}


RECOVERY_STEPS = [
    "Stop the KUHHAN API and worker services so no writes occur during recovery.",
    "Take a fresh backup of the current database before changing anything (unless it is corrupt).",
    "For a pg_dump backup: create an empty database, then run psql -U <user> -d <db> -f <backup>.sql.",
    "For a logical JSON backup: run python -m app.tools.restore_json <file> with DATABASE_URL pointing at the target database.",
    "Run the Alembic migration check: alembic current.",
    "Start the API, then the worker, and confirm System Health reports the database as reachable.",
    "Verify row counts against the backup report before resuming collection jobs.",
]

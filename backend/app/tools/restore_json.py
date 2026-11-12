"""Restore a logical JSON backup created by ``app.services.backup_service``.

Usage::

    python -m app.tools.restore_json /path/to/kuhhan-20260101T000000Z.json.gz
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

from sqlalchemy import insert

from app.db.base import Base
from app.db.session import engine


def main(path_arg: str) -> int:
    path = Path(path_arg)
    if not path.exists():
        print(f"Backup file not found: {path}")
        return 2
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:  # type: ignore[operator]
        payload = json.load(handle)

    tables = payload.get("tables") or {}
    if not tables:
        print("No table data found in the backup")
        return 3

    confirmed = input(
        "This will INSERT rows into the configured database. Type RESTORE to continue: "
    )
    if confirmed.strip() != "RESTORE":
        print("Aborted")
        return 1

    ordered = [t for t in Base.metadata.sorted_tables if t.name in tables]
    with engine.begin() as connection:
        for table in ordered:
            rows = tables[table.name]
            if not rows:
                continue
            connection.execute(insert(table), rows)
            print(f"{table.name}: {len(rows)} row(s) restored")
    print("Restore finished. Verify row counts before resuming collection jobs.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))

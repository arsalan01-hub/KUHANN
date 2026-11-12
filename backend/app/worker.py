"""Background worker: executes scheduled jobs independently of any browser."""

from __future__ import annotations

import logging
import os
import signal
import socket
import time
from datetime import datetime, timezone

from app.core.config import settings
from app.db.session import session_scope
from app.models.system import SystemSetting
from app.services import jobs

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
)
logger = logging.getLogger("kuhhan.worker")

_stop = False


def _handle_signal(signum, frame):  # noqa: ARG001
    global _stop
    _stop = True
    logger.info("Shutdown signal %s received; finishing current tick", signum)


def _heartbeat(runs: int) -> None:
    with session_scope() as db:
        row = db.get(SystemSetting, "runtime.worker_heartbeat")
        payload = {
            "last_tick": datetime.now(timezone.utc).isoformat(),
            "runs_last_tick": runs,
            "pid": os.getpid(),
            "host": socket.gethostname(),
        }
        if row is None:
            db.add(
                SystemSetting(
                    key="runtime.worker_heartbeat",
                    value=payload,
                    description="Background worker liveness marker",
                    updated_at=datetime.now(timezone.utc),
                )
            )
        else:
            row.value = payload
            row.updated_at = datetime.now(timezone.utc)


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    poll = max(5, int(settings.worker_poll_seconds))
    logger.info("KUHHAN worker starting (poll %ss)", poll)
    while not _stop:
        started = time.perf_counter()
        runs = 0
        try:
            with session_scope() as db:
                executed = jobs.tick(db)
                runs = len(executed)
                for run in executed:
                    logger.info("Job %s finished: %s", run.job_type, run.status)
        except Exception:  # noqa: BLE001 - the worker must survive database hiccups
            logger.exception("Worker tick failed")
        try:
            _heartbeat(runs)
        except Exception:  # noqa: BLE001
            logger.exception("Heartbeat write failed")
        elapsed = time.perf_counter() - started
        remaining = max(1.0, poll - elapsed)
        for _ in range(int(remaining)):
            if _stop:
                break
            time.sleep(1)
    logger.info("KUHHAN worker stopped")


if __name__ == "__main__":
    main()

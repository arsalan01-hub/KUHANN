"""Login throttling.

A small in-process sliding window protects the login endpoint against password
spraying. It is intentionally dependency-free; the database lockout on the user
row provides the durable second layer across processes.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from app.core.config import settings


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def hit(self, key: str) -> bool:
        """Record an attempt. Returns False when the limit is exceeded."""
        now = time.monotonic()
        with self._lock:
            bucket = self._events[key]
            while bucket and now - bucket[0] > self.window:
                bucket.popleft()
            if len(bucket) >= self.limit:
                return False
            bucket.append(now)
            return True

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._events.clear()
            else:
                self._events.pop(key, None)


login_limiter = SlidingWindowLimiter(
    settings.login_rate_limit, settings.login_rate_window_seconds
)

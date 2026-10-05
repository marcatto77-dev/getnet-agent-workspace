import threading
import time
from collections import defaultdict, deque
from hashlib import sha256
from math import ceil
from typing import Protocol

from .config import settings


class RateLimiter(Protocol):
    def allow(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]: ...


class InMemoryRateLimiter:
    """Process-local limiter; API intentionally permits a Redis implementation later."""

    def __init__(self):
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            while events and events[0] <= now - window_seconds:
                events.popleft()
            if len(events) >= limit:
                return False, max(1, int(window_seconds - (now - events[0])))
            events.append(now)
            return True, 0


class DatabaseRateLimiter:
    """Fixed-window limit guarded by PostgreSQL row locks across replicas."""

    def allow(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        from .db import connection

        key_hash = sha256(key.encode("utf-8")).hexdigest()
        with connection() as conn:
            conn.execute(
                "INSERT INTO request_rate_limits(key_hash,window_started_at) VALUES (%s,now()) ON CONFLICT DO NOTHING",
                (key_hash,),
            )
            row = conn.execute(
                "SELECT attempts,window_started_at,now() AS db_now FROM request_rate_limits "
                "WHERE key_hash=%s FOR UPDATE",
                (key_hash,),
            ).fetchone()
            elapsed = (row["db_now"] - row["window_started_at"]).total_seconds()
            if elapsed >= window_seconds:
                conn.execute(
                    "UPDATE request_rate_limits SET window_started_at=now(),attempts=1,updated_at=now() "
                    "WHERE key_hash=%s",
                    (key_hash,),
                )
                return True, 0
            if row["attempts"] >= limit:
                return False, max(1, ceil(window_seconds - elapsed))
            conn.execute(
                "UPDATE request_rate_limits SET attempts=attempts+1,updated_at=now() WHERE key_hash=%s",
                (key_hash,),
            )
            return True, 0


request_limiter: RateLimiter = (
    DatabaseRateLimiter() if settings().rate_limit_backend == "database" else InMemoryRateLimiter()
)

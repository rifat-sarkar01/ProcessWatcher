"""Per-client token bucket (30 req/min, burst 10 — `05_Schema.md` §13)."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from pw.security.errors import RateLimited

DEFAULT_CAPACITY = 10
DEFAULT_REFILL_PER_S = 30 / 60
_MESSAGE = "Too many requests, try again shortly."


@dataclass
class _Bucket:
    tokens: float
    updated: float


class RateLimiter:
    """Thread-safe token bucket keyed by client (IP). The count must hold under load."""

    def __init__(
        self,
        *,
        capacity: int = DEFAULT_CAPACITY,
        refill_per_s: float = DEFAULT_REFILL_PER_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if capacity < 1:
            raise ValueError(f"capacity must be at least 1: {capacity}")
        if refill_per_s < 0:
            raise ValueError(f"refill_per_s must be non-negative: {refill_per_s}")
        self._capacity = float(capacity)
        self._refill = refill_per_s
        self._clock = clock
        self._lock = threading.Lock()
        self._buckets: dict[str, _Bucket] = {}

    def check(self, key: str) -> None:
        """Consume one token for `key` or raise `RateLimited` with a retry hint."""
        with self._lock:
            now = self._clock()
            bucket = self._buckets.get(key) or _Bucket(self._capacity, now)
            elapsed = max(0.0, now - bucket.updated)
            bucket.tokens = min(self._capacity, bucket.tokens + elapsed * self._refill)
            bucket.updated = now
            self._buckets[key] = bucket
            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return
            retry = (1.0 - bucket.tokens) / self._refill if self._refill > 0 else None
            raise RateLimited(_MESSAGE, retry_after_s=None if retry is None else round(retry, 3))


__all__ = ["DEFAULT_CAPACITY", "DEFAULT_REFILL_PER_S", "RateLimiter"]

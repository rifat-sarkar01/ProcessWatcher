"""Per-IP token bucket: burst, refill, retry-after and concurrency."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from pw.security.ratelimit import RateLimited, RateLimiter


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_burst_is_allowed_then_limited() -> None:
    clock = Clock()
    limiter = RateLimiter(capacity=10, refill_per_s=0.5, clock=clock)
    for _ in range(10):
        limiter.check("203.0.113.7")
    with pytest.raises(RateLimited) as info:
        limiter.check("203.0.113.7")
    assert info.value.retry_after_s == pytest.approx(2.0)
    assert info.value.status_code == 429
    assert info.value.code == "E-05"


def test_tokens_refill_over_time() -> None:
    clock = Clock()
    limiter = RateLimiter(capacity=10, refill_per_s=0.5, clock=clock)
    for _ in range(10):
        limiter.check("ip")
    clock.now += 2.0
    limiter.check("ip")
    with pytest.raises(RateLimited):
        limiter.check("ip")


def test_limits_are_per_key() -> None:
    limiter = RateLimiter(capacity=1, refill_per_s=0.0, clock=Clock())
    limiter.check("a")
    limiter.check("b")
    with pytest.raises(RateLimited):
        limiter.check("a")


def test_concurrent_requests_cannot_exceed_the_burst() -> None:
    limiter = RateLimiter(capacity=10, refill_per_s=0.0, clock=Clock())
    allowed = 0

    def attempt(_: int) -> bool:
        try:
            limiter.check("shared")
        except RateLimited:
            return False
        return True

    with ThreadPoolExecutor(max_workers=16) as pool:
        allowed = sum(pool.map(attempt, range(50)))
    assert allowed == 10


def test_retry_after_shrinks_as_tokens_refill() -> None:
    clock = Clock()
    limiter = RateLimiter(capacity=1, refill_per_s=0.5, clock=clock)
    limiter.check("ip")
    clock.now += 1.0
    with pytest.raises(RateLimited) as info:
        limiter.check("ip")
    assert info.value.retry_after_s == pytest.approx(1.0)

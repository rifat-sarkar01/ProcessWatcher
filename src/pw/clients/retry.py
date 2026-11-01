"""Retry policy: exponential backoff with jitter, honouring `Retry-After`.

Only timeouts, transport failures, 429 and 5xx are retried; 4xx (except 429) is a
caller bug and fails immediately. `sleep` and the random source are injectable so tests
never wait.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypeVar

from pw.clients.errors import (
    RateLimitError,
    ServerError,
    TransportFailure,
    TransportTimeout,
)

T = TypeVar("T")

MAX_RETRIES = 3
BASE_DELAY_S = 1.0
MAX_DELAY_S = 20.0


@dataclass(slots=True)
class RetryPolicy:
    max_retries: int = MAX_RETRIES
    base_delay_s: float = BASE_DELAY_S
    max_delay_s: float = MAX_DELAY_S
    jitter_ratio: float = 0.25
    rng: random.Random = field(default_factory=random.Random)
    sleep: Callable[[float], None] = time.sleep

    def run(self, call: Callable[[], T]) -> T:
        attempt = 0
        while True:
            try:
                return call()
            except (TransportTimeout, TransportFailure) as error:
                if attempt >= self.max_retries:
                    error.attempts = attempt + 1
                    raise
                self.sleep(self._delay(attempt, None))
            except RateLimitError as error:
                if attempt >= self.max_retries:
                    error.attempts = attempt + 1
                    raise
                self.sleep(self._delay(attempt, error.retry_after_s))
            except ServerError as error:
                if attempt >= self.max_retries:
                    error.attempts = attempt + 1
                    raise
                self.sleep(self._delay(attempt, None))
            attempt += 1

    def _delay(self, attempt: int, retry_after_s: float | None) -> float:
        if retry_after_s is not None and retry_after_s >= 0:
            return float(min(self.max_delay_s, retry_after_s))
        exponential = float(min(self.max_delay_s, self.base_delay_s * (2**attempt)))
        jittered = exponential + self.rng.uniform(0.0, exponential * self.jitter_ratio)
        return float(min(self.max_delay_s, jittered))


def retry_after_seconds(headers: dict[str, str]) -> float | None:
    raw = next((value for key, value in headers.items() if key.lower() == "retry-after"), None)
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value >= 0 else None


__all__ = [
    "BASE_DELAY_S",
    "MAX_DELAY_S",
    "MAX_RETRIES",
    "RetryPolicy",
    "retry_after_seconds",
]

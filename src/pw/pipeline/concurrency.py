"""Bounded per-model fan-out for the stage DAG (T-6.6).

The TRD caps in-flight model calls per model (SAM 4, Wonder 4, Image 2). Every client is
synchronous, so stages fan out on threads and each task acquires its model's semaphore.
`map` returns results in input order, which keeps stitched tracks, identities and profile
output deterministic regardless of completion order.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from types import MappingProxyType
from typing import TypeVar

MODELS = ("sam", "wonder", "image")
DEFAULT_LIMITS: Mapping[str, int] = MappingProxyType({"sam": 4, "wonder": 4, "image": 2})

T = TypeVar("T")
R = TypeVar("R")


class ConcurrencyError(ValueError):
    """An unknown model or an invalid concurrency limit."""


@dataclass(frozen=True, slots=True)
class ConcurrencyLimits:
    """In-flight call caps from `docs/04_TRD.md` §4 (ADR-001/002 may lower them)."""

    sam: int = 4
    wonder: int = 4
    image: int = 2

    def __post_init__(self) -> None:
        for model, limit in self.as_dict().items():
            if limit < 1:
                raise ConcurrencyError(f"{model} limit must be at least 1; got {limit}")

    def as_dict(self) -> dict[str, int]:
        return {"sam": self.sam, "wonder": self.wonder, "image": self.image}

    def for_model(self, model: str) -> int:
        limits = self.as_dict()
        if model not in limits:
            raise ConcurrencyError(f"unknown model {model!r}; expected one of {', '.join(MODELS)}")
        return limits[model]


class ModelLimiter:
    """Run callables on a thread pool, never exceeding a model's concurrent-call cap."""

    def __init__(
        self,
        limits: ConcurrencyLimits | None = None,
        *,
        workers: int | None = None,
    ) -> None:
        self.limits = limits or ConcurrencyLimits()
        self._semaphores = {
            model: threading.BoundedSemaphore(self.limits.for_model(model)) for model in MODELS
        }
        size = workers if workers is not None else sum(self.limits.as_dict().values())
        if size < 1:
            raise ConcurrencyError(f"workers must be at least 1; got {size}")
        self._executor = ThreadPoolExecutor(max_workers=size, thread_name_prefix="pw-model")

    def map(self, model: str, func: Callable[[T], R], items: Iterable[T]) -> list[R]:
        """Apply `func` to every item in parallel; results keep the input order."""
        semaphore = self._semaphore(model)
        batch = list(items)
        if not batch:
            return []

        def task(item: T) -> R:
            with semaphore:
                return func(item)

        futures = [self._executor.submit(task, item) for item in batch]
        try:
            return [future.result() for future in futures]
        finally:
            for future in futures:
                future.cancel()

    def close(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)

    def __enter__(self) -> ModelLimiter:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _semaphore(self, model: str) -> threading.BoundedSemaphore:
        self.limits.for_model(model)
        return self._semaphores[model]


__all__ = [
    "DEFAULT_LIMITS",
    "MODELS",
    "ConcurrencyError",
    "ConcurrencyLimits",
    "ModelLimiter",
]

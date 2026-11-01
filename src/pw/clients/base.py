"""Shared client behaviour: mode dispatch, retries, cache and ledger.

A client is constructed once per run. In `live` it records every successful response
into the request cache and charges the ledger; `replay` and `demo` serve only from the
cache (never outbound, never write); `fake` calls an injected responder for unit tests.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pw.clients.cache import (
    ResponseCache,
    key_for_json,
    key_for_multipart,
)
from pw.clients.errors import (
    AuthError,
    BadRequestError,
    CacheMissError,
    MalformedResponseError,
    MissingKeyError,
    RateLimitError,
    ServerError,
    UnsupportedModeError,
)
from pw.clients.pricing import ESTIMATED_CALL_USD
from pw.clients.retry import RetryPolicy, retry_after_seconds
from pw.clients.transport import FilePart, RawResponse, Transport
from pw.core.ledger import LedgerEntry, RunLedger

MODES = ("live", "replay", "fake", "demo")

logger = logging.getLogger("pw.clients")

FakeResponder = Callable[[str, Mapping[str, Any]], Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class Usage:
    tokens_in: int = 0
    tokens_out: int = 0
    images: int = 0
    sam_units: int = 0


def raise_for_status(raw: RawResponse, *, model: str) -> None:
    if 200 <= raw.status < 300:
        return
    message = _error_message(raw)
    if raw.status == 429:
        raise RateLimitError(
            message,
            model=model,
            status=raw.status,
            retry_after_s=retry_after_seconds(dict(raw.headers)),
        )
    if raw.status in (401, 403):
        raise AuthError(message, model=model, status=raw.status)
    if raw.status >= 500:
        raise ServerError(message, model=model, status=raw.status)
    raise BadRequestError(message, model=model, status=raw.status)


def _error_message(raw: RawResponse) -> str:
    try:
        payload = raw.json()
    except MalformedResponseError:
        return f"HTTP {raw.status}"
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return f"HTTP {raw.status}: {error['message']}"
    return f"HTTP {raw.status}"


class ModelClient:
    """Base for typed clients; subclasses expose domain methods over `_call_json`."""

    model: str

    def __init__(
        self,
        *,
        mode: str,
        ledger: RunLedger,
        cache: ResponseCache | None = None,
        transport: Transport | None = None,
        fake: FakeResponder | None = None,
        policy: RetryPolicy | None = None,
    ) -> None:
        if mode not in MODES:
            raise UnsupportedModeError(f"unknown mode {mode!r}; expected one of {', '.join(MODES)}")
        if mode == "live" and transport is None:
            raise MissingKeyError("live mode needs a transport with an API key")
        if mode == "fake" and fake is None:
            raise UnsupportedModeError("fake mode needs a FakeResponder")
        self.mode = mode
        self.ledger = ledger
        self.cache = cache or ResponseCache(ledger.path.parent / "cache")
        self.transport = transport
        self.fake = fake
        self.policy = policy or RetryPolicy()

    def close(self) -> None:
        close = getattr(self.transport, "close", None)
        if callable(close):
            close()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(model={self.model!r}, mode={self.mode!r})"

    def _usage(self, body: Mapping[str, Any]) -> Usage:
        return Usage()

    def _call_json(
        self,
        path: str,
        payload: Mapping[str, Any],
        *,
        operation: str,
        timeout_s: float,
        estimated_usd: float | None = None,
    ) -> Mapping[str, Any]:
        key = key_for_json(path, payload)
        descriptor: dict[str, Any] = {"json": dict(payload)}
        return self._dispatch(
            key=key,
            path=path,
            descriptor=descriptor,
            operation=operation,
            estimated_usd=estimated_usd
            if estimated_usd is not None
            else ESTIMATED_CALL_USD.get(self.model, 0.05),
            send=lambda transport: transport.post_json(path, payload, timeout_s=timeout_s),
        )

    def _call_multipart(
        self,
        path: str,
        fields: Mapping[str, str],
        files: Sequence[FilePart],
        *,
        operation: str,
        timeout_s: float,
        estimated_usd: float | None = None,
    ) -> Mapping[str, Any]:
        key = key_for_multipart(path, fields, files)
        descriptor: dict[str, Any] = {
            "fields": dict(fields),
            "files": [
                {"field": part.field, "filename": part.filename, "content_type": part.content_type}
                for part in files
            ],
        }
        return self._dispatch(
            key=key,
            path=path,
            descriptor=descriptor,
            operation=operation,
            estimated_usd=estimated_usd
            if estimated_usd is not None
            else ESTIMATED_CALL_USD.get(self.model, 0.05),
            send=lambda transport: transport.post_multipart(
                path, fields, files, timeout_s=timeout_s
            ),
        )

    def _dispatch(
        self,
        *,
        key: str,
        path: str,
        descriptor: Mapping[str, Any],
        operation: str,
        estimated_usd: float,
        send: Callable[[Transport], RawResponse],
    ) -> Mapping[str, Any]:
        if self.mode == "fake":
            return self._fake(key, operation, descriptor)
        if self.mode in ("replay", "demo"):
            return self._replay(key, operation)
        assert self.transport is not None  # enforced in __init__
        return self._live(
            key=key,
            path=path,
            descriptor=descriptor,
            operation=operation,
            estimated_usd=estimated_usd,
            send=send,
        )

    def _fake(self, key: str, operation: str, descriptor: Mapping[str, Any]) -> Mapping[str, Any]:
        assert self.fake is not None
        body = self.fake(operation, descriptor)
        if not isinstance(body, Mapping):
            raise MalformedResponseError("fake responder must return a mapping", model=self.model)
        self.ledger.record(
            LedgerEntry(model=self.model, operation=operation, mode="fake", cache_hit=True)
        )
        logger.debug("%s %s served by fake responder", self.model, operation)
        return body

    def _replay(self, key: str, operation: str) -> Mapping[str, Any]:
        assert self.cache is not None
        hit = self.cache.read(key)
        if hit is None:
            raise CacheMissError(key, model=self.model)
        self.ledger.record(
            LedgerEntry(
                model=self.model,
                operation=operation,
                mode=self.mode,
                cache_hit=True,
                request_hash=key,
            )
        )
        logger.debug("%s served from cache %s", self.model, key[:12])
        return hit.response

    def _live(
        self,
        *,
        key: str,
        path: str,
        descriptor: Mapping[str, Any],
        operation: str,
        estimated_usd: float,
        send: Callable[[Transport], RawResponse],
    ) -> Mapping[str, Any]:
        assert self.transport is not None
        transport = self.transport
        with self.ledger.budget(estimated_usd):
            started = time.perf_counter()

            def attempt() -> RawResponse:
                raw = send(transport)
                raise_for_status(raw, model=self.model)
                return raw

            raw = self.policy.run(attempt)
            body = raw.json(model=self.model)
            latency_ms = int((time.perf_counter() - started) * 1000)
            if not isinstance(body, dict):
                raise MalformedResponseError("response must be a JSON object", model=self.model)
            usage = self._usage(body)
            self.ledger.record(
                LedgerEntry(
                    model=self.model,
                    operation=operation,
                    mode="live",
                    tokens_in=usage.tokens_in,
                    tokens_out=usage.tokens_out,
                    images=usage.images,
                    sam_units=usage.sam_units,
                    latency_ms=latency_ms,
                    request_hash=key,
                )
            )
            if self.cache is not None:
                self.cache.write(key, path=path, request=descriptor, response=body)
        logger.debug("%s %s recorded in %d ms", self.model, operation, latency_ms)
        return body


__all__ = ["MODES", "FakeResponder", "ModelClient", "Usage", "raise_for_status"]

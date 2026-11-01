"""Test doubles for the client layer: a scripted transport and a zero-wait policy."""

from __future__ import annotations

import json
import random
from collections.abc import Mapping, Sequence

from pw.clients.retry import RetryPolicy
from pw.clients.transport import FilePart, RawResponse

TEST_KEY = "test-key-not-a-real-secret"


def json_response(
    body: Mapping[str, object],
    *,
    status: int = 200,
    headers: Mapping[str, str] | None = None,
) -> RawResponse:
    return RawResponse(
        status=status,
        headers=dict(headers or {}),
        content=json.dumps(body).encode("utf-8"),
    )


class FakeTransport:
    """Returns scripted responses (or raises scripted errors) and records every call."""

    def __init__(self, outcomes: Sequence[RawResponse | Exception]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, object]] = []

    def post_json(
        self, path: str, payload: Mapping[str, object], *, timeout_s: float
    ) -> RawResponse:
        self.calls.append(
            {"kind": "json", "path": path, "payload": payload, "timeout_s": timeout_s}
        )
        return self._next()

    def post_multipart(
        self,
        path: str,
        fields: Mapping[str, str],
        files: Sequence[FilePart],
        *,
        timeout_s: float,
    ) -> RawResponse:
        self.calls.append(
            {
                "kind": "multipart",
                "path": path,
                "fields": fields,
                "field_names": [part.field for part in files],
                "timeout_s": timeout_s,
            }
        )
        return self._next()

    def _next(self) -> RawResponse:
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def no_wait(sleeps: list[float] | None = None) -> RetryPolicy:
    sink = sleeps if sleeps is not None else []
    return RetryPolicy(jitter_ratio=0.0, rng=random.Random(0), sleep=sink.append)

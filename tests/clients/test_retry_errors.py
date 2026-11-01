"""Retries, backoff and typed failures."""

from __future__ import annotations

import pytest
from fake_transport import FakeTransport, json_response, no_wait

from pw.clients.cache import ResponseCache
from pw.clients.errors import (
    AuthError,
    MalformedResponseError,
    RateLimitError,
    ServerError,
    TransportFailure,
    TransportTimeout,
)
from pw.clients.wonder import WonderClient
from pw.core.ledger import RunLedger

PAYLOAD = {"model": "muse-wonder-1.0", "input": []}
BODY = {"output": [], "usage": {"input_tokens": 1, "output_tokens": 1}}


def _client(
    ledger: RunLedger, cache: ResponseCache, transport: FakeTransport, sleeps: list[float]
) -> WonderClient:
    return WonderClient(
        mode="live",
        ledger=ledger,
        cache=cache,
        transport=transport,
        policy=no_wait(sleeps),
    )


def test_timeout_is_retried_three_times_then_typed(ledger: RunLedger, cache: ResponseCache) -> None:
    transport = FakeTransport([TransportTimeout("slow")] * 10)
    sleeps: list[float] = []
    with pytest.raises(TransportTimeout) as caught:
        _client(ledger, cache, transport, sleeps).create_response(PAYLOAD)
    assert len(transport.calls) == 4
    assert len(sleeps) == 3
    assert caught.value.attempts == 4
    assert ledger.entries == ()


def test_transport_failure_retries_then_succeeds(ledger: RunLedger, cache: ResponseCache) -> None:
    transport = FakeTransport([TransportFailure("boom"), json_response(BODY)])
    sleeps: list[float] = []
    result = _client(ledger, cache, transport, sleeps).create_response(PAYLOAD)
    assert result.body == BODY
    assert len(transport.calls) == 2
    assert sleeps and sleeps[0] >= 1.0


def test_rate_limit_honours_retry_after(ledger: RunLedger, cache: ResponseCache) -> None:
    limited = json_response(
        {"error": {"message": "slow down"}}, status=429, headers={"Retry-After": "7"}
    )
    transport = FakeTransport([limited, json_response(BODY)])
    sleeps: list[float] = []
    _client(ledger, cache, transport, sleeps).create_response(PAYLOAD)
    assert sleeps == [7.0]
    assert len(transport.calls) == 2


def test_rate_limit_exhausts_with_typed_error(ledger: RunLedger, cache: ResponseCache) -> None:
    limited = json_response(
        {"error": {"message": "slow down"}}, status=429, headers={"Retry-After": "0"}
    )
    transport = FakeTransport([limited] * 5)
    with pytest.raises(RateLimitError) as caught:
        _client(ledger, cache, transport, []).create_response(PAYLOAD)
    assert caught.value.retry_after_s == 0.0
    assert len(transport.calls) == 4


def test_server_error_retries_then_succeeds(ledger: RunLedger, cache: ResponseCache) -> None:
    transport = FakeTransport([json_response({"error": {}}, status=503), json_response(BODY)])
    _client(ledger, cache, transport, []).create_response(PAYLOAD)
    assert len(transport.calls) == 2


def test_auth_error_is_not_retried(ledger: RunLedger, cache: ResponseCache) -> None:
    transport = FakeTransport([json_response({"error": {"message": "no"}}, status=401)])
    with pytest.raises(AuthError):
        _client(ledger, cache, transport, []).create_response(PAYLOAD)
    assert len(transport.calls) == 1


def test_server_error_exhausts_as_typed(ledger: RunLedger, cache: ResponseCache) -> None:
    transport = FakeTransport([json_response({"error": {}}, status=500)] * 5)
    with pytest.raises(ServerError):
        _client(ledger, cache, transport, []).create_response(PAYLOAD)
    assert len(transport.calls) == 4


def test_malformed_json_is_a_typed_error(ledger: RunLedger, cache: ResponseCache) -> None:
    from pw.clients.transport import RawResponse

    transport = FakeTransport([RawResponse(200, {}, b"<html>not json</html>")])
    with pytest.raises(MalformedResponseError):
        _client(ledger, cache, transport, []).create_response(PAYLOAD)
    assert len(transport.calls) == 1

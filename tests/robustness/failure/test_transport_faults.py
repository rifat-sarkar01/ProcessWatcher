"""Transport faults: bounded retries, backoff, typed errors and honest charging."""

from __future__ import annotations

from pathlib import Path

import pytest
from support import ScriptedTransport, error_body, retry_policy, text_body

from pw.clients.cache import ResponseCache
from pw.clients.errors import (
    BadRequestError,
    MalformedResponseError,
    ServerError,
    TransportTimeout,
)
from pw.clients.transport import RawResponse
from pw.clients.wonder import WonderClient
from pw.core.ledger import RunLedger

REQUEST = {"model": "muse-wonder-1.0", "input": [{"role": "user"}]}


def _client(transport: ScriptedTransport, scratch: Path, delays: list[float]) -> WonderClient:
    return WonderClient(
        mode="live",
        ledger=RunLedger(scratch / "ledger.json", cap_usd=1.0),
        cache=ResponseCache(scratch / "cache"),
        transport=transport,
        policy=retry_policy(delays),
    )


@pytest.mark.unit
def test_timeout_is_retried_then_succeeds(scratch: Path) -> None:
    delays: list[float] = []
    transport = ScriptedTransport([TransportTimeout("request timed out"), text_body("hello")])
    client = _client(transport, scratch, delays)

    result = client.create_response(REQUEST)

    assert result.text == "hello"
    assert transport.calls == 2
    assert len(delays) == 1
    assert 1.0 <= delays[0] <= 1.25
    assert len(client.ledger.entries) == 1


@pytest.mark.unit
def test_server_error_is_retried_then_succeeds(scratch: Path) -> None:
    delays: list[float] = []
    transport = ScriptedTransport([error_body(503, "upstream down"), text_body("recovered")])
    client = _client(transport, scratch, delays)

    result = client.create_response(REQUEST)

    assert result.text == "recovered"
    assert transport.calls == 2
    assert len(delays) == 1
    assert len(client.ledger.entries) == 1


@pytest.mark.unit
def test_rate_limit_honours_retry_after(scratch: Path) -> None:
    delays: list[float] = []
    limited = error_body(429, "slow down", headers={"Retry-After": "2.5"})
    transport = ScriptedTransport([limited, text_body("ok")])
    client = _client(transport, scratch, delays)

    client.create_response(REQUEST)

    assert transport.calls == 2
    assert delays == [2.5]


@pytest.mark.unit
def test_retries_are_bounded_with_exponential_backoff(scratch: Path) -> None:
    delays: list[float] = []
    transport = ScriptedTransport([error_body(503, "still down")])
    client = _client(transport, scratch, delays)

    with pytest.raises(ServerError) as info:
        client.create_response(REQUEST)

    assert info.value.attempts == 4  # one attempt + three retries
    assert transport.calls == 4
    assert len(delays) == 3
    assert delays[0] < delays[1] < delays[2]
    assert client.ledger.entries == ()


@pytest.mark.unit
def test_client_errors_are_not_retried(scratch: Path) -> None:
    delays: list[float] = []
    transport = ScriptedTransport([error_body(400, "bad schema")])
    client = _client(transport, scratch, delays)

    with pytest.raises(BadRequestError):
        client.create_response(REQUEST)

    assert transport.calls == 1
    assert delays == []
    assert client.ledger.entries == ()


@pytest.mark.unit
def test_malformed_json_is_typed_and_not_charged(scratch: Path) -> None:
    delays: list[float] = []
    transport = ScriptedTransport(
        [RawResponse(status=200, headers={}, content=b"<html>not json</html>")]
    )
    client = _client(transport, scratch, delays)

    with pytest.raises(MalformedResponseError):
        client.create_response(REQUEST)

    assert transport.calls == 1
    assert delays == []
    assert client.ledger.entries == ()

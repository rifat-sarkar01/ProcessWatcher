"""Record in live, serve in replay/demo; cache keys are canonical."""

from __future__ import annotations

import json

import pytest
from fake_transport import FakeTransport, json_response, no_wait

from pw.clients.base import FakeResponder
from pw.clients.cache import ResponseCache, key_for_json, key_for_multipart
from pw.clients.errors import CacheMissError
from pw.clients.transport import FilePart
from pw.clients.wonder import WonderClient
from pw.core.ledger import RunLedger

PAYLOAD = {
    "model": "muse-wonder-1.0",
    "input": [{"role": "user", "content": [{"type": "input_text", "text": "hi"}]}],
}
BODY = {
    "output": [{"content": [{"type": "output_text", "text": "hello"}]}],
    "usage": {"input_tokens": 10, "output_tokens": 5},
}


def _wonder(
    mode: str,
    ledger: RunLedger,
    cache: ResponseCache,
    transport: FakeTransport | None = None,
    fake: FakeResponder | None = None,
) -> WonderClient:
    return WonderClient(
        mode=mode,
        ledger=ledger,
        cache=cache,
        transport=transport,
        fake=fake,
        policy=no_wait(),
    )


def test_live_records_then_replay_serves_without_transport(
    ledger: RunLedger, cache: ResponseCache
) -> None:
    transport = FakeTransport([json_response(BODY)])
    live = _wonder("live", ledger, cache, transport)
    first = live.create_response(PAYLOAD)
    assert first.text == "hello"
    assert len(transport.calls) == 1

    replay_transport = FakeTransport([])
    replay = _wonder("replay", ledger, cache, replay_transport)
    second = replay.create_response(PAYLOAD)
    assert second.body == first.body
    assert replay_transport.calls == []
    assert [entry.cache_hit for entry in ledger.entries] == [False, True]
    assert ledger.entries[1].usd == 0.0


def test_replay_cache_miss_is_typed_error(ledger: RunLedger, cache: ResponseCache) -> None:
    replay = _wonder("replay", ledger, cache, FakeTransport([]))
    with pytest.raises(CacheMissError) as caught:
        replay.create_response(PAYLOAD)
    assert caught.value.model == "muse-wonder-1.0"
    assert caught.value.code == "cache_miss"


def test_cache_key_is_stable_across_mapping_order() -> None:
    first = key_for_json("/v1/responses", {"b": 2, "a": {"y": 1, "x": 2}})
    second = key_for_json("/v1/responses", {"a": {"x": 2, "y": 1}, "b": 2})
    assert first == second
    assert first != key_for_json("/v1/responses", {"b": 3, "a": {"x": 2, "y": 1}})


def test_multipart_key_includes_file_digests() -> None:
    png = FilePart(field="image[0]", filename="a.png", content=b"one")
    other = FilePart(field="image[0]", filename="a.png", content=b"two")
    assert key_for_multipart("/v1/images/edits", {"prompt": "p"}, [png]) != key_for_multipart(
        "/v1/images/edits", {"prompt": "p"}, [other]
    )
    assert key_for_multipart(
        "/v1/images/edits", {"prompt": "p", "model": "m"}, [png]
    ) == key_for_multipart("/v1/images/edits", {"model": "m", "prompt": "p"}, [png])


def test_demo_mode_serves_but_never_writes(ledger: RunLedger, cache: ResponseCache) -> None:
    live = _wonder("live", ledger, cache, FakeTransport([json_response(BODY)]))
    live.create_response(PAYLOAD)
    recorded = sorted(path for path in cache.root.rglob("*.json") if path.is_file())

    demo = _wonder("demo", ledger, cache)
    assert demo.create_response(PAYLOAD).text == "hello"
    assert sorted(path for path in cache.root.rglob("*.json") if path.is_file()) == recorded


def test_demo_mode_miss_is_a_cache_miss(ledger: RunLedger, cache: ResponseCache) -> None:
    with pytest.raises(CacheMissError):
        _wonder("demo", ledger, cache).create_response(PAYLOAD)


def test_fake_mode_uses_responder_and_costs_nothing(
    ledger: RunLedger, cache: ResponseCache
) -> None:
    seen: list[tuple[str, dict[str, object]]] = []

    def responder(operation: str, descriptor: dict[str, object]) -> dict[str, object]:
        seen.append((operation, descriptor))
        return {"ok": True}

    client = _wonder("fake", ledger, cache, fake=responder)
    assert client.create_response(PAYLOAD).body == {"ok": True}
    assert seen and seen[0][0] == "responses"
    entry = ledger.entries[0]
    assert entry.mode == "fake" and entry.usd == 0.0


def test_cache_file_contains_no_headers(ledger: RunLedger, cache: ResponseCache) -> None:
    _wonder("live", ledger, cache, FakeTransport([json_response(BODY)])).create_response(PAYLOAD)
    files = list(cache.root.rglob("*.json"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    assert "authorization" not in text.lower()
    assert "bearer" not in text.lower()
    assert json.loads(text)["response"] == BODY

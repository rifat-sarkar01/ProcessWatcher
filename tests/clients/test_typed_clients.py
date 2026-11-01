"""Typed clients: payload shapes, usage extraction and fail-fast construction."""

from __future__ import annotations

import base64
import logging

import httpx
import pytest
from fake_transport import TEST_KEY, FakeTransport, json_response, no_wait

from pw.clients import build_clients
from pw.clients.cache import ResponseCache
from pw.clients.errors import MissingKeyError, SpendCapExceeded
from pw.clients.image import ImageClient, ImageInput
from pw.clients.sam import SamClient
from pw.clients.transport import HttpxTransport
from pw.clients.wonder import WonderClient
from pw.core.ledger import RunLedger

PNG = b"\x89PNG\r\n\x1a\nfake-image-bytes"
IMAGE_BODY = {"created": 0, "data": [{"b64_json": base64.b64encode(PNG).decode("ascii")}]}


def _image(ledger: RunLedger, cache: ResponseCache, transport: FakeTransport) -> ImageClient:
    return ImageClient(
        mode="live", ledger=ledger, cache=cache, transport=transport, policy=no_wait()
    )


def test_generate_decodes_image_and_prices_one_image(
    ledger: RunLedger, cache: ResponseCache
) -> None:
    transport = FakeTransport([json_response(IMAGE_BODY)])
    result = _image(ledger, cache, transport).generate("a blue square")
    assert result.images == (PNG,)
    assert result.usage.images == 1
    assert ledger.entries[0].usd == pytest.approx(0.01)
    payload = transport.calls[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == "muse-image-1.0"
    assert payload["response_format"] == "b64_json"
    assert "size" not in payload


def test_edit_single_image_uses_the_image_field(ledger: RunLedger, cache: ResponseCache) -> None:
    transport = FakeTransport([json_response(IMAGE_BODY)])
    _image(ledger, cache, transport).edit("redraw", [ImageInput(data=PNG)])
    call = transport.calls[0]
    assert call["kind"] == "multipart"
    assert call["path"] == "/images/edits"
    assert call["field_names"] == ["image"]
    assert call["fields"] == {"model": "muse-image-1.0", "prompt": "redraw"}


def test_edit_multi_image_uses_indexed_fields(ledger: RunLedger, cache: ResponseCache) -> None:
    transport = FakeTransport([json_response(IMAGE_BODY)])
    _image(ledger, cache, transport).edit(
        "compose", [ImageInput(data=PNG), ImageInput(data=PNG + b"2")]
    )
    assert transport.calls[0]["field_names"] == ["image[0]", "image[1]"]


def test_edit_requires_a_reference(ledger: RunLedger, cache: ResponseCache) -> None:
    with pytest.raises(ValueError):
        _image(ledger, cache, FakeTransport([])).edit("x", [])


def test_sam_uses_images_processed_and_prices_frames(
    ledger: RunLedger, cache: ResponseCache
) -> None:
    transport = FakeTransport([json_response({"output": [], "usage": {"images_processed": 2}})])
    client = SamClient(
        mode="live", ledger=ledger, cache=cache, transport=transport, policy=no_wait()
    )
    result = client.segment({"model": "sam-3.1", "input": []})
    assert result.sam_units == 2
    assert ledger.entries[0].sam_units == 2
    assert ledger.entries[0].usd == pytest.approx(0.0004)
    assert transport.calls[0]["timeout_s"] == 300.0


def test_wonder_records_token_usage(ledger: RunLedger, cache: ResponseCache) -> None:
    body = {
        "output": [{"content": [{"type": "output_text", "text": "{}"}]}],
        "usage": {"input_tokens": 616, "output_tokens": 666},
    }
    transport = FakeTransport([json_response(body)])
    client = WonderClient(
        mode="live", ledger=ledger, cache=cache, transport=transport, policy=no_wait()
    )
    result = client.create_response({"model": "muse-wonder-1.0", "input": []})
    assert result.text == "{}"
    assert (result.tokens_in, result.tokens_out) == (616, 666)
    assert ledger.entries[0].usd == pytest.approx(0.015784)
    assert transport.calls[0]["timeout_s"] == 120.0


def test_spend_cap_prevents_the_request(ledger: RunLedger, cache: ResponseCache) -> None:
    capped = RunLedger(ledger.path.with_name("capped.json"), cap_usd=0.005)
    transport = FakeTransport([json_response(IMAGE_BODY)])
    with pytest.raises(SpendCapExceeded):
        _image(capped, cache, transport).generate("x")
    assert transport.calls == []


def test_build_clients_live_needs_a_key(ledger: RunLedger) -> None:
    with pytest.raises(MissingKeyError):
        build_clients(mode="live", ledger=ledger, api_key="")


def test_httpx_transport_sends_bearer_but_hides_it(
    ledger: RunLedger, cache: ResponseCache, caplog: pytest.LogCaptureFixture
) -> None:
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization"))
        return httpx.Response(200, json={"output": [], "usage": {}})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = HttpxTransport(TEST_KEY, client=http_client)
    assert TEST_KEY not in repr(transport)
    caplog.set_level(logging.DEBUG, logger="pw.clients")
    client = WonderClient(
        mode="live", ledger=ledger, cache=cache, transport=transport, policy=no_wait()
    )
    client.create_response({"model": "muse-wonder-1.0", "input": []})
    http_client.close()
    assert seen == [f"Bearer {TEST_KEY}"]
    assert TEST_KEY not in caplog.text
    for path in cache.root.rglob("*.json"):
        assert TEST_KEY not in path.read_text(encoding="utf-8")

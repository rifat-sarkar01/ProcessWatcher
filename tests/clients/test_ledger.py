"""Ledger pricing, persistence and the spend cap."""

from __future__ import annotations

import json
import threading

import pytest

from pw.clients.errors import SpendCapExceeded
from pw.clients.pricing import usd_for
from pw.core.ledger import LedgerEntry, RunLedger


def test_wonder_is_priced_per_million_tokens() -> None:
    assert usd_for("muse-wonder-1.0", tokens_in=1_000_000, tokens_out=1_000_000) == pytest.approx(
        24.0
    )
    assert usd_for("muse-wonder-1.0", tokens_in=616, tokens_out=666) == pytest.approx(0.015784)


def test_images_and_sam_frames_are_priced_per_unit() -> None:
    assert usd_for("muse-image-1.0", images=3) == pytest.approx(0.03)
    assert usd_for("sam-3.1", frames=75) == pytest.approx(0.015)


def test_record_prices_the_entry_and_persists_json(scratch) -> None:
    path = scratch / "ledger.json"
    ledger = RunLedger(path, cap_usd=1.0)
    entry = ledger.record(
        LedgerEntry(model="muse-wonder-1.0", operation="responses", tokens_in=1000, tokens_out=1000)
    )
    assert entry.usd == pytest.approx(0.024)
    assert ledger.total_usd == pytest.approx(0.024)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["total_usd"] == pytest.approx(0.024)
    assert payload["entries"][0]["model"] == "muse-wonder-1.0"


def test_spend_cap_blocks_before_the_call(scratch) -> None:
    ledger = RunLedger(scratch / "ledger.json", cap_usd=0.005)
    with pytest.raises(SpendCapExceeded), ledger.budget(0.01):
        pass
    assert ledger.entries == ()


def test_reservations_are_concurrency_safe(scratch) -> None:
    ledger = RunLedger(scratch / "ledger.json", cap_usd=0.015)
    started = threading.Event()
    release = threading.Event()
    outcome: list[str] = []

    def hold() -> None:
        with ledger.budget(0.01):
            started.set()
            release.wait(timeout=5)

    def second() -> None:
        started.wait(timeout=5)
        try:
            with ledger.budget(0.01):
                outcome.append("allowed")
        except SpendCapExceeded:
            outcome.append("blocked")

    first = threading.Thread(target=hold)
    other = threading.Thread(target=second)
    first.start()
    other.start()
    started.wait(timeout=5)
    other.join(timeout=5)
    release.set()
    first.join(timeout=5)
    assert outcome == ["blocked"]


def test_ledger_reloads_entries(scratch) -> None:
    path = scratch / "ledger.json"
    RunLedger(path).record(
        LedgerEntry(model="muse-image-1.0", operation="image.generate", images=1)
    )
    reloaded = RunLedger(path)
    assert reloaded.total_usd == pytest.approx(0.01)
    assert reloaded.entries[0].images == 1

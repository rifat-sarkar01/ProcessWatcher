"""Client fixtures: scratch dirs, a ledger and a response cache."""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from pw.clients.cache import ResponseCache
from pw.core.ledger import RunLedger

SCRATCH_ROOT = Path(__file__).resolve().parents[2] / ".uv" / "tests-tmp"


@pytest.fixture()
def scratch() -> Iterator[Path]:
    root = SCRATCH_ROOT / f"clients-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.fixture()
def ledger(scratch: Path) -> RunLedger:
    return RunLedger(scratch / "ledger.json", cap_usd=3.0)


@pytest.fixture()
def cache(scratch: Path) -> ResponseCache:
    return ResponseCache(scratch / "cache")

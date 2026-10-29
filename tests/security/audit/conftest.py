"""Fixtures for the ASVS-lite audit suite (T-6.5)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pw.api.main import create_app

ACCESS_CODE = "audit-access-code"
HEADERS = {"X-Access-Code": ACCESS_CODE}


@pytest.fixture
def runs_dir(scratch: Path) -> Iterator[Path]:
    path = scratch / "audit-runs"
    path.mkdir(parents=True, exist_ok=True)
    yield path


@pytest.fixture
def client(runs_dir: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("PW_ACCESS_CODE", ACCESS_CODE)
    return TestClient(create_app(runs_dir=runs_dir))

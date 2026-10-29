"""Artifact serving: traversal, allowlist, Range, content type and error leakage.

Findings this suite covers (docs/security/audit.md): F-02 traversal attempts
(already guarded by T-5.1), F-03 unserved input media, F-10 header hardening.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HEADERS = {"X-Access-Code": "audit-access-code"}

RUN_ID = "run_01J9ZQ8M3K4V7B2C5D6E8F0GHJ"
# Raw `..` segments never reach the app (the HTTP client normalises the URL), so the
# traversal cases are the encoded forms a proxy would decode before routing.
TRAVERSALS = [
    "..%2Freport.json",
    "..%2f..%2fsecret.txt",
    "%2e%2e%2freport.json",
    "..%5C..%5Csecret.txt",
    "evidence/..%2f..%2fsecret.txt",
    "/etc/passwd",
    "C:/Windows/win.ini",
    "input/video.mp4",
    "stages/ingest.json",
    "%00/report.json",
]


@pytest.fixture
def served_run(runs_dir: Path) -> Path:
    root = runs_dir / RUN_ID
    for name in ("input", "stages", "media", "evidence", "illustrations"):
        (root / name).mkdir(parents=True, exist_ok=True)
    (root / "input" / "video.mp4").write_bytes(b"raw upload")
    (root / "stages" / "ingest.json").write_text("{}", encoding="utf-8")
    (root / "evidence" / "evd_001.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    (root / "media" / "analysis.mp4").write_bytes(b"\x00\x00\x00\x18ftyp" + b"\x00" * 64)
    (root / "report.json").write_text('{"kind": "report"}', encoding="utf-8")
    (runs_dir / "secret.txt").write_text("outside the run store", encoding="utf-8")
    return root


@pytest.mark.parametrize("attempt", TRAVERSALS)
def test_traversal_attempts_are_refused(client: TestClient, served_run: Path, attempt: str) -> None:
    response = client.get(f"/runs/{RUN_ID}/artifacts/{attempt}", headers=HEADERS)

    assert response.status_code == 404
    payload = response.json()
    assert set(payload) == {"error"}
    assert set(payload["error"]) == {"code", "message"}
    assert payload["error"]["code"] == "E-13"
    assert "secret" not in payload["error"]["message"].lower()
    assert str(served_run.parent) not in payload["error"]["message"]


def test_unserved_directories_are_refused(client: TestClient, served_run: Path) -> None:
    for path in ("stages/ingest.json", "input/video.mp4", "."):
        response = client.get(f"/runs/{RUN_ID}/artifacts/{path}", headers=HEADERS)
        assert response.status_code == 404


def test_unknown_run_is_not_found(client: TestClient) -> None:
    response = client.get("/runs/run_doesnotexist/report", headers=HEADERS)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "E-13"


def test_served_artifacts_get_a_fixed_content_type(client: TestClient, served_run: Path) -> None:
    response = client.get(f"/runs/{RUN_ID}/artifacts/evidence/evd_001.png", headers=HEADERS)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")


def test_range_requests_are_served(client: TestClient, served_run: Path) -> None:
    response = client.get(
        f"/runs/{RUN_ID}/artifacts/media/analysis.mp4",
        headers={**HEADERS, "Range": "bytes=0-3"},
    )

    assert response.status_code == 206
    assert response.headers["content-range"].startswith("bytes 0-3/")
    assert response.content == b"\x00\x00\x00\x18"


def test_report_is_409_until_the_run_finishes(client: TestClient, runs_dir: Path) -> None:
    running = runs_dir / RUN_ID
    (running / "stages").mkdir(parents=True)

    response = client.get(f"/runs/{RUN_ID}/report", headers=HEADERS)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "E-07"


def test_no_endpoint_echoes_the_access_code(client: TestClient) -> None:
    bad = client.get("/runs", headers={"X-Access-Code": "wrong-code"})
    missing = client.get("/runs")

    assert bad.status_code == 401
    assert missing.status_code == 401
    for response in (bad, missing):
        assert "wrong-code" not in response.text
        assert response.json()["error"]["code"] == "E-05"
        assert "traceback" not in response.text.lower()

"""Authorization coverage: every non-public route is guarded, and abuse is throttled.

Findings this suite covers (docs/security/audit.md): F-01 access code on all routes,
F-12 rate limit on run creation.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pw.api.main import create_app
from pw.security.ratelimit import RateLimiter

ACCESS_CODE = "audit-access-code"
HEADERS = {"X-Access-Code": ACCESS_CODE}
RUN_ID = "run_01J9ZQ8M3K4V7B2C5D6E8F0GHJ"
PROTECTED = [
    ("GET", "/runs"),
    ("GET", f"/runs/{RUN_ID}"),
    ("GET", f"/runs/{RUN_ID}/report"),
    ("GET", f"/runs/{RUN_ID}/events"),
    ("GET", f"/runs/{RUN_ID}/artifacts/report.json"),
    ("POST", "/runs"),
]


@pytest.fixture
def throttled_runs_dir(scratch: Path) -> Iterator[Path]:
    path = scratch / "audit-auth-runs"
    (path / RUN_ID / "stages").mkdir(parents=True)
    (path / RUN_ID / "report.json").write_text("{}", encoding="utf-8")
    yield path


@pytest.fixture
def throttled_client(throttled_runs_dir: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("PW_ACCESS_CODE", ACCESS_CODE)
    limiter = RateLimiter(capacity=2, refill_per_s=0.0)
    return TestClient(create_app(runs_dir=throttled_runs_dir, rate_limiter=limiter))


@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_protected_routes_require_the_access_code(
    client: TestClient, method: str, path: str
) -> None:
    response = client.request(method, path)

    assert response.status_code == 401
    assert response.json() == {"error": {"code": "E-05", "message": "Access code required."}}


@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_a_wrong_code_is_rejected(client: TestClient, method: str, path: str) -> None:
    response = client.request(method, path, headers={"X-Access-Code": "nope"})

    assert response.status_code == 401


def test_healthz_is_the_only_public_route(client: TestClient) -> None:
    assert client.get("/healthz").status_code == 200
    assert client.get("/runs").status_code == 401


def test_run_creation_is_rate_limited_with_a_retry_hint(
    throttled_client: TestClient, scratch: Path
) -> None:
    clip = scratch / "clip.mp4"
    clip.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)
    body = {"sop_text": "1. Tighten the bolt.\n"}

    first = throttled_client.post(
        "/runs",
        files={"video": ("clip.mp4", clip.read_bytes(), "video/mp4")},
        data=body,
        headers=HEADERS,
    )
    assert first.status_code in {202, 415, 422}

    statuses = [
        throttled_client.post(
            "/runs",
            files={"video": ("clip.mp4", clip.read_bytes(), "video/mp4")},
            data=body,
            headers=HEADERS,
        )
        for _ in range(3)
    ]
    limited = [response for response in statuses if response.status_code == 429]

    assert limited, [response.status_code for response in statuses]
    assert limited[0].json()["error"]["code"] == "E-05"
    assert "Retry-After" in limited[0].headers

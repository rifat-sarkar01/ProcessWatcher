"""Header hardening (TRD §8) and privacy/retention controls (NFR-05).

F-10 (headers) and F-09 (scratch cleanup) are fixed and covered here; F-13 (Pillow
advisories) stays a documented, tooling-level gap in docs/security/audit.md.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pw.security.redact import PLACEHOLDER, redact, redact_mapping
from pw.security.retention import RETENTION_S, purge_expired

HEADERS = {"X-Access-Code": "audit-access-code"}


def test_healthz_is_public_and_says_nothing_else(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert len(response.content) < 64


@pytest.mark.parametrize("path", ["/healthz", "/runs"])
def test_responses_carry_nosniff(client: TestClient, path: str) -> None:
    assert client.get(path).headers.get("x-content-type-options") == "nosniff"


@pytest.mark.parametrize("path", ["/healthz", "/runs"])
def test_responses_carry_a_referrer_policy(client: TestClient, path: str) -> None:
    assert client.get(path).headers.get("referrer-policy") == "no-referrer"


def test_responses_carry_a_content_security_policy(client: TestClient) -> None:
    policy = client.get("/healthz").headers.get("content-security-policy", "")

    assert "default-src 'self'" in policy
    assert "img-src 'self' data: blob:" in policy
    assert "media-src 'self' blob:" in policy
    assert "style-src 'self' 'unsafe-inline'" in policy


def test_security_headers_cover_streamed_responses(client: TestClient, runs_dir: Path) -> None:
    run_id = "run_01J9ZQ8M3K4V7B2C5D6E8F0GHJ"
    run = runs_dir / run_id
    (run / "stages").mkdir(parents=True)
    for artifact in (
        "ingest.json",
        "step_graph.json",
        "tracks.json",
        "timeline.json",
        "identities.json",
        "likelihoods.json",
        "alignment.json",
        "deviations.json",
        "verify.json",
        "evidence.json",
        "illustrations.json",
    ):
        (run / "stages" / artifact).write_text("{}", encoding="utf-8")
    (run / "report.json").write_text("{}", encoding="utf-8")

    response = client.get(f"/runs/{run_id}/events", headers=HEADERS)

    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("content-security-policy")


def test_no_cors_wildcard_is_granted(client: TestClient) -> None:
    response = client.get("/healthz", headers={"Origin": "https://evil.example"})

    assert "access-control-allow-origin" not in response.headers


def test_secrets_are_redacted_in_log_lines() -> None:
    line = (
        "META_API_KEY =placeholderone Authorization: Bearer plaintoken "
        'pw_access_code="placeholderthree" {"api_key": "placeholderfour"}'
    )
    cleaned = redact(line)

    for secret in ("placeholderone", "plaintoken", "placeholderthree", "placeholderfour"):
        assert secret not in cleaned
    assert cleaned.count(PLACEHOLDER) == 4


def test_structured_payloads_are_redacted_without_changing_shape() -> None:
    payload = {
        "run_id": "run_1",
        "headers": {"X-Access-Code": "secret", "Accept": "application/json"},
        "nested": [{"meta_api_key": "k"}],
        "note": "Authorization=Bearer abc",
    }

    cleaned = redact_mapping(payload)

    assert cleaned["run_id"] == "run_1"
    assert set(cleaned) == set(payload)
    assert cleaned["headers"]["X-Access-Code"] == PLACEHOLDER
    assert cleaned["headers"]["Accept"] == "application/json"
    assert cleaned["nested"][0]["meta_api_key"] == PLACEHOLDER
    assert "abc" not in cleaned["note"]


def test_retention_purges_media_but_keeps_exempt_demo_cases(scratch: Path) -> None:
    runs = scratch / "retention"
    old = runs / "run_old"
    fresh = runs / "run_fresh"
    demo = runs / "demo_cases"
    for root in (old, fresh, demo):
        (root / "media").mkdir(parents=True)
        (root / "media" / "analysis.mp4").write_bytes(b"pixels")

    now = time.time()
    stale = now - RETENTION_S - 60
    for root in (old, demo):
        for path in [root, root / "media", root / "media" / "analysis.mp4"]:
            _set_mtime(path, stale)

    purged = purge_expired(runs, now=now, exempt=[demo])

    assert purged == ["run_old"]
    assert not old.exists()
    assert fresh.exists()
    assert (demo / "media" / "analysis.mp4").is_file()


def _set_mtime(path: Path, moment: float) -> None:
    import os

    os.utime(path, (moment, moment))

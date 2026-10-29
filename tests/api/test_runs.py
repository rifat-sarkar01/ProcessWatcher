"""Runs API: upload, background fake run, report, artifact Range and guards."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pw.security.ratelimit import RateLimiter
from pw.security.uploads import UploadCaps

ACCESS = {"X-Access-Code": "test-access-code"}
UNKNOWN_RUN = "run_01J9ZQ8M3K4V7B2C5D6E8F0GHJ"


def upload(
    client: TestClient,
    video: Path,
    *,
    sop_text: str | None = "1. Tighten.\n",
    filename: str | None = None,
) -> Any:
    with video.open("rb") as handle:
        files = {"video": (filename or video.name, handle, "video/mp4")}
        data = {"sop_text": sop_text} if sop_text is not None else {}
        return client.post("/runs", files=files, data=data, headers=ACCESS)


def test_create_run_returns_202_and_completes(client: TestClient, clip: Path) -> None:
    response = upload(client, clip)
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    run_id = body["run_id"]

    detail = client.get(f"/runs/{run_id}", headers=ACCESS)
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["run_id"] == run_id
    assert payload["status"] == "done"
    assert len(payload["stages"]) == 12
    assert all(stage["status"] == "done" for stage in payload["stages"])

    report = client.get(f"/runs/{run_id}/report", headers=ACCESS)
    assert report.status_code == 200
    assert report.json()["run_id"] == run_id


def test_list_runs(client: TestClient, clip: Path) -> None:
    run_id = upload(client, clip).json()["run_id"]
    listing = client.get("/runs", headers=ACCESS)
    assert listing.status_code == 200
    assert [item["run_id"] for item in listing.json()] == [run_id]


def test_access_code_is_required_on_every_run_route(client: TestClient, clip: Path) -> None:
    assert client.get("/runs").status_code == 401
    assert client.get(f"/runs/{UNKNOWN_RUN}").status_code == 401
    assert client.get(f"/runs/{UNKNOWN_RUN}/report").status_code == 401
    assert client.get(f"/runs/{UNKNOWN_RUN}/artifacts/media/x.mp4").status_code == 401
    with clip.open("rb") as handle:
        denied = client.post("/runs", files={"video": (clip.name, handle, "video/mp4")})
    assert denied.status_code == 401
    assert denied.json()["error"]["code"] == "E-05"
    wrong = client.get("/runs", headers={"X-Access-Code": "wrong"})
    assert wrong.status_code == 401


def test_healthz_stays_public(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}


def test_unknown_run_is_404(client: TestClient) -> None:
    missing = client.get(f"/runs/{UNKNOWN_RUN}", headers=ACCESS)
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "E-13"
    assert client.get("/runs/not-a-run", headers=ACCESS).status_code == 404


def test_report_is_409_while_running(client: TestClient, runs_dir: Path) -> None:
    (runs_dir / UNKNOWN_RUN / "stages").mkdir(parents=True)
    (runs_dir / UNKNOWN_RUN / "stages" / "ingest.json").write_text("{}", encoding="utf-8")
    response = client.get(f"/runs/{UNKNOWN_RUN}/report", headers=ACCESS)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "E-07"


def test_artifact_serving_supports_range(client: TestClient, clip: Path, runs_dir: Path) -> None:
    run_id = upload(client, clip).json()["run_id"]
    (runs_dir / run_id / "media" / "analysis.mp4").write_bytes(b"0123456789")

    full = client.get(f"/runs/{run_id}/artifacts/media/analysis.mp4", headers=ACCESS)
    assert full.status_code == 200
    assert full.content == b"0123456789"

    ranged = client.get(
        f"/runs/{run_id}/artifacts/media/analysis.mp4",
        headers={**ACCESS, "Range": "bytes=2-5"},
    )
    assert ranged.status_code == 206
    assert ranged.content == b"2345"
    assert ranged.headers["content-range"] == "bytes 2-5/10"


def test_artifact_traversal_and_raw_inputs_are_blocked(
    client: TestClient, clip: Path, runs_dir: Path
) -> None:
    run_id = upload(client, clip).json()["run_id"]
    for path in (
        "../secret.txt",
        "..%2F..%2Fsecret.txt",
        "evidence/..%2F..%2Fsecret.txt",
        "input/video.mp4",
        "stages/ingest.json",
    ):
        response = client.get(f"/runs/{run_id}/artifacts/{path}", headers=ACCESS)
        assert response.status_code == 404, path


def test_wrong_magic_is_415(client: TestClient, runs_dir: Path) -> None:
    fake = runs_dir / "fake.mp4"
    fake.write_text("not a video", encoding="utf-8")
    response = upload(client, fake)
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "E-01"


def test_size_cap_is_413(make_client: Any, clip: Path) -> None:
    client = make_client(caps=UploadCaps(max_bytes=100))
    response = upload(client, clip)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "E-03"


def test_duration_cap_is_422(make_client: Any, clip: Path) -> None:
    client = make_client(caps=UploadCaps(max_duration_s=0.1))
    response = upload(client, clip)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "E-02"


def test_missing_sop_is_422(client: TestClient, clip: Path) -> None:
    response = upload(client, clip, sop_text=None)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "E-04"


def test_sop_file_is_accepted(client: TestClient, clip: Path, runs_dir: Path) -> None:
    sop = runs_dir / "steps.md"
    sop.write_text("# Steps\n\n1. Tighten.\n", encoding="utf-8")
    with clip.open("rb") as video, sop.open("rb") as sop_handle:
        response = client.post(
            "/runs",
            files={
                "video": (clip.name, video, "video/mp4"),
                "sop": ("steps.md", sop_handle, "text/markdown"),
            },
            headers=ACCESS,
        )
    assert response.status_code == 202


def test_rate_limit_is_429_with_retry_after(make_client: Any, clip: Path) -> None:
    client = make_client(limiter=RateLimiter(capacity=1, refill_per_s=0.0))
    assert upload(client, clip).status_code == 202
    limited = upload(client, clip)
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "E-05"
    assert "retry-after" in {key.lower() for key in limited.headers}


def test_concurrent_runs_are_independent(client: TestClient, clip: Path) -> None:
    first = upload(client, clip).json()["run_id"]
    second = upload(client, clip).json()["run_id"]
    assert first != second
    for run_id in (first, second):
        detail = client.get(f"/runs/{run_id}", headers=ACCESS)
        assert detail.json()["status"] == "done"
    assert len(client.get("/runs", headers=ACCESS).json()) == 2


@pytest.mark.parametrize("path", ["/runs", "/runs/{run_id}"])
def test_openapi_includes_run_routes(client: TestClient, path: str) -> None:
    schema = client.app.openapi()
    assert path in schema["paths"]

"""API fixtures: a tiny real clip, a scratch runs dir and an authenticated client."""

from __future__ import annotations

import shutil
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pw.api.main import create_app
from pw.security.ratelimit import RateLimiter
from pw.security.uploads import UploadCaps

SCRATCH_ROOT = Path(__file__).resolve().parents[2] / ".uv" / "tests-tmp"
ACCESS_CODE = "test-access-code"
HEADERS = {"X-Access-Code": ACCESS_CODE}


def _ffmpeg(*args: str) -> None:
    completed = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
        shell=False,
    )
    if completed.returncode != 0:  # pragma: no cover - fixture failure
        raise RuntimeError(f"ffmpeg failed: {completed.stderr.strip()}")


@pytest.fixture(scope="session")
def clip() -> Iterator[Path]:
    root = SCRATCH_ROOT / f"api-media-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    target = root / "clip.mp4"
    _ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "testsrc=d=1:s=320x240:r=15",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(target),
    )
    try:
        yield target
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def runs_dir() -> Iterator[Path]:
    path = SCRATCH_ROOT / f"api-runs-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def client(runs_dir: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("PW_ACCESS_CODE", ACCESS_CODE)
    return TestClient(create_app(runs_dir=runs_dir))


@pytest.fixture
def make_client(runs_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator:
    monkeypatch.setenv("PW_ACCESS_CODE", ACCESS_CODE)

    def factory(
        *,
        caps: UploadCaps | None = None,
        limiter: RateLimiter | None = None,
    ) -> TestClient:
        return TestClient(create_app(runs_dir=runs_dir, caps=caps, rate_limiter=limiter))

    yield factory


def upload(client: TestClient, video: Path, *, sop_text: str | None = "1. Tighten.\n"):
    with video.open("rb") as handle:
        files = {"video": (video.name, handle, "video/mp4")}
        data = {"sop_text": sop_text} if sop_text is not None else {}
        return client.post("/runs", files=files, data=data, headers=HEADERS)

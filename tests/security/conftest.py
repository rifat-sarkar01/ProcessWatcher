"""A tiny real video for upload validation (ffmpeg-generated, never committed)."""

from __future__ import annotations

import shutil
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

SCRATCH_ROOT = Path(__file__).resolve().parents[2] / ".uv" / "tests-tmp"


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


@pytest.fixture
def scratch() -> Iterator[Path]:
    path = SCRATCH_ROOT / f"security-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def run_dir(scratch: Path) -> Path:
    root = scratch / "runs" / "run_01J9ZQ8M3K4V7B2C5D6E8F0GHJ"
    for name in ("input", "stages", "media", "evidence", "illustrations"):
        (root / name).mkdir(parents=True)
    (root / "input" / "video.mp4").write_bytes(b"raw upload")
    (root / "stages" / "ingest.json").write_text("{}", encoding="utf-8")
    (root / "report.json").write_text("{}", encoding="utf-8")
    return root


@pytest.fixture(scope="session")
def video() -> Iterator[Path]:
    root = SCRATCH_ROOT / f"security-media-{uuid.uuid4().hex}"
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

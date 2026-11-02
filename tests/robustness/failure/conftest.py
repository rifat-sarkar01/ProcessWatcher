"""Failure-injection fixtures: a tiny clip, isolated run directories, no real waits."""

from __future__ import annotations

import shutil
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRATCH_ROOT = ROOT / ".uv" / "tests-tmp"


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
def tiny_video() -> Iterator[Path]:
    path = SCRATCH_ROOT / f"failure-media-{uuid.uuid4().hex}" / "tiny.mp4"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "testsrc=d=2:s=320x240:r=15",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(path),
    )
    try:
        yield path
    finally:
        shutil.rmtree(path.parent, ignore_errors=True)


@pytest.fixture(scope="session")
def tiny_sop() -> Path:
    return ROOT / "tests" / "fixtures" / "tiny_sop.md"


@pytest.fixture
def scratch() -> Iterator[Path]:
    path = SCRATCH_ROOT / f"failure-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)

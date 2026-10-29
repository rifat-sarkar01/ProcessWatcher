"""Walking-skeleton fixtures: a 2 s clip and a tiny SOP, generated locally.

`tests/fixtures/tiny.mp4` is also the input of the CI skeleton step, so the media
fixture writes it into the repo (nothing binary is committed) once per session.
"""

from __future__ import annotations

import shutil
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRATCH_ROOT = ROOT / ".uv" / "tests-tmp"
FIXTURES = ROOT / "tests" / "fixtures"


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
def tiny_video() -> Path:
    target = FIXTURES / "tiny.mp4"
    if not target.exists():
        FIXTURES.mkdir(parents=True, exist_ok=True)
        _ffmpeg(
            "-f",
            "lavfi",
            "-i",
            "testsrc=d=2:s=320x240:r=15",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(target),
        )
    return target


@pytest.fixture(scope="session")
def tiny_sop() -> Path:
    return FIXTURES / "tiny_sop.md"


@pytest.fixture
def runs_dir() -> Iterator[Path]:
    path = SCRATCH_ROOT / f"runs-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)

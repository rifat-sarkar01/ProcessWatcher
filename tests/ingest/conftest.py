"""Media fixtures for ingest tests, generated with ffmpeg at session scope.

Nothing binary is committed: every fixture is a lavfi source or a decoded copy, so the
suite stays reproducible on any machine with ffmpeg on PATH.
"""

from __future__ import annotations

import shutil
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

SCRATCH_ROOT = Path(__file__).resolve().parents[2] / ".uv" / "tests-tmp"


def ffmpeg(*args: str) -> None:
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
    """Repo-local scratch directory (pytest tmp_path is unusable on this host)."""
    path = SCRATCH_ROOT / f"ingest-out-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(scope="session")
def media() -> Iterator[dict[str, Path]]:
    root = SCRATCH_ROOT / f"ingest-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    try:
        files: dict[str, Path] = {}

        cfr = root / "cfr_30fps.mp4"
        ffmpeg(
            "-f",
            "lavfi",
            "-i",
            "testsrc=d=2:s=320x240:r=30",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(cfr),
        )
        files["cfr"] = cfr

        # Genuine VFR: 1 s at 30 fps concatenated with 1 s at 10 fps. Re-encoding with
        # `-fps_mode vfr` keeps both timestamp grids, so inter-frame gaps are 1/30 s and
        # 1/10 s in the same file - the phone-video case the pipeline must survive.
        first = root / "vfr_part1.mp4"
        second = root / "vfr_part2.mp4"
        ffmpeg(
            "-f",
            "lavfi",
            "-i",
            "testsrc=d=1:s=320x240:r=30",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(first),
        )
        ffmpeg(
            "-f",
            "lavfi",
            "-i",
            "testsrc=d=1:s=320x240:r=10",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(second),
        )
        listing = root / "concat.txt"
        listing.write_text(
            f"file '{first.as_posix()}'\nfile '{second.as_posix()}'\n", encoding="utf-8"
        )
        vfr = root / "vfr_phone.mp4"
        ffmpeg(
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-fps_mode",
            "vfr",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(vfr),
        )
        files["vfr"] = vfr

        tall = root / "tall.mp4"
        ffmpeg(
            "-f",
            "lavfi",
            "-i",
            "testsrc=d=1:s=480x960:r=15",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(tall),
        )
        files["tall"] = tall

        long_clip = root / "long.mp4"
        ffmpeg(
            "-f",
            "lavfi",
            "-i",
            "testsrc=d=181:s=64x64:r=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(long_clip),
        )
        files["long"] = long_clip

        audio_only = root / "audio_only.mp4"
        ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:a", "aac", str(audio_only))
        files["audio_only"] = audio_only

        corrupt = root / "corrupt.mp4"
        corrupt.write_bytes(b"this is definitely not a video")
        files["corrupt"] = corrupt

        weird = root / "evil & calc $(id) `rm -rf` .mp4"
        shutil.copy2(cfr, weird)
        files["weird_name"] = weird

        yield files
    finally:
        shutil.rmtree(root, ignore_errors=True)

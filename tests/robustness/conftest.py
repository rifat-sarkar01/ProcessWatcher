"""Robustness fixtures: legal but hostile media, generated with ffmpeg.

Nothing binary is committed. Camera shake, low light and variable frame rate are
synthesised with ffmpeg filters; the semantic cases (no hands, heavy occlusion,
mismatched SOP, repeated step) act on the aligner directly, because that is the
module that has to degrade gracefully when the perception stack is starved.
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
    """Repo-local scratch directory (`tmp_path` is unusable on this host)."""
    path = SCRATCH_ROOT / f"robust-out-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(scope="session")
def clips() -> Iterator[dict[str, Path]]:
    root = SCRATCH_ROOT / f"robust-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    try:
        files: dict[str, Path] = {}

        shaky = root / "shaky.mp4"
        ffmpeg(
            "-f",
            "lavfi",
            "-i",
            "testsrc=d=3:s=320x240:r=30",
            "-vf",
            "rotate=0.02*sin(2*PI*t)",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(shaky),
        )
        files["shaky"] = shaky

        dark = root / "dark.mp4"
        ffmpeg(
            "-f",
            "lavfi",
            "-i",
            "testsrc=d=2:s=320x240:r=30",
            "-vf",
            "eq=brightness=-0.35:contrast=0.8",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(dark),
        )
        files["dark"] = dark

        # A genuine VFR file: 1 s at 30 fps followed by 1 s at 10 fps, kept on
        # separate timestamp grids by `-fps_mode vfr` (the phone-video case).
        first = root / "vfr_30.mp4"
        second = root / "vfr_10.mp4"
        for target, rate in ((first, 30), (second, 10)):
            ffmpeg(
                "-f",
                "lavfi",
                "-i",
                f"testsrc=d=1:s=320x240:r={rate}",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(target),
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

        three_minutes = root / "three_minutes.mp4"
        ffmpeg(
            "-f",
            "lavfi",
            "-i",
            "testsrc=d=180:s=64x64:r=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(three_minutes),
        )
        files["three_minutes"] = three_minutes

        overlong = root / "overlong.mp4"
        ffmpeg(
            "-f",
            "lavfi",
            "-i",
            "testsrc=d=181:s=64x64:r=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(overlong),
        )
        files["overlong"] = overlong

        yield files
    finally:
        shutil.rmtree(root, ignore_errors=True)

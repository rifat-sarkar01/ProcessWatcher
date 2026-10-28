"""Normalise a source video for analysis: constant frame rate, <= 720p, silent.

The pipeline analyses a CFR copy so frame → time is unambiguous, but time itself is
still read from PTS values (see `timebase.py`). Audio is dropped: nothing downstream
uses it.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pw.ingest.errors import FileTooLarge, ProbeError, VideoTooLong
from pw.ingest.probe import VideoInfo, probe_video

DEFAULT_FPS = 15
MAX_HEIGHT = 720
MAX_DURATION_S = 180.0
MAX_BYTES = 500 * 1024 * 1024
NORMALISE_TIMEOUT_S = 600
HASH_CHUNK_BYTES = 1024 * 1024


def sha256_file(path: Path | str) -> str:
    """SHA-256 of a file, streamed in 1 MiB chunks."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_source(path: Path | str, info: VideoInfo) -> None:
    """Enforce the caps from 04_TRD §7 `limits` before any transcoding work."""
    size = Path(path).stat().st_size
    if size > MAX_BYTES:
        raise FileTooLarge(
            f"video is {size / (1024 * 1024):.1f} MB, the limit is {MAX_BYTES // (1024 * 1024)} MB"
        )
    if info.duration_s > MAX_DURATION_S:
        raise VideoTooLong(f"video is {info.duration_s:.1f} s, the limit is {MAX_DURATION_S:g} s")


@dataclass(frozen=True, slots=True)
class NormalisedVideo:
    """Result of a normalisation run."""

    path: Path
    source_sha256: str
    info: VideoInfo
    fps: int


def _scale_filter(info: VideoInfo, fps: int, max_height: int) -> str:
    filters = [f"fps={fps}"]
    if info.display_height > max_height:
        filters.append(f"scale=-2:{max_height}")
    return ",".join(filters)


def normalise_video(
    source: Path | str,
    destination: Path | str,
    *,
    fps: int = DEFAULT_FPS,
    max_height: int = MAX_HEIGHT,
) -> NormalisedVideo:
    """Write a CFR, <= `max_height`, audio-free copy and probe the result."""
    src = Path(source)
    info = probe_video(src)
    validate_source(src, info)

    out = Path(destination)
    out.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-i",
        str(src),
        "-vf",
        _scale_filter(info, fps, max_height),
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(out),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=NORMALISE_TIMEOUT_S,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - host timing
        raise ProbeError(f"ffmpeg timed out after {NORMALISE_TIMEOUT_S} s") from exc

    if completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()
        raise ProbeError(detail[-1] if detail else "ffmpeg failed to normalise the video")

    return NormalisedVideo(
        path=out,
        source_sha256=sha256_file(src),
        info=probe_video(out),
        fps=fps,
    )


def extract_keyframes(
    source: Path | str,
    times_s: list[float],
    destination_dir: Path | str,
    *,
    prefix: str = "frame",
) -> list[Path]:
    """Extract one PNG per requested timestamp (seconds)."""
    src = Path(source)
    out_dir = Path(destination_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for index, seconds in enumerate(times_s):
        target = out_dir / f"{prefix}_{index:03d}.png"
        command = [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-ss",
            f"{max(seconds, 0.0):.3f}",
            "-i",
            str(src),
            "-frames:v",
            "1",
            str(target),
        ]
        completed = subprocess.run(
            command, capture_output=True, text=True, check=False, timeout=60, shell=False
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip().splitlines()
            raise ProbeError(detail[-1] if detail else f"could not extract frame at {seconds} s")
        written.append(target)
    return written

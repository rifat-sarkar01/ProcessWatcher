"""ffprobe wrapper: one typed `VideoInfo` for a source file.

ffmpeg/ffprobe are always invoked with an argument list and **never** through a
shell, so a hostile filename can never become a command (AGENTS.md §15).
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from pw.ingest.errors import NoVideoStream, ProbeError

PROBE_TIMEOUT_S = 60


@dataclass(frozen=True, slots=True)
class VideoInfo:
    """What the pipeline needs to know about a source before touching pixels."""

    width: int
    height: int
    duration_s: float
    fps: float
    rotation: float = 0.0
    codec: str = ""
    has_audio: bool = False
    frame_count: int | None = None

    @property
    def display_width(self) -> int:
        """Width as a viewer sees it (rotation by 90/270 swaps the stored axes)."""
        return self.height if self.is_quarter_turned else self.width

    @property
    def display_height(self) -> int:
        return self.width if self.is_quarter_turned else self.height

    @property
    def is_quarter_turned(self) -> bool:
        return round(abs(self.rotation)) % 180 == 90


def _run(command: list[str], *, timeout_s: int = PROBE_TIMEOUT_S) -> str:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_s,
            shell=False,
        )
    except FileNotFoundError as exc:  # pragma: no cover - ffprobe is a host dependency
        raise ProbeError(f"{command[0]} is not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise ProbeError(f"{command[0]} timed out after {timeout_s} s") from exc

    if completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()
        reason = detail[-1] if detail else f"exit code {completed.returncode}"
        raise ProbeError(f"could not read media: {reason}")
    return completed.stdout


def _parse_rate(raw: object) -> float:
    if not isinstance(raw, str) or not raw or raw == "0/0":
        return 0.0
    try:
        return float(Fraction(raw))
    except (ValueError, ZeroDivisionError):
        return 0.0


def _parse_rotation(stream: dict[str, Any]) -> float:
    for side_data in stream.get("side_data_list", []):
        if isinstance(side_data, dict) and "rotation" in side_data:
            try:
                return float(side_data["rotation"])
            except (TypeError, ValueError):
                continue
    tags = stream.get("tags", {})
    if isinstance(tags, dict) and "rotate" in tags:
        try:
            return float(tags["rotate"])
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def parse_probe(payload: dict[str, Any]) -> VideoInfo:
    """Turn an `ffprobe -show_streams -show_format` payload into `VideoInfo`."""
    streams = payload.get("streams", [])
    if not isinstance(streams, list):
        raise ProbeError("ffprobe payload has no streams list")

    video = next(
        (
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "video"
        ),
        None,
    )
    if video is None:
        raise NoVideoStream("the file has no video stream")

    fmt = payload.get("format", {})
    duration = 0.0
    for raw in (video.get("duration"), fmt.get("duration") if isinstance(fmt, dict) else None):
        if raw is None:
            continue
        try:
            duration = float(raw)
        except (TypeError, ValueError):
            continue
        if duration > 0:
            break

    frame_count: int | None = None
    try:
        frame_count = int(video["nb_frames"])
    except (KeyError, TypeError, ValueError):
        frame_count = None

    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    if width <= 0 or height <= 0:
        raise ProbeError("video stream reports no usable dimensions")

    return VideoInfo(
        width=width,
        height=height,
        duration_s=duration,
        fps=_parse_rate(video.get("avg_frame_rate")) or _parse_rate(video.get("r_frame_rate")),
        rotation=_parse_rotation(video),
        codec=str(video.get("codec_name", "")),
        has_audio=any(
            isinstance(stream, dict) and stream.get("codec_type") == "audio" for stream in streams
        ),
        frame_count=frame_count,
    )


def probe_video(path: Path | str) -> VideoInfo:
    """Probe one media file. Raises `ProbeError` / `NoVideoStream` on bad input."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"video not found: {source}")

    payload = json.loads(
        _run(
            [
                "ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_streams",
                "-show_format",
                str(source),
            ]
        )
    )
    return parse_probe(payload)

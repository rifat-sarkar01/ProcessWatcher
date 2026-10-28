"""Render a 3-5 s overlay clip around a deviation.

The clip is cut from the analysis copy with an input seek so only the requested
window is decoded, then each frame is drawn with the tracked masks and an absolute
timestamp and re-encoded at the analysis frame rate. ffmpeg is always invoked with
an argument list (never a shell).
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from pw.evidence.render import FrameOverlay, draw_timestamp, render_overlay
from pw.ingest import probe_video, pts_times

ENCODE_TIMEOUT_S = 600
CLIP_MIN_S = 3.0
CLIP_MAX_S = 5.0
PAD_S = 0.5


class ClipError(Exception):
    """The clip window is invalid or ffmpeg could not cut/encode it."""


@dataclass(frozen=True, slots=True)
class ClipResult:
    path: Path
    t_start: float
    t_end: float
    frames: int


def clip_window(
    t_start: float,
    t_end: float,
    *,
    duration: float | None = None,
    min_s: float = CLIP_MIN_S,
    max_s: float = CLIP_MAX_S,
    pad_s: float = PAD_S,
) -> tuple[float, float]:
    """Window that brackets the deviation with padding, clamped to 3-5 s."""
    if not (0.0 <= t_start <= t_end):
        raise ClipError(f"invalid deviation window: {t_start}-{t_end}")
    if min_s <= 0 or max_s < min_s or pad_s < 0:
        raise ClipError(f"invalid clip bounds: min={min_s} max={max_s} pad={pad_s}")

    length = min(max((t_end - t_start) + 2 * pad_s, min_s), max_s)
    if duration is not None:
        if duration < 0:
            raise ClipError(f"negative video duration: {duration}")
        length = min(length, duration)
        start = min(max((t_start + t_end) / 2 - length / 2, 0.0), max(0.0, duration - length))
    else:
        start = max((t_start + t_end) / 2 - length / 2, 0.0)
    return (round(start, 6), round(start + length, 6))


def _first_target_index(times: Sequence[float], start: float) -> int:
    for index, t in enumerate(times):
        if t >= start - 1e-6:
            return index
    return len(times)


def render_clip(
    source: Path,
    destination: Path,
    *,
    window: tuple[float, float],
    overlays: Mapping[int, Sequence[FrameOverlay]] | None = None,
    fps: float | None = None,
) -> ClipResult:
    """Cut `window` out of `source` and burn masks and timestamps onto every frame."""
    start, end = window
    if end <= start:
        raise ClipError(f"empty clip window: {window}")
    info = probe_video(source)
    rate = fps if fps is not None else info.fps
    if rate <= 0:
        raise ClipError(f"analysis video has no frame rate: {info.fps}")

    times = sorted(pts_times(source))
    offset = _first_target_index(times, start)
    wanted = dict(overlays or {})

    frame_bytes = info.width * info.height * 3
    decoder = subprocess.Popen(
        [
            "ffmpeg",
            "-v",
            "error",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{end - start:.3f}",
            "-i",
            str(source),
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoder = subprocess.Popen(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{info.width}x{info.height}",
            "-r",
            f"{rate:g}",
            "-i",
            "-",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(destination),
        ],
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
    )
    assert decoder.stdout is not None
    assert decoder.stderr is not None
    assert encoder.stdin is not None
    assert encoder.stderr is not None

    count = 0
    error: ClipError | None = None
    try:
        while True:
            buffer = decoder.stdout.read(frame_bytes)
            if len(buffer) < frame_bytes:
                break
            index = offset + count
            image = Image.frombytes("RGB", (info.width, info.height), buffer)
            drawn = render_overlay(image, wanted.get(index, ()))
            t = times[index] if index < len(times) else start + count / rate
            encoder.stdin.write(draw_timestamp(drawn, t).tobytes())
            count += 1
    except BrokenPipeError as exc:
        error = ClipError("ffmpeg encoder stopped early")
        error.__cause__ = exc
    finally:
        encoder.stdin.close()
        encoder.wait(timeout=ENCODE_TIMEOUT_S)
        decoder.stdout.close()
        decoder.wait(timeout=ENCODE_TIMEOUT_S)
        decode_stderr = decoder.stderr.read().decode("utf-8", "replace").strip()
        encode_stderr = encoder.stderr.read().decode("utf-8", "replace").strip()

    if error is not None:
        raise error
    if decoder.returncode != 0:
        raise ClipError(decode_stderr or "ffmpeg could not decode the analysis video")
    if encoder.returncode != 0:
        raise ClipError(encode_stderr or "ffmpeg could not encode the clip")
    if count == 0:
        raise ClipError(f"no frames decoded in window {start:.3f}-{end:.3f}")
    return ClipResult(path=destination, t_start=start, t_end=end, frames=count)


__all__ = ["CLIP_MAX_S", "CLIP_MIN_S", "ClipError", "ClipResult", "clip_window", "render_clip"]

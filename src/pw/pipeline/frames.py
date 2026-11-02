"""Frame access for the real stages: decode one analysis frame by index, cached.

Identity crops, scorer keyframes and evidence selection all ask for frame indices, so
one provider serves all three. Decoding uses ffmpeg with an argument list (never a
shell) and a PNG pipe, so no temporary files accumulate.
"""

from __future__ import annotations

import io
import subprocess
from pathlib import Path

from PIL import Image

DECODE_TIMEOUT_S = 120


class FrameDecodeError(RuntimeError):
    """ffmpeg could not return the requested frame."""


class VideoFrames:
    """Callable frame provider over one normalised analysis video."""

    def __init__(self, path: Path, *, limit: int = 4096) -> None:
        self.path = Path(path)
        self.limit = limit
        self._cache: dict[int, Image.Image] = {}

    def __call__(self, frame_index: int) -> Image.Image | None:
        if frame_index < 0:
            return None
        cached = self._cache.get(frame_index)
        if cached is not None:
            return cached
        if len(self._cache) >= self.limit:
            self._cache.clear()
        command = [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(self.path),
            "-vf",
            f"select=eq(n\\,{frame_index})",
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-c:v",
            "png",
            "-",
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                check=False,
                timeout=DECODE_TIMEOUT_S,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if completed.returncode != 0 or not completed.stdout:
            return None
        try:
            image = Image.open(io.BytesIO(completed.stdout)).convert("RGB")
        except OSError:
            return None
        self._cache[frame_index] = image
        return image


__all__ = ["DECODE_TIMEOUT_S", "FrameDecodeError", "VideoFrames"]

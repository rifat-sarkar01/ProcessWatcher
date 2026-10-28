"""PTS-based time mapping.

Phone video is variable frame rate, so wall-clock time must come from presentation
timestamps, never from `frame_index / nominal_fps` (AGENTS.md §15). This module keeps
that rule in one place.
"""

from __future__ import annotations

import bisect
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pw.ingest.errors import ProbeError

PTS_TIMEOUT_S = 120


def pts_times(path: Path | str, *, limit: int | None = None) -> list[float]:
    """Presentation timestamps (seconds) of every video frame, in decode order."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"video not found: {source}")

    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "frame=pts_time",
        "-of",
        "csv=p=0",
        str(source),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=PTS_TIMEOUT_S,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - host timing
        raise ProbeError(f"ffprobe timed out after {PTS_TIMEOUT_S} s") from exc

    if completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()
        raise ProbeError(detail[-1] if detail else "ffprobe could not read timestamps")

    times: list[float] = []
    for line in completed.stdout.splitlines():
        raw = line.strip().rstrip(",")
        if not raw or raw.upper() == "N/A":
            continue
        try:
            times.append(float(raw))
        except ValueError:
            continue
        if limit is not None and len(times) >= limit:
            break
    return times


@dataclass(frozen=True, slots=True)
class TimeMap:
    """Frame index → presentation time, built from real PTS values."""

    pts: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.pts) < 2:
            raise ValueError("a time map needs at least two frames")
        if any(later <= earlier for earlier, later in zip(self.pts, self.pts[1:], strict=False)):
            raise ValueError("presentation timestamps must be strictly increasing")

    @property
    def frame_count(self) -> int:
        return len(self.pts)

    @property
    def duration_s(self) -> float:
        return self.pts[-1] - self.pts[0]

    @property
    def effective_fps(self) -> float:
        span = self.duration_s
        return (self.frame_count - 1) / span if span > 0 else 0.0

    @property
    def is_variable(self) -> bool:
        """True when inter-frame gaps differ by more than 5 % from the median gap."""
        gaps = [later - earlier for earlier, later in zip(self.pts, self.pts[1:], strict=False)]
        ordered = sorted(gaps)
        median = ordered[len(ordered) // 2]
        if median <= 0:
            return False
        return max(abs(gap - median) / median for gap in gaps) > 0.05

    def time_of_frame(self, index: int) -> float:
        return self.pts[index] - self.pts[0]

    def frame_at(self, seconds: float) -> int:
        return max(
            0, min(bisect.bisect_right(self.pts, self.pts[0] + seconds) - 1, self.frame_count - 1)
        )


def build_time_map(times: list[float]) -> TimeMap:
    """Normalise absolute PTS values so the clip starts at 0 s."""
    if not times:
        raise ValueError("no presentation timestamps")
    origin = times[0]
    return TimeMap(tuple(round(value - origin, 6) for value in times))

"""Frame-based chunk planning for SAM (ADR-001) and per-concept request planning.

Chunks overlap so stitching (T-2.3) can match objects in shared frames. Lengths are in
frames, never seconds, because the API limit is a frame ceiling. SAM accepts exactly one
noun phrase per request, so each concept is its own request and `hand` is always tracked;
the 16-object cap applies to object-prompt blocks (a later card can group those).
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pw.ingest.normalise import NormalisedVideo
from pw.ingest.timebase import pts_times

HAND_CONCEPT = "hand"
MAX_OBJECTS_PER_REQUEST = 16
# Conservative until ADR-001's file-size ceiling is measured: 10 s at 15 fps.
DEFAULT_FRAMES_PER_CHUNK = 150
DEFAULT_OVERLAP_FRAMES = 15
CUT_TIMEOUT_S = 300


class ChunkingError(ValueError):
    """Invalid chunk parameters, video metadata or a failed ffmpeg cut."""


@dataclass(frozen=True, slots=True)
class ChunkParams:
    frames_per_chunk: int = DEFAULT_FRAMES_PER_CHUNK
    overlap_frames: int = DEFAULT_OVERLAP_FRAMES
    max_objects: int = MAX_OBJECTS_PER_REQUEST
    always_concepts: tuple[str, ...] = (HAND_CONCEPT,)

    def __post_init__(self) -> None:
        if self.frames_per_chunk <= 0:
            raise ChunkingError("frames_per_chunk must be positive")
        if not 0 <= self.overlap_frames < self.frames_per_chunk:
            raise ChunkingError("overlap_frames must be non-negative and smaller than a chunk")
        if not 1 <= self.max_objects <= MAX_OBJECTS_PER_REQUEST:
            raise ChunkingError(f"max_objects must be between 1 and {MAX_OBJECTS_PER_REQUEST}")
        if len(set(self.always_concepts)) > self.max_objects:
            raise ChunkingError("always_concepts cannot exceed max_objects")


@dataclass(frozen=True, slots=True)
class AnalysisVideo:
    path: Path
    fps: float
    times: tuple[float, ...]

    def __post_init__(self) -> None:
        if self.fps <= 0:
            raise ChunkingError("fps must be positive")
        if not self.times:
            raise ChunkingError("times cannot be empty")
        if any(
            later <= earlier for earlier, later in zip(self.times, self.times[1:], strict=False)
        ):
            raise ChunkingError("times must be strictly increasing")

    @property
    def frame_count(self) -> int:
        return len(self.times)

    @classmethod
    def from_normalised(cls, video: NormalisedVideo) -> AnalysisVideo:
        times = tuple(pts_times(video.path))
        if len(times) < 2:
            raise ChunkingError(f"analysis video has {len(times)} frame(s)")
        return cls(path=video.path, fps=float(video.fps), times=times)


@dataclass(frozen=True, slots=True)
class ChunkPlan:
    chunk_id: str
    frame_start: int
    frame_end: int
    t_start: float
    t_end: float

    @property
    def frame_count(self) -> int:
        return self.frame_end - self.frame_start + 1


def plan_chunks(video: AnalysisVideo, params: ChunkParams | None = None) -> tuple[ChunkPlan, ...]:
    settings = params or ChunkParams()
    if video.frame_count <= 0:
        raise ChunkingError("video has no frames")
    step = settings.frames_per_chunk - settings.overlap_frames
    plans: list[ChunkPlan] = []
    start = 0
    last = video.frame_count - 1
    while True:
        end = min(start + settings.frames_per_chunk - 1, last)
        plans.append(
            ChunkPlan(
                chunk_id=f"chk_{len(plans):02d}",
                frame_start=start,
                frame_end=end,
                t_start=video.times[start],
                t_end=video.times[end],
            )
        )
        if end >= last:
            return tuple(plans)
        start += step


def group_concepts(
    concepts: Sequence[str], params: ChunkParams | None = None
) -> tuple[tuple[str, ...], ...]:
    """Build SAM requests for noun-phrase tracking.

    SAM's protocol allows exactly **one noun phrase per request** (a comma-separated
    list matches nothing — verified live on 2026-11-02), so each concept becomes its own
    request; `hand` is always tracked. The 16-object cap applies to object-prompt blocks,
    which a later card can group into one request.
    """
    settings = params or ChunkParams()
    always = tuple(dict.fromkeys(settings.always_concepts))
    ordered = list(always)
    for concept in concepts:
        if concept and concept not in ordered:
            ordered.append(concept)
    if not ordered:
        raise ChunkingError("at least one concept is required")
    return tuple((concept,) for concept in ordered)


def ffmpeg_cut(video: AnalysisVideo, plan: ChunkPlan, destination: Path) -> bytes:
    """Cut exactly `plan.frame_start..plan.frame_end` into a standalone CFR clip."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    selection = (
        f"select='between(n\\,{plan.frame_start}\\,{plan.frame_end})',setpts=N/FRAME_RATE/TB"
    )
    command = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-i",
        str(video.path),
        "-vf",
        selection,
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        f"{video.fps:g}",
        str(destination),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=CUT_TIMEOUT_S,
            shell=False,
        )
    except subprocess.TimeoutExpired as error:
        raise ChunkingError(f"ffmpeg chunk cut timed out after {CUT_TIMEOUT_S} s") from error
    if completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()
        raise ChunkingError(detail[-1] if detail else "ffmpeg could not cut the chunk")
    return destination.read_bytes()


__all__ = [
    "CUT_TIMEOUT_S",
    "DEFAULT_FRAMES_PER_CHUNK",
    "DEFAULT_OVERLAP_FRAMES",
    "HAND_CONCEPT",
    "MAX_OBJECTS_PER_REQUEST",
    "AnalysisVideo",
    "ChunkParams",
    "ChunkPlan",
    "ChunkingError",
    "ffmpeg_cut",
    "group_concepts",
    "plan_chunks",
]

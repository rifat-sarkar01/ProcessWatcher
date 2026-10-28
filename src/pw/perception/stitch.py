"""Stitch per-chunk SAM tracks into persistent global tracks.

Chunks overlap, so the same physical object appears in both raw outputs with different
local ids. Correspondences inside an overlap come from mask/box IoU; a track that
reappears after an occlusion is re-associated by appearance similarity within
`max_gap_s`. Different concepts are never merged. Frame indices are global analysis
frame indices, so overlap frames share indices by construction.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = "1.0.0"
_RASTER = 64
_INF = float("inf")


@dataclass(frozen=True, slots=True)
class ChunkFrame:
    frame: int
    t: float
    box: tuple[float, float, float, float]
    poly: tuple[tuple[float, float], ...] = ()
    score: float = 1.0


@dataclass(frozen=True, slots=True)
class ChunkTrack:
    local_id: str
    concept: str
    frames: tuple[ChunkFrame, ...]

    def __post_init__(self) -> None:
        if not self.frames:
            raise ValueError(f"track {self.local_id!r} has no frames")
        indices = [frame.frame for frame in self.frames]
        if indices != sorted(set(indices)):
            raise ValueError(f"track {self.local_id!r} frames must increase strictly")

    @property
    def first_t(self) -> float:
        return self.frames[0].t

    @property
    def last_t(self) -> float:
        return self.frames[-1].t


@dataclass(frozen=True, slots=True)
class ChunkTracks:
    chunk_id: str
    t_start: float
    t_end: float
    tracks: tuple[ChunkTrack, ...] = ()


AppearanceProvider = Callable[[str, ChunkFrame], Sequence[float]]


@dataclass(frozen=True, slots=True)
class StitchParams:
    iou_threshold: float = 0.3
    appearance_threshold: float = 0.6
    max_gap_s: float = 2.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.iou_threshold <= 1.0:
            raise ValueError(f"iou_threshold out of range: {self.iou_threshold}")
        if not 0.0 <= self.appearance_threshold <= 1.0:
            raise ValueError(f"appearance_threshold out of range: {self.appearance_threshold}")
        if self.max_gap_s < 0:
            raise ValueError(f"max_gap_s must be non-negative: {self.max_gap_s}")


@dataclass
class _WorkingTrack:
    id: str
    concept: str
    frames: dict[int, ChunkFrame] = field(default_factory=dict)
    chunks: list[str] = field(default_factory=list)
    local_ids: list[str] = field(default_factory=list)

    def add(self, chunk_id: str, local_id: str, frames: Sequence[ChunkFrame]) -> None:
        if chunk_id not in self.chunks:
            self.chunks.append(chunk_id)
        if local_id not in self.local_ids:
            self.local_ids.append(local_id)
        for frame in frames:
            current = self.frames.get(frame.frame)
            if current is None or frame.score >= current.score:
                self.frames[frame.frame] = frame


@dataclass(frozen=True, slots=True)
class StitchedTrack:
    id: str
    concept: str
    frames: tuple[ChunkFrame, ...]
    source_chunks: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StitchResult:
    tracks: tuple[StitchedTrack, ...]
    merges: int = 0
    gaps_filled: int = 0
    expected_instances: int | None = None

    @property
    def fragmentation_ratio(self) -> float | None:
        if not self.expected_instances:
            return None
        return round(len(self.tracks) / self.expected_instances, 3)

    def to_artifact(self, *, run_id: str, video: Mapping[str, Any]) -> dict[str, Any]:
        ordered = sorted(self.tracks, key=lambda track: (track.frames[0].t, track.id))
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "video": dict(video),
            "tracks": [
                {
                    "id": track.id,
                    "concept": track.concept,
                    "first_t": track.frames[0].t,
                    "last_t": track.frames[-1].t,
                    "frames": [_frame_payload(frame) for frame in track.frames],
                    "source_chunks": list(track.source_chunks),
                }
                for track in ordered
            ],
        }
        if self.expected_instances is not None:
            payload["stitching"] = {
                "fragmentation_ratio": self.fragmentation_ratio,
                "merges": self.merges,
                "gaps_filled": self.gaps_filled,
            }
        return payload


def _frame_payload(frame: ChunkFrame) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "frame": frame.frame,
        "t": frame.t,
        "box": list(frame.box),
        "score": frame.score,
    }
    if frame.poly:
        payload["poly"] = [list(point) for point in frame.poly]
    return payload


def _box_iou(
    left: tuple[float, float, float, float], right: tuple[float, float, float, float]
) -> float:
    x0 = max(left[0], right[0])
    y0 = max(left[1], right[1])
    x1 = min(left[2], right[2])
    y1 = min(left[3], right[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    intersection = (x1 - x0) * (y1 - y0)
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = left_area + right_area - intersection
    return intersection / union if union > 0 else 0.0


def _polygon_mask(poly: Sequence[tuple[float, float]]) -> set[tuple[int, int]]:
    points = [
        (
            min(_RASTER - 1, max(0, round(x * (_RASTER - 1)))),
            min(_RASTER - 1, max(0, round(y * (_RASTER - 1)))),
        )
        for x, y in poly
    ]
    inside: set[tuple[int, int]] = set()
    if len(points) < 3:
        return inside
    for row in range(_RASTER):
        for column in range(_RASTER):
            # even-odd ray casting on pixel centres
            if _inside(points, column, row):
                inside.add((column, row))
    return inside


def _inside(points: Sequence[tuple[int, int]], x: int, y: int) -> bool:
    result = False
    previous = points[-1]
    for current in points:
        x1, y1 = previous
        x2, y2 = current
        if (y1 > y) != (y2 > y):
            crossing = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < crossing:
                result = not result
        previous = current
    return result


def _frame_iou(left: ChunkFrame, right: ChunkFrame) -> float:
    if len(left.poly) >= 3 and len(right.poly) >= 3:
        left_mask = _polygon_mask(left.poly)
        right_mask = _polygon_mask(right.poly)
        union = len(left_mask | right_mask)
        return len(left_mask & right_mask) / union if union else 0.0
    return _box_iou(left.box, right.box)


def _overlap_iou(left: _WorkingTrack, right: ChunkTrack) -> float:
    shared = [frame.frame for frame in right.frames if frame.frame in left.frames]
    if not shared:
        return 0.0
    scores = [
        _frame_iou(left.frames[frame.frame], frame)
        for frame in right.frames
        if frame.frame in left.frames
    ]
    return sum(scores) / len(scores)


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _assignment(weights: Sequence[Sequence[float]]) -> dict[int, int]:
    """Hungarian assignment maximising weight; returns row -> column for real pairs."""
    rows = len(weights)
    columns = len(weights[0]) if rows else 0
    if rows == 0 or columns == 0:
        return {}
    size = max(rows, columns)
    big = 2.0
    cost = [
        [(1.0 - weights[i][j]) if i < rows and j < columns else big for j in range(size)]
        for i in range(size)
    ]
    result = _hungarian(cost)
    return {
        row: column for row, column in enumerate(result) if row < rows and 0 <= column < columns
    }


def _hungarian(cost: Sequence[Sequence[float]]) -> list[int]:
    n = len(cost)
    u = [0.0] * (n + 1)
    v = [0.0] * (n + 1)
    p = [0] * (n + 1)
    way = [0] * (n + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [_INF] * (n + 1)
        used = [False] * (n + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = _INF
            j1 = 0
            for j in range(1, n + 1):
                if used[j]:
                    continue
                current = cost[i0 - 1][j - 1] - u[i0] - v[j]
                if current < minv[j]:
                    minv[j] = current
                    way[j] = j0
                if minv[j] < delta:
                    delta = minv[j]
                    j1 = j
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    assignment = [-1] * n
    for j in range(1, n + 1):
        if p[j]:
            assignment[p[j] - 1] = j - 1
    return assignment


def stitch_chunks(
    chunks: Sequence[ChunkTracks],
    *,
    params: StitchParams | None = None,
    appearance: AppearanceProvider | None = None,
    expected_instances: int | None = None,
) -> StitchResult:
    """Assign global ids across chunk outputs."""
    settings = params or StitchParams()
    working: list[_WorkingTrack] = []
    merges = 0
    gaps_filled = 0

    for chunk in sorted(chunks, key=lambda item: (item.t_start, item.chunk_id)):
        tracks = sorted(chunk.tracks, key=lambda item: item.local_id)
        active = [
            track
            for track in working
            if chunk.t_start - track.frames[max(track.frames)].t <= settings.max_gap_s
        ]

        weights: list[list[float]] = []
        for previous in active:
            row: list[float] = []
            for candidate in tracks:
                if candidate.concept != previous.concept:
                    row.append(0.0)
                    continue
                row.append(_overlap_iou(previous, candidate))
            weights.append(row)

        assigned: dict[int, int] = {}
        for assigned_row, assigned_column in _assignment(weights).items():
            if weights[assigned_row][assigned_column] >= settings.iou_threshold:
                assigned[assigned_column] = assigned_row
                merges += 1

        for index, candidate in enumerate(tracks):
            if index in assigned:
                previous = active[assigned[index]]
                previous.add(chunk.chunk_id, candidate.local_id, candidate.frames)
                continue

            match: _WorkingTrack | None = None
            if appearance is not None:
                best = 0.0
                for previous in active:
                    if previous.concept != candidate.concept:
                        continue
                    gap = chunk.t_start - previous.frames[max(previous.frames)].t
                    if not 0.0 <= gap <= settings.max_gap_s:
                        continue
                    if any(frame.frame in previous.frames for frame in candidate.frames):
                        continue
                    similarity = _cosine(
                        appearance(previous.id, previous.frames[max(previous.frames)]),
                        appearance(f"{chunk.chunk_id}/{candidate.local_id}", candidate.frames[0]),
                    )
                    if similarity >= settings.appearance_threshold and similarity > best:
                        best = similarity
                        match = previous
            if match is not None:
                match.add(chunk.chunk_id, candidate.local_id, candidate.frames)
                gaps_filled += 1
                continue

            created = _WorkingTrack(
                id=f"trk_{len(working) + 1:03d}",
                concept=candidate.concept,
            )
            created.add(chunk.chunk_id, candidate.local_id, candidate.frames)
            working.append(created)

    stitched = tuple(
        StitchedTrack(
            id=track.id,
            concept=track.concept,
            frames=tuple(track.frames[index] for index in sorted(track.frames)),
            source_chunks=tuple(track.chunks),
        )
        for track in sorted(working, key=lambda item: item.id)
    )
    return StitchResult(
        tracks=stitched,
        merges=merges,
        gaps_filled=gaps_filled,
        expected_instances=expected_instances,
    )


__all__ = [
    "AppearanceProvider",
    "ChunkFrame",
    "ChunkTrack",
    "ChunkTracks",
    "StitchParams",
    "StitchResult",
    "StitchedTrack",
    "stitch_chunks",
]

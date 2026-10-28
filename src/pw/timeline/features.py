"""Hand-object interaction features from stitched tracks.

Contact is the dilated hand mask overlapping the object mask as a fraction of the
object's area (box overlap when polygons are missing). Holds use hysteresis: gaps up to
`bridge_s` are bridged and only runs of at least `hold_on_s` become holds. Object
velocity is normalised by the frame diagonal so it is resolution independent.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

HAND = "hand"
_RASTER = 64


@dataclass(frozen=True, slots=True)
class FrameSample:
    frame: int
    t: float
    box: tuple[float, float, float, float]
    poly: tuple[tuple[float, float], ...] = ()
    score: float = 1.0


@dataclass(frozen=True, slots=True)
class Track:
    id: str
    concept: str
    frames: tuple[FrameSample, ...]

    def __post_init__(self) -> None:
        if not self.frames:
            raise ValueError(f"track {self.id!r} has no frames")
        indices = [sample.frame for sample in self.frames]
        if indices != sorted(set(indices)):
            raise ValueError(f"track {self.id!r} frames must increase strictly")


@dataclass(frozen=True, slots=True)
class FeatureParams:
    contact_min: float = 0.2
    dilate_cells: int = 2
    bridge_s: float = 0.5
    hold_on_s: float = 0.3
    hold_off_s: float = 0.5
    frame_gap_s: float = 0.2
    velocity_window_s: float = 0.4
    frame_diagonal: float = math.sqrt(2.0)

    def __post_init__(self) -> None:
        if not 0.0 <= self.contact_min <= 1.0:
            raise ValueError(f"contact_min out of range: {self.contact_min}")
        if self.dilate_cells < 0:
            raise ValueError(f"dilate_cells must be non-negative: {self.dilate_cells}")
        if not 0.0 <= self.hold_on_s <= self.bridge_s:
            raise ValueError("hold_on_s must be within [0, bridge_s]")
        if self.hold_off_s < 0 or self.frame_gap_s < 0 or self.velocity_window_s <= 0:
            raise ValueError("invalid timing parameters")
        if self.frame_diagonal <= 0:
            raise ValueError(f"frame_diagonal must be positive: {self.frame_diagonal}")


@dataclass(frozen=True, slots=True)
class ContactWindow:
    hand_id: str
    object_id: str
    t_start: float
    t_end: float
    fraction: float
    proximity: float
    confidence: float


@dataclass(frozen=True, slots=True)
class HoldWindow:
    hand_id: str
    object_id: str
    t_start: float
    t_end: float
    confidence: float


@dataclass(frozen=True, slots=True)
class VelocitySample:
    track_id: str
    t: float
    velocity: float


@dataclass(frozen=True, slots=True)
class FeatureSet:
    contacts: tuple[ContactWindow, ...]
    holds: tuple[HoldWindow, ...]
    velocities: tuple[VelocitySample, ...]


def _grid_point(value: float) -> int:
    return min(_RASTER - 1, max(0, round(value * (_RASTER - 1))))


def _inside(points: Sequence[tuple[int, int]], x: float, y: float) -> bool:
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


def _polygon_cells(poly: Sequence[tuple[float, float]]) -> set[tuple[int, int]]:
    points = [(_grid_point(x), _grid_point(y)) for x, y in poly]
    if len(points) < 3:
        return set()
    return {(x, y) for y in range(_RASTER) for x in range(_RASTER) if _inside(points, x, y)}


def _box_cells(box: tuple[float, float, float, float], margin: float = 0.0) -> set[tuple[int, int]]:
    x0 = _grid_point(max(0.0, box[0] - margin))
    y0 = _grid_point(max(0.0, box[1] - margin))
    x1 = _grid_point(min(1.0, box[2] + margin))
    y1 = _grid_point(min(1.0, box[3] + margin))
    return {(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)}


def _dilate(cells: set[tuple[int, int]], radius: int) -> set[tuple[int, int]]:
    if radius <= 0:
        return set(cells)
    grown: set[tuple[int, int]] = set()
    for x, y in cells:
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                ny, nx = y + dy, x + dx
                if 0 <= nx < _RASTER and 0 <= ny < _RASTER:
                    grown.add((nx, ny))
    return grown


def _mask(sample: FrameSample) -> set[tuple[int, int]]:
    if len(sample.poly) >= 3:
        return _polygon_cells(sample.poly)
    return _box_cells(sample.box)


def _centre(box: tuple[float, float, float, float]) -> tuple[float, float]:
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def _distance(left: Sequence[float], right: Sequence[float]) -> float:
    return math.dist(left, right)


def _contact(hand: FrameSample, obj: FrameSample, params: FeatureParams) -> tuple[float, float]:
    """Return (overlap fraction of the object, proximity in hand diagonals)."""
    object_mask = _mask(obj)
    if not object_mask:
        return 0.0, 0.0
    hand_mask = _dilate(_mask(hand), params.dilate_cells)
    fraction = len(hand_mask & object_mask) / len(object_mask)
    hand_size = _distance((0.0, 0.0), (hand.box[2] - hand.box[0], hand.box[3] - hand.box[1]))
    gap = _distance(_centre(hand.box), _centre(obj.box))
    proximity = gap / hand_size if hand_size > 0 else gap
    return fraction, proximity


def _nearest(track: Track, t: float, tolerance: float) -> FrameSample | None:
    best: FrameSample | None = None
    for sample in track.frames:
        if abs(sample.t - t) <= tolerance and (best is None or abs(sample.t - t) < abs(best.t - t)):
            best = sample
    return best


def _windows(
    pairs: Sequence[tuple[float, float, float, float]],
    *,
    params: FeatureParams,
) -> list[list[tuple[float, float, float, float]]]:
    """Group (t, fraction, proximity, score) into runs, bridging short gaps."""
    runs: list[list[tuple[float, float, float, float]]] = []
    current: list[tuple[float, float, float, float]] = []
    for sample in pairs:
        if current and sample[0] - current[-1][0] > params.bridge_s:
            runs.append(current)
            current = []
        current.append(sample)
    if current:
        runs.append(current)
    return runs


def extract_features(tracks: Sequence[Track], *, params: FeatureParams | None = None) -> FeatureSet:
    """Compute contact/hold windows between hand tracks and every other track."""
    settings = params or FeatureParams()
    hands = [track for track in tracks if track.concept == HAND]
    objects = [track for track in tracks if track.concept != HAND]

    contacts: list[ContactWindow] = []
    holds: list[HoldWindow] = []
    for hand in hands:
        for obj in objects:
            samples: list[tuple[float, float, float, float]] = []
            for sample in hand.frames:
                partner = _nearest(obj, sample.t, settings.frame_gap_s)
                if partner is None:
                    continue
                fraction, proximity = _contact(sample, partner, settings)
                if fraction < settings.contact_min:
                    continue
                samples.append((sample.t, fraction, proximity, min(sample.score, partner.score)))
            for run in _windows(samples, params=settings):
                duration = run[-1][0] - run[0][0]
                confidence = sum(sample[3] for sample in run) / len(run)
                contacts.append(
                    ContactWindow(
                        hand_id=hand.id,
                        object_id=obj.id,
                        t_start=run[0][0],
                        t_end=run[-1][0],
                        fraction=sum(sample[1] for sample in run) / len(run),
                        proximity=sum(sample[2] for sample in run) / len(run),
                        confidence=round(confidence, 4),
                    )
                )
                if duration >= settings.hold_on_s:
                    holds.append(
                        HoldWindow(
                            hand_id=hand.id,
                            object_id=obj.id,
                            t_start=run[0][0],
                            t_end=run[-1][0],
                            confidence=round(confidence, 4),
                        )
                    )

    velocities: list[VelocitySample] = []
    for track in tracks:
        frames = track.frames
        for index, sample in enumerate(frames):
            previous = frames[0]
            for candidate in frames[:index]:
                if sample.t - candidate.t >= settings.velocity_window_s:
                    previous = candidate
                else:
                    break
            elapsed = sample.t - previous.t
            if elapsed <= 0:
                velocities.append(VelocitySample(track.id, sample.t, 0.0))
                continue
            moved = _distance(_centre(sample.box), _centre(previous.box))
            velocities.append(
                VelocitySample(
                    track.id,
                    sample.t,
                    round(moved / settings.frame_diagonal / elapsed, 6),
                )
            )

    contacts.sort(key=lambda item: (item.t_start, item.hand_id, item.object_id))
    holds.sort(key=lambda item: (item.t_start, item.hand_id, item.object_id))
    velocities.sort(key=lambda item: (item.track_id, item.t))
    return FeatureSet(tuple(contacts), tuple(holds), tuple(velocities))


__all__ = [
    "HAND",
    "ContactWindow",
    "FeatureParams",
    "FeatureSet",
    "FrameSample",
    "HoldWindow",
    "Track",
    "VelocitySample",
    "extract_features",
]

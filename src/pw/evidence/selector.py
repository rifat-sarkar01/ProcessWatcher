"""Choose and render the real frames shown as evidence for a deviation.

TRD §6.10: pick 2-4 frames per deviation by type, score them on mask area, Laplacian
sharpness and low occlusion, keep them at least 0.5 s apart, and render masks, labels
and a timestamp. A deviation with no usable frame returns an explicit
`evidence_unavailable` reason instead of inventing one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from PIL import Image

from pw.align.aligner import Alignment
from pw.align.deviations import Deviation
from pw.evidence.render import FrameOverlay, draw_timestamp, render_overlay

_NO_USABLE_FRAME = "no_frame_in_window"


class FrameProvider(Protocol):
    """Returns the real source/analysis frame for an analysis frame index."""

    def __call__(self, frame_index: int) -> Image.Image: ...


@dataclass(frozen=True, slots=True)
class TrackSample:
    frame: int
    t: float
    box: tuple[float, float, float, float]
    poly: tuple[tuple[float, float], ...] = ()
    score: float = 1.0


@dataclass(frozen=True, slots=True)
class Track:
    track_id: str
    concept: str
    frames: tuple[TrackSample, ...]


@dataclass(frozen=True, slots=True)
class EvidenceParams:
    """Defaults are the TRD §6.10 weights and spacing."""

    max_frames: int = 4
    min_spacing_s: float = 0.5
    area_weight: float = 0.4
    sharpness_weight: float = 0.3
    visibility_weight: float = 0.3

    def __post_init__(self) -> None:
        if self.max_frames < 1:
            raise ValueError(f"max_frames must be at least 1: {self.max_frames}")
        if self.min_spacing_s < 0:
            raise ValueError(f"min_spacing_s must be non-negative: {self.min_spacing_s}")
        weights = (self.area_weight, self.sharpness_weight, self.visibility_weight)
        if any(weight < 0 for weight in weights) or sum(weights) <= 0:
            raise ValueError("evidence scoring weights must be non-negative and non-zero")


@dataclass(frozen=True, slots=True)
class EvidenceFrame:
    deviation_id: str
    frame_index: int
    t: float
    track_ids: tuple[str, ...]
    score: float
    image: Image.Image


@dataclass(frozen=True, slots=True)
class EvidenceSelection:
    deviation_id: str
    frames: tuple[EvidenceFrame, ...]
    available: bool
    reason: str | None


@dataclass(frozen=True, slots=True)
class _Candidate:
    frame_index: int
    t: float
    samples: tuple[tuple[Track, TrackSample], ...]
    image: Image.Image
    raw_area: float
    raw_sharpness: float
    visibility: float


def _timeline(tracks: Sequence[Track]) -> list[tuple[int, float]]:
    seen: dict[int, float] = {}
    for track in tracks:
        for sample in track.frames:
            seen.setdefault(sample.frame, sample.t)
    return sorted(seen.items(), key=lambda item: (item[1], item[0]))


def _samples_by_frame(
    tracks: Sequence[Track],
) -> dict[int, list[tuple[Track, TrackSample]]]:
    by_frame: dict[int, list[tuple[Track, TrackSample]]] = {}
    for track in tracks:
        for sample in track.frames:
            by_frame.setdefault(sample.frame, []).append((track, sample))
    return by_frame


def _windows(deviation: Deviation, alignment: Alignment) -> list[tuple[float, float]]:
    windows = [(deviation.t_start, deviation.t_end)]
    if deviation.type == "out_of_order" and deviation.relates_to_step_id is not None:
        related = [
            interval
            for interval in alignment.intervals
            if interval.step_id == deviation.relates_to_step_id
        ]
        if related:
            nearest = min(
                related,
                key=lambda interval: (abs(interval.t_start - deviation.t_start), interval.id),
            )
            windows.append((nearest.t_start, nearest.t_end))
    return windows


def _seed_frames(
    deviation: Deviation,
    alignment: Alignment,
    timeline: Sequence[tuple[int, float]],
) -> list[int]:
    """Frames the strategy always wants: gap brackets, or one frame per window."""
    if deviation.type == "missed":
        seeds: list[int] = []
        before = [frame for frame, t in timeline if t <= deviation.t_start]
        after = [frame for frame, t in timeline if t >= deviation.t_end]
        if before:
            seeds.append(before[-1])
        if after:
            seeds.append(after[0])
        return seeds
    if deviation.type == "out_of_order":
        seeds = []
        for start, end in _windows(deviation, alignment):
            inside = [(frame, t) for frame, t in timeline if start <= t <= end]
            if inside:
                midpoint = (start + end) / 2
                seeds.append(min(inside, key=lambda item: (abs(item[1] - midpoint), item[0]))[0])
        return seeds
    return []


def _candidate_frames(
    deviation: Deviation,
    alignment: Alignment,
    timeline: Sequence[tuple[int, float]],
    by_frame: dict[int, list[tuple[Track, TrackSample]]],
) -> list[int]:
    windows = _windows(deviation, alignment)
    frames = [frame for frame, t in timeline if any(start <= t <= end for start, end in windows)]
    if deviation.type == "wrong_tool":
        relevant = set(deviation.track_ids)
        with_tool = [
            frame
            for frame in frames
            if any(track.track_id in relevant for track, _ in by_frame.get(frame, ()))
        ]
        if with_tool:
            return with_tool
    return frames


def _sample_area(sample: TrackSample) -> float:
    if len(sample.poly) >= 3:
        points = sample.poly
        total = 0.0
        for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1], strict=True):
            total += x1 * y2 - x2 * y1
        return abs(total) / 2
    left, top, right, bottom = sample.box
    return max(0.0, right - left) * max(0.0, bottom - top)


def _primary(
    samples: Sequence[tuple[Track, TrackSample]], relevant: Sequence[str]
) -> tuple[Track, TrackSample]:
    preferred = [pair for pair in samples if pair[0].track_id in relevant]
    pool = preferred or list(samples)
    return max(pool, key=lambda pair: (_sample_area(pair[1]), pair[0].track_id))


def _intersection_area(
    left: tuple[float, float, float, float], right: tuple[float, float, float, float]
) -> float:
    x0 = max(left[0], right[0])
    y0 = max(left[1], right[1])
    x1 = min(left[2], right[2])
    y1 = min(left[3], right[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return (x1 - x0) * (y1 - y0)


def _visibility(
    primary: tuple[Track, TrackSample],
    samples: Sequence[tuple[Track, TrackSample]],
) -> float:
    primary_area = _sample_area(primary[1])
    if primary_area <= 0:
        return 1.0
    occlusion = max(
        (
            _intersection_area(primary[1].box, sample.box) / primary_area
            for track, sample in samples
            if track.track_id != primary[0].track_id
        ),
        default=0.0,
    )
    return 1.0 - min(1.0, occlusion)


def _crop_box(
    box: tuple[float, float, float, float], size: tuple[int, int]
) -> tuple[int, int, int, int]:
    width, height = size
    left = max(0, min(width - 1, round(box[0] * width)))
    top = max(0, min(height - 1, round(box[1] * height)))
    right = max(left + 1, min(width, round(box[2] * width)))
    bottom = max(top + 1, min(height, round(box[3] * height)))
    return left, top, right, bottom


def _sharpness(image: Image.Image, box: tuple[float, float, float, float]) -> float:
    """Variance of the Laplacian over the track crop (downscaled for speed)."""
    grey = image.convert("L")
    crop = grey.crop(_crop_box(box, grey.size))
    crop.thumbnail((48, 48), Image.Resampling.BILINEAR)
    width, height = crop.size
    if width < 3 or height < 3:
        return 0.0
    pixels = crop.tobytes()
    values: list[float] = []
    for y in range(1, height - 1):
        row = y * width
        for x in range(1, width - 1):
            centre = pixels[row + x]
            laplacian = (
                -4 * centre
                + pixels[row + x - 1]
                + pixels[row + x + 1]
                + pixels[row - width + x]
                + pixels[row + width + x]
            )
            values.append(float(laplacian))
    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / len(values)


def _normalise(values: Sequence[float]) -> list[float]:
    low = min(values)
    high = max(values)
    if high - low < 1e-12:
        return [0.5] * len(values)
    return [(value - low) / (high - low) for value in values]


def _score_candidates(
    frame_indices: Sequence[int],
    by_frame: dict[int, list[tuple[Track, TrackSample]]],
    frames: FrameProvider,
    deviation: Deviation,
) -> tuple[list[_Candidate], int]:
    candidates: list[_Candidate] = []
    failures = 0
    for frame_index in sorted(set(frame_indices)):
        samples = by_frame.get(frame_index)
        if not samples:
            continue
        try:
            image = frames(frame_index)
        except (KeyError, OSError, IndexError):
            failures += 1
            continue
        primary = _primary(samples, deviation.track_ids)
        candidates.append(
            _Candidate(
                frame_index=frame_index,
                t=samples[0][1].t,
                samples=tuple(samples),
                image=image,
                raw_area=_sample_area(primary[1]),
                raw_sharpness=_sharpness(image, primary[1].box),
                visibility=_visibility(primary, samples),
            )
        )
    return candidates, failures


def select_evidence(
    deviation: Deviation,
    *,
    tracks: Sequence[Track],
    alignment: Alignment,
    frames: FrameProvider,
    params: EvidenceParams | None = None,
) -> EvidenceSelection:
    """Pick, score and render the evidence frames for one deviation."""
    settings = params or EvidenceParams()
    timeline = _timeline(tracks)
    if not timeline:
        return EvidenceSelection(deviation.id, (), False, "no_tracks")

    by_frame = _samples_by_frame(tracks)
    seeds = _seed_frames(deviation, alignment, timeline)
    requested = _candidate_frames(deviation, alignment, timeline, by_frame)
    candidates, failures = _score_candidates(
        list(dict.fromkeys([*seeds, *requested])), by_frame, frames, deviation
    )
    if not candidates:
        reason = "frame_read_failed" if failures else _NO_USABLE_FRAME
        return EvidenceSelection(deviation.id, (), False, reason)

    area_norm = _normalise([candidate.raw_area for candidate in candidates])
    sharpness_norm = _normalise([candidate.raw_sharpness for candidate in candidates])
    scored = [
        (
            candidate,
            min(
                1.0,
                max(
                    0.0,
                    settings.area_weight * area_norm[index]
                    + settings.sharpness_weight * sharpness_norm[index]
                    + settings.visibility_weight * candidate.visibility,
                ),
            ),
        )
        for index, candidate in enumerate(candidates)
    ]
    scores = {candidate.frame_index: score for candidate, score in scored}

    chosen: list[_Candidate] = []
    for frame_index in dict.fromkeys(seeds):
        if frame_index in scores and len(chosen) < settings.max_frames:
            chosen.append(next(item for item, _ in scored if item.frame_index == frame_index))
    for candidate, _ in sorted(scored, key=lambda item: (-item[1], item[0].t, item[0].frame_index)):
        if len(chosen) >= settings.max_frames:
            break
        if any(abs(candidate.t - existing.t) < settings.min_spacing_s for existing in chosen):
            continue
        if any(existing.frame_index == candidate.frame_index for existing in chosen):
            continue
        chosen.append(candidate)

    chosen.sort(key=lambda candidate: (candidate.t, candidate.frame_index))
    rendered = tuple(
        EvidenceFrame(
            deviation_id=deviation.id,
            frame_index=candidate.frame_index,
            t=candidate.t,
            track_ids=tuple(sorted({track.track_id for track, _ in candidate.samples})),
            score=scores[candidate.frame_index],
            image=draw_timestamp(
                render_overlay(
                    candidate.image,
                    [
                        FrameOverlay(track.track_id, track.concept, sample.box, sample.poly)
                        for track, sample in candidate.samples
                    ],
                ),
                candidate.t,
            ),
        )
        for candidate in chosen
    )
    return EvidenceSelection(deviation.id, rendered, True, None)


def select_all(
    deviations: Sequence[Deviation],
    *,
    tracks: Sequence[Track],
    alignment: Alignment,
    frames: FrameProvider,
    params: EvidenceParams | None = None,
) -> tuple[EvidenceSelection, ...]:
    return tuple(
        select_evidence(
            deviation,
            tracks=tracks,
            alignment=alignment,
            frames=frames,
            params=params,
        )
        for deviation in deviations
    )

"""Segment → step likelihood scoring with median-of-k and explicit failure flags.

One Wonder call per batch of segments (TRD §6.6), repeated `k = 3` times because
temperature 0 is not deterministic (ADR-002); the per-step median is normalised and
written as `likelihoods.json`. Any transport or schema failure degrades to a uniform
distribution with `scorer_unavailable` (or `scorer_partial` when some repeats succeeded),
so the aligner always receives a complete matrix.
"""

from __future__ import annotations

import json
import logging
import math
import re
import statistics
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from pw.align.prompts import (
    MAX_IMAGES_PER_CALL,
    MAX_KEYFRAMES,
    MAX_RATIONALE_CHARS,
    NONE,
    EventDescription,
    Keyframe,
    PromptSegment,
    SegmentDescription,
    StepDescription,
    TrackPoint,
    TrackSample,
    build_payload,
    clip,
)
from pw.clients.wonder import extract_text
from pw.data.validate import validate_payload
from pw.evidence.render import FrameOverlay, render_set_of_mark

SCHEMA_VERSION = "1.0.0"
REPEATS = 3
FLAG_UNAVAILABLE = "scorer_unavailable"
FLAG_PARTIAL = "scorer_partial"
FLAG_UNIFORM = "scorer_uniform_fallback"
_TRACK_ID = re.compile(r"^trk_\d{3,}$")

logger = logging.getLogger("pw.align.scorer")

ScorerCaller = Callable[[Mapping[str, Any]], Mapping[str, Any]]
FrameProvider = Callable[[int], Image.Image | None]


class ScorerError(ValueError):
    """The likelihoods would not satisfy the contract."""


@dataclass(frozen=True, slots=True)
class ObservedTool:
    track: str
    label: str
    confidence: float

    def to_payload(self) -> dict[str, object]:
        return {"track": self.track, "label": self.label, "confidence": round(self.confidence, 4)}


@dataclass(frozen=True, slots=True)
class ParsedPrediction:
    step_probs: Mapping[str, float]
    observed_tools: tuple[ObservedTool, ...]
    rationale_short: str
    flags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ScoredSegment:
    segment_id: str
    step_probs: Mapping[str, float]
    observed_tools: tuple[ObservedTool, ...]
    rationale_short: str
    flags: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "step_probs": dict(sorted(self.step_probs.items())),
            "observed_tools": [tool.to_payload() for tool in self.observed_tools],
            "rationale_short": self.rationale_short,
            "flags": list(self.flags),
        }


@dataclass(frozen=True, slots=True)
class ScorerResult:
    segments: tuple[ScoredSegment, ...]
    calls: int

    def to_payload(self, *, run_id: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "segments": [segment.to_payload() for segment in self.segments],
        }
        if run_id is not None:
            payload["run_id"] = run_id
        return payload

    def write(self, path: Path, *, run_id: str | None = None) -> Path:
        payload = self.to_payload(run_id=run_id)
        errors = validate_payload("likelihoods", payload)
        if errors:
            raise ScorerError("; ".join(errors))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path


def uniform(steps: Sequence[StepDescription]) -> dict[str, float]:
    value = round(1.0 / (len(steps) + 1), 6)
    return {step.step_id: value for step in steps} | {NONE: value}


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    number = float(value)
    return number if math.isfinite(number) else 0.0


def normalise_probs(
    raw: Mapping[str, Any], steps: Sequence[StepDescription]
) -> tuple[dict[str, float], tuple[str, ...]]:
    values: dict[str, float] = {}
    for step in steps:
        values[step.step_id] = min(1.0, max(0.0, _number(raw.get(step.step_id))))
    values[NONE] = min(1.0, max(0.0, _number(raw.get(NONE))))
    total = sum(values.values())
    if total <= 0:
        return uniform(steps), (FLAG_UNIFORM,)
    return {key: round(value / total, 6) for key, value in values.items()}, ()


def _tools(raw: object) -> tuple[ObservedTool, ...]:
    if not isinstance(raw, list):
        return ()
    tools: list[ObservedTool] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        track, label, confidence = item.get("track"), item.get("label"), item.get("confidence")
        if not isinstance(track, str) or not _TRACK_ID.match(track):
            continue
        if not isinstance(label, str) or not label.strip():
            continue
        value = _number(confidence)
        tools.append(ObservedTool(track, label.strip()[:80], min(1.0, max(0.0, value))))
    return tuple(tools[:16])


def parse_batch_response(
    body: Mapping[str, Any],
    *,
    expected_ids: Sequence[str],
    steps: Sequence[StepDescription],
) -> dict[str, ParsedPrediction]:
    text = extract_text(body)
    if text is None:
        raise ScorerError("scoring response has no text")
    try:
        payload = json.loads(text)
    except ValueError as error:
        raise ScorerError("scoring response is not valid JSON") from error
    items = payload.get("segments") if isinstance(payload, Mapping) else None
    if not isinstance(items, list) or len(items) != len(expected_ids):
        raise ScorerError("scoring response has the wrong number of segments")
    parsed: dict[str, ParsedPrediction] = {}
    for item in items:
        if not isinstance(item, Mapping):
            raise ScorerError("scoring segment is not an object")
        segment_id = item.get("segment_id")
        if not isinstance(segment_id, str) or segment_id not in expected_ids:
            raise ScorerError(f"unexpected segment_id: {segment_id!r}")
        if segment_id in parsed:
            raise ScorerError(f"duplicate segment_id: {segment_id!r}")
        probs_raw = item.get("step_probs")
        if not isinstance(probs_raw, Mapping):
            raise ScorerError("step_probs is not an object")
        probs, flags = normalise_probs(probs_raw, steps)
        rationale = item.get("rationale_short")
        parsed[segment_id] = ParsedPrediction(
            step_probs=probs,
            observed_tools=_tools(item.get("observed_tools")),
            rationale_short=clip(rationale, MAX_RATIONALE_CHARS)
            if isinstance(rationale, str)
            else "",
            flags=flags,
        )
    missing = set(expected_ids) - set(parsed)
    if missing:
        raise ScorerError(f"missing segments: {', '.join(sorted(missing))}")
    return parsed


def tracks_from_payload(payload: Mapping[str, Any]) -> tuple[TrackSample, ...]:
    samples: list[TrackSample] = []
    for item in payload.get("tracks", ()):
        if not isinstance(item, Mapping):
            continue
        track_id, concept = item.get("id"), item.get("concept")
        if not isinstance(track_id, str) or not isinstance(concept, str):
            continue
        frames: list[TrackPoint] = []
        for frame in item.get("frames", ()):
            if not isinstance(frame, Mapping):
                continue
            box = frame.get("box")
            if not isinstance(box, list) or len(box) != 4:
                continue
            poly = tuple(
                (float(point[0]), float(point[1]))
                for point in frame.get("poly", ())
                if isinstance(point, list) and len(point) == 2
            )
            frames.append(
                TrackPoint(
                    frame=int(frame.get("frame", 0)),
                    t=float(frame.get("t", 0.0)),
                    box=(float(box[0]), float(box[1]), float(box[2]), float(box[3])),
                    poly=poly,
                )
            )
        if frames:
            samples.append(
                TrackSample(track_id, concept, tuple(sorted(frames, key=lambda p: p.frame)))
            )
    return tuple(samples)


def timeline_parts(
    payload: Mapping[str, Any],
) -> tuple[tuple[SegmentDescription, ...], tuple[EventDescription, ...]]:
    segments = tuple(
        SegmentDescription(
            segment_id=str(item["id"]),
            t_start=float(item["t_start"]),
            t_end=float(item["t_end"]),
            event_ids=tuple(str(value) for value in item.get("event_ids", ())),
            salient_tracks=tuple(str(value) for value in item.get("salient_tracks", ())),
        )
        for item in payload.get("segments", ())
        if isinstance(item, Mapping) and "id" in item
    )
    events = tuple(
        EventDescription(
            event_id=str(item["id"]),
            kind=str(item.get("type", "")),
            t_start=float(item["t_start"]),
            t_end=float(item["t_end"]),
            tracks=tuple(str(value) for value in item.get("tracks", ())),
        )
        for item in payload.get("events", ())
        if isinstance(item, Mapping) and "id" in item
    )
    return segments, events


def _spread(items: Sequence[int], limit: int) -> list[int]:
    if len(items) <= limit:
        return list(items)
    step = (len(items) - 1) / (limit - 1)
    return [items[round(index * step)] for index in range(limit)]


def select_keyframes(
    segment: SegmentDescription,
    tracks: Sequence[TrackSample],
    frame_provider: FrameProvider,
    *,
    max_frames: int = MAX_KEYFRAMES,
) -> tuple[Keyframe, ...]:
    by_id = {track.track_id: track for track in tracks}
    candidates: set[int] = set()
    for track_id in segment.salient_tracks:
        track = by_id.get(track_id)
        if track is None:
            continue
        for point in track.frames:
            if segment.t_start <= point.t <= segment.t_end:
                candidates.add(point.frame)
    keyframes: list[Keyframe] = []
    for frame_index in _spread(sorted(candidates), max_frames):
        image = frame_provider(frame_index)
        if image is None:
            continue
        overlays: list[FrameOverlay] = []
        for track_id in sorted(by_id):
            if track_id not in segment.salient_tracks:
                continue
            track = by_id[track_id]
            match = next((p for p in track.frames if p.frame == frame_index), None)
            if match is not None:
                overlays.append(
                    FrameOverlay(
                        track_id=track_id,
                        concept=track.concept,
                        box=match.box,
                        poly=match.poly,
                    )
                )
        keyframes.append(
            Keyframe(
                frame=frame_index,
                image=render_set_of_mark(image, overlays),
                overlays=tuple(overlays),
            )
        )
    return tuple(keyframes)


def _batches(items: Sequence[SegmentDescription], size: int) -> list[Sequence[SegmentDescription]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _median_prediction(
    predictions: Sequence[ParsedPrediction], steps: Sequence[StepDescription], repeats: int
) -> ParsedPrediction:
    keys = [step.step_id for step in steps] + [NONE]
    medians = {
        key: statistics.median(prediction.step_probs.get(key, 0.0) for prediction in predictions)
        for key in keys
    }
    total = sum(medians.values())
    probs = (
        {key: round(value / total, 6) for key, value in medians.items()}
        if total > 0
        else uniform(steps)
    )
    flags: list[str] = []
    if len(predictions) < repeats:
        flags.append(FLAG_PARTIAL)
    if any(FLAG_UNIFORM in prediction.flags for prediction in predictions) or total <= 0:
        flags.append(FLAG_UNIFORM)
    first = predictions[0]
    return ParsedPrediction(
        step_probs=probs,
        observed_tools=first.observed_tools,
        rationale_short=first.rationale_short,
        flags=tuple(flags),
    )


def score_segments(
    segments: Sequence[SegmentDescription],
    steps: Sequence[StepDescription],
    *,
    tracks: Sequence[TrackSample] = (),
    events: Sequence[EventDescription] = (),
    frame_provider: FrameProvider | None = None,
    call: ScorerCaller,
    identities: Mapping[str, str] | None = None,
    repeats: int = REPEATS,
    batch_size: int = 1,
    max_keyframes: int = MAX_KEYFRAMES,
) -> ScorerResult:
    if not segments:
        return ScorerResult(segments=(), calls=0)
    if not steps:
        raise ScorerError("scoring needs at least one step")
    if repeats < 1:
        raise ScorerError("repeats must be at least 1")
    labels = dict(identities or {})
    effective_batch = max(1, min(batch_size, MAX_IMAGES_PER_CALL // max(1, max_keyframes)))
    results: dict[str, ScoredSegment] = {}
    calls = 0
    provider = frame_provider or (lambda frame: None)
    for batch in _batches(segments, effective_batch):
        prompt_segments = tuple(
            PromptSegment(
                segment=segment,
                keyframes=select_keyframes(segment, tracks, provider, max_frames=max_keyframes)
                if tracks
                else (),
            )
            for segment in batch
        )
        payload = build_payload(prompt_segments, steps, events, labels)
        successful: list[dict[str, ParsedPrediction]] = []
        for _ in range(repeats):
            calls += 1
            try:
                body = call(payload)
                successful.append(
                    parse_batch_response(
                        body,
                        expected_ids=[segment.segment_id for segment in batch],
                        steps=steps,
                    )
                )
            except Exception as error:
                logger.warning("scoring repeat failed: %s", error)
        for segment in batch:
            predictions = [
                parsed[segment.segment_id] for parsed in successful if segment.segment_id in parsed
            ]
            if not predictions:
                results[segment.segment_id] = ScoredSegment(
                    segment_id=segment.segment_id,
                    step_probs=uniform(steps),
                    observed_tools=(),
                    rationale_short="",
                    flags=(FLAG_UNAVAILABLE,),
                )
                continue
            merged = _median_prediction(predictions, steps, repeats)
            results[segment.segment_id] = ScoredSegment(
                segment_id=segment.segment_id,
                step_probs=merged.step_probs,
                observed_tools=merged.observed_tools,
                rationale_short=merged.rationale_short,
                flags=merged.flags,
            )
    ordered = tuple(results[segment.segment_id] for segment in segments)
    return ScorerResult(segments=ordered, calls=calls)


__all__ = [
    "FLAG_PARTIAL",
    "FLAG_UNAVAILABLE",
    "FLAG_UNIFORM",
    "REPEATS",
    "SCHEMA_VERSION",
    "FrameProvider",
    "ObservedTool",
    "ParsedPrediction",
    "ScoredSegment",
    "ScorerCaller",
    "ScorerError",
    "ScorerResult",
    "normalise_probs",
    "parse_batch_response",
    "score_segments",
    "select_keyframes",
    "timeline_parts",
    "tracks_from_payload",
    "uniform",
]

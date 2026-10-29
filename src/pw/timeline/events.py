"""Deterministic interaction events from hand-object features.

Rules (TRD §"Events"): holds come from sustained contact windows, contacts are a
held tool touching a part, moves are object displacement of at least `move_disp`
frame diagonals per `move_window_s`, and enter/exit come from an object centroid
crossing a tracked zone mask. Same-type events closer than `debounce_s` are merged.
Confidence is the mean source score times the observed frame coverage.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

from pw.data.validate import validate_payload
from pw.timeline.features import (
    HAND,
    ContactWindow,
    FeatureSet,
    FrameSample,
    HoldWindow,
    Track,
    extract_features,
)

SCHEMA_VERSION = "1.0.0"
TIMELINE_FILENAME = "timeline.json"
_EPSILON = 1e-9


class EventError(ValueError):
    """The generated timeline would not satisfy the contract."""


@dataclass(frozen=True, slots=True)
class EventParams:
    debounce_s: float = 0.3
    min_hold_s: float = 0.4
    move_disp: float = 0.06
    move_window_s: float = 0.5
    zone_tolerance_s: float = 0.2

    def __post_init__(self) -> None:
        if self.debounce_s < 0:
            raise ValueError(f"debounce_s must be non-negative: {self.debounce_s}")
        if self.min_hold_s < 0:
            raise ValueError(f"min_hold_s must be non-negative: {self.min_hold_s}")
        if not 0.0 < self.move_disp <= 1.0:
            raise ValueError(f"move_disp must be in (0, 1]: {self.move_disp}")
        if self.move_window_s <= 0:
            raise ValueError(f"move_window_s must be positive: {self.move_window_s}")
        if self.zone_tolerance_s < 0:
            raise ValueError(f"zone_tolerance_s must be non-negative: {self.zone_tolerance_s}")


@dataclass(frozen=True, slots=True)
class Event:
    id: str
    type: str
    t_start: float
    t_end: float
    tracks: tuple[str, ...]
    confidence: float

    def to_artifact(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "t_start": self.t_start,
            "t_end": self.t_end,
            "tracks": list(self.tracks),
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class EventSet:
    events: tuple[Event, ...]

    def to_artifact(self, run_id: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "events": [event.to_artifact() for event in self.events],
            "segments": [],
        }
        errors = validate_payload("timeline", payload)
        if errors:
            raise EventError("; ".join(errors))
        return payload


@dataclass(frozen=True, slots=True)
class _RawEvent:
    type: str
    t_start: float
    t_end: float
    tracks: tuple[str, ...]
    confidence: float


def _coverage(track: Track, t_start: float, t_end: float) -> float:
    """Fraction of expected samples observed inside the window."""
    observed = [
        sample for sample in track.frames if t_start - _EPSILON <= sample.t <= t_end + _EPSILON
    ]
    span = t_end - t_start
    if len(observed) < 2 or span <= _EPSILON:
        return 1.0
    gaps = [later.t - earlier.t for earlier, later in pairwise(observed)]
    gaps = [gap for gap in gaps if gap > _EPSILON]
    if not gaps:
        return 1.0
    gaps.sort()
    cadence = gaps[len(gaps) // 2]
    expected = round(span / cadence) + 1
    return min(1.0, len(observed) / expected)


def _pair_coverage(
    tracks: dict[str, Track],
    first: str,
    second: str,
    t_start: float,
    t_end: float,
) -> float:
    values = []
    for track_id in (first, second):
        track = tracks.get(track_id)
        if track is not None:
            values.append(_coverage(track, t_start, t_end))
    return sum(values) / len(values) if values else 1.0


def _hold_events(
    holds: Sequence[HoldWindow],
    tracks: dict[str, Track],
    zone_ids: set[str],
    params: EventParams,
) -> list[_RawEvent]:
    raw: list[_RawEvent] = []
    for hold in holds:
        if hold.object_id in zone_ids or hold.t_end - hold.t_start < params.min_hold_s:
            continue
        coverage = _pair_coverage(tracks, hold.hand_id, hold.object_id, hold.t_start, hold.t_end)
        confidence = round(hold.confidence * coverage, 4)
        subjects = (hold.hand_id, hold.object_id)
        raw.append(_RawEvent("hold_start", hold.t_start, hold.t_start, subjects, confidence))
        raw.append(_RawEvent("hold_end", hold.t_end, hold.t_end, subjects, confidence))
    return raw


def _contact_events(
    holds: Sequence[HoldWindow],
    contacts: Sequence[ContactWindow],
    tracks: dict[str, Track],
    zone_ids: set[str],
    params: EventParams,
) -> list[_RawEvent]:
    raw: list[_RawEvent] = []
    seen: set[tuple[float, float, frozenset[str]]] = set()
    held = [hold for hold in holds if hold.t_end - hold.t_start >= params.min_hold_s]
    active = sorted(held, key=lambda hold: (hold.t_start, hold.hand_id, hold.object_id))
    for hold in active:
        for contact in contacts:
            if contact.hand_id != hold.hand_id or contact.object_id == hold.object_id:
                continue
            if contact.object_id in zone_ids:
                continue
            start = max(contact.t_start, hold.t_start)
            end = min(contact.t_end, hold.t_end)
            if end < start - _EPSILON:
                continue
            pair = (hold.object_id, contact.object_id)
            key = (round(start, 3), round(end, 3), frozenset(pair))
            if key in seen:
                continue
            seen.add(key)
            coverage = _pair_coverage(tracks, pair[0], pair[1], start, end)
            confidence = round(contact.confidence * coverage, 4)
            raw.append(_RawEvent("contact_start", start, start, pair, confidence))
            raw.append(_RawEvent("contact_end", end, end, pair, confidence))
    return raw


def _move_events(
    features: FeatureSet,
    tracks: dict[str, Track],
    zone_ids: set[str],
    params: EventParams,
) -> list[_RawEvent]:
    threshold = params.move_disp / params.move_window_s
    flagged: dict[str, list[float]] = {}
    for sample in features.velocities:
        track = tracks.get(sample.track_id)
        if track is None or track.concept == HAND or sample.track_id in zone_ids:
            continue
        if sample.velocity >= threshold - _EPSILON:
            flagged.setdefault(sample.track_id, []).append(sample.t)

    raw: list[_RawEvent] = []
    for track_id, times in flagged.items():
        groups: list[list[float]] = []
        for t in sorted(times):
            if groups and t - groups[-1][-1] <= params.debounce_s + _EPSILON:
                groups[-1].append(t)
            else:
                groups.append([t])
        track = tracks[track_id]
        for group in groups:
            start, end = group[0], group[-1]
            scores = [
                sample.score
                for sample in track.frames
                if start - _EPSILON <= sample.t <= end + _EPSILON
            ]
            mean_score = sum(scores) / len(scores) if scores else 1.0
            confidence = round(mean_score * _coverage(track, start, end), 4)
            raw.append(_RawEvent("move", start, end, (track_id,), confidence))
    return raw


def _inside_polygon(poly: Sequence[tuple[float, float]], x: float, y: float) -> bool:
    result = False
    previous = poly[-1]
    for current in poly:
        x1, y1 = previous
        x2, y2 = current
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            result = not result
        previous = current
    return result


def _centroid(sample: FrameSample) -> tuple[float, float]:
    return ((sample.box[0] + sample.box[2]) / 2, (sample.box[1] + sample.box[3]) / 2)


def _inside(sample: FrameSample, zone: FrameSample) -> bool:
    x, y = _centroid(sample)
    if len(zone.poly) >= 3:
        return _inside_polygon(zone.poly, x, y)
    return zone.box[0] <= x <= zone.box[2] and zone.box[1] <= y <= zone.box[3]


def _nearest(samples: Sequence[FrameSample], t: float, tolerance: float) -> FrameSample | None:
    best: FrameSample | None = None
    for sample in samples:
        if abs(sample.t - t) <= tolerance and (best is None or abs(sample.t - t) < abs(best.t - t)):
            best = sample
    return best


def _zone_events(
    objects: Sequence[Track],
    zones: Sequence[Track],
    params: EventParams,
) -> list[_RawEvent]:
    raw: list[_RawEvent] = []
    for obj in objects:
        for zone in zones:
            was_inside: bool | None = None
            for sample in obj.frames:
                zone_sample = _nearest(zone.frames, sample.t, params.zone_tolerance_s)
                if zone_sample is None:
                    continue
                inside = _inside(sample, zone_sample)
                if was_inside is None:
                    if inside:
                        raw.append(_point_zone_event("enter", obj.id, zone.id, sample, zone_sample))
                elif inside != was_inside:
                    kind = "enter" if inside else "exit"
                    raw.append(_point_zone_event(kind, obj.id, zone.id, sample, zone_sample))
                was_inside = inside
    return raw


def _point_zone_event(
    kind: str, object_id: str, zone_id: str, sample: FrameSample, zone_sample: FrameSample
) -> _RawEvent:
    confidence = round((sample.score + zone_sample.score) / 2, 4)
    return _RawEvent(kind, sample.t, sample.t, (object_id, zone_id), confidence)


def _debounce(events: Sequence[_RawEvent], debounce_s: float) -> list[_RawEvent]:
    ordered = sorted(
        events, key=lambda event: (event.t_start, event.t_end, event.type, event.tracks)
    )
    merged: list[_RawEvent] = []
    latest: dict[tuple[str, tuple[str, ...]], int] = {}
    for event in ordered:
        key = (event.type, event.tracks)
        index = latest.get(key)
        if index is not None and event.t_start - merged[index].t_start <= debounce_s + _EPSILON:
            previous = merged[index]
            merged[index] = _RawEvent(
                previous.type,
                previous.t_start,
                max(previous.t_end, event.t_end),
                previous.tracks,
                max(previous.confidence, event.confidence),
            )
        else:
            merged.append(event)
            latest[key] = len(merged) - 1
    return merged


def extract_events(
    tracks: Sequence[Track],
    *,
    zones: Sequence[Track] = (),
    features: FeatureSet | None = None,
    params: EventParams | None = None,
) -> EventSet:
    """Extract contract-ready interaction events from stitched tracks."""
    settings = params or EventParams()
    computed = features if features is not None else extract_features(tracks)
    by_id = {track.id: track for track in tracks}
    zone_ids = {zone.id for zone in zones}
    zone_list = list(zones)

    raw: list[_RawEvent] = []
    raw.extend(_hold_events(computed.holds, by_id, zone_ids, settings))
    raw.extend(_contact_events(computed.holds, computed.contacts, by_id, zone_ids, settings))
    raw.extend(_move_events(computed, by_id, zone_ids, settings))
    objects = [track for track in tracks if track.concept != HAND and track.id not in zone_ids]
    raw.extend(_zone_events(objects, zone_list, settings))

    merged = _debounce(raw, settings.debounce_s)
    events = tuple(
        Event(
            id=f"evt_{index:03d}",
            type=event.type,
            t_start=round(event.t_start, 4),
            t_end=round(event.t_end, 4),
            tracks=event.tracks,
            confidence=min(1.0, max(0.0, event.confidence)),
        )
        for index, event in enumerate(merged, start=1)
    )
    return EventSet(events)


def write_timeline(event_set: EventSet, run_dir: Path, *, run_id: str) -> Path:
    """Write a contract-valid `timeline.json` into the run directory."""
    payload = event_set.to_artifact(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    target = run_dir / TIMELINE_FILENAME
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return target


__all__ = [
    "SCHEMA_VERSION",
    "TIMELINE_FILENAME",
    "Event",
    "EventError",
    "EventParams",
    "EventSet",
    "extract_events",
    "write_timeline",
]

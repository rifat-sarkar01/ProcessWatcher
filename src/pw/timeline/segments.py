"""Candidate action segments from timeline events.

Segments are cut at every event change-point, idle stretches shorter than `idle_gap_s`
are absorbed into a neighbour, activity shorter than `min_s` is merged away and
activity longer than `max_s` is split into equal parts. Each segment lists the tracks
and event ids it contains; the emitted `timeline.json` covers the whole video.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Any

from pw.data.validate import validate_payload
from pw.timeline.events import (
    SCHEMA_VERSION,
    TIMELINE_FILENAME,
    Event,
    EventSet,
)

_EPSILON = 1e-9
ACTIVITY = "activity"
IDLE = "idle"
# End-type point events close the interval before them, so the tail after the last
# hold/contact/zone exit stays idle instead of turning the rest of the video active.
_END_EVENTS = frozenset({"hold_end", "contact_end", "exit"})


class SegmentError(ValueError):
    """The generated timeline would not satisfy the contract."""


@dataclass(frozen=True, slots=True)
class SegmentParams:
    min_s: float = 1.0
    max_s: float = 20.0
    idle_gap_s: float = 2.0

    def __post_init__(self) -> None:
        if self.min_s <= 0:
            raise ValueError(f"min_s must be positive: {self.min_s}")
        if self.max_s < self.min_s:
            raise ValueError(f"max_s must be at least min_s: {self.max_s} < {self.min_s}")
        if self.idle_gap_s < 0:
            raise ValueError(f"idle_gap_s must be non-negative: {self.idle_gap_s}")


@dataclass(frozen=True, slots=True)
class Segment:
    id: str
    t_start: float
    t_end: float
    salient_tracks: tuple[str, ...]
    event_ids: tuple[str, ...]
    kind: str

    def to_artifact(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "t_start": self.t_start,
            "t_end": self.t_end,
            "salient_tracks": list(self.salient_tracks),
            "event_ids": list(self.event_ids),
            "kind": self.kind,
        }


@dataclass(frozen=True, slots=True)
class SegmentSet:
    segments: tuple[Segment, ...]


@dataclass
class _Piece:
    start: float
    end: float
    events: list[Event] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return ACTIVITY if self.events else IDLE

    @property
    def span(self) -> float:
        return self.end - self.start


def _bounds(events: Sequence[Event], duration_s: float) -> list[float]:
    values = {0.0, duration_s}
    for event in events:
        for t in (event.t_start, event.t_end):
            values.add(round(min(duration_s, max(0.0, t)), 4))
    return sorted(values)


def _piece_index(pieces: Sequence[_Piece], t: float) -> int:
    for index, piece in enumerate(pieces):
        if piece.start - _EPSILON <= t < piece.end - _EPSILON:
            return index
    return len(pieces) - 1


def _piece_ending(pieces: Sequence[_Piece], t: float) -> int:
    for index in range(len(pieces) - 1, -1, -1):
        if pieces[index].start + _EPSILON < t <= pieces[index].end + _EPSILON:
            return index
    return 0


def _assign(pieces: Sequence[_Piece], events: Sequence[Event]) -> None:
    for event in events:
        if event.t_end - event.t_start > _EPSILON:
            covered = [
                piece
                for piece in pieces
                if event.t_start < piece.end - _EPSILON and event.t_end > piece.start + _EPSILON
            ]
            if covered:
                for piece in covered:
                    piece.events.append(event)
                continue
        if event.type in _END_EVENTS:
            index = _piece_ending(pieces, event.t_start)
        else:
            index = _piece_index(pieces, event.t_start)
        pieces[index].events.append(event)


def _too_short(piece: _Piece, params: SegmentParams) -> bool:
    if piece.events:
        return piece.span < params.min_s - _EPSILON
    return piece.span < params.idle_gap_s - _EPSILON


def _merge_short(pieces: Sequence[_Piece], params: SegmentParams) -> list[_Piece]:
    result = list(pieces)
    while len(result) > 1:
        index = next(
            (position for position, piece in enumerate(result) if _too_short(piece, params)),
            None,
        )
        if index is None:
            break
        target = index - 1 if index > 0 else index + 1
        low, high = min(index, target), max(index, target)
        events = sorted(result[low].events + result[high].events, key=lambda e: (e.t_start, e.id))
        result[low : high + 1] = [_Piece(result[low].start, result[high].end, events)]
    return result


def _split_long(pieces: Sequence[_Piece], params: SegmentParams) -> list[_Piece]:
    result: list[_Piece] = []
    for piece in pieces:
        if not piece.events or piece.span <= params.max_s + _EPSILON:
            result.append(piece)
            continue
        parts = math.ceil(piece.span / params.max_s)
        step = piece.span / parts
        cuts = [round(piece.start + step * index, 4) for index in range(parts)]
        cuts.append(round(piece.end, 4))
        for index in range(parts):
            start, end = cuts[index], cuts[index + 1]
            events = [
                event
                for event in piece.events
                if _belongs(event, start, end, last=index == parts - 1)
            ]
            result.append(_Piece(start, end, events))
    return result


def _belongs(event: Event, start: float, end: float, *, last: bool) -> bool:
    if event.t_end - event.t_start > _EPSILON:
        return event.t_start < end - _EPSILON and event.t_end > start + _EPSILON
    if last:
        return event.t_start >= start - _EPSILON
    return start - _EPSILON <= event.t_start < end - _EPSILON


def _salient(events: Sequence[Event]) -> tuple[str, ...]:
    seen: list[str] = []
    for event in events:
        for track_id in event.tracks:
            if track_id not in seen:
                seen.append(track_id)
    return tuple(seen)


def build_segments(
    event_set: EventSet,
    *,
    duration_s: float,
    params: SegmentParams | None = None,
) -> SegmentSet:
    """Cut the video into ordered, non-overlapping activity and idle segments."""
    if duration_s <= 0:
        raise ValueError(f"duration_s must be positive: {duration_s}")
    settings = params or SegmentParams()
    ordered = _bounds(event_set.events, duration_s)
    pieces = [_Piece(start, end) for start, end in pairwise(ordered) if end - start > _EPSILON]
    if not pieces:
        pieces = [_Piece(0.0, round(duration_s, 4))]

    _assign(pieces, event_set.events)

    laid_out = _split_long(_merge_short(pieces, settings), settings)
    for piece in laid_out:
        piece.events.sort(key=lambda event: (event.t_start, event.id))
    segments = tuple(
        Segment(
            id=f"seg_{index:03d}",
            t_start=round(piece.start, 4),
            t_end=round(piece.end, 4),
            salient_tracks=_salient(piece.events),
            event_ids=tuple(event.id for event in piece.events),
            kind=piece.kind,
        )
        for index, piece in enumerate(laid_out, start=1)
    )
    return SegmentSet(segments)


def build_timeline(event_set: EventSet, segment_set: SegmentSet, run_id: str) -> dict[str, Any]:
    """Join events and segments into a contract-valid `timeline` payload."""
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "events": [event.to_artifact() for event in event_set.events],
        "segments": [segment.to_artifact() for segment in segment_set.segments],
    }
    errors = validate_payload("timeline", payload)
    if errors:
        raise SegmentError("; ".join(errors))
    return payload


def write_timeline(
    event_set: EventSet,
    segment_set: SegmentSet,
    run_dir: Path,
    *,
    run_id: str,
) -> Path:
    """Write a contract-valid segmented `timeline.json` into the run directory."""
    payload = build_timeline(event_set, segment_set, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    target = run_dir / TIMELINE_FILENAME
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return target


__all__ = [
    "Segment",
    "SegmentError",
    "SegmentParams",
    "SegmentSet",
    "build_segments",
    "build_timeline",
    "write_timeline",
]

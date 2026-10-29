"""Candidate action segments from timeline events."""

from __future__ import annotations

import json
import uuid
from itertools import pairwise
from pathlib import Path

import pytest

from pw.data.validate import validate_payload
from pw.timeline.events import Event, EventSet
from pw.timeline.segments import (
    SegmentParams,
    build_segments,
    build_timeline,
    write_timeline,
)

RUN_ID = "run_01J9ZQ8M3K4V7B2C5D6E8F0GHJ"
SCRATCH_ROOT = Path(__file__).resolve().parents[2] / ".uv" / "tests-tmp"
TRACKS = ("trk_001", "trk_002")


def event(event_id: str, kind: str, t: float, *, end: float | None = None) -> Event:
    return Event(
        id=event_id,
        type=kind,
        t_start=t,
        t_end=t if end is None else end,
        tracks=TRACKS,
        confidence=0.9,
    )


def shape(event_set: EventSet, duration_s: float) -> list[tuple[float, float, str]]:
    segments = build_segments(event_set, duration_s=duration_s).segments
    return [(segment.t_start, segment.t_end, segment.kind) for segment in segments]


def test_segment_boundaries_fall_on_events() -> None:
    events = EventSet((event("evt_001", "hold_start", 2.0), event("evt_002", "hold_end", 6.0)))
    segments = build_segments(events, duration_s=10.0).segments
    assert [(segment.t_start, segment.t_end, segment.kind) for segment in segments] == [
        (0.0, 2.0, "idle"),
        (2.0, 6.0, "activity"),
        (6.0, 10.0, "idle"),
    ]
    assert segments[0].event_ids == ()
    assert segments[0].salient_tracks == ()
    assert segments[1].event_ids == ("evt_001", "evt_002")
    assert segments[1].salient_tracks == TRACKS
    assert segments[2].event_ids == ()


def test_short_segments_are_merged_into_a_neighbour() -> None:
    events = EventSet(
        (
            event("evt_001", "hold_start", 2.0),
            event("evt_002", "contact_start", 5.5),
            event("evt_003", "hold_end", 6.0),
        )
    )
    segments = build_segments(events, duration_s=10.0).segments
    assert all(segment.t_end - segment.t_start >= 1.0 for segment in segments)
    merged = next(segment for segment in segments if segment.t_start == 2.0)
    assert (merged.t_end, merged.kind) == (6.0, "activity")
    assert merged.event_ids == ("evt_001", "evt_002", "evt_003")


def test_idle_gap_shorter_than_threshold_is_absorbed() -> None:
    events = EventSet(
        (
            event("evt_001", "hold_start", 2.0),
            event("evt_002", "hold_end", 4.0),
            event("evt_003", "contact_start", 5.2),
        )
    )
    segments = build_segments(events, duration_s=10.0).segments
    assert [(segment.t_start, segment.t_end, segment.kind) for segment in segments] == [
        (0.0, 2.0, "idle"),
        (2.0, 5.2, "activity"),
        (5.2, 10.0, "activity"),
    ]


def test_long_activity_segment_is_split() -> None:
    events = EventSet((event("evt_001", "hold_start", 0.0), event("evt_002", "hold_end", 30.0)))
    segments = build_segments(events, duration_s=30.0).segments
    assert [(segment.t_start, segment.t_end, segment.kind) for segment in segments] == [
        (0.0, 15.0, "activity"),
        (15.0, 30.0, "activity"),
    ]
    assert segments[0].event_ids == ("evt_001",)
    assert segments[1].event_ids == ("evt_002",)


def test_no_events_yields_one_idle_segment() -> None:
    segments = build_segments(EventSet(()), duration_s=12.5).segments
    assert [(segment.t_start, segment.t_end, segment.kind) for segment in segments] == [
        (0.0, 12.5, "idle")
    ]
    assert segments[0].salient_tracks == ()


def test_segments_cover_the_video_without_overlap() -> None:
    events = EventSet(
        (
            event("evt_001", "hold_start", 1.0),
            event("evt_002", "contact_start", 3.0, end=4.5),
            event("evt_003", "hold_end", 30.0),
        )
    )
    segments = build_segments(events, duration_s=40.0).segments
    assert segments[0].t_start == 0.0
    assert segments[-1].t_end == 40.0
    for previous, current in pairwise(segments):
        assert previous.t_end == current.t_start
    assert [segment.id for segment in segments] == [
        f"seg_{index:03d}" for index in range(1, len(segments) + 1)
    ]
    for segment in segments:
        if segment.kind == "activity":
            assert 1.0 <= segment.t_end - segment.t_start <= 20.0


def test_artifact_is_contract_valid_and_deterministic() -> None:
    events = EventSet((event("evt_001", "hold_start", 2.0), event("evt_002", "hold_end", 6.0)))
    first = build_segments(events, duration_s=10.0)
    second = build_segments(events, duration_s=10.0)
    payload = build_timeline(events, first, RUN_ID)
    assert payload == build_timeline(events, second, RUN_ID)
    assert validate_payload("timeline", payload) == []
    assert len(payload["segments"]) == 3


def test_write_timeline_persists_valid_json() -> None:
    events = EventSet((event("evt_001", "hold_start", 2.0),))
    segments = build_segments(events, duration_s=10.0)
    run_dir = SCRATCH_ROOT / f"segments-{uuid.uuid4().hex}"
    path = write_timeline(events, segments, run_dir, run_id=RUN_ID)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert path.name == "timeline.json"
    assert payload["events"] == [event("evt_001", "hold_start", 2.0).to_artifact()]
    assert validate_payload("timeline", payload) == []


def test_invalid_inputs_are_rejected() -> None:
    with pytest.raises(ValueError):
        build_segments(EventSet(()), duration_s=0.0)
    with pytest.raises(ValueError):
        SegmentParams(min_s=0.0)
    with pytest.raises(ValueError):
        SegmentParams(min_s=25.0, max_s=20.0)
    with pytest.raises(ValueError):
        SegmentParams(idle_gap_s=-1.0)

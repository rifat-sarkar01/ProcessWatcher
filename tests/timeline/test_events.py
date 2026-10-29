"""Interaction events on synthetic tracks: holds, contacts, moves, zone enter/exit."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from pw.data.validate import validate_payload
from pw.timeline.events import (
    EventError,
    EventParams,
    EventSet,
    extract_events,
    write_timeline,
)
from pw.timeline.features import FrameSample, Track

FPS = 15
RUN_ID = "run_01J9ZQ8M3K4V7B2C5D6E8F0GHJ"
SCRATCH_ROOT = Path(__file__).resolve().parents[2] / ".uv" / "tests-tmp"
HAND_BOX = (0.35, 0.35, 0.55, 0.55)
TOOL_BOX = (0.30, 0.30, 0.70, 0.70)


def frame(index: int, box: tuple[float, float, float, float], score: float = 0.9) -> FrameSample:
    return FrameSample(frame=index, t=round(index / FPS, 4), box=box, score=score)


def series(
    box: tuple[float, float, float, float],
    indices: range | list[int],
    *,
    x_offset: float = 0.0,
    score: float = 0.9,
) -> list[FrameSample]:
    return [
        frame(index, (box[0] + x_offset * index, box[1], box[2] + x_offset * index, box[3]), score)
        for index in indices
    ]


def track(track_id: str, concept: str, frames: list[FrameSample]) -> Track:
    return Track(id=track_id, concept=concept, frames=tuple(frames))


def types(event_set: EventSet) -> list[str]:
    return [event.type for event in event_set.events]


def test_pick_up_and_put_down_emit_hold_start_and_end() -> None:
    event_set = extract_events(
        [
            track("trk_001", "hand", series(HAND_BOX, range(0, 16))),
            track("trk_002", "wrench", series(TOOL_BOX, range(0, 16))),
        ]
    )
    assert types(event_set) == ["hold_start", "hold_end"]
    start, end = event_set.events
    assert start.tracks == ("trk_001", "trk_002")
    assert start.t_end == 0.0
    assert end.t_start == pytest.approx(1.0)
    assert start.confidence == pytest.approx(0.9)
    assert start.id == "evt_001" and end.id == "evt_002"


def test_hold_shorter_than_min_hold_is_ignored() -> None:
    event_set = extract_events(
        [
            track("trk_001", "hand", series(HAND_BOX, range(0, 6))),
            track("trk_002", "wrench", series(TOOL_BOX, range(0, 6))),
        ]
    )
    assert event_set.events == ()


def test_tool_swap_produces_two_hold_pairs() -> None:
    left_hand = (0.10, 0.10, 0.30, 0.30)
    right_hand = (0.60, 0.60, 0.80, 0.80)
    left_tool = (0.05, 0.05, 0.35, 0.35)
    right_tool = (0.55, 0.55, 0.85, 0.85)
    event_set = extract_events(
        [
            track(
                "trk_001",
                "hand",
                series(left_hand, range(0, 10)) + series(right_hand, range(12, 22)),
            ),
            track("trk_002", "wrench", series(left_tool, range(0, 10))),
            track("trk_003", "screwdriver", series(right_tool, range(12, 22))),
        ]
    )
    starts = [event for event in event_set.events if event.type == "hold_start"]
    ends = [event for event in event_set.events if event.type == "hold_end"]
    assert [(event.tracks, event.t_start) for event in starts] == [
        (("trk_001", "trk_002"), 0.0),
        (("trk_001", "trk_003"), pytest.approx(0.8)),
    ]
    assert len(ends) == 2


def test_drop_ends_the_hold_and_moves_the_object() -> None:
    hand = (0.35, 0.35, 0.55, 0.55)
    away = (0.80, 0.80, 0.90, 0.90)
    tool_frames = [
        frame(
            index,
            (
                0.25 + 0.02 * max(0, index - 11),
                0.25,
                0.45 + 0.02 * max(0, index - 11),
                0.45,
            ),
        )
        for index in range(0, 31)
    ]
    event_set = extract_events(
        [
            track(
                "trk_001",
                "hand",
                series(hand, range(0, 10)) + series(away, range(12, 31)),
            ),
            track("trk_002", "bolt", tool_frames),
        ]
    )
    assert "hold_end" in types(event_set)
    hold_end = next(event for event in event_set.events if event.type == "hold_end")
    assert hold_end.t_start == pytest.approx(0.6)
    moves = [event for event in event_set.events if event.type == "move"]
    assert moves and moves[-1].tracks == ("trk_002",)
    assert moves[-1].t_start >= 12 / FPS


def test_part_contacts_the_held_tool() -> None:
    hand = (0.30, 0.30, 0.70, 0.70)
    tool = (0.30, 0.30, 0.50, 0.50)
    part = (0.50, 0.30, 0.70, 0.50)
    event_set = extract_events(
        [
            track("trk_001", "hand", series(hand, range(0, 16))),
            track("trk_002", "wrench", series(tool, range(0, 16))),
            track("trk_003", "bolt", series(part, range(0, 16))),
        ]
    )
    contacts = [event for event in event_set.events if event.type.startswith("contact")]
    assert [(event.type, event.tracks) for event in contacts] == [
        ("contact_start", ("trk_002", "trk_003")),
        ("contact_end", ("trk_002", "trk_003")),
    ]
    assert contacts[0].t_start == 0.0
    assert contacts[1].t_start == pytest.approx(1.0)


def test_part_placed_into_a_zone_emits_enter_and_exit() -> None:
    part = track(
        "trk_001",
        "bolt",
        series((0.00, 0.00, 0.20, 0.20), range(0, 6))
        + series((0.50, 0.50, 0.70, 0.70), range(6, 16))
        + series((0.00, 0.00, 0.20, 0.20), range(16, 21)),
    )
    zone = track("trk_002", "tray", series((0.45, 0.45, 0.75, 0.75), range(0, 21)))
    event_set = extract_events([part, zone], zones=[zone])
    zone_events = [event for event in event_set.events if event.type in {"enter", "exit"}]
    assert [(event.type, event.tracks) for event in zone_events] == [
        ("enter", ("trk_001", "trk_002")),
        ("exit", ("trk_001", "trk_002")),
    ]
    assert zone_events[0].t_start == round(6 / FPS, 4)
    assert zone_events[1].t_start == round(16 / FPS, 4)


def test_zone_flicker_events_closer_than_debounce_merge() -> None:
    part = track(
        "trk_001",
        "bolt",
        series((0.50, 0.50, 0.70, 0.70), range(0, 3))
        + series((0.00, 0.00, 0.20, 0.20), range(3, 4))
        + series((0.50, 0.50, 0.70, 0.70), range(4, 16))
        + series((0.00, 0.00, 0.20, 0.20), range(16, 21)),
    )
    zone = track("trk_002", "tray", series((0.45, 0.45, 0.75, 0.75), range(0, 21)))
    events = extract_events([part, zone], zones=[zone]).events
    enters = [event for event in events if event.type == "enter"]
    exits = [event for event in events if event.type == "exit"]
    assert len(enters) == 1
    assert enters[0].t_start == 0.0
    assert enters[0].t_end == round(4 / FPS, 4)
    assert len(exits) == 2


def test_confidence_is_mean_score_times_coverage() -> None:
    indices = [index for index in range(0, 16) if index != 5]
    event_set = extract_events(
        [
            track("trk_001", "hand", series(HAND_BOX, range(0, 16))),
            track("trk_002", "wrench", series(TOOL_BOX, indices)),
        ]
    )
    hold_start = event_set.events[0]
    assert hold_start.type == "hold_start"
    assert 0.8 < hold_start.confidence < 0.9


def test_events_are_ordered_with_unique_ids_and_valid_contract() -> None:
    part = track(
        "trk_001",
        "bolt",
        series((0.00, 0.00, 0.20, 0.20), range(0, 6))
        + series((0.50, 0.50, 0.70, 0.70), range(6, 16)),
    )
    zone = track("trk_002", "tray", series((0.45, 0.45, 0.75, 0.75), range(0, 16)))
    event_set = extract_events(
        [part, zone, track("trk_003", "hand", series(HAND_BOX, range(0, 16)))],
        zones=[zone],
    )
    starts = [event.t_start for event in event_set.events]
    assert starts == sorted(starts)
    ids = [event.id for event in event_set.events]
    assert len(ids) == len(set(ids))
    artifact = event_set.to_artifact(RUN_ID)
    assert artifact["segments"] == []
    assert validate_payload("timeline", artifact) == []


def test_extraction_is_idempotent_and_order_independent() -> None:
    tracks = [
        track("trk_001", "hand", series(HAND_BOX, range(0, 16))),
        track("trk_002", "wrench", series(TOOL_BOX, range(0, 16))),
    ]
    first = extract_events(tracks).to_artifact(RUN_ID)
    second = extract_events(tracks).to_artifact(RUN_ID)
    reversed_order = extract_events(list(reversed(tracks))).to_artifact(RUN_ID)
    assert first == second == reversed_order


def test_no_tracks_yields_an_empty_but_valid_timeline() -> None:
    artifact = extract_events([]).to_artifact(RUN_ID)
    assert artifact["events"] == []
    assert validate_payload("timeline", artifact) == []


def test_zone_polygon_mask_is_used_when_present() -> None:
    part_box = (0.50, 0.50, 0.70, 0.70)
    poly = ((0.45, 0.45), (0.75, 0.45), (0.75, 0.75), (0.45, 0.75))
    part = track("trk_001", "bolt", series(part_box, range(0, 8)))
    zone_frames = [
        FrameSample(frame=index, t=round(index / FPS, 4), box=part_box, poly=poly)
        for index in range(0, 8)
    ]
    zone = track("trk_002", "tray", zone_frames)
    events = extract_events([part, zone], zones=[zone]).events
    assert [(event.type, event.tracks) for event in events] == [("enter", ("trk_001", "trk_002"))]


def test_zone_samples_outside_tolerance_are_ignored() -> None:
    part = track("trk_001", "bolt", series((0.50, 0.50, 0.70, 0.70), range(5, 16)))
    zone = track(
        "trk_002",
        "tray",
        [FrameSample(frame=0, t=0.0, box=(0.45, 0.45, 0.75, 0.75))],
    )
    events = extract_events([part, zone], zones=[zone]).events
    assert [event for event in events if event.type in {"enter", "exit"}] == []


def test_artifact_rejects_an_invalid_run_id() -> None:
    with pytest.raises(EventError):
        extract_events([]).to_artifact("run_not-a-ulid")


def test_write_timeline_persists_valid_json() -> None:
    run_dir = SCRATCH_ROOT / f"timeline-{uuid.uuid4().hex}"
    path = write_timeline(extract_events([]), run_dir, run_id=RUN_ID)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert path.name == "timeline.json"
    assert validate_payload("timeline", payload) == []


def test_invalid_params_are_rejected() -> None:
    with pytest.raises(ValueError):
        EventParams(debounce_s=-1.0)
    with pytest.raises(ValueError):
        EventParams(min_hold_s=-1.0)
    with pytest.raises(ValueError):
        EventParams(move_disp=0.0)
    with pytest.raises(ValueError):
        EventParams(move_window_s=0.0)
    with pytest.raises(ValueError):
        EventParams(zone_tolerance_s=-1.0)

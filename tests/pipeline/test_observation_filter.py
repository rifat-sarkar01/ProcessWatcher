"""Parts and the hand are not tools: they must not produce wrong_tool observations."""

from __future__ import annotations

import pytest

from pw.align.aligner import Alignment, AlignParams, Interval
from pw.pipeline.handlers import _neutral_concepts, _observations


def _timeline() -> dict[str, object]:
    return {
        "events": [
            {
                "type": "hold_start",
                "t_start": 1.0,
                "tracks": ["trk_001", "trk_002"],
            },
            {"type": "hold_end", "t_start": 8.0, "tracks": ["trk_001", "trk_002"]},
            {"type": "hold_start", "t_start": 2.0, "tracks": ["trk_003"]},
            {"type": "hold_end", "t_start": 7.0, "tracks": ["trk_003"]},
            {
                "type": "contact_start",
                "t_start": 1.0,
                "tracks": ["trk_001", "trk_002"],
            },
            {"type": "contact_end", "t_start": 8.0, "tracks": ["trk_001", "trk_002"]},
        ]
    }


def _tracks() -> dict[str, object]:
    return {
        "tracks": [
            {"id": "trk_001", "concept": "hand"},
            {"id": "trk_002", "concept": "keyboard"},
            {"id": "trk_003", "concept": "cleaning brush"},
        ]
    }


def _alignment() -> Alignment:
    return Alignment(
        path=(),
        intervals=(
            Interval(
                id="int_001",
                step_id="stp_02",
                t_start=0.0,
                t_end=10.0,
                segment_ids=("seg_001",),
                mean_prob=0.9,
                margin=2.0,
            ),
        ),
        total_cost=0.0,
        per_segment_cost=0.0,
        coverage=1.0,
        params=AlignParams(),
    )


@pytest.mark.unit
def test_parts_and_hand_are_not_held_tools() -> None:
    graph = {"steps": [{"parts": ["keyboard", "keycaps"], "tools": ["cleaning brush"]}]}

    neutral = _neutral_concepts(graph)
    observations = _observations(_timeline(), _alignment(), _tracks(), neutral)

    assert neutral == {"hand", "keyboard", "keycaps"}
    assert [held.track_id for held in observations[0].held] == ["trk_003"]

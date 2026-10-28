"""PTS time-map tests: the pipeline must never assume a nominal frame rate."""

from __future__ import annotations

import itertools
from pathlib import Path

import pytest

from pw.ingest import TimeMap, build_time_map, pts_times


@pytest.mark.unit
def test_pts_times_are_increasing(media: dict[str, Path]) -> None:
    times = pts_times(media["cfr"])

    assert len(times) >= 50
    assert all(later >= earlier for earlier, later in itertools.pairwise(times))


@pytest.mark.unit
def test_constant_frame_rate_is_not_variable(media: dict[str, Path]) -> None:
    time_map = build_time_map(pts_times(media["cfr"], limit=40))

    assert time_map.is_variable is False
    assert time_map.effective_fps == pytest.approx(30.0, abs=1.0)


@pytest.mark.unit
def test_variable_frame_rate_is_detected(media: dict[str, Path]) -> None:
    time_map = build_time_map(pts_times(media["vfr"]))

    assert time_map.is_variable is True


@pytest.mark.unit
def test_time_map_starts_at_zero_and_reports_duration(media: dict[str, Path]) -> None:
    time_map = build_time_map(pts_times(media["cfr"]))

    assert time_map.time_of_frame(0) == 0.0
    assert time_map.duration_s == pytest.approx(2.0, abs=0.1)
    assert time_map.frame_count == len(time_map.pts)


@pytest.mark.unit
def test_frame_lookup_round_trips() -> None:
    time_map = build_time_map([0.0, 0.1, 0.2, 0.3, 0.4])

    assert time_map.frame_at(0.0) == 0
    assert time_map.frame_at(0.05) == 0
    assert time_map.frame_at(0.25) == 2
    assert time_map.frame_at(9.0) == 4
    assert time_map.frame_at(-1.0) == 0
    assert time_map.time_of_frame(3) == pytest.approx(0.3)


@pytest.mark.unit
def test_time_map_rejects_non_increasing_timestamps() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        build_time_map([0.0, 0.1, 0.1])


@pytest.mark.unit
def test_time_map_rejects_a_single_frame() -> None:
    with pytest.raises(ValueError, match="at least two frames"):
        TimeMap((0.0,))


@pytest.mark.unit
def test_build_time_map_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="no presentation timestamps"):
        build_time_map([])


@pytest.mark.unit
def test_pts_times_on_missing_file(scratch: Path) -> None:
    with pytest.raises(FileNotFoundError):
        pts_times(scratch / "nope.mp4")

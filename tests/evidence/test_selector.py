"""Evidence selector tests: type strategies, scoring, spacing and rendering."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pytest
from PIL import Image, ImageDraw

from pw.align.aligner import Alignment, AlignParams, Interval
from pw.align.deviations import Deviation
from pw.evidence.selector import (
    EvidenceParams,
    Track,
    TrackSample,
    select_all,
    select_evidence,
)

SIZE = (160, 120)


@dataclass
class Frames:
    """Deterministic in-memory frame provider with content that varies by index."""

    def __call__(self, index: int) -> Image.Image:
        image = Image.new("RGB", SIZE, (20, 20, 20))
        draw = ImageDraw.Draw(image)
        left = (index * 7) % 100
        draw.rectangle((left, 20, left + 40, 70), fill=(220, 220, 220))
        draw.line((0, index % 100, 160, (index * 3) % 120), fill=(255, 0, 0), width=2)
        return image


def sample(
    frame: int,
    t: float,
    box: tuple[float, float, float, float] = (0.2, 0.2, 0.6, 0.7),
    poly: tuple[tuple[float, float], ...] = (),
) -> TrackSample:
    return TrackSample(frame=frame, t=t, box=box, poly=poly)


def track(
    track_id: str,
    concept: str,
    frames: Sequence[tuple[int, float, tuple[float, float, float, float]]],
) -> Track:
    return Track(
        track_id=track_id,
        concept=concept,
        frames=tuple(sample(frame, t, box) for frame, t, box in frames),
    )


def timeline_track(step_s: float = 0.5, end_s: float = 5.0, track_id: str = "trk_001") -> Track:
    count = round(end_s / step_s) + 1
    return track(
        track_id,
        "hand",
        [(index, round(index * step_s, 3), (0.2, 0.2, 0.6, 0.7)) for index in range(count)],
    )


def interval(number: int, step_id: str, t_start: float, t_end: float) -> Interval:
    return Interval(
        id=f"int_{number:02d}",
        step_id=step_id,
        t_start=t_start,
        t_end=t_end,
        segment_ids=(f"seg_{number:03d}",),
        mean_prob=0.9,
        margin=2.0,
    )


def alignment(*intervals: Interval) -> Alignment:
    return Alignment(
        path=tuple((iv.segment_ids[0], iv.step_id) for iv in intervals),
        intervals=tuple(intervals),
        total_cost=0.1,
        per_segment_cost=0.1,
        coverage=1.0,
        params=AlignParams(),
    )


def deviation(
    kind: str = "missed",
    *,
    step_id: str = "stp_02",
    t_start: float = 2.0,
    t_end: float = 3.0,
    relates_to: str | None = None,
    track_ids: tuple[str, ...] = ("trk_001",),
) -> Deviation:
    return Deviation(
        id="dev_001",
        type=kind,  # type: ignore[arg-type]
        status="flagged",
        severity="medium",
        step_id=step_id,
        t_start=t_start,
        t_end=t_end,
        track_ids=track_ids,
        confidence=0.9,
        margin=0.5,
        relates_to_step_id=relates_to,
    )


@pytest.mark.unit
def test_missed_deviation_brackets_the_gap() -> None:
    tracks = [timeline_track()]
    result = select_evidence(
        deviation("missed", t_start=2.0, t_end=3.0),
        tracks=tracks,
        alignment=alignment(),
        frames=Frames(),
    )

    assert result.available is True
    assert result.reason is None
    assert 2 <= len(result.frames) <= 4
    times = [frame.t for frame in result.frames]
    assert min(times) <= 2.0
    assert max(times) >= 3.0
    assert [frame.frame_index for frame in result.frames] == sorted(
        frame.frame_index for frame in result.frames
    )


@pytest.mark.unit
def test_out_of_order_uses_both_swapped_intervals() -> None:
    tracks = [timeline_track()]
    aligned = alignment(
        interval(1, "stp_01", 0.0, 1.0),
        interval(2, "stp_02", 2.0, 3.0),
    )
    result = select_evidence(
        deviation("out_of_order", step_id="stp_02", t_start=2.0, t_end=3.0, relates_to="stp_01"),
        tracks=tracks,
        alignment=aligned,
        frames=Frames(),
    )

    assert result.available is True
    times = [frame.t for frame in result.frames]
    assert any(time <= 1.0 for time in times)
    assert any(time >= 2.0 for time in times)


@pytest.mark.unit
def test_out_of_order_without_a_related_step_uses_one_window() -> None:
    tracks = [timeline_track()]
    result = select_evidence(
        deviation("out_of_order", t_start=2.0, t_end=3.0),
        tracks=tracks,
        alignment=alignment(),
        frames=Frames(),
    )

    assert result.available is True
    assert all(2.0 <= frame.t <= 3.0 for frame in result.frames)


@pytest.mark.unit
def test_wrong_tool_prefers_frames_where_the_wrong_tool_is_present() -> None:
    hand = timeline_track(track_id="trk_001")
    wrong = track(
        "trk_002",
        "screwdriver",
        [
            (4, 2.0, (0.55, 0.2, 0.8, 0.6)),
            (5, 2.5, (0.55, 0.2, 0.8, 0.6)),
            (6, 3.0, (0.55, 0.2, 0.8, 0.6)),
        ],
    )
    result = select_evidence(
        deviation("wrong_tool", t_start=1.0, t_end=4.0, track_ids=("trk_002",)),
        tracks=[hand, wrong],
        alignment=alignment(),
        frames=Frames(),
    )

    assert result.available is True
    assert result.frames
    assert all("trk_002" in frame.track_ids for frame in result.frames)


@pytest.mark.unit
def test_selected_frames_respect_minimum_spacing() -> None:
    dense = track(
        "trk_001",
        "hand",
        [(index, round(index * 0.1, 3), (0.2, 0.2, 0.6, 0.7)) for index in range(51)],
    )
    result = select_evidence(
        deviation("wrong_tool", t_start=0.0, t_end=5.0),
        tracks=[dense],
        alignment=alignment(),
        frames=Frames(),
        params=EvidenceParams(min_spacing_s=0.5, max_frames=4),
    )

    times = [frame.t for frame in result.frames]
    assert 1 <= len(times) <= 4
    for index, earlier in enumerate(times):
        for later in times[index + 1 :]:
            assert abs(later - earlier) >= 0.5


@pytest.mark.unit
def test_at_most_four_frames_are_returned() -> None:
    tracks = [timeline_track(step_s=1.0, end_s=20.0)]
    result = select_evidence(
        deviation("wrong_tool", t_start=0.0, t_end=20.0),
        tracks=tracks,
        alignment=alignment(),
        frames=Frames(),
    )

    assert len(result.frames) <= 4


@pytest.mark.unit
def test_selection_is_deterministic() -> None:
    tracks = [timeline_track()]
    args = dict(tracks=tracks, alignment=alignment(), frames=Frames())
    first = select_evidence(deviation("missed"), **args)
    second = select_evidence(deviation("missed"), **args)

    assert [frame.frame_index for frame in first.frames] == [
        frame.frame_index for frame in second.frames
    ]
    assert [frame.score for frame in first.frames] == pytest.approx(
        [frame.score for frame in second.frames]
    )


@pytest.mark.unit
def test_scores_stay_in_the_unit_interval() -> None:
    result = select_evidence(
        deviation("missed"),
        tracks=[timeline_track()],
        alignment=alignment(),
        frames=Frames(),
    )

    assert all(0.0 <= frame.score <= 1.0 for frame in result.frames)


@pytest.mark.unit
def test_rendered_frame_contains_the_overlay_and_timestamp() -> None:
    raw = Frames()(4)
    result = select_evidence(
        deviation("missed", t_start=2.0, t_end=2.0),
        tracks=[timeline_track()],
        alignment=alignment(),
        frames=Frames(),
    )

    rendered = result.frames[0].image
    assert rendered.size == SIZE
    assert rendered.tobytes() != raw.tobytes()
    box_pixel = (round(0.4 * SIZE[0]), round(0.45 * SIZE[1]))
    assert rendered.getpixel(box_pixel) != raw.getpixel(box_pixel)


@pytest.mark.unit
def test_no_tracks_is_a_graceful_fallback() -> None:
    result = select_evidence(
        deviation("missed"),
        tracks=[],
        alignment=alignment(),
        frames=Frames(),
    )

    assert result.available is False
    assert result.frames == ()
    assert result.reason == "no_tracks"


@pytest.mark.unit
def test_window_without_frames_is_a_graceful_fallback() -> None:
    tracks = [track("trk_001", "hand", [(0, 0.0, (0.2, 0.2, 0.6, 0.7))])]
    result = select_evidence(
        deviation("wrong_tool", t_start=10.0, t_end=11.0),
        tracks=tracks,
        alignment=alignment(),
        frames=Frames(),
    )

    assert result.available is False
    assert result.reason == "no_frame_in_window"


@pytest.mark.unit
def test_unreadable_frames_are_a_graceful_fallback() -> None:
    class BrokenFrames:
        def __call__(self, index: int) -> Image.Image:
            raise OSError("decode failed")

    result = select_evidence(
        deviation("missed"),
        tracks=[timeline_track()],
        alignment=alignment(),
        frames=BrokenFrames(),
    )

    assert result.available is False
    assert result.reason == "frame_read_failed"


@pytest.mark.unit
def test_batch_selection_keeps_deviation_order() -> None:
    deviations = (
        deviation("missed", step_id="stp_02", t_start=2.0, t_end=3.0),
        deviation("wrong_tool", step_id="stp_01", t_start=0.0, t_end=1.0),
    )
    results = select_all(
        deviations,
        tracks=[timeline_track()],
        alignment=alignment(),
        frames=Frames(),
    )

    assert [result.deviation_id for result in results] == [item.id for item in deviations]


@pytest.mark.unit
def test_invalid_params_are_rejected() -> None:
    with pytest.raises(ValueError, match="max_frames"):
        EvidenceParams(max_frames=0)

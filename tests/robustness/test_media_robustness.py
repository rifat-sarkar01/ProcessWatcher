"""Media robustness: VFR phone video, camera shake, low light and the duration cap."""

from __future__ import annotations

from pathlib import Path

import pytest

from pw.ingest import (
    MAX_DURATION_S,
    VideoTooLong,
    build_time_map,
    normalise_video,
    probe_video,
    pts_times,
    validate_source,
)


@pytest.mark.unit
def test_vfr_phone_clip_is_variable_and_normalises_to_cfr(
    clips: dict[str, Path], scratch: Path
) -> None:
    time_map = build_time_map(pts_times(clips["vfr"]))
    assert time_map.is_variable is True

    result = normalise_video(clips["vfr"], scratch / "vfr_analysis.mp4")

    assert result.path.is_file()
    assert result.info.fps == pytest.approx(15.0, abs=0.2)
    assert result.info.frame_count is not None
    assert abs(result.info.frame_count - result.info.duration_s * 15) <= 2


@pytest.mark.unit
@pytest.mark.parametrize("name", ["shaky", "dark"])
def test_degraded_capture_still_normalises(
    name: str, clips: dict[str, Path], scratch: Path
) -> None:
    result = normalise_video(clips[name], scratch / f"{name}_analysis.mp4")

    assert result.path.is_file()
    assert result.info.fps == pytest.approx(15.0, abs=0.2)
    assert result.info.height <= 720
    assert result.info.frame_count is not None and result.info.frame_count > 0


@pytest.mark.unit
def test_three_minute_clip_sits_exactly_on_the_cap(clips: dict[str, Path]) -> None:
    info = probe_video(clips["three_minutes"])

    assert info.duration_s == pytest.approx(MAX_DURATION_S, abs=0.5)
    validate_source(clips["three_minutes"], info)


@pytest.mark.unit
def test_overlong_clip_is_rejected_before_transcoding(
    clips: dict[str, Path], scratch: Path
) -> None:
    info = probe_video(clips["overlong"])

    with pytest.raises(VideoTooLong):
        validate_source(clips["overlong"], info)
    assert not (scratch / "overlong_analysis.mp4").exists()

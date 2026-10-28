"""Probe tests: typed metadata, rotation parsing and unreadable inputs."""

from __future__ import annotations

from pathlib import Path

import pytest

from pw.ingest import NoVideoStream, ProbeError, VideoInfo, parse_probe, probe_video


@pytest.mark.unit
def test_probe_reads_stream_facts(media: dict[str, Path]) -> None:
    info = probe_video(media["cfr"])

    assert (info.width, info.height) == (320, 240)
    assert info.fps == pytest.approx(30.0, abs=0.01)
    assert info.duration_s == pytest.approx(2.0, abs=0.1)
    assert info.has_audio is False
    assert info.rotation == 0.0
    assert info.codec == "h264"


@pytest.mark.unit
def test_audio_only_file_has_no_video_stream(media: dict[str, Path]) -> None:
    with pytest.raises(NoVideoStream):
        probe_video(media["audio_only"])


@pytest.mark.unit
def test_corrupt_file_raises_probe_error(media: dict[str, Path]) -> None:
    with pytest.raises(ProbeError):
        probe_video(media["corrupt"])


@pytest.mark.unit
def test_missing_file_raises_file_not_found(scratch: Path) -> None:
    with pytest.raises(FileNotFoundError):
        probe_video(scratch / "nope.mp4")


@pytest.mark.unit
def test_rotation_comes_from_side_data() -> None:
    payload = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "30000/1001",
                "duration": "12.5",
                "side_data_list": [{"rotation": -90}],
            }
        ],
        "format": {"duration": "12.5"},
    }

    info = parse_probe(payload)

    assert info.rotation == -90
    assert info.is_quarter_turned is True
    assert (info.display_width, info.display_height) == (1080, 1920)


@pytest.mark.unit
def test_rotation_falls_back_to_tags() -> None:
    payload = {
        "streams": [
            {
                "codec_type": "video",
                "width": 640,
                "height": 480,
                "avg_frame_rate": "25/1",
                "tags": {"rotate": "90"},
            }
        ]
    }

    assert parse_probe(payload).rotation == 90


@pytest.mark.unit
def test_fractional_frame_rate_is_parsed() -> None:
    payload = {
        "streams": [
            {
                "codec_type": "video",
                "width": 1280,
                "height": 720,
                "avg_frame_rate": "30000/1001",
            }
        ]
    }

    assert parse_probe(payload).fps == pytest.approx(29.97, abs=0.01)


@pytest.mark.unit
def test_video_info_without_rotation_keeps_axes() -> None:
    info = VideoInfo(width=1280, height=720, duration_s=10, fps=30)

    assert (info.display_width, info.display_height) == (1280, 720)
    assert info.is_quarter_turned is False

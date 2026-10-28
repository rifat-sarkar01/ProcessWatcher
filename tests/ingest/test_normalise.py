"""Normalisation tests: CFR output, caps, hostile filenames and keyframes."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pw.ingest import (
    FileTooLarge,
    ProbeError,
    VideoTooLong,
    extract_keyframes,
    normalise_video,
    probe_video,
    sha256_file,
)
from pw.ingest import normalise as normalise_module


@pytest.mark.unit
def test_normalise_produces_a_15fps_copy(media: dict[str, Path], scratch: Path) -> None:
    result = normalise_video(media["cfr"], scratch / "analysis.mp4")

    assert result.path.is_file()
    assert result.fps == 15
    assert result.info.fps == pytest.approx(15.0, abs=0.1)
    assert result.info.height <= 720
    assert result.info.has_audio is False


@pytest.mark.unit
def test_frame_count_matches_duration_times_fps(media: dict[str, Path], scratch: Path) -> None:
    result = normalise_video(media["cfr"], scratch / "analysis.mp4")
    expected = result.info.duration_s * 15

    if result.info.frame_count is not None:
        assert abs(result.info.frame_count - expected) <= 1.5


@pytest.mark.unit
def test_variable_frame_rate_input_becomes_constant(media: dict[str, Path], scratch: Path) -> None:
    source = probe_video(media["vfr"])
    result = normalise_video(media["vfr"], scratch / "analysis.mp4")

    assert source.duration_s > 1.0
    assert result.info.fps == pytest.approx(15.0, abs=0.2)


@pytest.mark.unit
def test_tall_video_is_scaled_to_720p(media: dict[str, Path], scratch: Path) -> None:
    result = normalise_video(media["tall"], scratch / "analysis.mp4")

    assert result.info.height == 720
    assert result.info.width < 480


@pytest.mark.unit
def test_long_video_is_rejected(media: dict[str, Path], scratch: Path) -> None:
    with pytest.raises(VideoTooLong):
        normalise_video(media["long"], scratch / "analysis.mp4")


@pytest.mark.unit
def test_oversized_file_is_rejected(
    media: dict[str, Path], scratch: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(normalise_module, "MAX_BYTES", 1024)

    with pytest.raises(FileTooLarge):
        normalise_video(media["cfr"], scratch / "analysis.mp4")


@pytest.mark.unit
def test_hostile_filename_never_reaches_a_shell(media: dict[str, Path], scratch: Path) -> None:
    result = normalise_video(media["weird_name"], scratch / "analysis.mp4")

    assert result.path.is_file()


@pytest.mark.unit
def test_corrupt_source_is_rejected(media: dict[str, Path], scratch: Path) -> None:
    with pytest.raises(ProbeError):
        normalise_video(media["corrupt"], scratch / "analysis.mp4")


@pytest.mark.unit
def test_sha256_matches_hashlib_and_survives_normalisation(
    media: dict[str, Path], scratch: Path
) -> None:
    expected = hashlib.sha256(media["cfr"].read_bytes()).hexdigest()

    assert sha256_file(media["cfr"]) == expected
    assert normalise_video(media["cfr"], scratch / "analysis.mp4").source_sha256 == expected


@pytest.mark.unit
def test_keyframes_are_png_files(media: dict[str, Path], scratch: Path) -> None:
    written = extract_keyframes(media["cfr"], [0.2, 1.2], scratch / "frames")

    assert len(written) == 2
    for frame in written:
        assert frame.is_file()
        assert frame.read_bytes().startswith(b"\x89PNG")

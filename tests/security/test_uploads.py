"""Upload validation: magic bytes, allowlists, caps and filename sanitation."""

from __future__ import annotations

from pathlib import Path

import pytest

from pw.security.errors import FileTooLarge, UploadRejected, VideoTooLong
from pw.security.uploads import (
    UploadCaps,
    sanitise_filename,
    validate_sop_upload,
    validate_video_upload,
)


def test_valid_video_passes_and_reports_metadata(video: Path) -> None:
    check = validate_video_upload(video)
    assert check.kind == "video"
    assert check.suffix == ".mp4"
    assert check.video is not None
    assert (check.video.width, check.video.height) == (320, 240)
    assert 0.9 <= check.video.duration_s <= 1.1
    assert check.size_bytes == video.stat().st_size


def test_valid_markdown_and_pdf_sops_pass(scratch: Path) -> None:
    markdown = scratch / "steps.md"
    markdown.write_text("# Steps\n\n1. Tighten.\n", encoding="utf-8")
    assert validate_sop_upload(markdown).kind == "sop"

    pdf = scratch / "steps.pdf"
    pdf.write_bytes(b"%PDF-1.7\n% minimal\n")
    assert validate_sop_upload(pdf).suffix == ".pdf"


def test_wrong_magic_is_rejected_even_with_a_video_extension(scratch: Path) -> None:
    fake = scratch / "fake.mp4"
    fake.write_bytes(b"PK\x03\x04" + b"\x00" * 64)
    with pytest.raises(UploadRejected) as info:
        validate_video_upload(fake, prober=lambda path: pytest.fail("must not probe"))
    assert info.value.code == "E-01"


def test_zip_container_is_a_bomb_not_a_video(scratch: Path) -> None:
    bomb = scratch / "bomb.webm"
    bomb.write_bytes(b"PK\x03\x04" + b"\x00" * 10_000)
    with pytest.raises(UploadRejected):
        validate_video_upload(bomb, prober=lambda path: pytest.fail("must not probe"))


def test_disallowed_extension_is_rejected(scratch: Path) -> None:
    script = scratch / "evil.exe"
    script.write_bytes(b"MZ" + b"\x00" * 64)
    with pytest.raises(UploadRejected) as info:
        validate_video_upload(script)
    assert info.value.code == "E-01"


def test_pdf_magic_is_required_for_pdf_sops(scratch: Path) -> None:
    fake = scratch / "notes.pdf"
    fake.write_text("not a pdf", encoding="utf-8")
    with pytest.raises(UploadRejected) as info:
        validate_sop_upload(fake)
    assert info.value.code == "E-01"


def test_size_exactly_at_the_cap_is_allowed(video: Path) -> None:
    size = video.stat().st_size
    check = validate_video_upload(video, caps=UploadCaps(max_bytes=size))
    assert check.size_bytes == size


def test_size_over_the_cap_is_rejected(video: Path) -> None:
    size = video.stat().st_size
    with pytest.raises(FileTooLarge) as info:
        validate_video_upload(video, caps=UploadCaps(max_bytes=size - 1))
    assert info.value.code == "E-03"
    assert info.value.status_code == 413


def test_duration_exactly_at_the_cap_is_allowed(video: Path) -> None:
    duration = validate_video_upload(video).video
    assert duration is not None
    check = validate_video_upload(video, caps=UploadCaps(max_duration_s=duration.duration_s))
    assert check.video is not None


def test_duration_over_the_cap_is_rejected(video: Path) -> None:
    duration = validate_video_upload(video).video
    assert duration is not None
    with pytest.raises(VideoTooLong) as info:
        validate_video_upload(video, caps=UploadCaps(max_duration_s=duration.duration_s - 0.5))
    assert info.value.code == "E-02"
    assert info.value.status_code == 422


def test_resolution_over_the_cap_is_rejected(video: Path) -> None:
    with pytest.raises(UploadRejected) as info:
        validate_video_upload(video, caps=UploadCaps(max_width=100, max_height=100))
    assert info.value.code == "E-01"


def test_unreadable_media_is_rejected(video: Path) -> None:
    def broken(path: Path) -> None:
        raise ValueError("probe failed")

    with pytest.raises(UploadRejected):
        validate_video_upload(video, prober=broken)


def test_missing_file_raises_file_not_found(scratch: Path) -> None:
    with pytest.raises(FileNotFoundError):
        validate_video_upload(scratch / "nope.mp4")


def test_filename_sanitation_strips_paths_and_control_characters() -> None:
    assert sanitise_filename("../../etc/passwd.mp4") == "passwd.mp4"
    assert sanitise_filename(r"C:\Users\evil\clip final.MP4") == "clip_final.mp4"
    assert sanitise_filename("a\x00b\x1f.mp4") == "ab.mp4"
    assert sanitise_filename(".hidden.mp4") == "hidden.mp4"
    assert len(sanitise_filename("x" * 300 + ".mp4")) <= 120

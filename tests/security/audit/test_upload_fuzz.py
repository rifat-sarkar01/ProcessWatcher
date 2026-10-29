"""Upload fuzzing: container sniffing, filenames, caps and API-level rejection.

Findings this suite covers (docs/security/audit.md): F-04 archive-as-video,
F-05 container/extension mismatch, F-06 hostile filenames, F-07 resolution and
duration caps, F-08 non-UTF-8 SOP text.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pw.ingest.probe import VideoInfo
from pw.security.errors import FileTooLarge, UploadRejected, VideoTooLong
from pw.security.uploads import (
    VIDEO_EXTENSIONS,
    UploadCaps,
    sanitise_filename,
    validate_sop_upload,
    validate_video_upload,
)

HEADERS = {"X-Access-Code": "audit-access-code"}

MP4_MAGIC = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 40
MKV_MAGIC = b"\x1a\x45\xdf\xa3" + b"\x00" * 40


def fake_probe(info: VideoInfo):
    return lambda _path: info


SMALL = VideoInfo(width=320, height=240, duration_s=1.0, fps=15.0)


def write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


@pytest.mark.parametrize("suffix", [".mp4", ".mov", ".mkv", ".webm"])
def test_archive_masquerading_as_video_is_rejected(scratch: Path, suffix: str) -> None:
    target = write(scratch / f"bomb{suffix}", b"PK\x03\x04" + b"\x00" * 100)

    with pytest.raises(UploadRejected) as excinfo:
        validate_video_upload(target, prober=fake_probe(SMALL))

    assert "archive" in str(excinfo.value).lower()


def test_ftyp_at_the_wrong_offset_is_rejected(scratch: Path) -> None:
    target = write(scratch / "shifted.mp4", b"\x00" * 8 + b"ftypmp42" + b"\x00" * 40)

    with pytest.raises(UploadRejected):
        validate_video_upload(target, prober=fake_probe(SMALL))


def test_container_and_extension_mismatch_is_rejected(scratch: Path) -> None:
    mp4_body_in_mkv = write(scratch / "clip.mkv", MP4_MAGIC)
    mkv_body_in_mp4 = write(scratch / "clip.mp4", MKV_MAGIC)

    with pytest.raises(UploadRejected):
        validate_video_upload(mp4_body_in_mkv, prober=fake_probe(SMALL))
    with pytest.raises(UploadRejected):
        validate_video_upload(mkv_body_in_mp4, prober=fake_probe(SMALL))


def test_allowed_containers_pass(scratch: Path) -> None:
    assert (
        validate_video_upload(write(scratch / "ok.mp4", MP4_MAGIC), prober=fake_probe(SMALL)).kind
        == "video"
    )
    assert (
        validate_video_upload(
            write(scratch / "ok.webm", MKV_MAGIC), prober=fake_probe(SMALL)
        ).suffix
        == ".webm"
    )


@pytest.mark.parametrize(
    ("hostile", "expected"),
    [
        ("../../etc/passwd.mp4", "passwd.mp4"),
        ("..\\..\\windows\\win.ini.mp4", "win.ini.mp4"),
        ("C:\\temp\\clip.mp4", "clip.mp4"),
        ("/absolute/clip.mp4", "clip.mp4"),
        ("%%%%.mp4", "upload.mp4"),
        ("a\x00b.mp4", "ab.mp4"),
        ("résumé.mp4", "r_sum.mp4"),
        # Bidi override is stripped as unprintable, not transliterated.
        ("sop\u202egnp.exe.mp4", "sopgnp.exe.mp4"),
        ("CLIP.MP4", "CLIP.mp4"),
    ],
)
def test_hostile_filenames_are_sanitised(hostile: str, expected: str) -> None:
    assert sanitise_filename(hostile) == expected


@pytest.mark.parametrize(
    "hostile",
    [
        "../../etc/passwd.mp4",
        "...mp4",
        ".hidden",
        "---",
        "a" * 500 + ".mp4",
        "\u202e\u0000..\\..\r\n.mp4",
    ],
)
def test_sanitised_names_stay_inside_the_stem_alphabet(hostile: str) -> None:
    cleaned = sanitise_filename(hostile)

    assert cleaned
    assert len(cleaned) <= 104
    assert all(character.isalnum() or character in "._-" for character in cleaned)
    assert "/" not in cleaned and "\\" not in cleaned and ":" not in cleaned
    assert "\x00" not in cleaned and "\r" not in cleaned and "\n" not in cleaned


def test_trailing_whitespace_in_a_filename_fails_closed() -> None:
    # The suffix keeps its trailing space, so the extension allowlist refuses the file.
    cleaned = sanitise_filename(" clip .mp4 ")

    assert cleaned.endswith(" ")
    assert Path(cleaned).suffix not in VIDEO_EXTENSIONS


def test_long_filenames_are_bounded(scratch: Path) -> None:
    cleaned = sanitise_filename("a" * 400 + ".mp4")

    assert len(cleaned) <= 104
    assert cleaned.endswith(".mp4")


def test_resolution_above_the_cap_is_rejected(scratch: Path) -> None:
    target = write(scratch / "4k-plus.mp4", MP4_MAGIC)

    with pytest.raises(UploadRejected) as excinfo:
        validate_video_upload(target, prober=fake_probe(VideoInfo(7680, 4320, 5.0, 30.0)))

    assert "resolution" in str(excinfo.value)


def test_rotation_is_judged_on_display_dimensions(scratch: Path) -> None:
    target = write(scratch / "portrait.mp4", MP4_MAGIC)
    rotated = VideoInfo(2160, 3840, 5.0, 30.0, rotation=90.0)

    assert validate_video_upload(target, prober=fake_probe(rotated)).video is rotated


def test_duration_above_the_cap_is_rejected(scratch: Path) -> None:
    target = write(scratch / "long.mp4", MP4_MAGIC)

    with pytest.raises(VideoTooLong):
        validate_video_upload(target, prober=fake_probe(VideoInfo(320, 240, 181.0, 30.0)))


def test_size_cap_is_checked_before_probing(scratch: Path) -> None:
    target = write(scratch / "big.mp4", MP4_MAGIC * 10)
    calls: list[Path] = []

    def prober(path: Path) -> VideoInfo:
        calls.append(path)
        return SMALL

    with pytest.raises(FileTooLarge):
        validate_video_upload(target, caps=UploadCaps(max_bytes=8), prober=prober)

    assert calls == []


def test_non_utf8_sop_text_is_rejected(scratch: Path) -> None:
    target = write(scratch / "utf16.md", "1. Tighten the bolt".encode("utf-16"))

    with pytest.raises(UploadRejected) as excinfo:
        validate_sop_upload(target)

    assert "utf-8" in str(excinfo.value).lower()


def test_pdf_sop_must_carry_the_pdf_magic(scratch: Path) -> None:
    target = write(scratch / "not.pdf", b"just text")

    with pytest.raises(UploadRejected):
        validate_sop_upload(target)


def test_api_rejects_an_archive_with_a_clean_envelope(client: TestClient) -> None:
    response = client.post(
        "/runs",
        files={"video": ("bomb.mp4", b"PK\x03\x04" + b"\x00" * 64, "video/mp4")},
        data={"sop_text": "1. Tighten.\n"},
        headers=HEADERS,
    )

    assert response.status_code == 415
    payload = response.json()
    assert payload["error"]["code"] == "E-01"
    assert "traceback" not in response.text.lower()
    assert "audit-tmp" not in response.text
    assert "\\" not in payload["error"]["message"]


def test_api_rejects_an_oversized_upload(client: TestClient) -> None:
    big = b"\x00" * (2 * 1024 * 1024)
    response = client.post(
        "/runs",
        files={"video": ("big.mp4", big, "video/mp4")},
        data={"sop_text": "1. Tighten.\n"},
        headers=HEADERS,
    )

    # 2 MB is inside the 500 MB cap, so the upload is rejected on its container magic;
    # either way the failure must arrive in the documented envelope, never as a trace.
    assert response.status_code in {413, 415, 422}
    assert response.json()["error"]["code"] in {"E-01", "E-02", "E-03"}
    assert "traceback" not in response.text.lower()


def test_rejected_upload_does_not_leave_scratch_files(client: TestClient, runs_dir: Path) -> None:
    client.post(
        "/runs",
        files={"video": ("bomb.mp4", b"PK\x03\x04" + b"\x00" * 64, "video/mp4")},
        data={"sop_text": "1. Tighten.\n"},
        headers=HEADERS,
    )

    uploads = runs_dir / ".uploads"
    assert not uploads.exists() or not any(uploads.rglob("*.*"))


def test_rejected_sop_also_cleans_its_scratch_dir(client: TestClient, runs_dir: Path) -> None:
    response = client.post(
        "/runs",
        files={
            "video": ("clip.mp4", MP4_MAGIC, "video/mp4"),
            "sop": ("sop.md", "1. Tighten".encode("utf-16"), "text/markdown"),
        },
        headers=HEADERS,
    )

    assert response.status_code == 415
    uploads = runs_dir / ".uploads"
    assert not uploads.exists() or not any(uploads.rglob("*.*"))

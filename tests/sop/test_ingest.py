"""Tests for SOP ingest (T-3.1): md, txt, text PDF, scanned PDF, caps and errors."""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path

import pymupdf
import pytest

from pw.sop.ingest import (
    MAX_PAGES,
    SopSource,
    from_text,
    normalise_numbering,
    read_sop,
)

BENCH_SOPS = Path(__file__).resolve().parents[2] / "bench" / "sops"
SCRATCH_ROOT = Path(__file__).resolve().parents[2] / ".uv" / "tests-tmp"


@pytest.fixture
def scratch() -> Iterator[Path]:
    """Repo-local scratch directory (pytest tmp_path is unusable on this host)."""
    path = SCRATCH_ROOT / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def make_text_pdf(pages: int = 1, text: str = "SOP step text for the test.") -> bytes:
    document = pymupdf.open()
    for index in range(pages):
        page = document.new_page()
        page.insert_text((72, 72), f"{index + 1}. {text}")
    data: bytes = document.tobytes()
    document.close()
    return data


def make_scanned_pdf() -> bytes:
    """A PDF whose only content is an image (no text layer)."""
    document = pymupdf.open()
    page = document.new_page()
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 64, 64), False)
    pixmap.clear_with(200)
    page.insert_image(pymupdf.Rect(72, 72, 300, 300), stream=pixmap.tobytes("png"))
    data: bytes = document.tobytes()
    document.close()
    return data


# --- numbering normalisation --------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1) Open the case.", "1. Open the case."),
        ("Step 2: Remove the panel.", "2. Remove the panel."),
        ("(3) Fit the drive", "3. Fit the drive"),
        ("4. Already normalised", "4. Already normalised"),
        ("Not a numbered line", "Not a numbered line"),
    ],
)
def test_normalise_numbering(raw: str, expected: str) -> None:
    assert normalise_numbering(raw) == expected


@pytest.mark.unit
def test_normalise_numbering_keeps_line_structure() -> None:
    text = "Title\n\n1) first\n2. second   "

    assert normalise_numbering(text) == "Title\n\n1. first\n2. second"


# --- markdown / text -----------------------------------------------------------------


@pytest.mark.unit
def test_read_markdown_sop() -> None:
    source = read_sop(BENCH_SOPS / "P-A-ssd-swap.md")

    assert source.kind == "md"
    assert source.needs_vision is False
    assert source.page_count is None
    assert source.images == ()
    assert len(source.sha256) == 64
    assert "1. Power the PC down" in source.text


@pytest.mark.unit
def test_read_text_sop(scratch: Path) -> None:
    path = scratch / "procedure.txt"
    path.write_bytes(b"1) Inspect the flange.\r\n2) Seat the bolts.\r\n")

    source = read_sop(path)

    assert source.kind == "txt"
    assert source.text == "1. Inspect the flange.\n2. Seat the bolts."


@pytest.mark.unit
def test_read_text_sop_accepts_windows_1252(scratch: Path) -> None:
    path = scratch / "procedure.txt"
    path.write_bytes("1. Torque 25 Nµm".encode("cp1252"))

    source = read_sop(path)

    assert "Nµm" in source.text


# --- PDFs -----------------------------------------------------------------------------


@pytest.mark.unit
def test_read_text_pdf(scratch: Path) -> None:
    path = scratch / "sop.pdf"
    path.write_bytes(make_text_pdf(pages=2))

    source = read_sop(path)

    assert source.kind == "pdf"
    assert source.page_count == 2
    assert source.needs_vision is False
    assert source.images == ()
    assert "SOP step text for the test." in source.text


@pytest.mark.unit
def test_scanned_pdf_is_flagged_for_vision_and_rendered(scratch: Path) -> None:
    path = scratch / "scan.pdf"
    path.write_bytes(make_scanned_pdf())

    source = read_sop(path)

    assert source.kind == "pdf"
    assert source.needs_vision is True
    assert len(source.images) == 1
    assert source.images[0].page == 1
    assert source.images[0].png.startswith(b"\x89PNG")


@pytest.mark.unit
def test_pdf_page_cap_is_enforced(scratch: Path) -> None:
    path = scratch / "huge.pdf"
    path.write_bytes(make_text_pdf(pages=MAX_PAGES + 1))

    with pytest.raises(ValueError, match="the limit is"):
        read_sop(path)


@pytest.mark.unit
def test_corrupt_pdf_is_rejected(scratch: Path) -> None:
    path = scratch / "broken.pdf"
    path.write_bytes(b"this is definitely not a pdf")

    with pytest.raises(ValueError, match="not a valid PDF"):
        read_sop(path)


# --- errors and caps ------------------------------------------------------------------


@pytest.mark.unit
def test_empty_file_is_rejected(scratch: Path) -> None:
    path = scratch / "empty.md"
    path.write_bytes(b"")

    with pytest.raises(ValueError, match="empty"):
        read_sop(path)


@pytest.mark.unit
def test_whitespace_only_file_is_rejected(scratch: Path) -> None:
    path = scratch / "blank.txt"
    path.write_text("   \n\n\t\n", encoding="utf-8")

    with pytest.raises(ValueError, match="empty"):
        read_sop(path)


@pytest.mark.unit
def test_unsupported_extension_is_rejected(scratch: Path) -> None:
    path = scratch / "sop.docx"
    path.write_bytes(b"PK\x03\x04")

    with pytest.raises(ValueError, match="unsupported SOP type"):
        read_sop(path)


@pytest.mark.unit
def test_missing_file_is_reported(scratch: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_sop(scratch / "missing.md")


@pytest.mark.unit
def test_oversized_file_is_rejected(scratch: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from pw.sop import ingest

    monkeypatch.setattr(ingest, "MAX_FILE_BYTES", 10)
    path = scratch / "big.txt"
    path.write_text("1. A step that is longer than ten bytes", encoding="utf-8")

    with pytest.raises(ValueError, match="the limit is"):
        read_sop(path)


# --- pasted text ----------------------------------------------------------------------


@pytest.mark.unit
def test_from_text_normalises_and_hashes() -> None:
    source = from_text("1) Inspect.\n2) Torque.")

    assert isinstance(source, SopSource)
    assert source.kind == "pasted"
    assert source.text == "1. Inspect.\n2. Torque."
    assert len(source.sha256) == 64
    assert source.needs_vision is False


@pytest.mark.unit
def test_from_text_rejects_blank() -> None:
    with pytest.raises(ValueError, match="empty"):
        from_text("   \n  ")

"""SOP ingest: normalise `.md`, `.txt` and `.pdf` sources into one `SopSource`.

Text-based files are read directly. A PDF is read with PyMuPDF; when it carries no
usable text layer (a scan or a photo export) every page is rendered to a PNG and the
source is flagged `needs_vision=True` so the SOP compiler (T-3.2) can send page images
to Muse Wonder instead of pretending the PDF had text.

This module never calls a model and never interprets the SOP into steps — that is the
compiler's job. It only guarantees: a non-empty source, a SHA-256 of the raw bytes,
a page count for PDFs, numbering normalised to `1. ` lines, and a hard page cap.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_PAGES = 50
"""Upper bound for a PDF SOP (06_Plan.md T-3.1 'Size caps (<= 50 pages)')."""

MAX_FILE_BYTES = 20 * 1024 * 1024
"""Refuse absurd uploads before a PDF parser sees them."""

MIN_TEXT_CHARS = 40
"""Below this much extracted text a PDF is treated as scanned."""

RENDER_DPI = 150
"""Page render resolution for scanned PDFs sent to Wonder vision."""

_MARKDOWN_SUFFIXES = frozenset({".md", ".markdown"})
_TEXT_SUFFIXES = frozenset({".txt", ".text"})
_PDF_SUFFIXES = frozenset({".pdf"})

# "1)" / "1." / "Step 1:" / "(1)" at the start of a line -> "1. "
_NUMBERED_LINE = re.compile(
    r"^\s*(?:step\s+)?\(?(\d{1,2})\)?\s*[).:]\s+",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class PageImage:
    """One rendered PDF page, 1-based page number, PNG bytes."""

    page: int
    png: bytes


@dataclass(frozen=True, slots=True)
class SopSource:
    """A normalised SOP ready for the compiler."""

    kind: str
    text: str
    sha256: str
    page_count: int | None = None
    images: tuple[PageImage, ...] = ()
    needs_vision: bool = False

    @property
    def is_empty(self) -> bool:
        return not self.text.strip() and not self.images


def normalise_numbering(text: str) -> str:
    """Rewrite numbered lines to a single `N. ` form and trim trailing spaces."""
    lines: list[str] = []
    for line in text.splitlines():
        match = _NUMBERED_LINE.match(line)
        if match is not None:
            line = f"{int(match.group(1))}. {line[match.end() :]}"
        lines.append(line.rstrip())
    return "\n".join(lines).strip("\n")


def _decode(data: bytes) -> str:
    """Decode text bytes: UTF-8 first (with BOM), then Windows-1252 as a fallback."""
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("SOP text is not valid UTF-8 or Windows-1252")


def _from_text(data: bytes, kind: str) -> SopSource:
    text = normalise_numbering(_decode(data))
    if not text.strip():
        raise ValueError("SOP is empty")
    return SopSource(
        kind=kind,
        text=text,
        sha256=hashlib.sha256(data).hexdigest(),
    )


def _page_texts(document: Any) -> list[str]:
    return [page.get_text("text") for page in document]


def _render_pages(document: Any) -> tuple[PageImage, ...]:
    images: list[PageImage] = []
    for page in document:
        pixmap = page.get_pixmap(dpi=RENDER_DPI)
        images.append(PageImage(page=int(page.number) + 1, png=bytes(pixmap.tobytes("png"))))
    return tuple(images)


def _from_pdf(data: bytes) -> SopSource:
    try:
        import pymupdf
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise RuntimeError("PyMuPDF is required to read PDF SOPs") from exc

    try:
        # PyMuPDF exposes no complete type information; the document is used
        # through a narrow, typed surface below.
        document = pymupdf.open(stream=data, filetype="pdf")  # type: ignore[no-untyped-call]
    except Exception as exc:  # pymupdf raises RuntimeError/FileDataError
        raise ValueError(f"not a valid PDF: {exc}") from exc

    try:
        page_count = int(document.page_count)
        if page_count == 0:
            raise ValueError("PDF has no pages")
        if page_count > MAX_PAGES:
            raise ValueError(f"PDF has {page_count} pages, the limit is {MAX_PAGES}")

        extracted = normalise_numbering("\n\n".join(_page_texts(document)))
        needs_vision = len(extracted.strip()) < MIN_TEXT_CHARS
        images = _render_pages(document) if needs_vision else ()
    finally:
        document.close()  # type: ignore[no-untyped-call]

    if not extracted.strip() and not images:
        raise ValueError("PDF has neither text nor renderable pages")

    return SopSource(
        kind="pdf",
        text=extracted,
        sha256=hashlib.sha256(data).hexdigest(),
        page_count=page_count,
        images=images,
        needs_vision=needs_vision,
    )


def read_sop(path: Path | str) -> SopSource:
    """Read one SOP file into a `SopSource`.

    Raises `FileNotFoundError` for a missing path, `ValueError` for an empty,
    oversized, unsupported or corrupt source.
    """
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"SOP not found: {source}")

    data = source.read_bytes()
    if not data:
        raise ValueError(f"SOP is empty: {source.name}")
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(
            f"SOP is {len(data) / (1024 * 1024):.1f} MB, the limit is "
            f"{MAX_FILE_BYTES // (1024 * 1024)} MB"
        )

    suffix = source.suffix.lower()
    if suffix in _MARKDOWN_SUFFIXES:
        return _from_text(data, "md")
    if suffix in _TEXT_SUFFIXES:
        return _from_text(data, "txt")
    if suffix in _PDF_SUFFIXES:
        return _from_pdf(data)

    raise ValueError(f"unsupported SOP type {suffix or '<none>'!r}; expected .md, .txt or .pdf")


def from_text(text: str, kind: str = "pasted") -> SopSource:
    """Build a `SopSource` from text that arrived through the API (no file)."""
    data = text.encode("utf-8")
    if not data:
        raise ValueError("SOP is empty")
    normalised = normalise_numbering(text)
    if not normalised.strip():
        raise ValueError("SOP is empty")
    return SopSource(kind=kind, text=normalised, sha256=hashlib.sha256(data).hexdigest())

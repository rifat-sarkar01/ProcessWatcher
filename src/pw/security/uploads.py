"""Upload validation: extension allowlist, magic bytes, caps and filename sanitation.

Caps come from `04_TRD.md` §5 ingestion limits (500 MB, 180 s, 3840x2160 source) and
the E-01..E-03 error messages in `02_AppFlow.md` §6; ADR-001 only fixes SAM limits.
"""

from __future__ import annotations

import os
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pw.ingest.errors import IngestError
from pw.ingest.normalise import MAX_BYTES, MAX_DURATION_S
from pw.ingest.probe import VideoInfo, probe_video
from pw.security.errors import FileTooLarge, UploadRejected, VideoTooLong

MAX_WIDTH = 3840
MAX_HEIGHT = 2160
VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".mkv", ".webm"})
SOP_EXTENSIONS = frozenset({".md", ".txt", ".pdf"})
_MAGIC_BYTES = 64
_ZIP_MAGIC = b"PK\x03\x04"


@dataclass(frozen=True, slots=True)
class UploadCaps:
    max_bytes: int = MAX_BYTES
    max_duration_s: float = MAX_DURATION_S
    max_width: int = MAX_WIDTH
    max_height: int = MAX_HEIGHT


@dataclass(frozen=True, slots=True)
class UploadCheck:
    filename: str
    suffix: str
    kind: str
    size_bytes: int
    video: VideoInfo | None = None


def sanitise_filename(name: str) -> str:
    """Basename only, printable ASCII-ish stem, lowercase extension, bounded length."""
    normalised = unicodedata.normalize("NFKC", name).replace("\\", "/")
    base = PurePosixPath(normalised).name
    base = "".join(character for character in base if character.isprintable())
    stem, suffix = os.path.splitext(base)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or "upload"
    return f"{stem[:100]}{suffix.lower()}"


def _head(path: Path) -> bytes:
    with path.open("rb") as handle:
        return handle.read(_MAGIC_BYTES)


def _is_zip(head: bytes) -> bool:
    return head.startswith(_ZIP_MAGIC)


def _check_video_magic(source: Path, suffix: str) -> None:
    head = _head(source)
    if _is_zip(head):
        raise UploadRejected("that file is an archive, not a video")
    if suffix in {".mp4", ".mov"}:
        if head[4:8] != b"ftyp":
            raise UploadRejected("that file type isn't supported (expected an MP4 container)")
    elif head[:4] != b"\x1a\x45\xdf\xa3":
        raise UploadRejected("that file type isn't supported (expected a Matroska container)")


def _check_sop_magic(source: Path, suffix: str) -> None:
    if suffix != ".pdf":
        return
    if not _head(source).startswith(b"%PDF-"):
        raise UploadRejected("that file type isn't supported (expected a PDF)")


def _size(source: Path, caps: UploadCaps) -> int:
    size = source.stat().st_size
    if size > caps.max_bytes:
        limit_mb = caps.max_bytes // (1024 * 1024)
        raise FileTooLarge(f"file is {size / (1024 * 1024):.1f} MB, the limit is {limit_mb} MB")
    return size


def validate_video_upload(
    path: Path | str,
    *,
    caps: UploadCaps | None = None,
    prober: Callable[[Path], VideoInfo] | None = None,
) -> UploadCheck:
    """Validate one uploaded video before it reaches the run store."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"upload not found: {source}")
    settings = caps or UploadCaps()
    size = _size(source, settings)
    filename = sanitise_filename(source.name)
    suffix = Path(filename).suffix
    if suffix not in VIDEO_EXTENSIONS:
        raise UploadRejected("that file type isn't supported. Use mp4, mov, webm or mkv.")
    _check_video_magic(source, suffix)

    try:
        info = (prober or probe_video)(source)
    except (IngestError, ValueError, OSError) as exc:
        raise UploadRejected(f"could not read the video: {exc}") from exc
    if info.duration_s > settings.max_duration_s:
        raise VideoTooLong(
            f"video is {info.duration_s:.1f} s, the limit is {settings.max_duration_s:g} s"
        )
    if info.display_width > settings.max_width or info.display_height > settings.max_height:
        raise UploadRejected(
            "video resolution "
            f"{info.display_width}x{info.display_height} exceeds "
            f"{settings.max_width}x{settings.max_height}"
        )
    return UploadCheck(filename=filename, suffix=suffix, kind="video", size_bytes=size, video=info)


def validate_sop_upload(path: Path | str, *, caps: UploadCaps | None = None) -> UploadCheck:
    """Validate a SOP file (Markdown, plain text or PDF)."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"upload not found: {source}")
    settings = caps or UploadCaps()
    size = _size(source, settings)
    filename = sanitise_filename(source.name)
    suffix = Path(filename).suffix
    if suffix not in SOP_EXTENSIONS:
        raise UploadRejected("that SOP type isn't supported. Use md, txt or pdf.")
    _check_sop_magic(source, suffix)
    if suffix != ".pdf":
        try:
            source.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise UploadRejected("that SOP is not valid UTF-8 text") from exc
    return UploadCheck(filename=filename, suffix=suffix, kind="sop", size_bytes=size)


__all__ = [
    "MAX_HEIGHT",
    "MAX_WIDTH",
    "SOP_EXTENSIONS",
    "VIDEO_EXTENSIONS",
    "UploadCaps",
    "UploadCheck",
    "sanitise_filename",
    "validate_sop_upload",
    "validate_video_upload",
]

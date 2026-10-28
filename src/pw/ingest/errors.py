"""Typed ingest failures, so callers can react to a cause instead of parsing strings."""

from __future__ import annotations


class IngestError(Exception):
    """Base class for every recoverable ingest problem."""


class ProbeError(IngestError):
    """The file could not be read as media at all (corrupt, truncated, unreadable)."""


class NoVideoStream(IngestError):
    """The media is readable but carries no video stream."""


class FileTooLarge(IngestError):
    """The source exceeds the byte cap (04_TRD §7 `limits.max_mb`)."""


class VideoTooLong(IngestError):
    """The source exceeds the duration cap (04_TRD §7 `limits.max_duration_s`)."""

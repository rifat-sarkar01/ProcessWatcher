"""Typed security failures carrying the API error envelope (`05_Schema.md` §13)."""

from __future__ import annotations

from typing import Any


class SecurityError(Exception):
    """Base failure: `code` is the E-xx code, `status_code` the HTTP mapping."""

    status_code = 400
    code = "E-01"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def to_payload(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message}}


class UploadRejected(SecurityError):
    """Wrong magic bytes, extension, resolution or unreadable media."""

    status_code = 415
    code = "E-01"


class FileTooLarge(SecurityError):
    status_code = 413
    code = "E-03"


class VideoTooLong(SecurityError):
    status_code = 422
    code = "E-02"


class AccessDenied(SecurityError):
    status_code = 401
    code = "E-05"


class RateLimited(SecurityError):
    status_code = 429
    code = "E-05"

    def __init__(self, message: str, *, retry_after_s: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class PathNotAllowed(SecurityError):
    status_code = 404
    code = "E-13"


__all__ = [
    "AccessDenied",
    "FileTooLarge",
    "PathNotAllowed",
    "RateLimited",
    "SecurityError",
    "UploadRejected",
    "VideoTooLong",
]

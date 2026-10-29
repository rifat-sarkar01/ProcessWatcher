"""Access-code verification: constant-time comparison, fail closed when unset."""

from __future__ import annotations

import hmac
import os
from typing import Annotated

from fastapi import Header

from pw.security.errors import AccessDenied

ENV_VAR = "PW_ACCESS_CODE"
HEADER = "X-Access-Code"
_MESSAGE = "Access code required."


def verify_access_code(provided: str | None, *, expected: str | None = None) -> None:
    """Raise `AccessDenied` unless the code matches the configured secret."""
    secret = os.environ.get(ENV_VAR, "") if expected is None else expected
    if not secret or not provided:
        raise AccessDenied(_MESSAGE)
    if not hmac.compare_digest(provided.encode("utf-8"), secret.encode("utf-8")):
        raise AccessDenied(_MESSAGE)


def require_access_code(
    x_access_code: Annotated[str | None, Header(alias=HEADER)] = None,
) -> None:
    """FastAPI dependency; T-5.2 maps `AccessDenied` to the 401 error envelope."""
    verify_access_code(x_access_code)


__all__ = ["ENV_VAR", "HEADER", "require_access_code", "verify_access_code"]

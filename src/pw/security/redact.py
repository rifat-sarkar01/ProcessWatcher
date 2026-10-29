"""Secret redaction for logs and error payloads (NFR-05)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, cast

PLACEHOLDER = "[REDACTED]"
_SECRET_KEYS = frozenset(
    {"authorization", "x-access-code", "meta_api_key", "pw_access_code", "api_key"}
)
_PATTERN = re.compile(
    r"(?i)"
    r"((?:authorization|x-access-code|meta_api_key|pw_access_code|api[_-]?key)"
    r"[\"']?\s*[:=]\s*[\"']?)"
    r"((?:bearer\s+)?[^\s,}}\"']+)"
)


def redact(text: str) -> str:
    """Replace header/env/JSON secret values with a placeholder."""
    return _PATTERN.sub(rf"\g<1>{PLACEHOLDER}", text)


def _redact_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: (PLACEHOLDER if str(key).lower() in _SECRET_KEYS else _redact_value(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, str):
        return redact(value)
    return value


def redact_mapping(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively redact a structured log/error payload without changing its shape."""
    return cast(dict[str, Any], _redact_value(payload))


__all__ = ["PLACEHOLDER", "redact", "redact_mapping"]

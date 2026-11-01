"""Muse Wonder client: Responses API with usage accounting."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pw.clients.base import ModelClient, Usage
from pw.clients.pricing import WONDER_MODEL
from pw.clients.transport import READ_TIMEOUT_S


@dataclass(frozen=True, slots=True)
class WonderResult:
    body: Mapping[str, Any]
    text: str | None
    usage: Usage

    @property
    def tokens_in(self) -> int:
        return self.usage.tokens_in

    @property
    def tokens_out(self) -> int:
        return self.usage.tokens_out


class WonderClient(ModelClient):
    model = WONDER_MODEL

    def create_response(
        self,
        payload: Mapping[str, Any],
        *,
        operation: str = "responses",
        timeout_s: float = READ_TIMEOUT_S,
    ) -> WonderResult:
        body = self._call_json("/responses", payload, operation=operation, timeout_s=timeout_s)
        return WonderResult(body=body, text=extract_text(body), usage=self._usage(body))

    def _usage(self, body: Mapping[str, Any]) -> Usage:
        usage = body.get("usage")
        if not isinstance(usage, Mapping):
            return Usage()
        return Usage(
            tokens_in=_int(usage.get("input_tokens")),
            tokens_out=_int(usage.get("output_tokens")),
        )


def extract_text(body: Mapping[str, Any]) -> str | None:
    """Return the concatenated `output_text` parts, or None when the run produced none."""
    parts: list[str] = []
    for item in body.get("output") or ():
        if not isinstance(item, Mapping):
            continue
        for part in item.get("content") or ():
            if isinstance(part, Mapping) and part.get("type") == "output_text":
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
    return "".join(parts) if parts else None


def _int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


__all__ = ["WonderClient", "WonderResult", "extract_text"]

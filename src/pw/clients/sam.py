"""SAM 3.1 client: segmentation through the same Responses API (ADR-001)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pw.clients.base import ModelClient, Usage
from pw.clients.pricing import SAM_MODEL
from pw.clients.transport import VIDEO_TIMEOUT_S


@dataclass(frozen=True, slots=True)
class SamResult:
    body: Mapping[str, Any]
    usage: Usage

    @property
    def sam_units(self) -> int:
        return self.usage.sam_units


class SamClient(ModelClient):
    model = SAM_MODEL

    def segment(
        self,
        payload: Mapping[str, Any],
        *,
        operation: str = "sam.segment",
        timeout_s: float = VIDEO_TIMEOUT_S,
    ) -> SamResult:
        body = self._call_json("/responses", payload, operation=operation, timeout_s=timeout_s)
        return SamResult(body=body, usage=self._usage(body))

    def _usage(self, body: Mapping[str, Any]) -> Usage:
        usage = body.get("usage")
        if not isinstance(usage, Mapping):
            return Usage()
        processed = usage.get("images_processed")
        # ADR-001: SAM bills per processed frame; the API reports `images_processed`.
        if isinstance(processed, int) and not isinstance(processed, bool):
            return Usage(sam_units=processed)
        return Usage()


__all__ = ["SamClient", "SamResult"]

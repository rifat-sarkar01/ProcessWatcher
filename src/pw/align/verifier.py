"""Verifier pass: an independent second look at each finding.

The aligner decides what is flagged; the verifier only checks it. A missed step is
checked for negative evidence ("did step X happen in this gap?"), wrong-tool and
out-of-order findings get a second look with the expected/observed tools. Agreement
raises confidence; disagreement downgrades to `needs_review` (never silently drops a
finding). A failed call keeps the original finding and records `verifier_unavailable`,
and `PW_DISABLE_VERIFIER` skips the pass entirely.

The model is a callable (`Verifier`), so `pw.clients` plugs in at T-3.9 and tests use a
fake without touching the network.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any

from pw.align.deviations import Deviation

VERIFIER_VERSION = "verify-1.0.0"
TIME_TOLERANCE_S = 0.5
MAX_NOTE_CHARS = 300

Verifier = Callable[[str], str]

_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")
_TIME = re.compile(r"(?<![\d:])(\d{1,3}):([0-5]\d)(?:\.(\d+))?(?![\d:])")


@dataclass(frozen=True, slots=True)
class VerifierParams:
    """Confidence nudges and the kill switch (03_Plan T-3.7 / AGENTS.md §15)."""

    enabled: bool = True
    confidence_bonus: float = 0.1
    confidence_penalty: float = 0.2

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence_bonus <= 1.0:
            raise ValueError("confidence_bonus must be within [0, 1]")
        if not 0.0 <= self.confidence_penalty <= 1.0:
            raise ValueError("confidence_penalty must be within [0, 1]")


@dataclass(frozen=True, slots=True)
class VerifyResult:
    deviations: tuple[Deviation, ...]
    verifiers: dict[str, dict[str, Any]]


def format_time(seconds: float) -> str:
    total = max(0.0, seconds)
    minutes = int(total // 60)
    return f"{minutes:02d}:{total - minutes * 60:04.1f}"


def _clip(note: str) -> str:
    return note[:MAX_NOTE_CHARS]


def build_verifier_prompt(deviation: Deviation) -> str:
    """Prompt for one finding; deterministic and self-contained."""
    lines = [
        f"VERIFIER {VERIFIER_VERSION}",
        "",
        "A deterministic aligner flagged this finding. Check it independently.",
        f"- type: {deviation.type}",
        f"- step: {deviation.step_id}",
        f"- window: {format_time(deviation.t_start)} - {format_time(deviation.t_end)}",
        f"- confidence: {deviation.confidence:.2f}",
    ]
    if deviation.relates_to_step_id:
        lines.append(f"- related step: {deviation.relates_to_step_id}")
    if deviation.expected_tools:
        lines.append(f"- expected tools: {', '.join(deviation.expected_tools)}")
    if deviation.observed_tools:
        lines.append(f"- observed tools: {', '.join(deviation.observed_tools)}")
    lines.extend(
        [
            "",
            'Watch only that window. For a missed step, "occurred": false means the',
            "step did not happen. Be conservative: if the clip is inconclusive, set",
            "confidence below 0.5.",
            "",
            "Return strict JSON and nothing else:",
            '{"occurred": true | false, "confidence": 0.0, "note": "why", "times": ["mm:ss.s"]}',
        ]
    )
    return "\n".join(lines)


def _parse(raw: str) -> dict[str, Any]:
    text = _FENCE.sub("", raw.strip())
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid_json: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("not_an_object")
    if not isinstance(payload.get("occurred"), bool):
        raise ValueError("occurred_not_boolean")
    return payload


def _times(values: object) -> tuple[float, ...]:
    if not isinstance(values, list):
        return ()
    parsed: list[float] = []
    for value in values:
        if isinstance(value, (int, float)):
            parsed.append(float(value))
            continue
        if not isinstance(value, str):
            continue
        match = _TIME.search(value)
        if match is None:
            continue
        seconds = float(int(match.group(1)) * 60 + int(match.group(2)))
        if match.group(3):
            seconds += float(f"0.{match.group(3)}")
        parsed.append(seconds)
    return tuple(parsed)


def _agrees(deviation: Deviation, occurred: bool) -> bool:
    return not occurred if deviation.type == "missed" else occurred


def verify_deviations(
    deviations: Sequence[Deviation],
    *,
    verifier: Verifier,
    params: VerifierParams | None = None,
) -> VerifyResult:
    """Return updated findings plus the contract-shaped verifier record per id."""
    settings = params or VerifierParams()
    updated: list[Deviation] = []
    records: dict[str, dict[str, Any]] = {}

    for deviation in deviations:
        if not settings.enabled:
            updated.append(deviation)
            records[deviation.id] = {"ran": False, "agreed": None, "note": "PW_DISABLE_VERIFIER"}
            continue

        try:
            raw = verifier(build_verifier_prompt(deviation))
        except Exception as exc:  # any transport failure keeps the finding
            updated.append(deviation)
            records[deviation.id] = {
                "ran": False,
                "agreed": None,
                "note": _clip(f"verifier_unavailable: {type(exc).__name__}"),
            }
            continue

        try:
            payload = _parse(raw)
        except ValueError as exc:
            updated.append(deviation)
            records[deviation.id] = {
                "ran": True,
                "agreed": None,
                "note": _clip(f"unverified: {exc}"),
            }
            continue

        occurred = bool(payload["occurred"])
        note = str(payload.get("note") or "").strip()
        if _agrees(deviation, occurred):
            updated.append(
                replace(
                    deviation,
                    confidence=min(1.0, deviation.confidence + settings.confidence_bonus),
                )
            )
            records[deviation.id] = {
                "ran": True,
                "agreed": True,
                "note": _clip(f"confirmed: {note}" if note else "confirmed"),
            }
            continue

        pieces = [f"rejected: {note}" if note else "rejected by the second look"]
        cited = _times(payload.get("times"))
        if (
            deviation.type == "missed"
            and occurred
            and cited
            and not any(
                deviation.t_start - TIME_TOLERANCE_S <= value <= deviation.t_end + TIME_TOLERANCE_S
                for value in cited
            )
        ):
            pieces.append("cited times fall outside the gap")
        updated.append(
            replace(
                deviation,
                status="needs_review",
                confidence=max(0.0, deviation.confidence - settings.confidence_penalty),
            )
        )
        records[deviation.id] = {"ran": True, "agreed": False, "note": _clip("; ".join(pieces))}

    return VerifyResult(deviations=tuple(updated), verifiers=records)


__all__ = [
    "MAX_NOTE_CHARS",
    "TIME_TOLERANCE_S",
    "VERIFIER_VERSION",
    "Verifier",
    "VerifierParams",
    "VerifyResult",
    "build_verifier_prompt",
    "format_time",
    "verify_deviations",
]

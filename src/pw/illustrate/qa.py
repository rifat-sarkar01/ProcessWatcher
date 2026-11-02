"""Illustration QA: Wonder checks the diagram against the SOP step (FR-10, ADR-003).

Pass requires every check to be good — matches the step, shows the expected tool, has
legible text, lists no hallucinated labels and shows no people. A failed check triggers
at most two regenerations (three images total); after that the illustration is dropped
with a reason, never shown with a caveat. The QA record matches the report contract.
"""

from __future__ import annotations

import base64
import io
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from PIL import Image

from pw.clients.wonder import extract_text

QA_VERSION = "illustration-qa-v1"
MAX_ATTEMPTS = 3
REASON_MAX_CHARS = 200
UNAVAILABLE = "illustration_unavailable"
QACaller = Callable[[Mapping[str, Any]], Mapping[str, Any]]
Regenerate = Callable[[int], bytes | None]


class QAError(ValueError):
    """The QA request or response is not usable."""


@dataclass(frozen=True, slots=True)
class QAChecks:
    matches_step: bool
    correct_tool_shown: bool
    text_legible: bool
    hallucinated_labels: tuple[str, ...] = ()
    people_visible: bool = False
    verdict: str = "fail"
    reason: str = ""

    @property
    def passed(self) -> bool:
        return (
            self.verdict == "pass"
            and self.matches_step
            and self.correct_tool_shown
            and self.text_legible
            and not self.hallucinated_labels
            and not self.people_visible
        )


@dataclass(frozen=True, slots=True)
class QAOutcome:
    image: bytes | None
    attempts: int
    verdict: str
    reason: str | None = None
    checks: tuple[QAChecks, ...] = field(default_factory=tuple)

    def to_report(self) -> dict[str, Any]:
        """The `illustration.qa` block: verdict, attempts and an optional reason."""
        payload: dict[str, Any] = {
            "verdict": "pass" if self.verdict == "pass" else "fail",
            "attempts": max(1, self.attempts),
        }
        if self.reason:
            payload["reason"] = self.reason[:REASON_MAX_CHARS]
        return payload


def _data_uri(image: bytes) -> str:
    with Image.open(io.BytesIO(image)) as opened:
        converted = opened.convert("RGB")
    buffer = io.BytesIO()
    converted.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def qa_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "matches_step",
            "correct_tool_shown",
            "text_legible",
            "hallucinated_labels",
            "people_visible",
            "verdict",
            "reason",
        ],
        "properties": {
            "matches_step": {"type": "boolean"},
            "correct_tool_shown": {"type": "boolean"},
            "text_legible": {"type": "boolean"},
            "hallucinated_labels": {"type": "array", "items": {"type": "string"}},
            "people_visible": {"type": "boolean"},
            "verdict": {"enum": ["pass", "fail"]},
            "reason": {"type": "string"},
        },
    }


def _phrase_list(value: object) -> str:
    if not isinstance(value, (list, tuple)):
        return ""
    return ", ".join(str(item) for item in value)


def build_qa_payload(image: bytes, step: Mapping[str, Any]) -> dict[str, Any]:
    text = str(step.get("text") or "").strip()
    tools = _phrase_list(step.get("tools")) or "none listed"
    parts = _phrase_list(step.get("parts")) or "none listed"
    prompt = (
        "This is an AI illustration for a procedure step. Judge it against the step, not "
        "against a photograph.\n"
        f"Step: {text}\nExpected tool: {tools}. Expected part: {parts}.\n"
        "Set matches_step only if the image depicts this step. correct_tool_shown only if "
        "the expected tool (or an equivalent) is visible. text_legible only if the caption "
        "can be read. List any text labels that are not part of the step as "
        "hallucinated_labels. people_visible is true for any face or person. verdict is "
        "'pass' only when every check is good."
    )
    return {
        "model": "muse-wonder-1.0",
        "temperature": 0,
        "reasoning": {"effort": "low"},
        "text": {
            "format": {
                "type": "json_schema",
                "name": "illustration_qa",
                "schema": qa_schema(),
                "strict": True,
            }
        },
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": _data_uri(image)},
                ],
            }
        ],
    }


def _boolean(value: object) -> bool:
    if isinstance(value, bool):
        return value
    raise QAError(f"expected a boolean, got {type(value).__name__}")


def _labels(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise QAError("hallucinated_labels must be an array of strings")
    return tuple(item.strip() for item in value if item.strip())


def parse_qa_response(body: Mapping[str, Any]) -> QAChecks:
    text = extract_text(body)
    if text is None:
        raise QAError("QA response has no text")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise QAError("QA response is not JSON") from error
    if not isinstance(payload, Mapping):
        raise QAError("QA response is not an object")
    verdict = payload.get("verdict")
    if verdict not in ("pass", "fail"):
        raise QAError("QA verdict must be 'pass' or 'fail'")
    reason = payload.get("reason", "")
    if not isinstance(reason, str):
        raise QAError("QA reason must be a string")
    return QAChecks(
        matches_step=_boolean(payload.get("matches_step")),
        correct_tool_shown=_boolean(payload.get("correct_tool_shown")),
        text_legible=_boolean(payload.get("text_legible")),
        hallucinated_labels=_labels(payload.get("hallucinated_labels", [])),
        people_visible=_boolean(payload.get("people_visible")),
        verdict=verdict,
        reason=reason.strip(),
    )


def _failure_reason(checks: QAChecks) -> str:
    pieces: list[str] = []
    if not checks.matches_step:
        pieces.append("step mismatch")
    if not checks.correct_tool_shown:
        pieces.append("wrong tool")
    if not checks.text_legible:
        pieces.append("illegible text")
    if checks.hallucinated_labels:
        pieces.append("hallucinated labels: " + ", ".join(checks.hallucinated_labels))
    if checks.people_visible:
        pieces.append("people visible")
    if checks.verdict != "pass" and not pieces:
        pieces.append("reviewer rejected")
    return "; ".join(pieces) or "reviewer rejected"


def run_qa_loop(
    step: Mapping[str, Any],
    *,
    first_image: bytes | None,
    regenerate: Regenerate,
    call: QACaller,
    max_attempts: int = MAX_ATTEMPTS,
) -> QAOutcome:
    """Check the image, regenerating up to `max_attempts - 1` times; never raise."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    checks_seen: list[QAChecks] = []
    image = first_image
    attempts = 0
    regenerations = 0
    last_reason = "no image"
    while attempts < max_attempts:
        attempts += 1
        if image is None:
            image = regenerate(regenerations)
            regenerations += 1
        if image is None:
            last_reason = "no image from the generator"
            image = None
            continue

        try:
            checks = parse_qa_response(call(build_qa_payload(image, step)))
        except Exception as error:  # reviewer failure drops the illustration
            reason = f"{UNAVAILABLE}: qa_unavailable ({type(error).__name__})"
            return QAOutcome(
                image=None,
                attempts=attempts,
                verdict="fail",
                reason=reason[:REASON_MAX_CHARS],
                checks=tuple(checks_seen),
            )
        checks_seen.append(checks)
        if checks.passed:
            return QAOutcome(
                image=image,
                attempts=attempts,
                verdict="pass",
                checks=tuple(checks_seen),
            )
        last_reason = _failure_reason(checks)
        image = None

    reason = f"{UNAVAILABLE}: {last_reason} after {attempts} attempts"
    return QAOutcome(
        image=None,
        attempts=attempts,
        verdict="fail",
        reason=reason[:REASON_MAX_CHARS],
        checks=tuple(checks_seen),
    )


__all__ = [
    "MAX_ATTEMPTS",
    "QA_VERSION",
    "QAChecks",
    "QAError",
    "QAOutcome",
    "build_qa_payload",
    "parse_qa_response",
    "qa_schema",
    "run_qa_loop",
]

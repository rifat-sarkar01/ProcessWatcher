"""T-4.4: Wonder QA loop — pass, regenerate, exhaustion and reviewer failure."""

from __future__ import annotations

import io
import json
from collections.abc import Mapping
from typing import Any

import pytest
from PIL import Image

from pw.illustrate.qa import (
    MAX_ATTEMPTS,
    QAChecks,
    QAError,
    build_qa_payload,
    parse_qa_response,
    qa_schema,
    run_qa_loop,
)

STEP = {
    "id": "stp_01",
    "text": "Unplug the power cable from the rear of the case.",
    "action": "unplug the power cable",
    "tools": ["hand"],
    "parts": ["power cable"],
}


def _png(color: tuple[int, int, int] = (180, 180, 180)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 24), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _body(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "matches_step": True,
        "correct_tool_shown": True,
        "text_legible": True,
        "hallucinated_labels": [],
        "people_visible": False,
        "verdict": "pass",
        "reason": "looks right",
    }
    payload.update(overrides)
    return {"output": [{"content": [{"type": "output_text", "text": json.dumps(payload)}]}]}


class Reviewer:
    def __init__(self, bodies: list[dict[str, Any] | Exception]) -> None:
        self.bodies = list(bodies)
        self.payloads: list[Mapping[str, Any]] = []

    def __call__(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self.payloads.append(payload)
        body = self.bodies.pop(0)
        if isinstance(body, Exception):
            raise body
        return body


class Regenerator:
    def __init__(self, images: list[bytes]) -> None:
        self.images = list(images)
        self.attempts: list[int] = []

    def __call__(self, attempt: int) -> bytes:
        self.attempts.append(attempt)
        return self.images.pop(0)


@pytest.mark.unit
def test_payload_is_strict_json_with_the_step_and_image() -> None:
    payload = build_qa_payload(_png(), STEP)

    assert payload["temperature"] == 0
    assert payload["text"]["format"]["name"] == "illustration_qa"
    assert payload["text"]["format"]["strict"] is True
    assert payload["text"]["format"]["schema"] == qa_schema()
    content = payload["input"][0]["content"]
    assert "Unplug the power cable" in content[0]["text"]
    assert content[1]["image_url"].startswith("data:image/png;base64,")


@pytest.mark.unit
def test_parse_pass_response() -> None:
    checks = parse_qa_response(_body())

    assert checks.passed is True
    assert checks.verdict == "pass"
    assert checks.hallucinated_labels == ()


@pytest.mark.unit
def test_parse_rejects_malformed_responses() -> None:
    with pytest.raises(QAError):
        parse_qa_response({"output": []})
    with pytest.raises(QAError):
        parse_qa_response({"output": [{"content": [{"text": "not json"}]}]})
    with pytest.raises(QAError):
        parse_qa_response(_body(verdict="maybe"))
    with pytest.raises(QAError):
        parse_qa_response(_body(matches_step="yes"))


@pytest.mark.unit
def test_people_or_hallucinated_labels_never_pass() -> None:
    people = parse_qa_response(_body(people_visible=True))
    labels = parse_qa_response(_body(hallucinated_labels=["TORQUE WRENCH"]))

    assert people.passed is False
    assert labels.passed is False


@pytest.mark.unit
def test_pass_on_the_first_image_does_not_regenerate() -> None:
    reviewer = Reviewer([_body()])
    regenerate = Regenerator([])

    outcome = run_qa_loop(STEP, first_image=_png(), regenerate=regenerate, call=reviewer)

    assert outcome.verdict == "pass"
    assert outcome.attempts == 1
    assert outcome.image is not None
    assert regenerate.attempts == []


@pytest.mark.unit
def test_fail_then_pass_regenerates_once() -> None:
    reviewer = Reviewer([_body(verdict="fail", text_legible=False), _body()])
    regenerate = Regenerator([_png((1, 2, 3))])

    outcome = run_qa_loop(STEP, first_image=_png(), regenerate=regenerate, call=reviewer)

    assert outcome.verdict == "pass"
    assert outcome.attempts == 2
    assert regenerate.attempts == [0]
    assert len(outcome.checks) == 2


@pytest.mark.unit
def test_three_failures_fall_back_to_no_illustration() -> None:
    reviewer = Reviewer([_body(verdict="fail") for _ in range(MAX_ATTEMPTS)])
    regenerate = Regenerator([_png((1, 1, 1)), _png((2, 2, 2))])

    outcome = run_qa_loop(STEP, first_image=_png(), regenerate=regenerate, call=reviewer)

    assert outcome.verdict == "fail"
    assert outcome.attempts == MAX_ATTEMPTS
    assert outcome.image is None
    assert outcome.reason is not None
    assert outcome.reason.startswith("illustration_unavailable")
    assert "after 3 attempts" in outcome.reason
    assert len(reviewer.payloads) == MAX_ATTEMPTS


@pytest.mark.unit
def test_a_missing_first_image_is_regenerated() -> None:
    reviewer = Reviewer([_body()])
    regenerate = Regenerator([_png()])

    outcome = run_qa_loop(STEP, first_image=None, regenerate=regenerate, call=reviewer)

    assert outcome.verdict == "pass"
    assert outcome.attempts == 1
    assert regenerate.attempts == [0]


@pytest.mark.unit
def test_reviewer_error_falls_back_without_raising() -> None:
    reviewer = Reviewer([RuntimeError("wonder 503")])

    outcome = run_qa_loop(STEP, first_image=_png(), regenerate=Regenerator([]), call=reviewer)

    assert outcome.verdict == "fail"
    assert outcome.attempts == 1
    assert outcome.image is None
    assert outcome.reason is not None
    assert "qa_unavailable" in outcome.reason
    assert "RuntimeError" in outcome.reason


@pytest.mark.unit
def test_report_block_matches_the_contract_shape() -> None:
    outcome = run_qa_loop(
        STEP, first_image=_png(), regenerate=Regenerator([]), call=Reviewer([_body()])
    )

    report = outcome.to_report()

    assert set(report) <= {"verdict", "attempts", "reason"}
    assert report["verdict"] == "pass"
    assert report["attempts"] == 1


@pytest.mark.unit
def test_failure_reason_names_the_failed_checks() -> None:
    checks = QAChecks(
        matches_step=True,
        correct_tool_shown=False,
        text_legible=False,
        people_visible=True,
        verdict="fail",
    )
    reviewer = Reviewer(
        [_body(verdict="fail", correct_tool_shown=False, people_visible=True) for _ in range(3)]
    )
    regenerate = Regenerator([_png(), _png()])

    outcome = run_qa_loop(STEP, first_image=_png(), regenerate=regenerate, call=reviewer)

    assert checks.passed is False
    assert outcome.reason is not None
    assert "wrong tool" in outcome.reason
    assert "people visible" in outcome.reason
    assert outcome.attempts == MAX_ATTEMPTS


@pytest.mark.unit
def test_invalid_attempt_budget_is_rejected() -> None:
    with pytest.raises(ValueError):
        run_qa_loop(
            STEP,
            first_image=_png(),
            regenerate=Regenerator([]),
            call=Reviewer([]),
            max_attempts=0,
        )

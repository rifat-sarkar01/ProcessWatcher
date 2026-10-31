"""Verifier tests: agreement, downgrade to needs_review, failure and the kill switch."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import pytest

from pw.align.deviations import Deviation
from pw.align.verifier import (
    VerifierParams,
    build_verifier_prompt,
    format_time,
    verify_deviations,
)

TRACKS = ("trk_001",)


def deviation(
    *,
    deviation_type: str = "missed",
    confidence: float = 0.8,
    status: str = "flagged",
    **overrides: Any,
) -> Deviation:
    return Deviation(
        id="dev_001",
        type=deviation_type,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        severity="high",
        step_id="stp_05",
        t_start=61.0,
        t_end=71.5,
        track_ids=TRACKS,
        confidence=confidence,
        margin=2.4,
        **overrides,
    )


def response(
    occurred: bool,
    *,
    confidence: float = 0.9,
    note: str = "",
    times: Sequence[str] | None = None,
) -> str:
    payload: dict[str, Any] = {"occurred": occurred, "confidence": confidence, "note": note}
    if times is not None:
        payload["times"] = list(times)
    return json.dumps(payload)


class FakeVerifier:
    """Returns queued raw responses (or raises) and records the prompts."""

    def __init__(self, responses: Sequence[object]) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self.responses:
            raise AssertionError("verifier called more times than expected")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return str(item)


def run(deviation: Deviation, raw: object) -> tuple[Deviation, dict[str, Any], FakeVerifier]:
    verifier = FakeVerifier([raw])
    result = verify_deviations((deviation,), verifier=verifier)
    return result.deviations[0], result.verifiers[deviation.id], verifier


@pytest.mark.unit
def test_confirms_a_missed_step_and_raises_confidence() -> None:
    updated, record, verifier = run(deviation(), response(False, note="no bolt 2 torque"))

    assert updated.status == "flagged"
    assert updated.confidence == pytest.approx(0.9)
    assert record == {"ran": True, "agreed": True, "note": "confirmed: no bolt 2 torque"}
    assert len(verifier.prompts) == 1


@pytest.mark.unit
def test_confirms_a_wrong_tool_finding() -> None:
    finding = deviation(
        deviation_type="wrong_tool",
        expected_tools=("torque wrench",),
        observed_tools=("adjustable wrench",),
    )

    updated, record, _ = run(finding, response(True, note="adjustable wrench visible"))

    assert updated.status == "flagged"
    assert record["agreed"] is True


@pytest.mark.unit
def test_rejecting_a_missed_finding_downgrades_to_needs_review() -> None:
    updated, record, _ = run(deviation(), response(True, note="bolt 2 was torqued"))

    assert updated.status == "needs_review"
    assert updated.confidence == pytest.approx(0.6)
    assert record["agreed"] is False
    assert "rejected" in record["note"]


@pytest.mark.unit
def test_rejecting_a_wrong_tool_finding_downgrades_to_needs_review() -> None:
    finding = deviation(deviation_type="wrong_tool", confidence=0.9)

    updated, record, _ = run(finding, response(False))

    assert updated.status == "needs_review"
    assert updated.confidence == pytest.approx(0.7)
    assert record["agreed"] is False


@pytest.mark.unit
def test_out_of_order_confirmation_keeps_the_finding_flagged() -> None:
    finding = deviation(deviation_type="out_of_order", relates_to_step_id="stp_04")

    updated, record, _ = run(finding, response(True))

    assert updated.status == "flagged"
    assert record["agreed"] is True


@pytest.mark.unit
def test_reviewer_failure_keeps_the_original_finding() -> None:
    finding = deviation(confidence=0.8)

    updated, record, _ = run(finding, RuntimeError("timeout"))

    assert updated == finding
    assert record["ran"] is False
    assert record["agreed"] is None
    assert record["note"].startswith("verifier_unavailable")


@pytest.mark.unit
def test_malformed_response_is_never_trusted() -> None:
    updated, record, _ = run(deviation(), "not json")

    assert updated.status == "flagged"
    assert record["ran"] is True
    assert record["agreed"] is None
    assert record["note"].startswith("unverified")


@pytest.mark.unit
def test_a_non_boolean_occurred_is_unverified() -> None:
    updated, record, _ = run(deviation(), json.dumps({"occurred": "yes"}))

    assert record["agreed"] is None
    assert updated.status == "flagged"


@pytest.mark.unit
def test_disabled_switch_makes_no_calls() -> None:
    verifier = FakeVerifier([])
    findings = (deviation(), deviation(deviation_type="wrong_tool", confidence=0.9))

    result = verify_deviations(findings, verifier=verifier, params=VerifierParams(enabled=False))

    assert verifier.prompts == []
    assert result.deviations == findings
    assert all(record["note"] == "PW_DISABLE_VERIFIER" for record in result.verifiers.values())
    assert all(record["ran"] is False for record in result.verifiers.values())


@pytest.mark.unit
def test_confidence_is_clamped_to_the_unit_interval() -> None:
    high, _, _ = run(deviation(confidence=0.95), response(False))
    low, _, _ = run(deviation(confidence=0.1), response(True))

    assert high.confidence == pytest.approx(1.0)
    assert low.confidence == pytest.approx(0.0)


@pytest.mark.unit
def test_cited_times_outside_the_gap_are_recorded() -> None:
    updated, record, _ = run(
        deviation(),
        response(True, note="torque at 00:30", times=["00:30.0"]),
    )

    assert updated.status == "needs_review"
    assert "outside" in record["note"]


@pytest.mark.unit
def test_cited_times_inside_the_gap_are_accepted() -> None:
    updated, record, _ = run(deviation(), response(True, times=["01:05.0"]))

    assert updated.status == "needs_review"
    assert "outside" not in record["note"]


@pytest.mark.unit
def test_no_deviations_means_no_calls() -> None:
    verifier = FakeVerifier([])

    result = verify_deviations((), verifier=verifier)

    assert result.deviations == ()
    assert result.verifiers == {}
    assert verifier.prompts == []


@pytest.mark.unit
def test_prompt_names_the_finding_and_demands_strict_json() -> None:
    prompt = build_verifier_prompt(
        deviation(
            deviation_type="wrong_tool",
            expected_tools=("torque wrench",),
            observed_tools=("adjustable wrench",),
        )
    )

    assert "verify-1.0.0" in prompt
    assert "wrong_tool" in prompt
    assert "stp_05" in prompt
    assert f"{format_time(61.0)}" in prompt
    assert "occurred" in prompt
    assert "JSON" in prompt
    assert "torque wrench" in prompt and "adjustable wrench" in prompt


@pytest.mark.unit
def test_format_time_uses_mm_ss_tenths() -> None:
    assert format_time(61.0) == "01:01.0"
    assert format_time(71.45) == "01:11.5"
    assert format_time(-2) == "00:00.0"

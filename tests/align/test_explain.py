"""Grounded explanations: validator, retry policy and template fallback."""

from __future__ import annotations

import pytest

from pw.align.deviations import Deviation
from pw.align.explain import (
    MAX_ATTEMPTS,
    MAX_SENTENCES,
    MAX_WORDS,
    TIME_TOLERANCE_S,
    count_sentences,
    explain_deviation,
    format_time,
    make_prompt,
    mentioned_times,
    mentioned_tools,
    step_index_of,
    template_explanation,
    validate_explanation,
)

MISSED_TIMES = (61.0, 71.5)
MISSED_TEXT = "Step 5 was not observed between 01:01.00 and 01:11.50."
WRONG_TOOL_TIMES = (72.4, 81.0)
WRONG_TOOL_TEXT = (
    "Step 4 needs the torque wrench; an adjustable wrench was used between 01:12.40 and 01:21.00."
)
TOOLS = ("torque wrench", "adjustable wrench")


def missed() -> Deviation:
    return Deviation(
        id="dev_001",
        type="missed",
        status="flagged",
        severity="high",
        step_id="stp_05",
        t_start=MISSED_TIMES[0],
        t_end=MISSED_TIMES[1],
        track_ids=("trk_001",),
        confidence=0.82,
        margin=2.4,
    )


def wrong_tool() -> Deviation:
    return Deviation(
        id="dev_002",
        type="wrong_tool",
        status="flagged",
        severity="high",
        step_id="stp_04",
        t_start=WRONG_TOOL_TIMES[0],
        t_end=WRONG_TOOL_TIMES[1],
        track_ids=("trk_002",),
        confidence=0.86,
        margin=3.8,
        expected_tools=("torque wrench",),
        observed_tools=("adjustable wrench",),
    )


def out_of_order() -> Deviation:
    return Deviation(
        id="dev_003",
        type="out_of_order",
        status="needs_review",
        severity="medium",
        step_id="stp_06",
        t_start=92.0,
        t_end=110.5,
        track_ids=("trk_001",),
        confidence=0.6,
        margin=1.2,
        relates_to_step_id="stp_03",
    )


def valid_text_checks() -> list[tuple[str, Deviation, tuple[float, ...], tuple[str, ...]]]:
    return [
        (MISSED_TEXT, missed(), MISSED_TIMES, ()),
        (WRONG_TOOL_TEXT, wrong_tool(), WRONG_TOOL_TIMES, TOOLS),
        (
            "Step 6 ran out of order at 01:32.00 to 01:50.50; it should follow step 3.",
            out_of_order(),
            (92.0, 110.5),
            (),
        ),
    ]


@pytest.mark.parametrize(("text", "deviation", "times", "vocabulary"), valid_text_checks())
def test_valid_grounded_text_is_accepted(
    text: str, deviation: Deviation, times: tuple[float, ...], vocabulary: tuple[str, ...]
) -> None:
    assert (
        validate_explanation(
            text,
            step_index=step_index_of(deviation.step_id),
            step_id=deviation.step_id,
            data_times=times,
            vocabulary=vocabulary,
        )
        == ()
    )


@pytest.mark.parametrize(("text", "deviation", "times", "vocabulary"), valid_text_checks())
def test_template_fallback_always_passes_the_validator(
    text: str, deviation: Deviation, times: tuple[float, ...], vocabulary: tuple[str, ...]
) -> None:
    template = template_explanation(deviation, step_index=step_index_of(deviation.step_id))
    assert (
        validate_explanation(
            template,
            step_index=step_index_of(deviation.step_id),
            step_id=deviation.step_id,
            data_times=times,
            vocabulary=vocabulary,
        )
        == ()
    )


def test_model_text_is_used_when_valid() -> None:
    result = explain_deviation(
        wrong_tool(), writer=lambda prompt: WRONG_TOOL_TEXT, vocabulary=TOOLS
    )
    assert result.source == "model"
    assert result.attempts == 1
    assert result.text == WRONG_TOOL_TEXT
    assert result.issues == ()


def test_invented_timestamp_is_rejected_and_falls_back() -> None:
    result = explain_deviation(
        missed(),
        writer=lambda prompt: "Step 5 was missed at 09:59.00.",
        vocabulary=(),
    )
    assert result.source == "template"
    assert result.attempts == MAX_ATTEMPTS
    assert any(issue.startswith("unknown_time") for issue in result.issues)
    assert result.text == template_explanation(missed(), step_index=5)


def test_unknown_tool_is_rejected() -> None:
    result = explain_deviation(
        missed(),
        writer=lambda prompt: "Step 5 needs the sledgehammer between 01:01.00 and 01:11.50.",
        vocabulary=("torque wrench",),
    )
    assert result.source == "template"
    assert "unknown_tool:sledgehammer" in result.issues


def test_retry_accepts_the_second_attempt() -> None:
    responses = iter(
        [
            "Step 5 was missed at 09:59.00.",
            MISSED_TEXT,
        ]
    )
    result = explain_deviation(missed(), writer=lambda prompt: next(responses), vocabulary=())
    assert result.source == "model"
    assert result.attempts == 2
    assert result.text == MISSED_TEXT


def test_three_failures_end_in_the_template_with_the_last_issue() -> None:
    calls: list[str] = []

    def writer(prompt: str) -> str:
        calls.append(prompt)
        return "Nothing to report."

    result = explain_deviation(missed(), writer=writer, vocabulary=())
    assert len(calls) == MAX_ATTEMPTS
    assert result.attempts == MAX_ATTEMPTS
    assert result.source == "template"
    assert "missing_step" in result.issues


def test_writer_error_degrades_to_the_template() -> None:
    def writer(prompt: str) -> str:
        raise RuntimeError("upstream timeout")

    result = explain_deviation(missed(), writer=writer, vocabulary=())
    assert result.source == "template"
    assert result.issues == ("writer_error",)


def test_too_many_sentences_or_words_are_rejected() -> None:
    long_sentences = (
        "Step 5 was not observed between 01:01.00 and 01:11.50. "
        "The operator skipped ahead. No wrench was used."
    )
    issues = validate_explanation(
        long_sentences,
        step_index=5,
        step_id="stp_05",
        data_times=MISSED_TIMES,
        vocabulary=(),
    )
    assert f"too_many_sentences:{MAX_SENTENCES + 1}" in issues

    too_many_words = "Step 5 " + "word " * (MAX_WORDS - 1) + "."
    assert any(
        issue.startswith("too_many_words")
        for issue in validate_explanation(
            too_many_words,
            step_index=5,
            step_id="stp_05",
            data_times=MISSED_TIMES,
            vocabulary=(),
        )
    )


def test_missing_step_citation_is_rejected() -> None:
    issues = validate_explanation(
        "The bolt was never torqued between 01:01.00 and 01:11.50.",
        step_index=5,
        step_id="stp_05",
        data_times=MISSED_TIMES,
        vocabulary=(),
    )
    assert issues == ("missing_step",)


def test_empty_text_is_rejected() -> None:
    assert validate_explanation(
        "   ", step_index=5, step_id="stp_05", data_times=MISSED_TIMES, vocabulary=()
    ) == ("empty",)


def test_time_tolerance_is_half_a_second() -> None:
    within = "Step 5 was missed at 01:01.40."
    outside = "Step 5 was missed at 01:01.60."
    for text, expected in ((within, ()), (outside, ("unknown_time:01:01.60",))):
        assert (
            validate_explanation(
                text,
                step_index=5,
                step_id="stp_05",
                data_times=MISSED_TIMES,
                vocabulary=(),
            )
            == expected
        )
    assert TIME_TOLERANCE_S == 0.5


def test_prompt_lists_the_allowed_facts() -> None:
    prompt = make_prompt(
        wrong_tool(),
        step_index=4,
        step_text="Tighten bolt 3 to 25 Nm.",
        data_times=WRONG_TOOL_TIMES,
        vocabulary=TOOLS,
    )
    assert "01:12.40" in prompt and "01:21.00" in prompt
    assert "torque wrench" in prompt and "adjustable wrench" in prompt
    assert "at most 2 sentences" in prompt
    assert "Tighten bolt 3 to 25 Nm." in prompt
    assert "stp_04" in prompt


def test_time_and_tool_extraction_helpers() -> None:
    assert mentioned_times("from 01:02.50 to 10:00") == (62.5, 600.0)
    assert mentioned_tools(WRONG_TOOL_TEXT) == ("adjustable wrench", "torque wrench")
    assert count_sentences(WRONG_TOOL_TEXT) == 1
    assert format_time(72.4) == "01:12.40"
    assert step_index_of("stp_05") == 5


def test_overlong_text_is_rejected() -> None:
    issues = validate_explanation(
        "Step 5 " + "detail " * 60,
        step_index=5,
        step_id="stp_05",
        data_times=MISSED_TIMES,
        vocabulary=(),
    )
    assert any(issue.startswith("too_long") for issue in issues)


def test_out_of_order_without_a_related_step_still_has_a_template() -> None:
    deviation = out_of_order()
    payload = Deviation(
        id=deviation.id,
        type=deviation.type,
        status=deviation.status,
        severity=deviation.severity,
        step_id=deviation.step_id,
        t_start=deviation.t_start,
        t_end=deviation.t_end,
        track_ids=deviation.track_ids,
        confidence=deviation.confidence,
        margin=deviation.margin,
    )
    text = template_explanation(payload, step_index=6)
    assert text == "Step 6 ran out of order at 01:32.00 to 01:50.50."
    assert (
        validate_explanation(
            text,
            step_index=6,
            step_id="stp_06",
            data_times=(92.0, 110.5),
            vocabulary=(),
        )
        == ()
    )

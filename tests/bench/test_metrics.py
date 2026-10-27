"""Unit tests for the PW-Bench metrics (T-1.6)."""

from __future__ import annotations

import pytest

from pw.bench.metrics import (
    Deviation,
    Prf,
    aggregate,
    evaluate_clip,
    from_ground_truth,
    from_report,
    match_deviations,
    step_timing_accuracy,
    summarise_costs,
)


def dev(
    kind: str = "missed",
    step_id: str = "stp_03",
    start: float = 10.0,
    end: float = 14.0,
    status: str | None = "flagged",
) -> Deviation:
    return Deviation(step_id=step_id, kind=kind, t_start=start, t_end=end, status=status)


# --- matching ---------------------------------------------------------------------


@pytest.mark.unit
def test_perfect_match() -> None:
    result = match_deviations([dev()], [dev(status=None)])

    assert len(result.matches) == 1
    assert result.unmatched_predictions == ()
    assert result.unmatched_truths == ()


@pytest.mark.unit
def test_no_predictions_leaves_every_truth_unmatched() -> None:
    result = match_deviations([], [dev(status=None)])

    assert result.matches == ()
    assert len(result.unmatched_truths) == 1


@pytest.mark.unit
def test_shifted_within_tolerance_matches() -> None:
    # truth ends at 14.0, prediction starts at 15.5 -> 1.5 s gap, inside 2.0 s
    prediction = dev(start=15.5, end=18.0)
    truth = dev(start=10.0, end=14.0, status=None)

    result = match_deviations([prediction], [truth])

    assert len(result.matches) == 1
    assert result.matches[0].gap_s == pytest.approx(1.5)


@pytest.mark.unit
def test_shifted_outside_tolerance_does_not_match() -> None:
    prediction = dev(start=16.5, end=20.0)
    truth = dev(start=10.0, end=14.0, status=None)

    result = match_deviations([prediction], [truth])

    assert result.matches == ()
    assert len(result.unmatched_predictions) == 1
    assert len(result.unmatched_truths) == 1


@pytest.mark.unit
def test_wrong_type_does_not_match() -> None:
    prediction = dev(kind="wrong_tool")
    truth = dev(kind="missed", status=None)

    result = match_deviations([prediction], [truth])

    assert result.matches == ()


@pytest.mark.unit
def test_wrong_step_does_not_match() -> None:
    prediction = dev(step_id="stp_04")
    truth = dev(step_id="stp_03", status=None)

    result = match_deviations([prediction], [truth])

    assert result.matches == ()


@pytest.mark.unit
def test_duplicate_predictions_score_one_tp_and_one_fp() -> None:
    result = match_deviations(
        [dev(start=10.0, end=14.0), dev(start=10.5, end=14.5)],
        [dev(status=None)],
    )

    assert len(result.matches) == 1
    assert len(result.unmatched_predictions) == 1


@pytest.mark.unit
def test_greedy_matching_prefers_the_better_overlap() -> None:
    weak = dev(start=12.0, end=16.0)
    strong = dev(start=10.5, end=14.5)
    truth = dev(start=10.0, end=14.0, status=None)

    result = match_deviations([weak, strong], [truth])

    assert len(result.matches) == 1
    assert result.matches[0].prediction is strong


@pytest.mark.unit
def test_tolerance_is_configurable() -> None:
    prediction = dev(start=16.5, end=20.0)
    truth = dev(start=10.0, end=14.0, status=None)

    assert match_deviations([prediction], [truth], tolerance_s=2.0).matches == ()
    assert len(match_deviations([prediction], [truth], tolerance_s=3.0).matches) == 1


# --- per-clip metrics ---------------------------------------------------------------


@pytest.mark.unit
def test_perfect_clip_scores_one() -> None:
    metrics = evaluate_clip("C1", [dev()], [dev(status=None)])

    assert (metrics.overall.tp, metrics.overall.fp, metrics.overall.fn) == (1, 0, 0)
    assert metrics.overall.f1 == pytest.approx(1.0)


@pytest.mark.unit
def test_empty_predictions_give_zero_recall() -> None:
    metrics = evaluate_clip("C2", [], [dev(status=None)])

    assert metrics.overall.recall == 0.0
    assert metrics.overall.f1 == 0.0


@pytest.mark.unit
def test_needs_review_is_reported_but_not_counted() -> None:
    metrics = evaluate_clip(
        "C3",
        [dev(status="needs_review")],
        [],
        compliant=True,
    )

    assert metrics.overall.fp == 0
    assert metrics.flagged == 0
    assert metrics.needs_review == 1


@pytest.mark.unit
def test_false_flag_on_a_compliant_clip_is_counted() -> None:
    metrics = evaluate_clip("C4", [dev()], [], compliant=True)

    assert metrics.overall.fp == 1
    assert metrics.overall.precision == 0.0


@pytest.mark.unit
def test_per_type_metrics_are_separate() -> None:
    metrics = evaluate_clip(
        "C5",
        [dev(kind="missed"), dev(kind="wrong_tool", step_id="stp_07")],
        [dev(kind="missed", status=None), dev(kind="out_of_order", step_id="stp_08", status=None)],
    )

    assert metrics.by_type["missed"].tp == 1
    assert metrics.by_type["wrong_tool"].fp == 1
    assert metrics.by_type["out_of_order"].fn == 1


@pytest.mark.unit
def test_timestamp_errors_are_recorded_for_matches() -> None:
    metrics = evaluate_clip(
        "C6",
        [dev(start=11.5, end=15.0)],
        [dev(start=10.0, end=14.0, status=None)],
    )

    assert metrics.matched_errors_s == (pytest.approx(1.5),)


# --- aggregation --------------------------------------------------------------------


@pytest.mark.unit
def test_aggregate_sums_counts_across_clips() -> None:
    clips = [
        evaluate_clip("C1", [dev()], [dev(status=None)]),
        evaluate_clip("C2", [], [dev(status=None)]),
    ]

    bench = aggregate(clips)

    assert (bench.overall.tp, bench.overall.fp, bench.overall.fn) == (1, 0, 1)
    assert bench.overall.precision == pytest.approx(1.0)
    assert bench.overall.recall == pytest.approx(0.5)


@pytest.mark.unit
def test_false_flags_per_compliant_clip_uses_only_compliant_clips() -> None:
    clips = [
        evaluate_clip("C1", [dev()], [], compliant=True),
        evaluate_clip("C2", [], [], compliant=True),
        evaluate_clip("C3", [dev()], [dev(status=None)], compliant=False),
    ]

    bench = aggregate(clips)

    assert bench.false_flags_per_compliant_clip == pytest.approx(0.5)


@pytest.mark.unit
def test_timestamp_mae_across_clips() -> None:
    clips = [
        evaluate_clip("C1", [dev(start=11.0)], [dev(start=10.0, status=None)]),
        evaluate_clip("C2", [dev(start=14.0)], [dev(start=10.0, status=None)]),
    ]

    bench = aggregate(clips)

    assert bench.timestamp_mae_s == pytest.approx(2.5)


@pytest.mark.unit
def test_needs_review_rate() -> None:
    clips = [
        evaluate_clip("C1", [dev(), dev(status="needs_review", start=40.0, end=44.0)], []),
        evaluate_clip("C2", [dev(status="needs_review", start=60.0, end=64.0)], []),
    ]

    bench = aggregate(clips)

    assert bench.needs_review_rate == pytest.approx(2 / 3)


@pytest.mark.unit
def test_aggregate_of_no_clips_is_zeroed() -> None:
    bench = aggregate([])

    assert bench.clips == 0
    assert bench.overall.f1 == 0.0
    assert bench.false_flags_per_compliant_clip == 0.0
    assert bench.timestamp_mae_s == 0.0


@pytest.mark.unit
def test_prf_addition_is_exact() -> None:
    total = Prf(1, 2, 3) + Prf(4, 5, 6)

    assert (total.tp, total.fp, total.fn) == (5, 7, 9)


# --- adapters and validation --------------------------------------------------------


@pytest.mark.unit
def test_from_report_reads_status_and_times() -> None:
    report = {
        "deviations": [
            {"type": "missed", "step_id": "stp_03", "t_start": 1.0, "t_end": 2.0, "status": "flagged"}
        ]
    }

    deviations = from_report(report)

    assert deviations[0].status == "flagged"
    assert deviations[0].t_end == 2.0


@pytest.mark.unit
def test_from_ground_truth_has_no_status() -> None:
    gt = {"deviations": [{"type": "missed", "step_id": "stp_05", "t_start": 1.0, "t_end": 2.0}]}

    deviations = from_ground_truth(gt)

    assert deviations[0].status is None


@pytest.mark.unit
def test_deviation_rejects_unknown_type() -> None:
    with pytest.raises(ValueError, match="unknown deviation type"):
        dev(kind="teleport")


@pytest.mark.unit
def test_deviation_rejects_backwards_time() -> None:
    with pytest.raises(ValueError, match="t_end"):
        dev(start=10.0, end=5.0)


# --- cost/latency and step accuracy -------------------------------------------------


@pytest.mark.unit
def test_cost_summary_per_video_minute() -> None:
    summary = summarise_costs([0.4, 0.6], [60.0, 60.0], [30.0, 50.0])

    assert summary.total_usd == pytest.approx(1.0)
    assert summary.per_video_minute == pytest.approx(0.5)
    assert summary.mean_latency_s == pytest.approx(40.0)


@pytest.mark.unit
def test_cost_summary_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="same length"):
        summarise_costs([0.4], [60.0, 30.0], [30.0])


@pytest.mark.unit
def test_cost_summary_handles_no_clips() -> None:
    summary = summarise_costs([], [], [])

    assert summary.total_usd == 0.0
    assert summary.per_video_minute == 0.0
    assert summary.mean_latency_s == 0.0


@pytest.mark.unit
def test_step_timing_accuracy() -> None:
    expected = {"stp_01": (3.0, 12.0), "stp_02": (13.0, 20.0), "stp_03": (41.0, 55.0)}
    observed = {"stp_01": (3.5, 12.0), "stp_02": (18.0, 24.0)}

    assert step_timing_accuracy(expected, observed) == pytest.approx(1 / 3)


@pytest.mark.unit
def test_step_timing_accuracy_without_expected_steps() -> None:
    assert step_timing_accuracy({}, {}) == 0.0

"""Aligner tests: deterministic constrained decoding over synthetic likelihoods."""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

import pytest
from jsonschema import validate

from pw.align.aligner import (
    AlignParams,
    Segment,
    StepSpec,
    align,
    order_ranks,
)

ROOT = Path(__file__).resolve().parents[2]
ALIGNMENT_SCHEMA = json.loads(
    (ROOT / "contracts" / "alignment.schema.json").read_text(encoding="utf-8")
)


def step(number: int, idx: int | None = None, *, critical: bool = False) -> StepSpec:
    return StepSpec(f"stp_{number:02d}", idx if idx is not None else number, critical=critical)


def segment(number: int, probs: dict[str, float], t_start: float = 0.0) -> Segment:
    return Segment(f"seg_{number:03d}", t_start, t_start + 1.0, probs)


def strong(step_id: str, none: float = 0.1) -> dict[str, float]:
    return {step_id: 1.0 - none, "none": none}


@pytest.mark.unit
def test_perfect_alignment_follows_the_sop() -> None:
    steps = [step(1), step(2), step(3)]
    segments = [
        segment(1, strong("stp_01")),
        segment(2, strong("stp_02")),
        segment(3, strong("stp_03")),
    ]

    result = align(segments, steps)

    assert [entry[1] for entry in result.path] == ["stp_01", "stp_02", "stp_03"]
    assert [interval.step_id for interval in result.intervals] == ["stp_01", "stp_02", "stp_03"]
    assert result.coverage == pytest.approx(1.0)
    assert result.total_cost == pytest.approx(3 * -math.log(0.9 + 1e-3), abs=1e-9)
    assert all(interval.margin > 0 for interval in result.intervals)


@pytest.mark.unit
def test_adjacent_swap_is_decoded_as_observed_not_as_written() -> None:
    steps = [step(1), step(2)]
    segments = [
        segment(1, strong("stp_02", none=0.001)),
        segment(2, strong("stp_01", none=0.001)),
    ]

    result = align(segments, steps)

    assert [entry[1] for entry in result.path] == ["stp_02", "stp_01"]
    assert result.total_cost == pytest.approx(2.5)


@pytest.mark.unit
def test_missing_step_costs_a_skip_and_gets_no_interval() -> None:
    steps = [step(1), step(2), step(3)]
    segments = [segment(1, strong("stp_01")), segment(2, strong("stp_03"))]

    result = align(segments, steps)

    assert [entry[1] for entry in result.path] == ["stp_01", "stp_03"]
    assert [interval.step_id for interval in result.intervals] == ["stp_01", "stp_03"]
    assert result.total_cost == pytest.approx(2 * -math.log(0.9 + 1e-3) + 1.5)


@pytest.mark.unit
def test_consecutive_same_step_merges_into_one_interval() -> None:
    steps = [step(1), step(2)]
    segments = [segment(1, strong("stp_01")), segment(2, strong("stp_01"), t_start=1.0)]

    result = align(segments, steps)

    assert [entry[1] for entry in result.path] == ["stp_01", "stp_01"]
    assert len(result.intervals) == 1
    interval = result.intervals[0]
    assert interval.segment_ids == ("seg_001", "seg_002")
    assert (interval.t_start, interval.t_end) == (0.0, 2.0)
    assert interval.mean_prob == pytest.approx(0.9)


@pytest.mark.unit
def test_unordered_group_permits_any_order_at_zero_cost() -> None:
    steps = [
        StepSpec("stp_01", 1, group_id="grp_01"),
        StepSpec("stp_02", 2, group_id="grp_01"),
        step(3, 3),
    ]
    segments = [
        segment(1, strong("stp_02")),
        segment(2, strong("stp_01")),
        segment(3, strong("stp_03")),
    ]

    result = align(segments, steps)

    assert [entry[1] for entry in result.path] == ["stp_02", "stp_01", "stp_03"]
    assert result.total_cost == pytest.approx(3 * -math.log(0.9 + 1e-3))


@pytest.mark.unit
def test_critical_skips_are_penalised_more_than_ordinary_skips() -> None:
    ordinary = [step(1), step(2), step(3), step(4)]
    critical = [step(1), step(2, 2, critical=True), step(3, 3, critical=True), step(4)]
    segments = [
        segment(1, strong("stp_01", none=0.001)),
        segment(2, strong("stp_04", none=0.001)),
    ]

    cheap = align(segments, ordinary)
    expensive = align(segments, critical)

    assert expensive.total_cost - cheap.total_cost == pytest.approx(3.0)


@pytest.mark.unit
def test_noisy_likelihoods_produce_small_margins_and_deterministic_output() -> None:
    steps = [step(1), step(2)]
    noisy = {"stp_01": 0.34, "stp_02": 0.33, "none": 0.33}
    segments = [segment(1, noisy), segment(2, dict(noisy))]

    first = align(segments, steps)
    second = align(segments, steps)

    assert first == second
    assert all(interval.margin < 0.2 for interval in first.intervals)


@pytest.mark.unit
def test_best_alternative_is_used_for_the_margin() -> None:
    steps = [step(1), step(2)]
    segments = [segment(1, {"stp_01": 0.60, "stp_02": 0.399, "none": 0.001})]

    result = align(segments, steps)

    assert all(interval.margin >= 0 for interval in result.intervals)
    assert result.intervals[0].margin == pytest.approx(math.log((0.6 + 1e-3) / (0.399 + 1e-3)))


@pytest.mark.unit
def test_none_wins_when_step_probabilities_are_low() -> None:
    steps = [step(1)]
    segments = [segment(1, {"stp_01": 0.2, "none": 0.8})]

    result = align(segments, steps)

    assert [entry[1] for entry in result.path] == ["none"]
    assert result.intervals == ()
    assert result.coverage == 0.0


@pytest.mark.unit
def test_unknown_step_keys_are_ignored() -> None:
    steps = [step(1)]
    segments = [segment(1, {"stp_99": 0.9, "none": 0.1})]

    result = align(segments, steps)

    assert [entry[1] for entry in result.path] == ["none"]


@pytest.mark.unit
def test_empty_segments_return_an_empty_alignment() -> None:
    result = align([], [step(1)])

    assert result.path == ()
    assert result.intervals == ()
    assert result.total_cost == 0.0
    assert result.per_segment_cost == 0.0
    assert result.coverage == 0.0


@pytest.mark.unit
def test_missing_none_probability_is_treated_as_zero() -> None:
    steps = [step(1), step(2)]
    segments = [segment(1, {"stp_01": 0.7, "stp_02": 0.3})]

    result = align(segments, steps)

    assert result.path[0][1] == "stp_01"


@pytest.mark.unit
def test_non_consecutive_repeat_yields_two_intervals() -> None:
    steps = [step(1), step(2)]
    segments = [
        segment(1, strong("stp_01", none=0.001)),
        segment(2, strong("stp_02", none=0.001), t_start=1.0),
        segment(3, strong("stp_01", none=0.001), t_start=2.0),
    ]

    result = align(segments, steps)

    assert [interval.step_id for interval in result.intervals] == [
        "stp_01",
        "stp_02",
        "stp_01",
    ]
    assert [interval.id for interval in result.intervals] == ["int_01", "int_02", "int_03"]


@pytest.mark.unit
def test_none_gap_splits_intervals_and_keeps_the_order_context() -> None:
    steps = [step(1), step(2)]
    segments = [
        segment(1, strong("stp_01")),
        segment(2, {"none": 0.95, "stp_01": 0.025, "stp_02": 0.025}, t_start=1.0),
        segment(3, strong("stp_02"), t_start=2.0),
    ]

    result = align(segments, steps)

    assert [entry[1] for entry in result.path] == ["stp_01", "none", "stp_02"]
    assert [interval.step_id for interval in result.intervals] == ["stp_01", "stp_02"]
    assert result.total_cost < 2.0


@pytest.mark.unit
def test_order_ranks_share_numbers_inside_a_group() -> None:
    steps = [
        step(1, 1),
        StepSpec("stp_02", 2, group_id="grp_01"),
        StepSpec("stp_03", 3, group_id="grp_01"),
        step(4, 4),
    ]

    assert order_ranks(steps) == {"stp_01": 0, "stp_02": 1, "stp_03": 1, "stp_04": 2}


@pytest.mark.unit
def test_artifact_matches_the_contract() -> None:
    steps = [step(1), step(2)]
    segments = [segment(1, strong("stp_01")), segment(2, strong("stp_02"))]

    artifact = align(segments, steps).to_artifact(run_id="run_01J9ZQ8M3K4V7B2C5D6E8F0GHJ")

    validate(artifact, ALIGNMENT_SCHEMA)
    assert artifact["status"] == "ok"
    assert artifact["cost"]["coverage"] == pytest.approx(1.0)
    assert artifact["params"]["epsilon"] == pytest.approx(1e-3)


@pytest.mark.unit
def test_artifact_without_run_id_also_validates() -> None:
    artifact = align([segment(1, strong("stp_01"))], [step(1)]).to_artifact()

    validate(artifact, ALIGNMENT_SCHEMA)
    assert "run_id" not in artifact


@pytest.mark.unit
def test_200_segments_align_in_under_a_second() -> None:
    steps = [step(number) for number in range(1, 9)]
    segments = [
        segment(index + 1, strong(f"stp_{(index % 8) + 1:02d}"), t_start=float(index))
        for index in range(200)
    ]

    started = time.perf_counter()
    result = align(segments, steps)
    elapsed = time.perf_counter() - started

    assert len(result.path) == 200
    assert elapsed < 1.0


@pytest.mark.unit
@pytest.mark.parametrize(
    ("segments", "steps", "message"),
    [
        ([segment(1, strong("stp_01"))], [], "at least one step"),
        (
            [segment(1, strong("stp_01"))],
            [step(1), step(1, 2)],
            "duplicate step",
        ),
        ([segment(1, strong("stp_01"))], [StepSpec("stp_01", 0)], "idx"),
        (
            [Segment("seg_001", 2.0, 1.0, strong("stp_01"))],
            [step(1)],
            "t_end",
        ),
        (
            [Segment("seg_001", 0.0, 1.0, {"stp_01": -0.1, "none": 1.1})],
            [step(1)],
            "probability",
        ),
        (
            [segment(1, strong("stp_01")), segment(1, strong("stp_01"))],
            [step(1)],
            "duplicate segment",
        ),
        (
            [Segment("", 0.0, 1.0, strong("stp_01"))],
            [step(1)],
            "segment id",
        ),
    ],
)
def test_invalid_inputs_are_rejected(
    segments: list[Segment], steps: list[StepSpec], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        align(segments, steps)


@pytest.mark.unit
def test_params_are_echoed_into_the_artifact() -> None:
    params = AlignParams(lambda_back=5.0, coverage_prob=0.5)
    artifact: dict[str, Any] = align(
        [segment(1, strong("stp_01"))], [step(1)], params=params
    ).to_artifact()

    validate(artifact, ALIGNMENT_SCHEMA)
    assert artifact["params"]["lambda_back"] == pytest.approx(5.0)
    assert artifact["params"]["coverage_prob"] == pytest.approx(0.5)

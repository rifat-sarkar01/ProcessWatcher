"""Deviation tests: missed, out-of-order and wrong-tool derived from alignment."""

from __future__ import annotations

import pytest

from pw.align.aligner import (
    Alignment,
    AlignParams,
    Interval,
    Segment,
    StepSpec,
)
from pw.align.deviations import (
    Deviation,
    DeviationParams,
    HeldTool,
    IntervalObservation,
    TrackActivity,
    TrackIdentity,
    derive_deviations,
)


def step(number: int, idx: int | None = None, *, critical: bool = False) -> StepSpec:
    return StepSpec(f"stp_{number:02d}", idx if idx is not None else number, critical=critical)


def interval(
    number: int, step_id: str, t_start: float, t_end: float, margin: float = 2.0
) -> Interval:
    return Interval(
        id=f"int_{number:02d}",
        step_id=step_id,
        t_start=t_start,
        t_end=t_end,
        segment_ids=(f"seg_{number:03d}",),
        mean_prob=0.9,
        margin=margin,
    )


def alignment(*intervals: Interval) -> Alignment:
    return Alignment(
        path=tuple((iv.segment_ids[0], iv.step_id) for iv in intervals),
        intervals=tuple(intervals),
        total_cost=0.5,
        per_segment_cost=0.1,
        coverage=0.5,
        params=AlignParams(),
    )


def segment(number: int, t_start: float, probs: dict[str, float]) -> Segment:
    return Segment(f"seg_{number:03d}", t_start, t_start + 1.0, probs)


@pytest.mark.unit
def test_missed_step_uses_the_gap_window_and_active_tracks() -> None:
    steps = [step(1), step(2)]
    aligned = alignment(interval(1, "stp_01", 0.0, 1.0))
    segments = [
        segment(1, 0.0, {"stp_01": 0.9, "stp_02": 0.05, "none": 0.05}),
        segment(2, 1.0, {"none": 0.8, "stp_01": 0.1, "stp_02": 0.1}),
    ]
    activity = [TrackActivity("trk_001", 0.0, 4.0)]

    deviations = derive_deviations(aligned, segments, steps, activity=activity)

    assert len(deviations) == 1
    missed = deviations[0]
    assert missed.type == "missed"
    assert missed.step_id == "stp_02"
    assert (missed.t_start, missed.t_end) == (1.0, 2.0)
    assert missed.track_ids == ("trk_001",)
    assert missed.status == "flagged"
    assert missed.severity == "medium"
    assert missed.confidence == pytest.approx(0.9)


@pytest.mark.unit
def test_missed_critical_step_is_high_severity() -> None:
    steps = [step(1, critical=True)]
    segments = [segment(1, 0.0, {"stp_01": 0.1, "none": 0.9})]
    activity = [TrackActivity("trk_001", 0.0, 1.0)]

    deviations = derive_deviations(alignment(), segments, steps, activity=activity)

    assert deviations[0].type == "missed"
    assert deviations[0].severity == "high"


@pytest.mark.unit
def test_step_above_the_miss_threshold_is_not_missed() -> None:
    steps = [step(1)]
    segments = [segment(1, 0.0, {"stp_01": 0.3, "none": 0.7})]

    assert derive_deviations(alignment(), segments, steps, activity=[]) == ()


@pytest.mark.unit
def test_out_of_order_step_is_the_one_outside_the_lis() -> None:
    steps = [step(1), step(2), step(3)]
    aligned = alignment(
        interval(1, "stp_02", 0.0, 1.0),
        interval(2, "stp_01", 1.0, 2.0),
        interval(3, "stp_03", 2.0, 3.0),
    )
    segments = [
        segment(1, 0.0, {"stp_02": 0.9, "none": 0.1}),
        segment(2, 1.0, {"stp_01": 0.9, "none": 0.1}),
        segment(3, 2.0, {"stp_03": 0.9, "none": 0.1}),
    ]
    activity = [TrackActivity("trk_001", 0.0, 3.0)]

    deviations = derive_deviations(aligned, segments, steps, activity=activity)

    assert len(deviations) == 1
    violation = deviations[0]
    assert violation.type == "out_of_order"
    assert violation.step_id == "stp_02"
    assert violation.relates_to_step_id == "stp_01"
    assert violation.track_ids == ("trk_001",)
    assert violation.confidence > 0.7
    assert violation.status == "flagged"


@pytest.mark.unit
def test_unordered_group_permutation_is_not_out_of_order() -> None:
    steps = [
        StepSpec("stp_01", 1, group_id="grp_01"),
        StepSpec("stp_02", 2, group_id="grp_01"),
    ]
    aligned = alignment(
        interval(1, "stp_02", 0.0, 1.0),
        interval(2, "stp_01", 1.0, 2.0),
    )
    segments = [
        segment(1, 0.0, {"stp_02": 0.9, "none": 0.1}),
        segment(2, 1.0, {"stp_01": 0.9, "none": 0.1}),
    ]

    deviations = derive_deviations(
        aligned, segments, steps, activity=[TrackActivity("trk_001", 0.0, 2.0)]
    )

    assert deviations == ()


@pytest.mark.unit
def test_wrong_tool_flags_majority_contact_with_an_unrequired_tool() -> None:
    steps = [step(1)]
    aligned = alignment(interval(1, "stp_01", 1.0, 2.0))
    segments = [segment(1, 1.0, {"stp_01": 0.9, "none": 0.1})]
    identities = {"trk_002": TrackIdentity("flat-head screwdriver", 0.9)}
    observations = [IntervalObservation("int_01", contact_s=10.0, held=(HeldTool("trk_002", 8.0),))]

    deviations = derive_deviations(
        aligned,
        segments,
        steps,
        identities=identities,
        tools_by_step={"stp_01": ("Phillips screwdriver",)},
        observations=observations,
        activity=[TrackActivity("trk_002", 1.0, 2.0)],
    )

    assert len(deviations) == 1
    wrong = deviations[0]
    assert wrong.type == "wrong_tool"
    assert wrong.step_id == "stp_01"
    assert wrong.expected_tools == ("Phillips screwdriver",)
    assert wrong.observed_tools == ("flat-head screwdriver",)
    assert wrong.track_ids == ("trk_002",)
    assert wrong.status == "flagged"
    assert wrong.margin == pytest.approx(0.3)


@pytest.mark.unit
def test_wrong_tool_below_half_contact_is_not_flagged() -> None:
    steps = [step(1)]
    aligned = alignment(interval(1, "stp_01", 0.0, 1.0))
    segments = [segment(1, 0.0, {"stp_01": 0.9, "none": 0.1})]

    deviations = derive_deviations(
        aligned,
        segments,
        steps,
        identities={"trk_002": TrackIdentity("flat-head screwdriver", 0.9)},
        tools_by_step={"stp_01": ("Phillips screwdriver",)},
        observations=[
            IntervalObservation("int_01", contact_s=10.0, held=(HeldTool("trk_002", 4.0),))
        ],
        activity=[TrackActivity("trk_002", 0.0, 1.0)],
    )

    assert deviations == ()


@pytest.mark.unit
@pytest.mark.parametrize("label", ["unknown", "other"])
def test_unknown_identity_never_flags_wrong_tool(label: str) -> None:
    steps = [step(1)]
    aligned = alignment(interval(1, "stp_01", 0.0, 1.0))
    segments = [segment(1, 0.0, {"stp_01": 0.9, "none": 0.1})]

    deviations = derive_deviations(
        aligned,
        segments,
        steps,
        identities={"trk_002": TrackIdentity(label, 0.95)},
        tools_by_step={"stp_01": ("Phillips screwdriver",)},
        observations=[
            IntervalObservation("int_01", contact_s=10.0, held=(HeldTool("trk_002", 9.0),))
        ],
        activity=[TrackActivity("trk_002", 0.0, 1.0)],
    )

    assert deviations == ()


@pytest.mark.unit
def test_low_confidence_identity_never_flags_wrong_tool() -> None:
    steps = [step(1)]
    aligned = alignment(interval(1, "stp_01", 0.0, 1.0))
    segments = [segment(1, 0.0, {"stp_01": 0.9, "none": 0.1})]

    deviations = derive_deviations(
        aligned,
        segments,
        steps,
        identities={"trk_002": TrackIdentity("flat-head screwdriver", 0.5)},
        tools_by_step={"stp_01": ("Phillips screwdriver",)},
        observations=[
            IntervalObservation("int_01", contact_s=10.0, held=(HeldTool("trk_002", 9.0),))
        ],
        activity=[TrackActivity("trk_002", 0.0, 1.0)],
    )

    assert deviations == ()


@pytest.mark.unit
def test_compound_scenario_lists_all_three_types_with_unique_ids() -> None:
    steps = [step(1), step(2), step(3), step(4)]
    aligned = alignment(
        interval(1, "stp_02", 0.0, 1.0),
        interval(2, "stp_01", 1.0, 2.0),
        interval(3, "stp_03", 2.0, 3.0),
    )
    segments = [
        segment(1, 0.0, {"stp_02": 0.9, "none": 0.1}),
        segment(2, 1.0, {"stp_01": 0.9, "none": 0.1}),
        segment(3, 2.0, {"stp_03": 0.9, "none": 0.1}),
        segment(4, 3.0, {"none": 0.9, "stp_04": 0.1}),
    ]
    identities = {"trk_002": TrackIdentity("flat-head screwdriver", 0.9)}
    observations = [IntervalObservation("int_02", contact_s=10.0, held=(HeldTool("trk_002", 8.0),))]
    activity = [
        TrackActivity("trk_001", 0.0, 4.0),
        TrackActivity("trk_002", 1.0, 2.0),
    ]

    deviations = derive_deviations(
        aligned,
        segments,
        steps,
        identities=identities,
        tools_by_step={"stp_01": ("Phillips screwdriver",)},
        observations=observations,
        activity=activity,
    )

    assert [item.type for item in deviations] == ["out_of_order", "wrong_tool", "missed"]
    assert [item.id for item in deviations] == ["dev_001", "dev_002", "dev_003"]
    assert (
        derive_deviations(
            aligned,
            segments,
            steps,
            identities=identities,
            tools_by_step={"stp_01": ("Phillips screwdriver",)},
            observations=observations,
            activity=activity,
        )
        == deviations
    )


@pytest.mark.unit
def test_compliant_alignment_has_no_deviations() -> None:
    steps = [step(1), step(2)]
    aligned = alignment(
        interval(1, "stp_01", 0.0, 1.0),
        interval(2, "stp_02", 1.0, 2.0),
    )
    segments = [
        segment(1, 0.0, {"stp_01": 0.9, "none": 0.1}),
        segment(2, 1.0, {"stp_02": 0.9, "none": 0.1}),
    ]

    assert (
        derive_deviations(
            aligned,
            segments,
            steps,
            activity=[TrackActivity("trk_001", 0.0, 2.0)],
        )
        == ()
    )


@pytest.mark.unit
def test_findings_below_review_threshold_are_dropped() -> None:
    steps = [step(1)]
    aligned = alignment(interval(1, "stp_01", 0.0, 1.0))
    segments = [segment(1, 0.0, {"stp_01": 0.9, "none": 0.1})]
    params = DeviationParams(tau_review=0.8)

    deviations = derive_deviations(
        aligned,
        segments,
        steps,
        identities={"trk_002": TrackIdentity("flat-head screwdriver", 0.75)},
        tools_by_step={"stp_01": ("Phillips screwdriver",)},
        observations=[
            IntervalObservation("int_01", contact_s=10.0, held=(HeldTool("trk_002", 8.0),))
        ],
        activity=[TrackActivity("trk_002", 0.0, 1.0)],
        params=params,
    )

    assert deviations == ()


@pytest.mark.unit
def test_deviation_without_track_references_is_rejected() -> None:
    with pytest.raises(ValueError, match="track reference"):
        Deviation(
            id="dev_001",
            type="missed",
            status="flagged",
            severity="medium",
            step_id="stp_01",
            t_start=0.0,
            t_end=1.0,
            track_ids=(),
            confidence=0.9,
            margin=0.1,
        )


@pytest.mark.unit
def test_alignment_referencing_an_unknown_step_is_rejected() -> None:
    aligned = alignment(interval(1, "stp_99", 0.0, 1.0))
    segments = [segment(1, 0.0, {"stp_01": 0.9, "none": 0.1})]

    with pytest.raises(ValueError, match="unknown step"):
        derive_deviations(aligned, segments, [step(1)], activity=[])


@pytest.mark.unit
def test_duplicate_steps_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate step"):
        derive_deviations(alignment(), [], [step(1), step(1, 2)], activity=[])

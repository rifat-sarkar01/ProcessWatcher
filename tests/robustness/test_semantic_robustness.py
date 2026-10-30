"""Semantic robustness: starved perception must abstain, never invent findings.

These cases act on the aligner and the domain guard, which are the modules that
decide whether a video is checkable at all. A clip with no hands, a heavily occluded
clip (all likelihoods flat) and a video of a different procedure must all end in
`not_recognized` with no deviations, while a repeated step must stay explainable.
"""

from __future__ import annotations

import pytest

from pw.align.aligner import Segment, StepSpec, align
from pw.align.deviations import TrackActivity, derive_deviations
from pw.align.domain_guard import apply_domain_guard

STEPS = (
    StepSpec(step_id="stp_01", idx=1),
    StepSpec(step_id="stp_02", idx=2),
    StepSpec(step_id="stp_03", idx=3),
)
ACTIVITY = (TrackActivity(track_id="trk_001", t_start=0.0, t_end=15.0),)


def segment(segment_id: str, t_start: float, t_end: float, best: str) -> Segment:
    probs = {step.step_id: (0.9 if step.step_id == best else 0.05) for step in STEPS}
    return Segment(segment_id=segment_id, t_start=t_start, t_end=t_end, probs=probs)


@pytest.mark.unit
def test_no_hand_clip_has_no_segments_and_is_not_recognized() -> None:
    alignment = align([], STEPS)

    decision = apply_domain_guard(alignment)

    assert alignment.intervals == ()
    assert alignment.coverage == 0.0
    assert decision.status == "not_recognized"
    assert decision.deviations == ()


@pytest.mark.unit
def test_heavy_occlusion_abstains_instead_of_guessing() -> None:
    flat = {"stp_01": 0.1, "stp_02": 0.1, "stp_03": 0.1, "none": 0.7}
    segments = [
        Segment(segment_id="seg_01", t_start=0.0, t_end=5.0, probs=flat),
        Segment(segment_id="seg_02", t_start=5.0, t_end=10.0, probs=flat),
    ]

    alignment = align(segments, STEPS)
    decision = apply_domain_guard(alignment)

    assert [step_id for _, step_id in alignment.path] == ["none", "none"]
    assert alignment.coverage == 0.0
    assert decision.status == "not_recognized"
    assert decision.deviations == ()


@pytest.mark.unit
def test_mismatched_sop_reports_the_coverage_reason() -> None:
    flat = {"stp_01": 0.1, "stp_02": 0.1, "stp_03": 0.1, "none": 0.7}
    alignment = align([Segment("seg_01", 0.0, 5.0, flat)], STEPS)

    decision = apply_domain_guard(alignment)

    assert decision.status == "not_recognized"
    assert decision.message is not None
    assert "coverage" in decision.message


@pytest.mark.unit
def test_repeated_step_is_aligned_as_a_return_and_flagged() -> None:
    segments = [
        segment("seg_01", 0.0, 5.0, "stp_01"),
        segment("seg_02", 5.0, 10.0, "stp_02"),
        segment("seg_03", 10.0, 15.0, "stp_01"),
    ]

    alignment = align(segments, STEPS)
    deviations = derive_deviations(alignment, segments, STEPS, activity=ACTIVITY)

    assert [step_id for _, step_id in alignment.path] == ["stp_01", "stp_02", "stp_01"]
    assert apply_domain_guard(alignment).recognized is True
    assert "out_of_order" in {deviation.type for deviation in deviations}
    assert all(deviation.track_ids for deviation in deviations)
    assert all(deviation.t_end >= deviation.t_start for deviation in deviations)


@pytest.mark.unit
def test_a_single_observation_is_not_a_procedure() -> None:
    steps = (*STEPS, StepSpec(step_id="stp_04", idx=4))
    segments = [segment("seg_01", 0.0, 5.0, "stp_01")]

    alignment = align(segments, steps)
    decision = apply_domain_guard(
        alignment, derive_deviations(alignment, segments, steps, activity=ACTIVITY)
    )

    assert alignment.coverage < 0.3
    assert decision.status == "not_recognized"
    assert decision.deviations == ()

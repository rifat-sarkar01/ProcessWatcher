"""Domain-guard tests: a video that does not match the SOP is not recognized."""

from __future__ import annotations

import pytest

from pw.align.aligner import Alignment, AlignParams
from pw.align.deviations import Deviation
from pw.align.domain_guard import DomainGuardParams, apply_domain_guard


def alignment(coverage: float, per_segment_cost: float = 0.5) -> Alignment:
    return Alignment(
        path=(),
        intervals=(),
        total_cost=per_segment_cost,
        per_segment_cost=per_segment_cost,
        coverage=coverage,
        params=AlignParams(),
    )


def deviation() -> Deviation:
    return Deviation(
        id="dev_001",
        type="missed",
        status="flagged",
        severity="medium",
        step_id="stp_01",
        t_start=0.0,
        t_end=1.0,
        track_ids=("trk_001",),
        confidence=0.9,
        margin=0.1,
    )


@pytest.mark.unit
def test_matching_pair_is_recognized_and_keeps_deviations() -> None:
    finding = deviation()

    decision = apply_domain_guard(alignment(0.9), (finding,))

    assert decision.recognized is True
    assert decision.status == "ok"
    assert decision.message is None
    assert decision.deviations == (finding,)


@pytest.mark.unit
def test_other_procedure_is_not_recognized_and_drops_deviations() -> None:
    decision = apply_domain_guard(alignment(0.1), (deviation(),))

    assert decision.recognized is False
    assert decision.status == "not_recognized"
    assert decision.deviations == ()
    assert decision.message is not None
    assert "coverage" in decision.message
    assert "0.10" in decision.message


@pytest.mark.unit
def test_blank_video_is_not_recognized() -> None:
    decision = apply_domain_guard(alignment(0.0))

    assert decision.recognized is False
    assert decision.status == "not_recognized"
    assert decision.deviations == ()


@pytest.mark.unit
def test_coverage_exactly_at_the_minimum_is_recognized() -> None:
    assert apply_domain_guard(alignment(0.3)).recognized is True


@pytest.mark.unit
def test_coverage_below_the_minimum_is_not_recognized() -> None:
    assert apply_domain_guard(alignment(0.29)).recognized is False


@pytest.mark.unit
def test_cost_cap_rejects_an_expensive_alignment() -> None:
    params = DomainGuardParams(coverage_min=0.3, cost_max=2.0)

    decision = apply_domain_guard(alignment(0.9, per_segment_cost=2.5), params=params)

    assert decision.recognized is False
    assert decision.status == "not_recognized"
    assert decision.message is not None
    assert "cost" in decision.message
    assert "2.50" in decision.message


@pytest.mark.unit
def test_cost_exactly_at_the_cap_is_recognized() -> None:
    params = DomainGuardParams(coverage_min=0.3, cost_max=2.0)

    assert apply_domain_guard(alignment(0.9, per_segment_cost=2.0), params=params).recognized


@pytest.mark.unit
def test_null_cost_cap_ignores_cost() -> None:
    params = DomainGuardParams(coverage_min=0.3, cost_max=None)

    assert apply_domain_guard(alignment(0.9, per_segment_cost=99.0), params=params).recognized


@pytest.mark.unit
def test_default_params_match_the_thresholds_example() -> None:
    params = DomainGuardParams()

    assert params.coverage_min == pytest.approx(0.3)
    assert params.cost_max is None


@pytest.mark.unit
def test_recognized_alignment_without_deviations() -> None:
    decision = apply_domain_guard(alignment(1.0))

    assert decision.recognized is True
    assert decision.deviations == ()


@pytest.mark.unit
def test_invalid_coverage_minimum_raises() -> None:
    with pytest.raises(ValueError, match="coverage_min"):
        DomainGuardParams(coverage_min=1.5)


@pytest.mark.unit
def test_negative_cost_cap_raises() -> None:
    with pytest.raises(ValueError, match="cost_max"):
        DomainGuardParams(cost_max=-0.5)

"""Threshold calibration: grid picks the best constrained pair (T-3.10)."""

from __future__ import annotations

import pytest

from pw.bench.metrics import Deviation
from pw.bench.tune import (
    ClipSample,
    RawPrediction,
    TuneError,
    choose_thresholds,
)

TRUTH = (Deviation("stp_02", "missed", 5.0, 8.0),)


def _deviated() -> ClipSample:
    return ClipSample(
        clip_id="A1",
        compliant=False,
        truths=TRUTH,
        predictions=(RawPrediction("stp_02", "missed", 5.2, 7.8, 0.75),),
    )


def _compliant(confidence: float) -> ClipSample:
    return ClipSample(
        clip_id="A2",
        compliant=True,
        truths=(),
        predictions=(RawPrediction("stp_04", "wrong_tool", 10.0, 12.0, confidence),),
    )


@pytest.mark.unit
def test_grid_keeps_the_true_positive_and_drops_the_weak_false_one() -> None:
    tau_review, tau_flag, metrics = choose_thresholds([_deviated(), _compliant(0.45)])

    assert tau_review <= tau_flag
    assert metrics.overall.f1 == 1.0
    assert metrics.false_flags_per_compliant_clip == 0.0


@pytest.mark.unit
def test_constraint_rejects_every_pair_when_the_false_flag_is_certain() -> None:
    with pytest.raises(TuneError):
        choose_thresholds([_deviated(), _compliant(0.99)])

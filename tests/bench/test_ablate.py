"""Bootstrap CI for the dev ablation table (T-6.1)."""

from __future__ import annotations

import pytest

from pw.bench.ablate import bootstrap_f1


@pytest.mark.unit
def test_bootstrap_perfect_predictions_has_a_unit_interval() -> None:
    low, high = bootstrap_f1([(1, 0, 0), (2, 0, 0)], resamples=50)

    assert low == 1.0
    assert high == 1.0


@pytest.mark.unit
def test_bootstrap_with_errors_stays_inside_the_unit_interval() -> None:
    low, high = bootstrap_f1([(1, 1, 0), (0, 1, 1), (1, 0, 1)], resamples=200)

    assert 0.0 <= low <= high <= 1.0

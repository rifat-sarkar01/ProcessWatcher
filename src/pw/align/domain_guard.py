"""Procedure-not-recognized guard: abstain when the video does not match the SOP.

TRD §6.7: coverage below `domain_coverage_min` (0.3) or per-segment cost above the
calibrated `domain_cost_max` means the SOP/video pair is mismatched. The report must
say `not_recognized` and carry no deviations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pw.align.aligner import Alignment
from pw.align.deviations import Deviation

DomainStatus = Literal["ok", "not_recognized"]


@dataclass(frozen=True, slots=True)
class DomainGuardParams:
    """Defaults mirror `contracts/examples/thresholds.example.json`; the cost cap stays
    null until T-3.10 calibrates it on dev."""

    coverage_min: float = 0.3
    cost_max: float | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.coverage_min <= 1.0:
            raise ValueError(f"coverage_min outside [0, 1]: {self.coverage_min}")
        if self.cost_max is not None and self.cost_max < 0:
            raise ValueError(f"cost_max must be non-negative: {self.cost_max}")


@dataclass(frozen=True, slots=True)
class DomainDecision:
    recognized: bool
    status: DomainStatus
    message: str | None
    deviations: tuple[Deviation, ...]


def apply_domain_guard(
    alignment: Alignment,
    deviations: tuple[Deviation, ...] = (),
    *,
    params: DomainGuardParams | None = None,
) -> DomainDecision:
    """Return `not_recognized` with no deviations when the pair is mismatched."""
    settings = params or DomainGuardParams()
    if alignment.coverage < settings.coverage_min:
        return DomainDecision(
            recognized=False,
            status="not_recognized",
            message=(
                "procedure not recognized: step coverage "
                f"{alignment.coverage:.2f} is below {settings.coverage_min:.2f}"
            ),
            deviations=(),
        )
    if settings.cost_max is not None and alignment.per_segment_cost > settings.cost_max:
        return DomainDecision(
            recognized=False,
            status="not_recognized",
            message=(
                "procedure not recognized: alignment cost "
                f"{alignment.per_segment_cost:.2f} per segment exceeds "
                f"{settings.cost_max:.2f}"
            ),
            deviations=(),
        )
    return DomainDecision(
        recognized=True,
        status="ok",
        message=None,
        deviations=tuple(deviations),
    )

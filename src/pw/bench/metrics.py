"""PW-Bench metrics: type-aware deviation matching and aggregation.

Pure functions only (no I/O, no model calls) so the yardstick can be tested before any
model exists. Definitions follow `docs/04_TRD.md` §10:

* one-to-one greedy matching by temporal overlap;
* a prediction matches a ground-truth deviation when `type` and `step_id` are equal
  and the intervals overlap **or** lie within ±`tolerance_s` (default 2.0 s);
* only `flagged` predictions count as positives — `needs_review` is reported separately;
* per-type and overall precision/recall/F1, false flags per compliant clip,
  timestamp MAE, needs-review rate and cost/latency aggregation.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

TOLERANCE_S = 2.0
"""Maximum gap (seconds) at which a prediction still matches a truth (TRD §10)."""

DEVIATION_TYPES: tuple[str, ...] = ("missed", "out_of_order", "wrong_tool")

FLAGGED = "flagged"
NEEDS_REVIEW = "needs_review"


@dataclass(frozen=True, slots=True)
class Deviation:
    """A deviation, either predicted (`status` set) or ground truth (`status=None`)."""

    step_id: str
    kind: str
    t_start: float
    t_end: float
    status: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in DEVIATION_TYPES:
            raise ValueError(f"unknown deviation type {self.kind!r}")
        if self.t_end < self.t_start:
            raise ValueError(f"t_end ({self.t_end}) is before t_start ({self.t_start})")


def from_report(report: Mapping[str, Any]) -> list[Deviation]:
    """Read deviations out of a `report.json` mapping."""
    deviations: Iterable[Mapping[str, Any]] = report.get("deviations", [])
    return [
        Deviation(
            step_id=str(item["step_id"]),
            kind=str(item["type"]),
            t_start=float(item["t_start"]),
            t_end=float(item["t_end"]),
            status=str(item["status"]),
        )
        for item in deviations
    ]


def from_ground_truth(gt: Mapping[str, Any]) -> list[Deviation]:
    """Read deviations out of a clip's ground truth (`bench/gt.schema.json`)."""
    deviations: Iterable[Mapping[str, Any]] = gt.get("deviations", [])
    return [
        Deviation(
            step_id=str(item["step_id"]),
            kind=str(item["type"]),
            t_start=float(item["t_start"]),
            t_end=float(item["t_end"]),
        )
        for item in deviations
    ]


def _gap_s(left: Deviation, right: Deviation) -> float:
    return max(0.0, left.t_start - right.t_end, right.t_start - left.t_end)


def _overlap_s(left: Deviation, right: Deviation) -> float:
    return max(0.0, min(left.t_end, right.t_end) - max(left.t_start, right.t_start))


@dataclass(frozen=True, slots=True)
class Match:
    prediction: Deviation
    truth: Deviation
    overlap_s: float
    gap_s: float

    @property
    def timestamp_error_s(self) -> float:
        return abs(self.prediction.t_start - self.truth.t_start)


@dataclass(frozen=True, slots=True)
class MatchResult:
    matches: tuple[Match, ...]
    unmatched_predictions: tuple[Deviation, ...]
    unmatched_truths: tuple[Deviation, ...]


def match_deviations(
    predictions: Sequence[Deviation],
    truths: Sequence[Deviation],
    tolerance_s: float = TOLERANCE_S,
) -> MatchResult:
    """One-to-one greedy matching by temporal overlap, then by smallest gap."""
    candidates: list[tuple[float, float, float, int, int]] = []
    for prediction_index, prediction in enumerate(predictions):
        for truth_index, truth in enumerate(truths):
            if prediction.step_id != truth.step_id or prediction.kind != truth.kind:
                continue
            gap = _gap_s(prediction, truth)
            if gap > tolerance_s:
                continue
            overlap = _overlap_s(prediction, truth)
            candidates.append((overlap, gap, prediction.t_start, prediction_index, truth_index))

    # Best overlap first, then the closest start, then stable input order.
    candidates.sort(key=lambda item: (-item[0], item[1], item[2], item[3], item[4]))

    used_predictions: set[int] = set()
    used_truths: set[int] = set()
    matches: list[Match] = []
    for overlap, gap, _, prediction_index, truth_index in candidates:
        if prediction_index in used_predictions or truth_index in used_truths:
            continue
        used_predictions.add(prediction_index)
        used_truths.add(truth_index)
        matches.append(
            Match(
                prediction=predictions[prediction_index],
                truth=truths[truth_index],
                overlap_s=overlap,
                gap_s=gap,
            )
        )

    unmatched_predictions = tuple(
        prediction
        for index, prediction in enumerate(predictions)
        if index not in used_predictions
    )
    unmatched_truths = tuple(
        truth for index, truth in enumerate(truths) if index not in used_truths
    )
    return MatchResult(tuple(matches), unmatched_predictions, unmatched_truths)


@dataclass(frozen=True, slots=True)
class Prf:
    """Precision/recall/F1 with integer counts, so aggregation stays exact."""

    tp: int
    fp: int
    fn: int

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def f1(self) -> float:
        precision, recall = self.precision, self.recall
        return 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    def __add__(self, other: Prf) -> Prf:
        return Prf(self.tp + other.tp, self.fp + other.fp, self.fn + other.fn)


@dataclass(frozen=True, slots=True)
class ClipMetrics:
    clip_id: str
    compliant: bool
    overall: Prf
    by_type: Mapping[str, Prf]
    flagged: int
    needs_review: int
    matched_errors_s: tuple[float, ...]


def evaluate_clip(
    clip_id: str,
    predictions: Sequence[Deviation],
    truths: Sequence[Deviation],
    compliant: bool = False,
    tolerance_s: float = TOLERANCE_S,
) -> ClipMetrics:
    """Score one clip. `needs_review` predictions are reported but never counted."""
    flagged = [prediction for prediction in predictions if prediction.status == FLAGGED]
    needs_review = sum(1 for prediction in predictions if prediction.status == NEEDS_REVIEW)

    result = match_deviations(flagged, truths, tolerance_s)
    overall = Prf(
        tp=len(result.matches),
        fp=len(result.unmatched_predictions),
        fn=len(result.unmatched_truths),
    )

    by_type: dict[str, Prf] = {}
    for kind in DEVIATION_TYPES:
        kind_result = match_deviations(
            [prediction for prediction in flagged if prediction.kind == kind],
            [truth for truth in truths if truth.kind == kind],
            tolerance_s,
        )
        by_type[kind] = Prf(
            tp=len(kind_result.matches),
            fp=len(kind_result.unmatched_predictions),
            fn=len(kind_result.unmatched_truths),
        )

    return ClipMetrics(
        clip_id=clip_id,
        compliant=compliant,
        overall=overall,
        by_type=by_type,
        flagged=len(flagged),
        needs_review=needs_review,
        matched_errors_s=tuple(match.timestamp_error_s for match in result.matches),
    )


@dataclass(frozen=True, slots=True)
class BenchMetrics:
    clips: int
    overall: Prf
    by_type: Mapping[str, Prf]
    false_flags_per_compliant_clip: float
    timestamp_mae_s: float
    needs_review_rate: float


def aggregate(clips: Sequence[ClipMetrics]) -> BenchMetrics:
    """Aggregate per-clip metrics into the bench headline numbers."""
    overall = Prf(0, 0, 0)
    by_type = {kind: Prf(0, 0, 0) for kind in DEVIATION_TYPES}
    for clip in clips:
        overall = overall + clip.overall
        for kind in DEVIATION_TYPES:
            by_type[kind] = by_type[kind] + clip.by_type[kind]

    compliant_clips = [clip for clip in clips if clip.compliant]
    compliant_false_flags = sum(clip.overall.fp for clip in compliant_clips)
    false_flags_per_compliant_clip = (
        compliant_false_flags / len(compliant_clips) if compliant_clips else 0.0
    )

    errors = [error for clip in clips for error in clip.matched_errors_s]
    timestamp_mae_s = sum(errors) / len(errors) if errors else 0.0

    total_predictions = sum(clip.flagged + clip.needs_review for clip in clips)
    total_needs_review = sum(clip.needs_review for clip in clips)
    needs_review_rate = (
        total_needs_review / total_predictions if total_predictions else 0.0
    )

    return BenchMetrics(
        clips=len(clips),
        overall=overall,
        by_type=by_type,
        false_flags_per_compliant_clip=false_flags_per_compliant_clip,
        timestamp_mae_s=timestamp_mae_s,
        needs_review_rate=needs_review_rate,
    )


@dataclass(frozen=True, slots=True)
class CostSummary:
    total_usd: float
    per_video_minute: float
    mean_latency_s: float


def summarise_costs(
    per_clip_usd: Sequence[float],
    durations_s: Sequence[float],
    latency_s: Sequence[float],
) -> CostSummary:
    """Cost and latency per clip, normalised by video minutes (NFR-02, TRD §9)."""
    if not (len(per_clip_usd) == len(durations_s) == len(latency_s)):
        raise ValueError("per_clip_usd, durations_s and latency_s must have the same length")

    total_usd = sum(per_clip_usd)
    total_minutes = sum(durations_s) / 60.0
    per_video_minute = total_usd / total_minutes if total_minutes else 0.0
    mean_latency_s = sum(latency_s) / len(latency_s) if latency_s else 0.0
    return CostSummary(
        total_usd=total_usd,
        per_video_minute=per_video_minute,
        mean_latency_s=mean_latency_s,
    )


def step_timing_accuracy(
    expected: Mapping[str, tuple[float, float]],
    observed: Mapping[str, tuple[float, float]],
    tolerance_s: float = TOLERANCE_S,
) -> float:
    """Share of expected steps found at the right time in the observed lane (TRD §10)."""
    if not expected:
        return 0.0
    hits = 0
    for step_id, (expected_start, _) in expected.items():
        window = observed.get(step_id)
        if window is not None and abs(window[0] - expected_start) <= tolerance_s:
            hits += 1
    return hits / len(expected)

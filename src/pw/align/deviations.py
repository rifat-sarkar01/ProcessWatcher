"""Derive deviations from an alignment: missed, out-of-order and wrong-tool.

Only three types exist (A-9) and every deviation must cite a step, a time window and
at least one track. Statuses come from the evidence strength here; the verifier
(T-3.7) may later downgrade a finding to `needs_review`.
"""

from __future__ import annotations

import bisect
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal

from pw.align.aligner import Alignment, Segment, StepSpec, order_ranks

DeviationType = Literal["missed", "out_of_order", "wrong_tool"]
DeviationStatus = Literal["flagged", "needs_review"]
Severity = Literal["high", "medium"]

_STEP_ID = re.compile(r"^stp_\d{2,}$")
_DEVIATION_ID = re.compile(r"^dev_\d{3,}$")
_NEUTRAL_LABELS = frozenset({"unknown", "other"})
_TYPE_ORDER: dict[str, int] = {"missed": 0, "out_of_order": 1, "wrong_tool": 2}


@dataclass(frozen=True, slots=True)
class DeviationParams:
    """Thresholds from TRD §6.8."""

    tau_miss: float = 0.25
    tau_review: float = 0.4
    tau_flag: float = 0.7
    tau_margin: float = 2.0
    wrong_tool_fraction: float = 0.5
    identity_confidence: float = 0.6


@dataclass(frozen=True, slots=True)
class TrackIdentity:
    label: str
    confidence: float


@dataclass(frozen=True, slots=True)
class TrackActivity:
    """A track's presence over time, used to cite references."""

    track_id: str
    t_start: float
    t_end: float


@dataclass(frozen=True, slots=True)
class HeldTool:
    """A tool track held during an interval, from hold events."""

    track_id: str
    held_s: float


@dataclass(frozen=True, slots=True)
class IntervalObservation:
    """Contact facts for one alignment interval, from the timeline + identities."""

    interval_id: str
    contact_s: float
    held: tuple[HeldTool, ...] = ()


@dataclass(frozen=True, slots=True)
class Deviation:
    id: str
    type: DeviationType
    status: DeviationStatus
    severity: Severity
    step_id: str
    t_start: float
    t_end: float
    track_ids: tuple[str, ...]
    confidence: float
    margin: float
    relates_to_step_id: str | None = None
    expected_tools: tuple[str, ...] = ()
    observed_tools: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _DEVIATION_ID.match(self.id):
            raise ValueError(f"invalid deviation id: {self.id}")
        if self.type not in {"missed", "out_of_order", "wrong_tool"}:
            raise ValueError(f"invalid deviation type: {self.type}")
        if not _STEP_ID.match(self.step_id):
            raise ValueError(f"invalid step id: {self.step_id}")
        if self.t_end < self.t_start:
            raise ValueError(f"deviation {self.id}: t_end is before t_start")
        if not self.track_ids:
            raise ValueError(f"deviation {self.id} needs at least one track reference")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"deviation {self.id}: confidence outside [0, 1]")
        if self.relates_to_step_id is not None and not _STEP_ID.match(self.relates_to_step_id):
            raise ValueError(f"invalid related step id: {self.relates_to_step_id}")


def _status(confidence: float, params: DeviationParams) -> DeviationStatus | None:
    if confidence < params.tau_review:
        return None
    return "flagged" if confidence >= params.tau_flag else "needs_review"


def _tracks_during(
    activity: Sequence[TrackActivity], t_start: float, t_end: float
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {item.track_id for item in activity if item.t_start <= t_end and t_start <= item.t_end}
        )
    )


def _lis_indices(values: Sequence[int]) -> set[int]:
    """Indices of one longest non-decreasing subsequence (unambiguous tie-break)."""
    if not values:
        return set()
    tails: list[int] = []
    tail_indices: list[int] = []
    previous = [-1] * len(values)
    for index, value in enumerate(values):
        position = bisect.bisect_right(tails, value)
        if position == len(tails):
            tails.append(value)
            tail_indices.append(index)
        else:
            tails[position] = value
            tail_indices[position] = index
        if position > 0:
            previous[index] = tail_indices[position - 1]
    kept: set[int] = set()
    cursor = tail_indices[-1]
    while cursor != -1:
        kept.add(cursor)
        cursor = previous[cursor]
    return kept


def _validate(steps: Sequence[StepSpec], alignment: Alignment) -> None:
    if not steps:
        raise ValueError("at least one step is required")
    known: set[str] = set()
    for spec in steps:
        if spec.step_id in known:
            raise ValueError(f"duplicate step id: {spec.step_id}")
        known.add(spec.step_id)
    for interval in alignment.intervals:
        if interval.step_id not in known:
            raise ValueError(f"unknown step in alignment: {interval.step_id}")


def _missed(
    alignment: Alignment,
    segments: Sequence[Segment],
    steps: Sequence[StepSpec],
    tools_by_step: Mapping[str, Sequence[str]],
    activity: Sequence[TrackActivity],
    params: DeviationParams,
) -> list[Deviation]:
    present = {interval.step_id for interval in alignment.intervals}
    intervals = sorted(alignment.intervals, key=lambda item: (item.t_start, item.step_id))
    ranks = order_ranks(steps)
    video_end = max((item.t_end for item in segments), default=0.0)
    if intervals:
        video_end = max(video_end, max(item.t_end for item in intervals))

    found: list[Deviation] = []
    for spec in steps:
        if spec.step_id in present:
            continue
        max_prob = max((item.probs.get(spec.step_id, 0.0) for item in segments), default=0.0)
        if max_prob >= params.tau_miss:
            continue
        rank = ranks[spec.step_id]
        t_start = max((item.t_end for item in intervals if ranks[item.step_id] < rank), default=0.0)
        t_end = min(
            (item.t_start for item in intervals if ranks[item.step_id] > rank),
            default=video_end,
        )
        if t_end < t_start:
            t_end = t_start
        confidence = 1.0 - max_prob
        status = _status(confidence, params)
        if status is None:
            continue
        found.append(
            Deviation(
                id="dev_000",
                type="missed",
                status=status,
                severity="high" if spec.critical else "medium",
                step_id=spec.step_id,
                t_start=t_start,
                t_end=t_end,
                track_ids=_tracks_during(activity, t_start, t_end),
                confidence=confidence,
                margin=params.tau_miss - max_prob,
                expected_tools=tuple(tools_by_step.get(spec.step_id, ())),
            )
        )
    return found


def _out_of_order(
    alignment: Alignment,
    steps: Sequence[StepSpec],
    activity: Sequence[TrackActivity],
    params: DeviationParams,
) -> list[Deviation]:
    if len(alignment.intervals) < 2:
        return []
    intervals = sorted(alignment.intervals, key=lambda item: (item.t_start, item.step_id))
    ranks = order_ranks(steps)
    kept = _lis_indices([ranks[item.step_id] for item in intervals])
    specs = {spec.step_id: spec for spec in steps}
    ordered = sorted(steps, key=lambda item: (item.idx, item.step_id))
    previous_step: dict[str, str | None] = {
        spec.step_id: (ordered[index - 1].step_id if index else None)
        for index, spec in enumerate(ordered)
    }

    found: list[Deviation] = []
    for index, interval in enumerate(intervals):
        if index in kept:
            continue
        spec = specs[interval.step_id]
        confidence = 1.0 / (1.0 + math.exp(-interval.margin / params.tau_margin))
        status = _status(confidence, params)
        if status is None:
            continue
        found.append(
            Deviation(
                id="dev_000",
                type="out_of_order",
                status=status,
                severity="high" if spec.critical else "medium",
                step_id=interval.step_id,
                relates_to_step_id=previous_step[interval.step_id],
                t_start=interval.t_start,
                t_end=interval.t_end,
                track_ids=_tracks_during(activity, interval.t_start, interval.t_end),
                confidence=confidence,
                margin=interval.margin,
            )
        )
    return found


def _wrong_tools(
    alignment: Alignment,
    steps: Sequence[StepSpec],
    identities: Mapping[str, TrackIdentity],
    tools_by_step: Mapping[str, Sequence[str]],
    observations: Sequence[IntervalObservation],
    params: DeviationParams,
) -> list[Deviation]:
    by_interval = {item.interval_id: item for item in observations}
    specs = {spec.step_id: spec for spec in steps}
    found: list[Deviation] = []
    for interval in alignment.intervals:
        required = tuple(tools_by_step.get(interval.step_id, ()))
        if not required:
            continue
        observation = by_interval.get(interval.id)
        if observation is None or observation.contact_s <= 0:
            continue
        offending_s = 0.0
        track_ids: set[str] = set()
        labels: set[str] = set()
        confidences: list[float] = []
        for held in observation.held:
            identity = identities.get(held.track_id)
            if identity is None or identity.confidence < params.identity_confidence:
                continue
            if identity.label in _NEUTRAL_LABELS or identity.label in required:
                continue
            offending_s += max(0.0, held.held_s)
            track_ids.add(held.track_id)
            labels.add(identity.label)
            confidences.append(identity.confidence)
        fraction = offending_s / observation.contact_s
        if fraction < params.wrong_tool_fraction or not track_ids:
            continue
        confidence = min(confidences)
        status = _status(confidence, params)
        if status is None:
            continue
        spec = specs[interval.step_id]
        found.append(
            Deviation(
                id="dev_000",
                type="wrong_tool",
                status=status,
                severity="high" if spec.critical else "medium",
                step_id=interval.step_id,
                t_start=interval.t_start,
                t_end=interval.t_end,
                track_ids=tuple(sorted(track_ids)),
                confidence=confidence,
                margin=fraction - params.wrong_tool_fraction,
                expected_tools=required,
                observed_tools=tuple(sorted(labels)),
            )
        )
    return found


def derive_deviations(
    alignment: Alignment,
    segments: Sequence[Segment],
    steps: Sequence[StepSpec],
    *,
    identities: Mapping[str, TrackIdentity] | None = None,
    tools_by_step: Mapping[str, Sequence[str]] | None = None,
    activity: Sequence[TrackActivity] = (),
    observations: Sequence[IntervalObservation] = (),
    params: DeviationParams | None = None,
) -> tuple[Deviation, ...]:
    """Return time-ordered findings; anything below `tau_review` is dropped."""
    settings = params or DeviationParams()
    _validate(steps, alignment)
    identity_map = identities or {}
    tool_map = tools_by_step or {}

    candidates: list[Deviation] = []
    candidates.extend(_missed(alignment, segments, steps, tool_map, activity, settings))
    candidates.extend(_out_of_order(alignment, steps, activity, settings))
    candidates.extend(
        _wrong_tools(alignment, steps, identity_map, tool_map, observations, settings)
    )
    candidates.sort(key=lambda item: (item.t_start, _TYPE_ORDER[item.type], item.step_id))
    return tuple(
        replace(candidate, id=f"dev_{index:03d}")
        for index, candidate in enumerate(candidates, start=1)
    )

"""Alignment: deterministic constrained decoding of timeline segments onto SOP steps.

The scorer (T-3.4) supplies likelihoods; this module decides. It is pure and fully
deterministic: the same likelihoods and step graph always produce the same path, so
every finding downstream is explainable and unit-tested.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

NONE = "none"
SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class AlignParams:
    """Cost-model weights; the values are the TRD §6.7 defaults."""

    epsilon: float = 1e-3
    lambda_skip: float = 1.5
    lambda_critical_skip: float = 3.0
    lambda_back: float = 2.0
    back_per_rank: float = 0.5
    coverage_prob: float = 0.4

    def as_dict(self) -> dict[str, float]:
        return {
            "epsilon": self.epsilon,
            "lambda_skip": self.lambda_skip,
            "lambda_critical_skip": self.lambda_critical_skip,
            "lambda_back": self.lambda_back,
            "back_per_rank": self.back_per_rank,
            "coverage_prob": self.coverage_prob,
        }


@dataclass(frozen=True, slots=True)
class Segment:
    """One candidate action segment and its step likelihoods (sum 1 +/- 0.02)."""

    segment_id: str
    t_start: float
    t_end: float
    probs: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class StepSpec:
    """The ordering facts the aligner needs from the compiled SOP."""

    step_id: str
    idx: int
    critical: bool = False
    group_id: str | None = None


@dataclass(frozen=True, slots=True)
class Interval:
    """Consecutive segments assigned to the same step."""

    id: str
    step_id: str
    t_start: float
    t_end: float
    segment_ids: tuple[str, ...]
    mean_prob: float
    margin: float


@dataclass(frozen=True, slots=True)
class Alignment:
    path: tuple[tuple[str, str], ...]
    intervals: tuple[Interval, ...]
    total_cost: float
    per_segment_cost: float
    coverage: float
    params: AlignParams

    def to_artifact(self, *, run_id: str | None = None) -> dict[str, object]:
        """Build a value valid against `contracts/alignment.schema.json`."""
        artifact: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "path": [
                {"segment_id": segment_id, "step_id": step_id} for segment_id, step_id in self.path
            ],
            "intervals": [
                {
                    "id": interval.id,
                    "step_id": interval.step_id,
                    "t_start": interval.t_start,
                    "t_end": interval.t_end,
                    "segment_ids": list(interval.segment_ids),
                    "mean_prob": interval.mean_prob,
                    "margin": interval.margin,
                }
                for interval in self.intervals
            ],
            "cost": {
                "total": self.total_cost,
                "per_segment": self.per_segment_cost,
                "coverage": self.coverage,
            },
            "params": self.params.as_dict(),
            # T-3.11 owns the domain guard; until then every decode is a valid alignment.
            "status": "ok",
        }
        if run_id is not None:
            artifact["run_id"] = run_id
        return artifact


def order_ranks(steps: Sequence[StepSpec]) -> dict[str, int]:
    """Map each step to its order rank; unordered-group members share a rank."""
    ranks: dict[str, int] = {}
    rank = -1
    previous_key: str | None = None
    for spec in sorted(steps, key=lambda item: (item.idx, item.step_id)):
        key = spec.group_id if spec.group_id is not None else f"step:{spec.step_id}"
        if key != previous_key:
            rank += 1
            previous_key = key
        ranks[spec.step_id] = rank
    return ranks


def _validate(segments: Sequence[Segment], steps: Sequence[StepSpec]) -> None:
    if not steps:
        raise ValueError("at least one step is required")
    seen_steps: set[str] = set()
    for spec in steps:
        if spec.step_id in seen_steps:
            raise ValueError(f"duplicate step id: {spec.step_id}")
        if spec.idx < 1:
            raise ValueError(f"step {spec.step_id} needs a 1-based idx")
        seen_steps.add(spec.step_id)

    seen_segments: set[str] = set()
    for segment in segments:
        if not segment.segment_id:
            raise ValueError("segment id must not be empty")
        if segment.segment_id in seen_segments:
            raise ValueError(f"duplicate segment id: {segment.segment_id}")
        if segment.t_end < segment.t_start:
            raise ValueError(f"segment {segment.segment_id}: t_end is before t_start")
        for value in segment.probs.values():
            if value < 0 or value > 1:
                raise ValueError(
                    f"segment {segment.segment_id}: probability {value} outside [0, 1]"
                )
        seen_segments.add(segment.segment_id)


def _emission(segment: Segment, step_id: str, epsilon: float) -> float:
    return -math.log(segment.probs.get(step_id, 0.0) + epsilon)


def _transition(
    previous: str | None,
    current: str | None,
    ranks: Mapping[str, int],
    critical_by_rank: Mapping[int, bool],
    params: AlignParams,
) -> float:
    if previous is None or current is None:
        return 0.0
    previous_rank = ranks[previous]
    current_rank = ranks[current]
    if current_rank in {previous_rank, previous_rank + 1}:
        return 0.0
    if current_rank > previous_rank + 1:
        skipped = current_rank - previous_rank - 1
        any_critical = any(
            critical_by_rank.get(rank, False) for rank in range(previous_rank + 1, current_rank)
        )
        penalty = params.lambda_critical_skip if any_critical else params.lambda_skip
        return penalty * skipped
    return params.lambda_back + params.back_per_rank * (previous_rank - current_rank)


def _decode(
    segments: Sequence[Segment],
    step_ids: Sequence[str],
    ranks: Mapping[str, int],
    critical_by_rank: Mapping[int, bool],
    params: AlignParams,
) -> tuple[list[int], float]:
    """Viterbi over choices `0..K-1` (steps) and `K` (none).

    A state is `(choice_at_i, last_non_none_step)`; `last` is `-1` before any step.
    """
    count = len(step_ids)
    none_index = count
    total = len(segments)

    current: dict[tuple[int, int], float] = {}
    for choice in range(count + 1):
        step_id = step_ids[choice] if choice < count else NONE
        last = choice if choice < count else -1
        current[(choice, last)] = _emission(segments[0], step_id, params.epsilon)

    parents: list[dict[tuple[int, int], tuple[int, int]]] = []
    for index in range(1, total):
        following: dict[tuple[int, int], float] = {}
        parent: dict[tuple[int, int], tuple[int, int]] = {}
        for (previous_choice, previous_last), cost in current.items():
            previous_step = (
                step_ids[previous_choice]
                if previous_choice < count
                else (step_ids[previous_last] if previous_last >= 0 else None)
            )
            for choice in range(count + 1):
                step_id = step_ids[choice] if choice < count else NONE
                candidate = cost + _transition(
                    previous_step,
                    None if choice == none_index else step_id,
                    ranks,
                    critical_by_rank,
                    params,
                )
                candidate += _emission(segments[index], step_id, params.epsilon)
                last = choice if choice < count else previous_last
                key = (choice, last)
                existing = following.get(key)
                if (
                    existing is None
                    or candidate < existing - 1e-12
                    or (
                        abs(candidate - existing) <= 1e-12
                        and (previous_choice, previous_last) < parent[key]
                    )
                ):
                    following[key] = candidate
                    parent[key] = (previous_choice, previous_last)
        current = following
        parents.append(parent)

    state = min(current, key=lambda key: (current[key], key))
    best_cost = current[state]
    choices = [0] * total
    for index in range(total - 1, -1, -1):
        choices[index] = state[0]
        if index > 0:
            state = parents[index - 1][state]
    return choices, best_cost


def _segment_margins(
    segments: Sequence[Segment],
    step_ids: Sequence[str],
    choices: Sequence[int],
    ranks: Mapping[str, int],
    critical_by_rank: Mapping[int, bool],
    params: AlignParams,
) -> list[float]:
    """Extra cost of the best single-segment alternative to the chosen path."""
    count = len(step_ids)
    margins: list[float] = []
    previous_step: str | None = None
    for index, chosen in enumerate(choices):
        chosen_step = step_ids[chosen] if chosen < count else None
        next_choice = choices[index + 1] if index + 1 < len(choices) else None
        next_step = (
            step_ids[next_choice] if next_choice is not None and next_choice < count else None
        )
        chosen_emission = _emission(segments[index], chosen_step or NONE, params.epsilon)
        best_alternative = math.inf
        for alternative in range(count + 1):
            if alternative == chosen:
                continue
            alternative_step = step_ids[alternative] if alternative < count else None
            delta = (
                _emission(segments[index], alternative_step or NONE, params.epsilon)
                - chosen_emission
            )
            delta += _transition(previous_step, alternative_step, ranks, critical_by_rank, params)
            delta -= _transition(previous_step, chosen_step, ranks, critical_by_rank, params)
            if next_choice is not None:
                chosen_last = chosen_step if chosen_step is not None else previous_step
                alternative_last = (
                    alternative_step if alternative_step is not None else previous_step
                )
                delta += _transition(chosen_last, next_step, ranks, critical_by_rank, params)
                delta -= _transition(alternative_last, next_step, ranks, critical_by_rank, params)
            best_alternative = min(best_alternative, delta)
        margins.append(max(0.0, best_alternative))
        if chosen_step is not None:
            previous_step = chosen_step
    return margins


def _intervals(
    segments: Sequence[Segment],
    step_ids: Sequence[str],
    choices: Sequence[int],
    margins: Sequence[float],
    params: AlignParams,
) -> tuple[Interval, ...]:
    count = len(step_ids)
    collected: list[Interval] = []

    def flush(first: int, end: int) -> None:
        step_id = step_ids[choices[first]]
        assigned = [segments[index].probs.get(step_id, 0.0) for index in range(first, end)]
        collected.append(
            Interval(
                id=f"int_{len(collected) + 1:02d}",
                step_id=step_id,
                t_start=segments[first].t_start,
                t_end=segments[end - 1].t_end,
                segment_ids=tuple(segments[index].segment_id for index in range(first, end)),
                mean_prob=sum(assigned) / len(assigned),
                margin=min(margins[first:end]),
            )
        )

    first: int | None = None
    for index, choice in enumerate(choices):
        if choice == count:
            if first is not None:
                flush(first, index)
                first = None
            continue
        if first is None:
            first = index
        elif choice != choices[first]:
            flush(first, index)
            first = index
    if first is not None:
        flush(first, len(choices))
    return tuple(collected)


def align(
    segments: Sequence[Segment],
    steps: Sequence[StepSpec],
    *,
    params: AlignParams | None = None,
) -> Alignment:
    """Decode the cheapest path under the SOP's partial order."""
    settings = params or AlignParams()
    _validate(segments, steps)
    step_ids = [spec.step_id for spec in steps]
    if not segments:
        return Alignment(
            path=(),
            intervals=(),
            total_cost=0.0,
            per_segment_cost=0.0,
            coverage=0.0,
            params=settings,
        )

    ranks = order_ranks(steps)
    critical_by_rank: dict[int, bool] = {}
    for spec in steps:
        rank = ranks[spec.step_id]
        critical_by_rank[rank] = critical_by_rank.get(rank, False) or spec.critical

    choices, total_cost = _decode(segments, step_ids, ranks, critical_by_rank, settings)
    margins = _segment_margins(segments, step_ids, choices, ranks, critical_by_rank, settings)
    intervals = _intervals(segments, step_ids, choices, margins, settings)
    coverage = sum(
        1 for interval in intervals if interval.mean_prob >= settings.coverage_prob
    ) / len(step_ids)
    return Alignment(
        path=tuple(
            (segment.segment_id, step_ids[choice] if choice < len(step_ids) else NONE)
            for segment, choice in zip(segments, choices, strict=True)
        ),
        intervals=intervals,
        total_cost=total_cost,
        per_segment_cost=total_cost / len(segments),
        coverage=coverage,
        params=settings,
    )

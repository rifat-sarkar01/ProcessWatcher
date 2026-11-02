"""SOP compiler evaluation against `bench/golden` (FR-02, FR-13, gate G3).

The evaluator compares two contract-valid step graphs and reports four numbers per SOP:
exact step count, tool precision/recall (normalised phrases), ordering-constraint F1 and
critical-step recall. The gates are the ones named in T-3.3: count exact, tool P and R
>= 0.9, ordering F1 >= 0.9 and critical recall 1.0. It can compare directories or run
the compiler itself, so T-3.9 can call it with a replay cache.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pw.sop.compiler import CompileError, Compiler, compile_sop, normalise_phrase
from pw.sop.ingest import SopSource

GOLDEN_DIR = Path(__file__).resolve().parents[3] / "bench" / "golden"
TOOL_PRECISION_MIN = 0.9
TOOL_RECALL_MIN = 0.9
ORDERING_F1_MIN = 0.9
CRITICAL_RECALL_MIN = 1.0
StepKey = tuple[str, int]


@dataclass(frozen=True, slots=True)
class SOPMetrics:
    sop_id: str
    golden_steps: int
    candidate_steps: int
    step_count_ok: bool
    tool_precision: float
    tool_recall: float
    ordering_f1: float
    critical_recall: float
    failures: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.failures

    def to_payload(self) -> dict[str, object]:
        return {
            "sop_id": self.sop_id,
            "golden_steps": self.golden_steps,
            "candidate_steps": self.candidate_steps,
            "step_count_ok": self.step_count_ok,
            "tool_precision": round(self.tool_precision, 4),
            "tool_recall": round(self.tool_recall, 4),
            "ordering_f1": round(self.ordering_f1, 4),
            "critical_recall": round(self.critical_recall, 4),
            "passed": self.passed,
            "failures": list(self.failures),
        }


@dataclass(frozen=True, slots=True)
class EvalReport:
    results: tuple[SOPMetrics, ...]

    @property
    def passed_count(self) -> int:
        return sum(1 for result in self.results if result.passed)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> bool:
        return self.total > 0 and self.passed_count == self.total

    @property
    def summary(self) -> str:
        state = "PASS" if self.passed else "FAIL"
        return f"{state} {self.passed_count}/{self.total}"

    def to_payload(self) -> dict[str, object]:
        return {
            "summary": self.summary,
            "results": [result.to_payload() for result in self.results],
        }


class EvalError(ValueError):
    """The evaluation inputs are not usable graphs."""


def _steps(graph: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    steps = graph.get("steps")
    if not isinstance(steps, list):
        raise EvalError("graph has no steps array")
    return [step for step in steps if isinstance(step, Mapping)]


def _by_idx(steps: Sequence[Mapping[str, Any]]) -> dict[int, Mapping[str, Any]]:
    indexed: dict[int, Mapping[str, Any]] = {}
    for position, step in enumerate(steps, start=1):
        raw = step.get("idx", position)
        idx = raw if isinstance(raw, int) and not isinstance(raw, bool) else position
        indexed.setdefault(idx, step)
    return indexed


def _tools(step: Mapping[str, Any]) -> set[str]:
    tools = step.get("tools", ())
    if not isinstance(tools, list):
        return set()
    return {normalise_phrase(str(tool)) for tool in tools if str(tool).strip()}


def _critical(step: Mapping[str, Any]) -> bool:
    return step.get("critical") is True


def _tool_scores(
    golden: Mapping[int, Mapping[str, Any]], candidate: Mapping[int, Mapping[str, Any]]
) -> tuple[float, float]:
    true_positive = false_positive = false_negative = 0
    for idx, step in golden.items():
        expected = _tools(step)
        observed = _tools(candidate.get(idx, {}))
        true_positive += len(expected & observed)
        false_positive += len(observed - expected)
        false_negative += len(expected - observed)
    precision = (
        true_positive / (true_positive + false_positive) if true_positive + false_positive else 1.0
    )
    recall = (
        true_positive / (true_positive + false_negative) if true_positive + false_negative else 1.0
    )
    return precision, recall


def _base_key(step: Mapping[str, Any]) -> str:
    text = normalise_phrase(str(step.get("text", "")))
    if text:
        return text
    return "|".join(sorted(_tools(step)))


def _step_keys(steps: Mapping[int, Mapping[str, Any]]) -> dict[int, tuple[str, int]]:
    """Identify a step by its text, numbering duplicates in idx order."""
    seen: dict[str, int] = {}
    keys: dict[int, tuple[str, int]] = {}
    for idx in sorted(steps):
        base = _base_key(steps[idx])
        occurrence = seen.get(base, 0)
        seen[base] = occurrence + 1
        keys[idx] = (base, occurrence)
    return keys


def _constraints(steps: Mapping[int, Mapping[str, Any]]) -> set[tuple[StepKey, StepKey]]:
    """Ordered step-identity pairs that are not inside the same unordered group."""
    keys = _step_keys(steps)
    ordered = sorted(steps)
    constraints: set[tuple[StepKey, StepKey]] = set()
    for position, first in enumerate(ordered):
        for second in ordered[position + 1 :]:
            group_a = steps[first].get("group_id")
            group_b = steps[second].get("group_id")
            if group_a is not None and group_a == group_b:
                continue
            constraints.add((keys[first], keys[second]))
    return constraints


def _f1(expected: set[tuple[StepKey, StepKey]], observed: set[tuple[StepKey, StepKey]]) -> float:
    if not expected and not observed:
        return 1.0
    true_positive = len(expected & observed)
    precision = true_positive / len(observed) if observed else 0.0
    recall = true_positive / len(expected) if expected else 0.0
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _critical_recall(
    golden: Mapping[int, Mapping[str, Any]], candidate: Mapping[int, Mapping[str, Any]]
) -> float:
    expected = {idx for idx, step in golden.items() if _critical(step)}
    if not expected:
        return 1.0
    matched = sum(1 for idx in expected if _critical(candidate.get(idx, {})))
    return matched / len(expected)


def evaluate_graph(golden: Mapping[str, Any], candidate: Mapping[str, Any]) -> SOPMetrics:
    golden_steps = _steps(golden)
    candidate_steps = _steps(candidate)
    golden_by_idx = _by_idx(golden_steps)
    candidate_by_idx = _by_idx(candidate_steps)
    step_count_ok = len(golden_steps) == len(candidate_steps)
    precision, recall = _tool_scores(golden_by_idx, candidate_by_idx)
    ordering_f1 = _f1(_constraints(golden_by_idx), _constraints(candidate_by_idx))
    critical_recall = _critical_recall(golden_by_idx, candidate_by_idx)

    failures: list[str] = []
    if not step_count_ok:
        failures.append(f"step_count {len(candidate_steps)} != {len(golden_steps)}")
    if precision < TOOL_PRECISION_MIN:
        failures.append(f"tool_precision {precision:.2f} < {TOOL_PRECISION_MIN:g}")
    if recall < TOOL_RECALL_MIN:
        failures.append(f"tool_recall {recall:.2f} < {TOOL_RECALL_MIN:g}")
    if ordering_f1 < ORDERING_F1_MIN:
        failures.append(f"ordering_f1 {ordering_f1:.2f} < {ORDERING_F1_MIN:g}")
    if critical_recall < CRITICAL_RECALL_MIN:
        failures.append(f"critical_recall {critical_recall:.2f} < {CRITICAL_RECALL_MIN:g}")
    return SOPMetrics(
        sop_id=str(golden.get("sop_id", "unknown")),
        golden_steps=len(golden_steps),
        candidate_steps=len(candidate_steps),
        step_count_ok=step_count_ok,
        tool_precision=precision,
        tool_recall=recall,
        ordering_f1=ordering_f1,
        critical_recall=critical_recall,
        failures=tuple(failures),
    )


def load_goldens(directory: Path | None = None) -> dict[str, Mapping[str, Any]]:
    root = GOLDEN_DIR if directory is None else Path(directory)
    goldens: dict[str, Mapping[str, Any]] = {}
    for path in sorted(root.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise EvalError(f"{path} is not a JSON object")
        goldens[path.stem] = payload
    return goldens


def load_candidates(directory: Path | None = None) -> dict[str, Mapping[str, Any]]:
    return load_goldens(directory)


def evaluate_against_goldens(
    candidates: Mapping[str, Mapping[str, Any]], goldens: Mapping[str, Mapping[str, Any]]
) -> EvalReport:
    results: list[SOPMetrics] = []
    for name in sorted(goldens):
        candidate = candidates.get(name)
        if candidate is None:
            results.append(
                SOPMetrics(
                    sop_id=str(goldens[name].get("sop_id", name)),
                    golden_steps=len(_steps(goldens[name])),
                    candidate_steps=0,
                    step_count_ok=False,
                    tool_precision=0.0,
                    tool_recall=0.0,
                    ordering_f1=0.0,
                    critical_recall=0.0,
                    failures=("missing candidate graph",),
                )
            )
            continue
        results.append(evaluate_graph(goldens[name], candidate))
    return EvalReport(results=tuple(results))


def evaluate_directories(
    golden_dir: Path | None = None, candidate_dir: Path | None = None
) -> EvalReport:
    goldens = load_goldens(golden_dir)
    candidates = load_candidates(golden_dir if candidate_dir is None else candidate_dir)
    return evaluate_against_goldens(candidates, goldens)


def evaluate_compiler(
    sources: Mapping[str, SopSource],
    *,
    compiler: Compiler | None = None,
    cache: MutableMapping[str, str] | None = None,
    goldens: Mapping[str, Mapping[str, Any]] | None = None,
) -> EvalReport:
    """Compile each `name -> SopSource` and compare it with the same-named golden."""
    expected = load_goldens() if goldens is None else goldens
    call = compiler or (lambda prompt: "")
    results: list[SOPMetrics] = []
    for name in sorted(expected):
        source = sources.get(name)
        if source is None:
            continue
        try:
            graph = compile_sop(source, compiler=call, cache=cache).graph
        except CompileError as error:
            results.append(
                SOPMetrics(
                    sop_id=str(expected[name].get("sop_id", name)),
                    golden_steps=len(_steps(expected[name])),
                    candidate_steps=0,
                    step_count_ok=False,
                    tool_precision=0.0,
                    tool_recall=0.0,
                    ordering_f1=0.0,
                    critical_recall=0.0,
                    failures=(f"compile_error: {error}",),
                )
            )
            continue
        results.append(evaluate_graph(expected[name], graph))
    return EvalReport(results=tuple(results))


def format_report(report: EvalReport) -> str:
    lines = []
    for result in report.results:
        state = "PASS" if result.passed else "FAIL"
        detail = (
            f"steps={result.candidate_steps}/{result.golden_steps} "
            f"tools P={result.tool_precision:.2f} R={result.tool_recall:.2f} "
            f"order F1={result.ordering_f1:.2f} crit={result.critical_recall:.2f}"
        )
        if result.failures:
            detail += " (" + "; ".join(result.failures) + ")"
        lines.append(f"{result.sop_id}: {state} {detail}")
    lines.append(report.summary)
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pw.sop.eval")
    parser.add_argument("--golden-dir", type=Path, default=None)
    parser.add_argument("--candidate-dir", type=Path, default=None)
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="compare goldens with themselves (no model, proves the metrics)",
    )
    args = parser.parse_args(argv)
    candidate_dir = args.golden_dir if args.self_check else args.candidate_dir
    try:
        report = evaluate_directories(args.golden_dir, candidate_dir)
    except (OSError, ValueError, EvalError) as error:
        print(f"sop-eval: {error}", file=sys.stderr)
        return 2
    print(format_report(report))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CRITICAL_RECALL_MIN",
    "GOLDEN_DIR",
    "ORDERING_F1_MIN",
    "TOOL_PRECISION_MIN",
    "TOOL_RECALL_MIN",
    "EvalError",
    "EvalReport",
    "SOPMetrics",
    "evaluate_against_goldens",
    "evaluate_compiler",
    "evaluate_directories",
    "evaluate_graph",
    "format_report",
    "load_candidates",
    "load_goldens",
    "main",
]

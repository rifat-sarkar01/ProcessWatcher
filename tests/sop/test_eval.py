"""SOP compiler golden evaluation: step count, tools, ordering, critical recall."""

from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from pw.sop.compiler import CompileError, cache_key, compile_sop
from pw.sop.eval import (
    EvalReport,
    evaluate_against_goldens,
    evaluate_compiler,
    evaluate_directories,
    evaluate_graph,
    format_report,
    load_goldens,
    main,
)
from pw.sop.ingest import from_text

SCRATCH_ROOT = Path(__file__).resolve().parents[2] / ".uv" / "tests-tmp"


@pytest.fixture
def scratch() -> Iterator[Path]:
    root = SCRATCH_ROOT / f"eval-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def step(
    idx: int,
    *,
    tools: tuple[str, ...] = ("hand",),
    critical: bool = False,
    group_id: str | None = None,
) -> dict[str, Any]:
    return {
        "id": f"stp_{idx:02d}",
        "idx": idx,
        "text": f"Step {idx}.",
        "action": "do",
        "tools": list(tools),
        "parts": [],
        "ordering": "unordered_group" if group_id else "strict",
        "group_id": group_id,
        "critical": critical,
        "visual_check": None,
    }


def graph(steps: list[dict[str, Any]], *, sop_id: str = "sop_00000000") -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "sop_id": sop_id,
        "title": "Test SOP",
        "source": {"kind": "md", "sha256": "0" * 64},
        "steps": steps,
        "vocabulary": {"sam_concepts": ["hand"]},
        "warnings": [],
    }


BASE = graph(
    [
        step(1, critical=True),
        step(2),
        step(3, group_id="grp_01"),
        step(4, group_id="grp_01"),
        step(5, critical=True),
    ]
)


@pytest.mark.unit
def test_an_identical_graph_scores_one_on_every_metric() -> None:
    metrics = evaluate_graph(BASE, json.loads(json.dumps(BASE)))

    assert metrics.passed
    assert metrics.step_count_ok
    assert metrics.tool_precision == metrics.tool_recall == 1.0
    assert metrics.ordering_f1 == 1.0
    assert metrics.critical_recall == 1.0
    assert metrics.failures == ()


@pytest.mark.unit
def test_a_dropped_step_fails_the_exact_count() -> None:
    candidate = graph(BASE["steps"][:-1])

    metrics = evaluate_graph(BASE, candidate)

    assert not metrics.passed
    assert metrics.step_count_ok is False
    assert metrics.candidate_steps == 4
    assert metrics.failures[0] == "step_count 4 != 5"
    assert metrics.critical_recall == 0.5


@pytest.mark.unit
def test_an_extra_tool_lowers_precision() -> None:
    steps = [step(idx) for idx in range(1, 6)]
    candidate = [dict(item) for item in steps]
    candidate[0] = {**candidate[0], "tools": ["hand", "screwdriver"]}

    metrics = evaluate_graph(graph(steps), graph(candidate))

    assert not metrics.passed
    assert metrics.tool_precision == pytest.approx(5 / 6)
    assert metrics.tool_recall == 1.0
    assert any(failure.startswith("tool_precision") for failure in metrics.failures)


@pytest.mark.unit
def test_a_missing_tool_lowers_recall() -> None:
    steps = [step(idx, tools=("hand", "cable")) for idx in range(1, 6)]
    candidate = [dict(item) for item in steps]
    candidate[0] = {**candidate[0], "tools": ["hand"]}
    candidate[1] = {**candidate[1], "tools": ["hand"]}

    metrics = evaluate_graph(graph(steps), graph(candidate))

    assert metrics.tool_precision == 1.0
    assert metrics.tool_recall == pytest.approx(0.8)
    assert any(failure.startswith("tool_recall") for failure in metrics.failures)


@pytest.mark.unit
def test_swapped_strict_steps_lower_ordering_f1() -> None:
    steps = [step(idx) for idx in range(1, 6)]
    candidate = [dict(item) for item in steps]
    candidate[1] = {**candidate[1], "idx": 5}
    candidate[4] = {**candidate[4], "idx": 2}

    metrics = evaluate_graph(graph(steps), graph(candidate))

    assert metrics.ordering_f1 < 1.0
    assert any(failure.startswith("ordering_f1") for failure in metrics.failures)


@pytest.mark.unit
def test_swapping_steps_inside_an_unordered_group_still_passes() -> None:
    candidate = [dict(item) for item in BASE["steps"]]
    candidate[2] = {**candidate[2], "idx": 4}
    candidate[3] = {**candidate[3], "idx": 3}

    metrics = evaluate_graph(BASE, graph(candidate))

    assert metrics.ordering_f1 == 1.0
    assert metrics.passed


@pytest.mark.unit
def test_losing_a_critical_flag_fails_critical_recall() -> None:
    candidate = [dict(item) for item in BASE["steps"]]
    candidate[-1] = {**candidate[-1], "critical": False}

    metrics = evaluate_graph(BASE, graph(candidate))

    assert metrics.critical_recall == 0.5
    assert any(failure.startswith("critical_recall") for failure in metrics.failures)


@pytest.mark.unit
def test_tool_phrases_are_normalised_before_comparison() -> None:
    steps = [step(idx, tools=("SATA Cable",)) for idx in range(1, 4)]
    candidate = [step(idx, tools=("  sata   CABLE ",)) for idx in range(1, 4)]

    metrics = evaluate_graph(graph(steps), graph(candidate))

    assert metrics.tool_precision == metrics.tool_recall == 1.0
    assert metrics.passed


@pytest.mark.unit
def test_a_missing_candidate_is_reported_not_skipped() -> None:
    report = evaluate_against_goldens({}, {"P": BASE})

    assert report.total == 1
    assert not report.passed
    assert report.results[0].failures == ("missing candidate graph",)
    assert report.summary == "FAIL 0/1"


@pytest.mark.unit
def test_compiler_output_is_compared_through_the_cache() -> None:
    source = from_text("1. Do the first thing.\n2. Do the second thing.\n3. Done.\n")
    cache = {cache_key(source): json.dumps(BASE)}
    goldens = {"P": BASE}

    def must_not_call(prompt: str) -> str:
        raise AssertionError("cache hit should not call the model")

    report = evaluate_compiler({"P": source}, compiler=must_not_call, cache=cache, goldens=goldens)

    assert report.summary == "PASS 1/1"
    assert report.results[0].passed


@pytest.mark.unit
def test_a_compile_error_is_reported_as_failure() -> None:
    source = from_text("1. Do the first thing.\n")

    def fail(prompt: str) -> str:
        raise CompileError("boom", attempts=1, issues=("invalid_json",))

    report = evaluate_compiler({"P": source}, compiler=fail, goldens={"P": BASE})

    assert not report.passed
    assert report.results[0].failures == ("compile_error: boom",)


@pytest.mark.unit
def test_real_goldens_load_and_pass_against_themselves() -> None:
    goldens = load_goldens()

    assert sorted(goldens) == ["P-A", "P-B", "P-C"]
    report = evaluate_against_goldens(goldens, goldens)

    assert isinstance(report, EvalReport)
    assert report.summary == "PASS 3/3"
    assert format_report(report).count(": PASS") == 3


@pytest.mark.unit
def test_directory_evaluation_reports_the_summary(scratch: Path) -> None:
    golden_dir = scratch / "golden"
    candidate_dir = scratch / "candidate"
    golden_dir.mkdir()
    candidate_dir.mkdir()
    (golden_dir / "P-A.json").write_text(json.dumps(BASE), encoding="utf-8")
    (candidate_dir / "P-A.json").write_text(json.dumps(BASE), encoding="utf-8")
    (golden_dir / "P-B.json").write_text(json.dumps(BASE), encoding="utf-8")
    bad = graph(BASE["steps"][:-1])
    (candidate_dir / "P-B.json").write_text(json.dumps(bad), encoding="utf-8")

    report = evaluate_directories(golden_dir, candidate_dir)

    assert report.summary == "FAIL 1/2"
    assert report.passed_count == 1


@pytest.mark.unit
def test_self_check_cli_passes_on_the_real_goldens(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--self-check"])

    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.strip().splitlines()[-1] == "PASS 3/3"


@pytest.mark.unit
def test_cli_returns_one_when_a_candidate_misses_the_gate(
    scratch: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    golden_dir = scratch / "golden"
    golden_dir.mkdir()
    (golden_dir / "P-A.json").write_text(json.dumps(BASE), encoding="utf-8")
    candidate_dir = scratch / "candidate"
    candidate_dir.mkdir()
    (candidate_dir / "P-A.json").write_text(json.dumps(graph(BASE["steps"][:-1])), encoding="utf-8")

    code = main(["--golden-dir", str(golden_dir), "--candidate-dir", str(candidate_dir)])

    assert code == 1
    assert capsys.readouterr().out.strip().splitlines()[-1] == "FAIL 0/1"


@pytest.mark.unit
def test_compiled_graph_still_reaches_the_compiler_when_the_cache_is_cold() -> None:
    source = from_text("1. Do the first thing.\n")
    cache: dict[str, str] = {}
    compile_sop(source, compiler=lambda prompt: json.dumps(BASE), cache=cache)

    assert len(cache) == 1

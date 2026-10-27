"""Bench authoring tests: SOP text vs golden graphs, and ground-truth clips."""

from __future__ import annotations

import copy
import json
import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from pw.data import cli
from pw.data.schemas import load_json
from pw.data.sopcheck import (
    default_bench_dir,
    golden_step_ids,
    parse_sop_steps,
    validate_bench_sops,
    validate_gt,
    validate_sop_pairing,
)

BENCH_DIR = default_bench_dir()
GOLDEN_DIR = BENCH_DIR / "golden"
SOPS_DIR = BENCH_DIR / "sops"
SCRATCH_ROOT = Path(__file__).resolve().parents[2] / ".uv" / "tests-tmp"


def golden(procedure: str) -> dict[str, Any]:
    payload = load_json(GOLDEN_DIR / f"P-{procedure}.json")
    assert isinstance(payload, dict)
    return copy.deepcopy(payload)


def sample_gt(procedure: str = "C") -> dict[str, Any]:
    graph = golden(procedure)
    steps = [
        {
            "step_id": step["id"],
            "t_start": round(index * 8.0, 3),
            "t_end": round(index * 8.0 + 6.0, 3),
        }
        for index, step in enumerate(graph["steps"])
    ]
    return {
        "clip_id": f"{procedure}1",
        "procedure": procedure,
        "sop_file": f"bench/sops/P-{procedure}-*.md",
        "compliant": True,
        "operator": "op-2",
        "camera": "tripod-right",
        "instances": {"bolt": 4, "hand": 2, "torque wrench": 1},
        "steps": steps,
        "deviations": [],
    }


@pytest.fixture
def bench_copy() -> Iterator[Path]:
    """A writable copy of bench/sops + bench/golden for negative cases."""
    root = SCRATCH_ROOT / uuid.uuid4().hex
    (root / "sops").mkdir(parents=True, exist_ok=True)
    (root / "golden").mkdir(parents=True, exist_ok=True)
    for path in SOPS_DIR.glob("*.md"):
        shutil.copy2(path, root / "sops" / path.name)
    for path in GOLDEN_DIR.glob("*.json"):
        shutil.copy2(path, root / "golden" / path.name)
    shutil.copy2(BENCH_DIR / "gt.schema.json", root / "gt.schema.json")
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --- authored SOPs and golden graphs ---------------------------------------------


@pytest.mark.unit
def test_validate_sops_cli_passes(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["validate-sops"]) == 0
    out = capsys.readouterr().out
    assert "3 SOPs, 3 golden graphs valid; steps 8–12; critical ≥ 1; tools ≥ 3" in out


@pytest.mark.unit
def test_bench_sops_have_no_errors() -> None:
    sop_count, golden_count, errors = validate_bench_sops()

    assert (sop_count, golden_count) == (3, 3)
    assert errors == []


@pytest.mark.unit
@pytest.mark.parametrize("procedure", ["A", "B", "C"])
def test_sop_text_matches_golden_step_count(procedure: str) -> None:
    sop_path = next(SOPS_DIR.glob(f"P-{procedure}-*.md"))
    text_steps = parse_sop_steps(sop_path.read_text(encoding="utf-8"))

    assert 8 <= len(text_steps) <= 12
    assert len(text_steps) == len(golden(procedure)["steps"])


@pytest.mark.unit
@pytest.mark.parametrize("procedure", ["A", "B", "C"])
def test_golden_graph_meets_procedure_shape(procedure: str) -> None:
    steps = golden(procedure)["steps"]
    tools = {tool for step in steps for tool in step["tools"]}

    assert any(step["critical"] for step in steps)
    assert len(tools) >= 3
    assert any(step["ordering"] == "unordered_group" for step in steps)


@pytest.mark.unit
def test_missing_critical_step_is_rejected(bench_copy: Path) -> None:
    path = bench_copy / "golden" / "P-C.json"
    payload = load_json(path)
    assert isinstance(payload, dict)
    for step in payload["steps"]:
        step["critical"] = False
    path.write_text(json.dumps(payload), encoding="utf-8")

    _, _, errors = validate_bench_sops(bench_copy)

    assert any("no critical step" in error for error in errors)


@pytest.mark.unit
def test_too_few_tools_is_rejected(bench_copy: Path) -> None:
    path = bench_copy / "golden" / "P-C.json"
    payload = load_json(path)
    assert isinstance(payload, dict)
    for step in payload["steps"]:
        step["tools"] = ["hand"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    _, _, errors = validate_bench_sops(bench_copy)

    assert any("distinct tools" in error for error in errors)


@pytest.mark.unit
def test_single_member_unordered_group_is_rejected(bench_copy: Path) -> None:
    path = bench_copy / "golden" / "P-C.json"
    payload = load_json(path)
    assert isinstance(payload, dict)
    payload["steps"][7]["ordering"] = "strict"
    payload["steps"][7]["group_id"] = None
    path.write_text(json.dumps(payload), encoding="utf-8")

    _, _, errors = validate_bench_sops(bench_copy)

    assert any("expected >= 2" in error for error in errors)


@pytest.mark.unit
def test_sop_text_step_count_mismatch_is_rejected(bench_copy: Path) -> None:
    sop_path = next((bench_copy / "sops").glob("P-A-*.md"))
    text = sop_path.read_text(encoding="utf-8") + "\n11. An extra step that is not in the graph.\n"
    sop_path.write_text(text, encoding="utf-8")

    errors = validate_sop_pairing(sop_path, bench_copy / "golden" / "P-A.json")

    assert any("numbered steps" in error for error in errors)


# --- ground truth ----------------------------------------------------------------


@pytest.mark.unit
def test_ground_truth_sample_is_valid() -> None:
    steps = golden_step_ids(GOLDEN_DIR / "P-C.json")

    assert validate_gt(sample_gt(), steps) == []


@pytest.mark.unit
def test_ground_truth_rejects_unknown_step_id() -> None:
    payload = sample_gt()
    payload["steps"][0]["step_id"] = "stp_99"
    steps = golden_step_ids(GOLDEN_DIR / "P-C.json")

    errors = validate_gt(payload, steps)

    assert any("unknown step" in error for error in errors)


@pytest.mark.unit
def test_ground_truth_rejects_compliant_clip_with_deviations() -> None:
    payload = sample_gt()
    payload["deviations"] = [
        {"type": "missed", "step_id": "stp_05", "t_start": 40.0, "t_end": 48.0}
    ]
    steps = golden_step_ids(GOLDEN_DIR / "P-C.json")

    errors = validate_gt(payload, steps)

    assert any("compliant clips must have an empty deviations" in error for error in errors)


@pytest.mark.unit
def test_ground_truth_rejects_bad_deviation_type() -> None:
    payload = sample_gt()
    payload["compliant"] = False
    payload["deviations"] = [
        {"type": "teleport", "step_id": "stp_05", "t_start": 40.0, "t_end": 48.0}
    ]
    steps = golden_step_ids(GOLDEN_DIR / "P-C.json")

    errors = validate_gt(payload, steps)

    assert any("teleport" in error for error in errors)


@pytest.mark.unit
def test_ground_truth_rejects_backwards_deviation_time() -> None:
    payload = sample_gt()
    payload["compliant"] = False
    payload["deviations"] = [
        {"type": "missed", "step_id": "stp_05", "t_start": 48.0, "t_end": 40.0}
    ]
    steps = golden_step_ids(GOLDEN_DIR / "P-C.json")

    errors = validate_gt(payload, steps)

    assert any("t_end is before t_start" in error for error in errors)


@pytest.mark.unit
def test_validate_gt_cli_ok() -> None:
    scratch = SCRATCH_ROOT / uuid.uuid4().hex
    scratch.mkdir(parents=True, exist_ok=True)
    try:
        path = scratch / "gt.json"
        path.write_text(json.dumps(sample_gt()), encoding="utf-8")
        assert cli.main(["validate-gt", str(path), "--golden", str(GOLDEN_DIR / "P-C.json")]) == 0
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

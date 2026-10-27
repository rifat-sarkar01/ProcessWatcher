"""Bench authoring checks: SOP text vs golden step graphs, and ground-truth clips.

`pw-data validate-sops` proves the authored bench inputs are complete and consistent
before any clip is filmed (docs/06_Plan.md T-1.3). It ties three things together:

* the SOP markdown in `bench/sops/*.md` (numbered steps, critical cues, ordering notes),
* the hand-written golden step graph in `bench/golden/*.json` (contract-valid),
* the ground-truth schema in `bench/gt.schema.json` (docs/05_Schema.md §14).
"""

from __future__ import annotations

import itertools
import os
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from pw.data.schemas import load_json
from pw.data.validate import validate_payload

BENCH_DIR_ENV = "PW_BENCH_DIR"
GT_SCHEMA_FILENAME = "gt.schema.json"

MIN_STEPS = 8
MAX_STEPS = 12
MIN_CRITICAL = 1
MIN_TOOLS = 3

_STEP_LINE = re.compile(r"^\s*(\d+)\.\s+(.+?)\s*$")


def default_bench_dir() -> Path:
    """Return the bench directory: `PW_BENCH_DIR`, else `<repo>/bench`."""
    override = os.environ.get(BENCH_DIR_ENV)
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[3] / "bench"


def parse_sop_steps(text: str) -> list[str]:
    """Return the numbered step lines of an SOP markdown document, in order."""
    steps: list[str] = []
    for line in text.splitlines():
        match = _STEP_LINE.match(line)
        if match is not None:
            steps.append(match.group(2))
    return steps


def _golden_for(sop_path: Path, bench_dir: Path) -> Path:
    """P-A-ssd-swap.md -> bench/golden/P-A.json"""
    procedure = "-".join(sop_path.name.split("-")[:2])
    return bench_dir / "golden" / f"{procedure}.json"


def validate_sop_pairing(sop_path: Path, golden_path: Path) -> list[str]:
    """Check one SOP document against its hand-written golden step graph."""
    errors: list[str] = []
    name = sop_path.name

    if not golden_path.is_file():
        return [f"{name}: missing golden step graph {golden_path.name}"]

    golden: dict[str, Any] = load_json(golden_path)
    contract_errors = validate_payload("sop", golden)
    if contract_errors:
        return [f"{golden_path.name}: {error}" for error in contract_errors]

    text_steps = parse_sop_steps(sop_path.read_text(encoding="utf-8"))
    graph_steps: list[dict[str, Any]] = list(golden["steps"])

    if len(text_steps) != len(graph_steps):
        errors.append(
            f"{name}: {len(text_steps)} numbered steps in the SOP text but "
            f"{len(graph_steps)} steps in {golden_path.name}"
        )

    if not MIN_STEPS <= len(graph_steps) <= MAX_STEPS:
        errors.append(
            f"{golden_path.name}: {len(graph_steps)} steps, expected {MIN_STEPS}-{MAX_STEPS}"
        )

    critical = sum(1 for step in graph_steps if step["critical"])
    if critical < MIN_CRITICAL:
        errors.append(f"{golden_path.name}: no critical step (expected >= {MIN_CRITICAL})")

    tools = {tool for step in graph_steps for tool in step["tools"]}
    if len(tools) < MIN_TOOLS:
        errors.append(f"{golden_path.name}: {len(tools)} distinct tools, expected >= {MIN_TOOLS}")

    groups: dict[str, int] = {}
    for step in graph_steps:
        if step["ordering"] == "unordered_group":
            group_id = str(step["group_id"])
            groups[group_id] = groups.get(group_id, 0) + 1
    if not groups:
        errors.append(f"{golden_path.name}: no any-order (unordered_group) steps")
    for group_id, size in sorted(groups.items()):
        if size < 2:
            errors.append(f"{golden_path.name}: group {group_id!r} has {size} step, expected >= 2")

    order_sensitive = any(
        first["ordering"] == "strict" and second["ordering"] == "strict"
        for first, second in itertools.pairwise(graph_steps)
    )
    if not order_sensitive:
        errors.append(f"{golden_path.name}: no adjacent strict pair (order-sensitive pair)")

    if "hand" not in golden["vocabulary"]["sam_concepts"]:
        errors.append(f"{golden_path.name}: vocabulary must contain 'hand'")

    return errors


def validate_bench_sops(bench_dir: Path | None = None) -> tuple[int, int, list[str]]:
    """Validate every authored SOP and golden graph. Returns (sops, goldens, errors)."""
    base = bench_dir if bench_dir is not None else default_bench_dir()
    sop_paths = sorted((base / "sops").glob("*.md"))
    errors: list[str] = []

    if len(sop_paths) != 3:
        errors.append(f"expected 3 SOPs in bench/sops, found {len(sop_paths)}")

    golden_count = 0
    for sop_path in sop_paths:
        golden_path = _golden_for(sop_path, base)
        errors.extend(validate_sop_pairing(sop_path, golden_path))
        if golden_path.is_file():
            golden_count += 1

    return len(sop_paths), golden_count, errors


def load_gt_schema(bench_dir: Path | None = None) -> dict[str, Any]:
    """Load `bench/gt.schema.json` (a bench contract, not part of `contracts/`)."""
    base = bench_dir if bench_dir is not None else default_bench_dir()
    path = base / GT_SCHEMA_FILENAME
    if not path.is_file():
        raise FileNotFoundError(f"ground-truth schema not found: {path}")
    schema = load_json(path)
    if not isinstance(schema, dict):
        raise ValueError(f"{path}: schema root must be a JSON object")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:  # pragma: no cover - guarded by tests
        raise ValueError(f"{path}: invalid JSON Schema: {exc.message}") from exc
    return schema


def validate_gt(
    payload: Any,
    golden_steps: set[str],
    bench_dir: Path | None = None,
) -> list[str]:
    """Validate one clip's ground truth against the schema and its golden step graph."""
    schema = load_gt_schema(bench_dir)
    validator = Draft202012Validator(schema)
    errors = [
        f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(payload), key=lambda err: list(err.absolute_path))
    ]
    if errors:
        return [f"gt: {error}" for error in errors]
    if not isinstance(payload, dict):  # pragma: no cover - schema already enforced this
        return ["gt: <root>: expected an object"]

    problems: list[str] = []
    seen: set[str] = set()
    for index, window in enumerate(payload["steps"]):
        step_id = str(window["step_id"])
        if step_id in seen:
            problems.append(f"gt: steps[{index}].step_id: duplicate step {step_id!r}")
        seen.add(step_id)
        if step_id not in golden_steps:
            problems.append(f"gt: steps[{index}].step_id: unknown step {step_id!r}")
        if float(window["t_end"]) < float(window["t_start"]):
            problems.append(f"gt: steps[{index}]: t_end is before t_start")

    if payload["compliant"] and payload["deviations"]:
        problems.append("gt: compliant clips must have an empty deviations list")

    for index, deviation in enumerate(payload["deviations"]):
        step_id = str(deviation["step_id"])
        if step_id not in golden_steps:
            problems.append(f"gt: deviations[{index}].step_id: unknown step {step_id!r}")
        if float(deviation["t_end"]) < float(deviation["t_start"]):
            problems.append(f"gt: deviations[{index}]: t_end is before t_start")

    return problems


def golden_step_ids(golden_path: Path) -> set[str]:
    """Return the step ids of a golden step graph."""
    golden: dict[str, Any] = load_json(golden_path)
    return {str(step["id"]) for step in golden["steps"]}

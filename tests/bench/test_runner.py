"""T-1.7: bench runner on a synthetic split (no dev clips needed)."""

from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import Iterator
from hashlib import sha256
from pathlib import Path

import pytest

import pw.bench.cli as cli
from pw.bench.runner import BenchError, load_split_manifest, run_bench

ROOT = Path(__file__).resolve().parents[2]
SCRATCH_ROOT = ROOT / ".uv" / "tests-tmp"


def _write(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _truth(
    clip_id: str, *, compliant: bool, deviations: list[dict[str, object]]
) -> dict[str, object]:
    return {
        "clip_id": clip_id,
        "procedure": "A",
        "sop_file": "P-A-keyboard-clean.md",
        "compliant": compliant,
        "operator": "tester",
        "camera": "tripod",
        "instances": {"hand": 1},
        "steps": [
            {"step_id": "stp_01", "t_start": 0.0, "t_end": 2.0},
            {"step_id": "stp_02", "t_start": 2.0, "t_end": 4.0},
        ],
        "deviations": deviations,
    }


def _deviation() -> dict[str, object]:
    return {
        "type": "missed",
        "step_id": "stp_02",
        "t_start": 4.0,
        "t_end": 6.0,
    }


@pytest.fixture()
def bench_dir() -> Iterator[Path]:
    root = SCRATCH_ROOT / f"bench-{uuid.uuid4().hex}"
    (root / "dev" / "gt").mkdir(parents=True)
    shutil.copyfile(ROOT / "bench" / "gt.schema.json", root / "gt.schema.json")
    _write(root / "golden" / "P-A.json", {"steps": [{"id": "stp_01"}, {"id": "stp_02"}]})
    _write(
        root / "dev" / "manifest.json",
        {
            "split": "dev",
            "clips": [
                {
                    "clip_id": "A1",
                    "procedure": "A",
                    "sha256": "0" * 64,
                    "duration_s": 60.0,
                    "storage_ref": "A1.mp4",
                    "gt_path": "gt/A1.json",
                },
                {
                    "clip_id": "A2",
                    "procedure": "A",
                    "sha256": "1" * 64,
                    "duration_s": 60.0,
                    "storage_ref": "A2.mp4",
                    "gt_path": "gt/A2.json",
                },
            ],
        },
    )
    _write(
        root / "dev" / "gt" / "A1.json",
        _truth("A1", compliant=False, deviations=[_deviation()]),
    )
    _write(root / "dev" / "gt" / "A2.json", _truth("A2", compliant=True, deviations=[]))
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_oracle_scores_perfect_and_writes_the_result_set(bench_dir: Path) -> None:
    results = bench_dir / "results"
    result = run_bench(
        split="dev",
        predictor="oracle",
        bench_dir=bench_dir,
        results_dir=results,
        run_id="run_ORACLEFIXED",
    )

    overall = result.summary["overall"]
    assert overall["precision"] == 1.0
    assert overall["recall"] == 1.0
    assert overall["f1"] == 1.0
    assert result.summary["clips"] == 2
    assert [clip["clip_id"] for clip in result.per_clip] == ["A1", "A2"]

    for name in ("summary.json", "per_clip.json", "table.md", "manifest.json"):
        assert (result.run_dir / name).is_file(), name
    manifest = json.loads((result.run_dir / "manifest.json").read_text(encoding="utf-8"))
    for name, digest in manifest["files"].items():
        assert sha256((result.run_dir / name).read_bytes()).hexdigest() == digest


def test_empty_predictor_has_zero_recall_and_no_false_flags(bench_dir: Path) -> None:
    result = run_bench(
        split="dev",
        predictor="empty",
        bench_dir=bench_dir,
        results_dir=bench_dir / "results",
        run_id="run_EMPTYFIXED",
    )

    overall = result.summary["overall"]
    assert overall["recall"] == 0.0
    assert overall["tp"] == 0
    assert overall["fn"] == 1
    assert result.summary["false_flags_per_compliant_clip"] == 0.0
    assert result.summary["costs"]["total_usd"] == 0.0


def test_cli_runs_the_oracle(bench_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli.main(
        [
            "run",
            "--split",
            "dev",
            "--predictor",
            "oracle",
            "--bench-dir",
            str(bench_dir),
            "--results-dir",
            str(bench_dir / "results"),
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "predictor=oracle" in output
    assert "F1=1.0000" in output
    assert len(list((bench_dir / "results").iterdir())) == 1


def test_unknown_predictor_exits_two(bench_dir: Path) -> None:
    exit_code = cli.main(
        [
            "run",
            "--split",
            "dev",
            "--predictor",
            "oracle-ish",
            "--bench-dir",
            str(bench_dir),
            "--results-dir",
            str(bench_dir / "results"),
        ]
    )
    assert exit_code == 2


def test_declared_but_unimplemented_predictor_exits_three(bench_dir: Path) -> None:
    exit_code = cli.main(
        [
            "run",
            "--split",
            "dev",
            "--predictor",
            "baseline_a",
            "--bench-dir",
            str(bench_dir),
            "--results-dir",
            str(bench_dir / "results"),
        ]
    )
    assert exit_code == 3


def test_missing_manifest_exits_two(bench_dir: Path) -> None:
    exit_code = cli.main(
        [
            "run",
            "--split",
            "heldout",
            "--predictor",
            "oracle",
            "--bench-dir",
            str(bench_dir),
            "--results-dir",
            str(bench_dir / "results"),
        ]
    )
    assert exit_code == 2


def test_invalid_ground_truth_exits_one(bench_dir: Path) -> None:
    _write(
        bench_dir / "dev" / "gt" / "A2.json",
        _truth("A2", compliant=True, deviations=[_deviation()]),
    )
    exit_code = cli.main(
        [
            "run",
            "--split",
            "dev",
            "--predictor",
            "oracle",
            "--bench-dir",
            str(bench_dir),
            "--results-dir",
            str(bench_dir / "results"),
        ]
    )
    assert exit_code == 1


def test_duplicate_clip_ids_are_rejected(bench_dir: Path) -> None:
    manifest = json.loads((bench_dir / "dev" / "manifest.json").read_text(encoding="utf-8"))
    manifest["clips"][1]["clip_id"] = "A1"
    _write(bench_dir / "dev" / "manifest.json", manifest)

    with pytest.raises(BenchError):
        load_split_manifest(bench_dir, "dev")

"""Perception check: hand coverage, fragmentation and pick-up alignment (T-2.10)."""

from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from pw.bench import cli
from pw.bench.perception_check import perception_check, render_markdown

REPO = Path(__file__).resolve().parents[2]
SCRATCH_ROOT = REPO / ".uv" / "tests-tmp"
RUN_ID = "run_01M6FYT2GE6VS98YPAMJWSDXS7"


def _frame(index: int) -> dict[str, float | int]:
    return {"frame": index, "t": index / 10, "box": [0, 0, 10, 10]}


def _tracks(hand_frames: int = 10, fragmentation: float = 1.0) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "run_id": RUN_ID,
        "video": {
            "sha256": "a" * 64,
            "duration_s": 1.0,
            "analysis_fps": 10,
            "width": 16,
            "height": 16,
            "frame_count": 10,
        },
        "tracks": [
            {
                "id": "trk_001",
                "concept": "hand",
                "first_t": 0.0,
                "last_t": (hand_frames - 1) / 10,
                "frames": [_frame(index) for index in range(hand_frames)],
            },
            {
                "id": "trk_002",
                "concept": "brush",
                "first_t": 0.4,
                "last_t": 0.9,
                "frames": [_frame(index) for index in range(4, 10)],
            },
        ],
        "stitching": {"fragmentation_ratio": fragmentation},
    }


def _timeline(pickup_t: float = 5.0) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "run_id": RUN_ID,
        "events": [
            {
                "id": "evt_001",
                "type": "hold_start",
                "t_start": pickup_t,
                "t_end": pickup_t,
                "tracks": ["trk_002"],
                "confidence": 0.9,
            }
        ],
        "segments": [],
    }


def _gt() -> dict[str, object]:
    return {
        "clip_id": "A1",
        "procedure": "A",
        "sop_file": "bench/sops/P-A-keyboard-clean.md",
        "compliant": True,
        "operator": "operator_1",
        "camera": "tripod",
        "instances": {"hand": 1, "keyboard": 1, "brush": 1},
        "steps": [{"step_id": "stp_02", "t_start": 4.0, "t_end": 8.0}],
        "deviations": [],
    }


@pytest.fixture
def bench_and_runs() -> Iterator[tuple[Path, Path]]:
    root = SCRATCH_ROOT / uuid.uuid4().hex
    bench = root / "bench"
    runs = root / "runs"
    (bench / "dev" / "gt").mkdir(parents=True)
    run_dir = runs / RUN_ID / "stages"
    run_dir.mkdir(parents=True)

    (bench / "dev" / "gt" / "A1.json").write_text(json.dumps(_gt()), encoding="utf-8")
    manifest = {
        "split": "dev",
        "clips": [
            {
                "clip_id": "A1",
                "sha256": "a" * 64,
                "gt_path": "gt/A1.json",
            }
        ],
    }
    (bench / "dev" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (runs / RUN_ID / "manifest.json").write_text(
        json.dumps(
            {
                "mode": "replay",
                "created_at": "2026-11-03T00:00:00Z",
                "inputs": {"video_sha256": "a" * 64},
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "tracks.json").write_text(json.dumps(_tracks()), encoding="utf-8")
    (run_dir / "timeline.json").write_text(json.dumps(_timeline()), encoding="utf-8")
    try:
        yield bench, runs
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.mark.unit
def test_perception_check_passes(bench_and_runs: tuple[Path, Path]) -> None:
    bench, runs = bench_and_runs

    result = perception_check(split="dev", mode="replay", bench_dir=bench, runs_dir=runs)

    assert result.ok
    assert result.passed == 1
    assert result.clips[0].passed


@pytest.mark.unit
def test_low_hand_coverage_fails(bench_and_runs: tuple[Path, Path]) -> None:
    bench, runs = bench_and_runs
    (runs / RUN_ID / "stages" / "tracks.json").write_text(
        json.dumps(_tracks(hand_frames=5)), encoding="utf-8"
    )

    result = perception_check(split="dev", mode="replay", bench_dir=bench, runs_dir=runs)

    assert not result.clips[0].passed
    assert any("hand coverage" in reason for reason in result.clips[0].reasons)


@pytest.mark.unit
def test_high_fragmentation_fails(bench_and_runs: tuple[Path, Path]) -> None:
    bench, runs = bench_and_runs
    (runs / RUN_ID / "stages" / "tracks.json").write_text(
        json.dumps(_tracks(fragmentation=2.0)), encoding="utf-8"
    )

    result = perception_check(split="dev", mode="replay", bench_dir=bench, runs_dir=runs)

    assert any("fragmentation" in reason for reason in result.clips[0].reasons)


@pytest.mark.unit
def test_pickup_outside_step_window_fails(bench_and_runs: tuple[Path, Path]) -> None:
    bench, runs = bench_and_runs
    (runs / RUN_ID / "stages" / "timeline.json").write_text(
        json.dumps(_timeline(pickup_t=20.0)), encoding="utf-8"
    )

    result = perception_check(split="dev", mode="replay", bench_dir=bench, runs_dir=runs)

    assert any("pick-up hit rate" in reason for reason in result.clips[0].reasons)


@pytest.mark.unit
def test_missing_run_is_reported(bench_and_runs: tuple[Path, Path]) -> None:
    bench, runs = bench_and_runs
    shutil.rmtree(runs / RUN_ID)

    result = perception_check(split="dev", mode="replay", bench_dir=bench, runs_dir=runs)

    assert not result.ok
    assert result.clips[0].run_id is None
    assert any("no replay run" in reason for reason in result.clips[0].reasons)


@pytest.mark.unit
def test_cli_writes_markdown_and_exit_code(
    bench_and_runs: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    bench, runs = bench_and_runs
    out = bench.parent / "perception.md"

    assert (
        cli.main(
            [
                "perception-check",
                "--split",
                "dev",
                "--mode",
                "replay",
                "--bench-dir",
                str(bench),
                "--runs-dir",
                str(runs),
                "--out",
                str(out),
            ]
        )
        == 0
    )
    assert "PASS 1/1" in capsys.readouterr().out
    assert "## Exceptions" in out.read_text(encoding="utf-8")


@pytest.mark.unit
def test_markdown_lists_exceptions(bench_and_runs: tuple[Path, Path]) -> None:
    bench, runs = bench_and_runs
    (runs / RUN_ID / "stages" / "tracks.json").write_text(
        json.dumps(_tracks(hand_frames=1)), encoding="utf-8"
    )
    result = perception_check(split="dev", mode="replay", bench_dir=bench, runs_dir=runs)

    markdown = render_markdown(result)

    assert "**FAIL 0/1**" in markdown
    assert "- **A1**: hand coverage" in markdown

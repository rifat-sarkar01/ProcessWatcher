"""Held-out lock: unchanged files pass, any edit/add/remove is a violation (T-1.8)."""

from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from pw.data import cli
from pw.data.lock import LOCK_FILENAME, verify_lock, write_lock

REPO = Path(__file__).resolve().parents[2]
SCRATCH_ROOT = REPO / ".uv" / "tests-tmp"


def _gt(clip_id: str) -> dict[str, object]:
    return {
        "clip_id": clip_id,
        "procedure": "A",
        "sop_file": "bench/sops/P-A-keyboard-clean.md",
        "compliant": True,
        "operator": "operator_2",
        "camera": "tripod",
        "instances": {"hand": 2, "keyboard": 1},
        "steps": [{"step_id": "stp_01", "t_start": 1.0, "t_end": 10.0}],
        "deviations": [],
    }


@pytest.fixture
def bench() -> Iterator[Path]:
    root = SCRATCH_ROOT / uuid.uuid4().hex
    (root / "heldout" / "gt").mkdir(parents=True)
    clips = []
    for number in (16, 17):
        clip_id = f"A{number}"
        gt_path = root / "heldout" / "gt" / f"{clip_id}.json"
        gt_path.write_text(json.dumps(_gt(clip_id)), encoding="utf-8")
        clips.append({"clip_id": clip_id})
    (root / "heldout" / "manifest.json").write_text(
        json.dumps({"split": "heldout", "clips": clips}), encoding="utf-8"
    )
    write_lock(root, "74ff3a4", "2026-11-03T00:00:00Z")
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.mark.unit
def test_unchanged_lock_passes(bench: Path) -> None:
    assert (bench / LOCK_FILENAME).is_file()
    assert verify_lock(bench) == []


@pytest.mark.unit
def test_edited_gt_is_a_violation(bench: Path) -> None:
    path = bench / "heldout" / "gt" / "A16.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["operator"] = "someone-else"
    path.write_text(json.dumps(payload), encoding="utf-8")

    errors = verify_lock(bench)

    assert any("changed held-out file heldout/gt/A16.json" in error for error in errors)


@pytest.mark.unit
def test_added_file_is_a_violation(bench: Path) -> None:
    (bench / "heldout" / "gt" / "A18.json").write_text(json.dumps(_gt("A18")), encoding="utf-8")

    errors = verify_lock(bench)

    assert any("added held-out file heldout/gt/A18.json" in error for error in errors)


@pytest.mark.unit
def test_removed_file_is_a_violation(bench: Path) -> None:
    (bench / "heldout" / "gt" / "A17.json").unlink()

    errors = verify_lock(bench)

    assert any("removed held-out file heldout/gt/A17.json" in error for error in errors)


@pytest.mark.unit
def test_missing_lock_is_a_violation(bench: Path) -> None:
    (bench / LOCK_FILENAME).unlink()

    errors = verify_lock(bench)

    assert any("held-out lock not found" in error for error in errors)


@pytest.mark.unit
def test_verify_lock_cli_exit_codes(bench: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["verify-lock", "--bench-dir", str(bench)]) == 0
    assert "LOCK OK" in capsys.readouterr().out

    (bench / "heldout" / "gt" / "A16.json").write_text("{}", encoding="utf-8")
    assert cli.main(["verify-lock", "--bench-dir", str(bench)]) == 1
    assert "LOCK VIOLATION" in capsys.readouterr().err

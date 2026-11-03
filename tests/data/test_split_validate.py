"""Split validation: manifest, clip hashes and per-clip ground truth (T-1.4/T-1.5)."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from pw.data import cli
from pw.data.split import validate_split

REPO = Path(__file__).resolve().parents[2]
BENCH = REPO / "bench"
SCRATCH_ROOT = REPO / ".uv" / "tests-tmp"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _gt(clip_id: str, duration: float, t_end: float = 20.0) -> dict[str, object]:
    return {
        "clip_id": clip_id,
        "procedure": "A",
        "sop_file": "bench/sops/P-A-keyboard-clean.md",
        "compliant": True,
        "operator": "operator_1",
        "camera": "tripod",
        "instances": {"hand": 2, "keyboard": 1},
        "steps": [{"step_id": "stp_01", "t_start": 1.0, "t_end": t_end}],
        "deviations": [],
    }


@pytest.fixture
def split_dir() -> Iterator[Path]:
    root = SCRATCH_ROOT / uuid.uuid4().hex
    bench = root / "bench"
    (bench / "dev" / "videos").mkdir(parents=True)
    (bench / "dev" / "gt").mkdir(parents=True)
    (bench / "golden").mkdir(parents=True)
    shutil.copy2(BENCH / "gt.schema.json", bench / "gt.schema.json")
    shutil.copy2(BENCH / "golden" / "P-A.json", bench / "golden" / "P-A.json")

    clips = []
    for number in range(1, 16):
        clip_id = f"A{number}"
        video = bench / "dev" / "videos" / f"{clip_id}.bin"
        video.write_bytes(f"clip-{clip_id}".encode())
        (bench / "dev" / "gt" / f"{clip_id}.json").write_text(
            json.dumps(_gt(clip_id, 30.0)), encoding="utf-8"
        )
        clips.append(
            {
                "clip_id": clip_id,
                "procedure": "A",
                "sha256": _sha(video),
                "duration_s": 30.0,
                "storage_ref": f"videos/{clip_id}.bin",
                "gt_path": f"gt/{clip_id}.json",
            }
        )
    manifest = {"split": "dev", "clips": clips}
    (bench / "dev" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    try:
        yield bench
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _manifest(bench: Path) -> dict[str, object]:
    return json.loads((bench / "dev" / "manifest.json").read_text(encoding="utf-8"))


@pytest.mark.unit
def test_valid_split_passes(split_dir: Path) -> None:
    clips, ground_truths, errors = validate_split("dev", split_dir)

    assert (clips, ground_truths, errors) == (15, 15, [])


@pytest.mark.unit
def test_missing_clip_is_reported(split_dir: Path) -> None:
    (split_dir / "dev" / "videos" / "A3.bin").unlink()

    _, _, errors = validate_split("dev", split_dir)

    assert any("clip not found" in error for error in errors)


@pytest.mark.unit
def test_sha_mismatch_is_reported(split_dir: Path) -> None:
    (split_dir / "dev" / "videos" / "A2.bin").write_bytes(b"tampered")

    _, _, errors = validate_split("dev", split_dir)

    assert any("does not match" in error for error in errors)


@pytest.mark.unit
def test_ground_truth_past_duration_is_reported(split_dir: Path) -> None:
    gt_path = split_dir / "dev" / "gt" / "A4.json"
    gt_path.write_text(json.dumps(_gt("A4", 30.0, t_end=45.0)), encoding="utf-8")

    _, _, errors = validate_split("dev", split_dir)

    assert any("past the clip duration" in error for error in errors)


@pytest.mark.unit
def test_duplicate_clip_id_is_reported(split_dir: Path) -> None:
    manifest = _manifest(split_dir)
    manifest["clips"][1]["clip_id"] = "A1"
    (split_dir / "dev" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    _, _, errors = validate_split("dev", split_dir)

    assert any("duplicate clip id" in error for error in errors)


@pytest.mark.unit
def test_clip_count_is_enforced(split_dir: Path) -> None:
    manifest = _manifest(split_dir)
    manifest["clips"].pop()
    (split_dir / "dev" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    _, _, errors = validate_split("dev", split_dir)

    assert any("expected 15 clips" in error for error in errors)


@pytest.mark.unit
def test_validate_split_cli(split_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["validate", "--split", "dev", "--bench-dir", str(split_dir)]) == 0
    assert "15 clips OK · 15 GT OK" in capsys.readouterr().out

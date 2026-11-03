"""Demo pack: freeze a run, verify checksums, detect tampering (T-7.1)."""

from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from pw.demo.pack import CaseSpec, build_case, verify_cases

REPO = Path(__file__).resolve().parents[2]
SCRATCH_ROOT = REPO / ".uv" / "tests-tmp"


@pytest.fixture
def run_dir() -> Iterator[Path]:
    root = SCRATCH_ROOT / uuid.uuid4().hex / "run"
    (root / "stages").mkdir(parents=True)
    (root / "evidence").mkdir()
    (root / "media").mkdir()
    (root / "report.json").write_text(json.dumps({"status": "done"}), encoding="utf-8")
    (root / "manifest.json").write_text(json.dumps({"mode": "demo"}), encoding="utf-8")
    (root / "stages" / "tracks.json").write_text(json.dumps({"tracks": []}), encoding="utf-8")
    (root / "evidence" / "evd_001.png").write_bytes(b"png")
    (root / "media" / "analysis.mp4").write_bytes(b"mp4")
    try:
        yield root
    finally:
        shutil.rmtree(root.parent, ignore_errors=True)


@pytest.mark.unit
def test_build_and_verify_case(run_dir: Path) -> None:
    cases = run_dir.parent / "cases"

    build_case(CaseSpec("A1", run_dir, "Clean keyboard", "Compliant"), cases)
    count, errors = verify_cases(cases)

    assert (count, errors) == (1, [])
    assert (cases / "A1" / "case.json").is_file()
    assert (cases / "A1" / "evidence" / "evd_001.png").read_bytes() == b"png"


@pytest.mark.unit
def test_tampered_artifact_is_detected(run_dir: Path) -> None:
    cases = run_dir.parent / "cases"
    build_case(CaseSpec("A1", run_dir, "Clean keyboard", "Compliant"), cases)
    (cases / "A1" / "evidence" / "evd_001.png").write_bytes(b"tampered")

    _, errors = verify_cases(cases)

    assert any("checksum mismatch" in error for error in errors)


@pytest.mark.unit
def test_unlisted_file_is_detected(run_dir: Path) -> None:
    cases = run_dir.parent / "cases"
    build_case(CaseSpec("A1", run_dir, "Clean keyboard", "Compliant"), cases)
    (cases / "A1" / "extra.txt").write_text("surprise", encoding="utf-8")

    _, errors = verify_cases(cases)

    assert any("unlisted file" in error for error in errors)

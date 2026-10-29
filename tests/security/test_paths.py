"""Traversal-safe artifact resolution with a directory allowlist."""

from __future__ import annotations

from pathlib import Path

import pytest

from pw.security.paths import PathNotAllowed, resolve_artifact


def test_allowed_artifacts_resolve(run_dir: Path) -> None:
    assert (
        resolve_artifact(run_dir, "evidence/evd_001.png")
        == (run_dir / "evidence" / "evd_001.png").resolve()
    )
    assert resolve_artifact(run_dir, "media/analysis.mp4").name == "analysis.mp4"
    assert resolve_artifact(run_dir, "illustrations/ill_001.png").name == "ill_001.png"
    assert resolve_artifact(run_dir, "report.json").name == "report.json"
    assert resolve_artifact(run_dir, "manifest.json").name == "manifest.json"


def test_parent_traversal_is_rejected(run_dir: Path) -> None:
    with pytest.raises(PathNotAllowed):
        resolve_artifact(run_dir, "../secret.txt")
    with pytest.raises(PathNotAllowed):
        resolve_artifact(run_dir, "evidence/../../secret.txt")


def test_encoded_traversal_is_rejected(run_dir: Path) -> None:
    with pytest.raises(PathNotAllowed):
        resolve_artifact(run_dir, "..%2fsecret.txt")
    with pytest.raises(PathNotAllowed):
        resolve_artifact(run_dir, "%2e%2e%2fsecret.txt")
    with pytest.raises(PathNotAllowed):
        resolve_artifact(run_dir, "evidence/%2e%2e/%2e%2e/secret.txt")


def test_backslash_traversal_is_rejected(run_dir: Path) -> None:
    with pytest.raises(PathNotAllowed):
        resolve_artifact(run_dir, "..\\secret.txt")
    with pytest.raises(PathNotAllowed):
        resolve_artifact(run_dir, "evidence\\..\\..\\secret.txt")


def test_absolute_and_drive_paths_are_rejected(run_dir: Path) -> None:
    with pytest.raises(PathNotAllowed):
        resolve_artifact(run_dir, "/etc/passwd")
    with pytest.raises(PathNotAllowed):
        resolve_artifact(run_dir, "C:/Windows/win.ini")


def test_input_uploads_are_never_served(run_dir: Path) -> None:
    with pytest.raises(PathNotAllowed):
        resolve_artifact(run_dir, "input/video.mp4")


def test_unknown_directories_and_root_files_are_rejected(run_dir: Path) -> None:
    with pytest.raises(PathNotAllowed):
        resolve_artifact(run_dir, "stages/ingest.json")
    with pytest.raises(PathNotAllowed):
        resolve_artifact(run_dir, "environment.env")


def test_null_bytes_are_rejected(run_dir: Path) -> None:
    with pytest.raises(PathNotAllowed):
        resolve_artifact(run_dir, "evidence/evd_001.png\x00.txt")

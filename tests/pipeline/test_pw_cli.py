"""`pw` entry point: run, overlay and verify-evidence delegation."""

from __future__ import annotations

from pathlib import Path

import pytest

import pw.cli as cli


def test_run_command_returns_zero_and_prints_the_run(
    tiny_video: Path, tiny_sop: Path, runs_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = cli.main(
        [
            "run",
            "--mode",
            "fake",
            "--video",
            str(tiny_video),
            "--sop",
            str(tiny_sop),
            "--runs-dir",
            str(runs_dir),
        ]
    )
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "run_" in output
    assert len(list(runs_dir.iterdir())) == 1


def test_run_with_missing_video_exits_two(tiny_sop: Path, runs_dir: Path) -> None:
    exit_code = cli.main(
        [
            "run",
            "--mode",
            "fake",
            "--video",
            str(runs_dir / "missing.mp4"),
            "--sop",
            str(tiny_sop),
            "--runs-dir",
            str(runs_dir),
        ]
    )
    assert exit_code == 2


def test_run_with_unwired_mode_exits_two(tiny_video: Path, tiny_sop: Path, runs_dir: Path) -> None:
    exit_code = cli.main(
        [
            "run",
            "--mode",
            "replay",
            "--video",
            str(tiny_video),
            "--sop",
            str(tiny_sop),
            "--runs-dir",
            str(runs_dir),
        ]
    )
    assert exit_code == 2


def test_overlay_delegates_with_remaining_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[list[str]] = []

    def fake_overlay(argv: list[str]) -> int:
        captured.append(argv)
        return 7

    monkeypatch.setattr(cli, "overlay_main", fake_overlay)
    assert cli.main(["overlay", "--video", "a.mp4", "--out", "b.mp4"]) == 7
    assert captured == [["--video", "a.mp4", "--out", "b.mp4"]]


def test_verify_evidence_delegates_with_remaining_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[list[str]] = []

    def fake_verify(argv: list[str]) -> int:
        captured.append(argv)
        return 5

    monkeypatch.setattr(cli, "verify_main", fake_verify)
    assert cli.main(["verify-evidence", "report.json", "--video", "a.mp4"]) == 5
    assert captured == [["report.json", "--video", "a.mp4"]]

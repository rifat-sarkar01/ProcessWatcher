"""`python -m pw.ingest` CLI tests: the T-2.1 smoke contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from pw.ingest.__main__ import main


@pytest.mark.unit
def test_cli_prints_fps_and_a_consistent_frame_count(
    media: dict[str, Path], scratch: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main([str(media["cfr"]), "--out", str(scratch / "cli")])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "fps=15" in output
    assert "size=320x240" in output

    values = dict(
        line.split("=", 1)
        for line in output.splitlines()
        if "=" in line and not line.startswith("source=")
    )
    frame_count = int(values["frame_count"])
    duration = float(values["duration_s"])
    assert abs(frame_count - duration * 15) <= 1.5


@pytest.mark.unit
def test_cli_reports_a_missing_file_with_exit_code_two(
    scratch: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main([str(scratch / "missing.mp4")])

    assert exit_code == 2
    assert "ERROR" in capsys.readouterr().err


@pytest.mark.unit
def test_cli_reports_a_corrupt_file_with_exit_code_one(
    media: dict[str, Path], scratch: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main([str(media["corrupt"]), "--out", str(scratch / "cli")])

    assert exit_code == 1
    assert "ERROR" in capsys.readouterr().err

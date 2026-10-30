"""Pipeline robustness: degraded capture must finish instead of crashing."""

from __future__ import annotations

from pathlib import Path

import pytest

from pw.pipeline.orchestrator import run_pipeline

SOP = Path(__file__).resolve().parents[1] / "fixtures" / "tiny_sop.md"


@pytest.mark.unit
@pytest.mark.parametrize("name", ["shaky", "dark", "vfr"])
def test_degraded_clip_completes_all_twelve_stages(
    name: str, clips: dict[str, Path], scratch: Path
) -> None:
    result = run_pipeline(
        video=clips[name],
        sop=SOP,
        mode="fake",
        runs_dir=scratch / "runs",
    )

    assert len(result.stages) == 12
    assert result.cached == 0
    assert all(stage.artifact.is_file() for stage in result.stages)
    assert (result.run_dir / "report.json").is_file()

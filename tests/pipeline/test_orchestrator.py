"""Fake walking skeleton: 12 stub stages, content-hash cache and run store."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from pw.pipeline.orchestrator import PipelineError, run_pipeline
from pw.pipeline.runstore import list_runs, new_run_id
from pw.pipeline.stages import STAGE_ORDER

RUN_ID_RE = re.compile(r"^run_[0-9A-HJKMNP-TV-Z]{26}$")
STAGE_FILES = {
    "ingest.json",
    "step_graph.json",
    "tracks.json",
    "timeline.json",
    "identities.json",
    "likelihoods.json",
    "alignment.json",
    "deviations.json",
    "verify.json",
    "evidence.json",
    "illustrations.json",
    "report.json",
}


def test_run_id_has_the_contract_format_and_is_unique() -> None:
    ids = {new_run_id() for _ in range(100)}
    assert len(ids) == 100
    assert all(RUN_ID_RE.match(value) for value in ids)


def test_stage_dag_is_topologically_ordered() -> None:
    from pw.pipeline.stages import FAKE_STAGES

    positions = {name: index for index, name in enumerate(STAGE_ORDER)}
    assert len(STAGE_ORDER) == 12
    for stage in FAKE_STAGES:
        for dependency in stage.depends:
            assert positions[dependency] < positions[stage.name]


def test_fake_run_writes_twelve_stage_artifacts(
    tiny_video: Path, tiny_sop: Path, runs_dir: Path
) -> None:
    result = run_pipeline(video=tiny_video, sop=tiny_sop, mode="fake", runs_dir=runs_dir)
    assert RUN_ID_RE.match(result.run_id)
    assert len(result.stages) == 12
    assert result.cached == 0

    stage_files = {path.name for path in (result.run_dir / "stages").glob("*.json")}
    assert stage_files == STAGE_FILES
    for name in ("input", "stages", "media", "evidence", "illustrations"):
        assert (result.run_dir / name).is_dir()
    assert (result.run_dir / "report.json").is_file()

    ingest = json.loads((result.run_dir / "stages" / "ingest.json").read_text("utf-8"))
    assert ingest["run_id"] == result.run_id
    assert ingest["mode"] == "fake"
    assert ingest["stub"] is True


def test_rerun_is_a_noop_via_the_stage_cache(
    tiny_video: Path, tiny_sop: Path, runs_dir: Path
) -> None:
    first = run_pipeline(video=tiny_video, sop=tiny_sop, mode="fake", runs_dir=runs_dir)
    before = {path.name: path.read_bytes() for path in (first.run_dir / "stages").glob("*.json")}
    second = run_pipeline(
        video=tiny_video, sop=tiny_sop, mode="fake", runs_dir=runs_dir, run_id=first.run_id
    )
    assert second.run_id == first.run_id
    assert second.cached == 12
    assert all(outcome.cached for outcome in second.stages)
    after = {path.name: path.read_bytes() for path in (second.run_dir / "stages").glob("*.json")}
    assert after == before


def test_missing_video_is_a_typed_usage_error(tiny_sop: Path, runs_dir: Path) -> None:
    missing = runs_dir / "nope.mp4"
    with pytest.raises(PipelineError) as info:
        run_pipeline(video=missing, sop=tiny_sop, mode="fake", runs_dir=runs_dir)
    assert info.value.exit_code == 2


def test_missing_sop_is_a_typed_usage_error(tiny_video: Path, runs_dir: Path) -> None:
    with pytest.raises(PipelineError) as info:
        run_pipeline(video=tiny_video, sop=runs_dir / "nope.md", mode="fake", runs_dir=runs_dir)
    assert info.value.exit_code == 2


def test_only_fake_mode_is_wired(tiny_video: Path, tiny_sop: Path, runs_dir: Path) -> None:
    with pytest.raises(PipelineError) as info:
        run_pipeline(video=tiny_video, sop=tiny_sop, mode="live", runs_dir=runs_dir)
    assert info.value.exit_code == 2
    assert "fake" in str(info.value)


def test_run_store_lists_completed_runs(tiny_video: Path, tiny_sop: Path, runs_dir: Path) -> None:
    result = run_pipeline(video=tiny_video, sop=tiny_sop, mode="fake", runs_dir=runs_dir)
    summaries = list_runs(runs_dir)
    assert [summary.run_id for summary in summaries] == [result.run_id]
    assert summaries[0].status == "done"
    assert summaries[0].cost_usd == 0.0
    assert summaries[0].created_at.endswith("Z")

"""T-3.9: real stage DAG — resume, spend cap, isolated failures, manifest."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from pw.clients.errors import SpendCapExceeded
from pw.core.settings import Settings
from pw.data.validate import validate_payload
from pw.pipeline.handlers import StageRun, StageServices
from pw.pipeline.orchestrator import PipelineError, run_pipeline

SCRATCH_ROOT = Path(__file__).resolve().parents[2] / ".uv" / "tests-tmp"
FPS = 15.0
FRAMES = 30
STEP_IDS = ("stp_01", "stp_02", "stp_03")


def _step(idx: int, text: str) -> dict[str, Any]:
    return {
        "id": f"stp_{idx:02d}",
        "idx": idx,
        "text": text,
        "action": text,
        "tools": ["cable"] if idx == 2 else [],
        "parts": ["power cable"],
        "ordering": "strict",
        "group_id": None,
        "critical": idx == 1,
        "visual_check": None,
    }


GRAPH: dict[str, Any] = {
    "schema_version": "1.0.0",
    "sop_id": "sop_00000000",
    "title": "Test procedure",
    "source": {"kind": "md", "sha256": "a" * 64},
    "steps": [
        _step(1, "Power the unit down."),
        _step(2, "Unplug the power cable."),
        _step(3, "Remove the cover."),
    ],
    "vocabulary": {"sam_concepts": ["hand", "power cable", "cable"]},
    "warnings": [],
}


def _ingest(run: StageRun) -> dict[str, Any]:
    duration = round(FRAMES / FPS, 4)
    video = run.video.resolve()
    return {
        "schema_version": "1.0.0",
        "run_id": run.run_id,
        "stage": "ingest",
        "mode": run.mode,
        "source": {"name": video.name, "sha256": "b" * 64, "bytes": video.stat().st_size},
        "analysis": {"path": str(video), "fps": FPS, "frame_count": FRAMES},
        "video": {
            "sha256": "c" * 64,
            "duration_s": duration,
            "analysis_fps": FPS,
            "width": 320,
            "height": 240,
            "frame_count": FRAMES,
        },
        "degraded": False,
    }


def _perceive(run: StageRun) -> dict[str, Any]:
    times = [round(index / FPS, 4) for index in range(FRAMES)]
    hand = {
        "id": "trk_001",
        "concept": "hand",
        "first_t": times[0],
        "last_t": times[-1],
        "frames": [
            {"frame": index, "t": time, "box": [0.4, 0.4, 0.6, 0.6], "score": 0.9}
            for index, time in enumerate(times)
        ],
        "source_chunks": ["chk_01"],
    }
    cable = {
        "id": "trk_002",
        "concept": "power cable",
        "first_t": times[0],
        "last_t": times[-1],
        "frames": [
            {"frame": index, "t": time, "box": [0.45, 0.45, 0.55, 0.55], "score": 0.8}
            for index, time in enumerate(times)
        ],
        "source_chunks": ["chk_01"],
    }
    ingest = run.artifacts["ingest"]
    return {
        "schema_version": "1.0.0",
        "run_id": run.run_id,
        "video": dict(ingest["video"]),
        "tracks": [hand, cable],
    }


def _identify(run: StageRun) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "run_id": run.run_id,
        "identities": [
            {
                "track_id": "trk_002",
                "label": "power cable",
                "confidence": 0.9,
                "votes": [{"label": "power cable", "count": 3}],
                "crop_frames": [5, 10, 15],
            }
        ],
    }


def _score(run: StageRun) -> dict[str, Any]:
    timeline = run.artifacts["timeline"]
    segments = [
        {
            "segment_id": str(segment["id"]),
            "step_probs": {"stp_01": 0.7, "stp_02": 0.15, "stp_03": 0.15, "none": 0.0},
            "observed_tools": [],
            "rationale_short": "fake",
            "flags": [],
        }
        for segment in timeline["segments"]
    ]
    return {
        "schema_version": "1.0.0",
        "run_id": run.run_id,
        "segments": segments,
    }


def _evidence(run: StageRun) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "run_id": run.run_id,
        "available": False,
        "evidence": [],
        "reasons": {},
    }


def handlers(**overrides: Any) -> dict[str, Any]:
    base = {
        "ingest": _ingest,
        "sop_compile": lambda run: dict(GRAPH),
        "perceive": _perceive,
        "identify": _identify,
        "score": _score,
        "evidence": _evidence,
    }
    base.update(overrides)
    return base


def _settings(runs_dir: Path) -> Settings:
    return Settings(
        mode="replay",
        meta_api_key="",
        access_code="",
        spend_cap_usd=1.0,
        runs_dir=runs_dir,
    )


def _run(
    tiny_video: Path,
    tiny_sop: Path,
    runs_dir: Path,
    *,
    step_graph: dict[str, Any] | None = None,
    **overrides: Any,
) -> Any:
    return run_pipeline(
        video=tiny_video,
        sop=tiny_sop,
        mode="replay",
        runs_dir=runs_dir,
        settings=_settings(runs_dir),
        services=StageServices(handlers=handlers(**overrides)),
        step_graph=step_graph,
    )


@pytest.fixture
def scratch_runs() -> Iterator[Path]:
    import shutil
    import uuid

    path = SCRATCH_ROOT / f"pipeline-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.mark.unit
def test_real_run_resumes_from_the_stage_cache(
    tiny_video: Path, tiny_sop: Path, scratch_runs: Path
) -> None:
    first = _run(tiny_video, tiny_sop, scratch_runs)
    before = {path.name: path.read_bytes() for path in (first.run_dir / "stages").glob("*.json")}

    second = run_pipeline(
        video=tiny_video,
        sop=tiny_sop,
        mode="replay",
        runs_dir=scratch_runs,
        run_id=first.run_id,
        settings=_settings(scratch_runs),
        services=StageServices(handlers=handlers()),
    )

    assert second.run_id == first.run_id
    assert second.cached == 12
    assert first.degraded == ()
    after = {path.name: path.read_bytes() for path in (second.run_dir / "stages").glob("*.json")}
    assert after == before


@pytest.mark.unit
def test_spend_cap_aborts_with_a_partial_report(
    tiny_video: Path, tiny_sop: Path, scratch_runs: Path
) -> None:
    def capped(run: StageRun) -> dict[str, Any]:
        raise SpendCapExceeded(0.9, 0.5, 1.0)

    result = _run(tiny_video, tiny_sop, scratch_runs, verify=capped)

    assert result.cap_reached is True
    assert "verify" in result.degraded
    report = json.loads((result.run_dir / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "partial"
    assert "verify" in report["degraded_stages"]
    assert validate_payload("report", report) == []

    manifest = json.loads((result.run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["ledger"]["cap_reached"] is True
    assert validate_payload("manifest", manifest) == []


@pytest.mark.unit
def test_a_failed_stage_is_isolated_and_bannered(
    tiny_video: Path, tiny_sop: Path, scratch_runs: Path
) -> None:
    def broken(run: StageRun) -> dict[str, Any]:
        raise RuntimeError("identity service down")

    result = _run(tiny_video, tiny_sop, scratch_runs, identify=broken)

    assert result.degraded == ("identify",)
    assert result.cap_reached is False
    report = json.loads((result.run_dir / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "partial"
    assert report["degraded_stages"] == ["identify"]
    assert validate_payload("report", report) == []
    identities = json.loads(
        (result.run_dir / "stages" / "identities.json").read_text(encoding="utf-8")
    )
    assert identities["identities"] == []


@pytest.mark.unit
def test_progress_events_cover_every_stage(
    tiny_video: Path, tiny_sop: Path, scratch_runs: Path
) -> None:
    events: list[dict[str, Any]] = []
    run_pipeline(
        video=tiny_video,
        sop=tiny_sop,
        mode="replay",
        runs_dir=scratch_runs,
        settings=_settings(scratch_runs),
        services=StageServices(handlers=handlers()),
        on_event=events.append,
    )

    stages = {event["stage"] for event in events}
    assert len(stages) == 12
    assert {event["status"] for event in events} >= {"running", "done"}


@pytest.mark.unit
def test_manifest_records_inputs_models_and_costs(
    tiny_video: Path, tiny_sop: Path, scratch_runs: Path
) -> None:
    result = _run(tiny_video, tiny_sop, scratch_runs)
    manifest = json.loads((result.run_dir / "manifest.json").read_text(encoding="utf-8"))

    assert validate_payload("manifest", manifest) == []
    assert manifest["run_id"] == result.run_id
    assert {model["name"] for model in manifest["models"]} == {
        "muse-wonder-1.0",
        "sam-3.1",
    }
    assert len(manifest["stages"]) == 12
    assert manifest["ledger"]["spend_cap_usd"] == 1.0
    assert manifest["inputs"]["video_sha256"] != manifest["inputs"]["sop_sha256"]


@pytest.mark.unit
def test_edited_step_graph_replaces_the_compiled_one(
    tiny_video: Path, tiny_sop: Path, scratch_runs: Path
) -> None:
    edited = {**GRAPH, "title": "Edited procedure"}
    result = _run(tiny_video, tiny_sop, scratch_runs, step_graph=edited)

    stored = json.loads((result.run_dir / "stages" / "step_graph.json").read_text(encoding="utf-8"))
    assert stored == edited
    manifest = json.loads((result.run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["inputs"]["edited_by_user"] is True
    assert (
        manifest["inputs"]["step_graph_sha256"]
        == hashlib.sha256(json.dumps(edited, sort_keys=True).encode("utf-8")).hexdigest()
    )
    assert result.degraded == ()


@pytest.mark.unit
def test_edited_and_compiled_graphs_do_not_share_a_cache_key(
    tiny_video: Path, tiny_sop: Path, scratch_runs: Path
) -> None:
    edited = {**GRAPH, "title": "Edited procedure"}
    first = _run(tiny_video, tiny_sop, scratch_runs, step_graph=edited)

    second = run_pipeline(
        video=tiny_video,
        sop=tiny_sop,
        mode="replay",
        runs_dir=scratch_runs,
        run_id=first.run_id,
        settings=_settings(scratch_runs),
        services=StageServices(handlers=handlers()),
    )

    compile_stage = next(stage for stage in second.stages if stage.name == "sop_compile")
    assert compile_stage.cached is False
    stored = json.loads((second.run_dir / "stages" / "step_graph.json").read_text(encoding="utf-8"))
    assert stored == GRAPH


@pytest.mark.unit
def test_an_invalid_step_graph_is_rejected(
    tiny_video: Path, tiny_sop: Path, scratch_runs: Path
) -> None:
    with pytest.raises(PipelineError):
        _run(
            tiny_video,
            tiny_sop,
            scratch_runs,
            step_graph={"schema_version": "1.0.0"},
        )

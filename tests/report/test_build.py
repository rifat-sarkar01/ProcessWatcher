"""Report assembly: joins, ordering, summary counts and contract validation."""

from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from PIL import Image

from pw.align.aligner import Alignment, AlignParams, Interval
from pw.align.deviations import Deviation
from pw.align.domain_guard import DomainDecision
from pw.data.validate import validate_artifact_file, validate_payload
from pw.evidence.labeling import KindError
from pw.evidence.provenance import write_evidence
from pw.evidence.selector import EvidenceFrame, EvidenceSelection
from pw.report.build import (
    DEFAULT_ILLUSTRATION_REASON,
    NOT_RECOGNIZED_NOTICE,
    ReportError,
    VideoMeta,
    build_report,
    format_mmss,
    write_report,
)

ROOT = Path(__file__).resolve().parents[2]
SCRATCH_ROOT = ROOT / ".uv" / "tests-tmp"
RUN_ID = "run_01J9ZQ8M3K4V7B2C5D6E8F0GHJ"
CREATED_AT = "2026-10-28T09:15:47Z"
SOURCE_SHA = "c4a1f7e2b9d053816a2e4c6f8b0d1e3a5c7f9b2d4e6a8c0f1b3d5e7a9c2f4b6d"
ILLUSTRATION_SHA = "d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4"


@pytest.fixture(scope="module")
def sop() -> dict[str, object]:
    return json.loads((ROOT / "contracts" / "examples" / "sop.example.json").read_text("utf-8"))


@pytest.fixture
def run_dir() -> Iterator[Path]:
    path = SCRATCH_ROOT / f"report-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _alignment() -> Alignment:
    intervals = (
        Interval("int_01", "stp_01", 3.0, 12.4, ("seg_001",), 0.9, 2.5),
        Interval("int_02", "stp_02", 13.1, 28.6, ("seg_002",), 0.8, 2.0),
        Interval("int_03", "stp_03", 41.0, 55.2, ("seg_003",), 0.75, 1.8),
        Interval("int_04", "stp_04", 72.4, 81.0, ("seg_004",), 0.7, 1.5),
        Interval("int_05", "stp_06", 92.0, 110.5, ("seg_005",), 0.85, 2.1),
    )
    return Alignment(
        path=tuple((interval.segment_ids[0], interval.step_id) for interval in intervals),
        intervals=intervals,
        total_cost=4.2,
        per_segment_cost=0.84,
        coverage=0.83,
        params=AlignParams(),
    )


def _deviation(
    deviation_id: str,
    deviation_type: str,
    step_id: str,
    t_start: float,
    t_end: float,
    *,
    status: str = "flagged",
    severity: str = "high",
    expected: tuple[str, ...] = (),
    observed: tuple[str, ...] = (),
) -> Deviation:
    return Deviation(
        id=deviation_id,
        type=deviation_type,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        step_id=step_id,
        t_start=t_start,
        t_end=t_end,
        track_ids=("trk_001",),
        confidence=0.82,
        margin=2.4,
        expected_tools=expected,
        observed_tools=observed,
    )


def _evidence(run_dir: Path, deviation_id: str, frame_index: int, t: float) -> list[dict]:
    frame = EvidenceFrame(
        deviation_id=deviation_id,
        frame_index=frame_index,
        t=t,
        track_ids=("trk_001",),
        score=0.8,
        image=Image.new("RGB", (64, 48), (20, 20, 20)),
    )
    selection = EvidenceSelection(deviation_id, (frame,), True, None)
    return [
        dict(item)
        for item in write_evidence([selection], run_dir=run_dir, source_sha256=SOURCE_SHA)
    ]


def _illustration() -> dict[str, object]:
    return {
        "id": "ill_001",
        "kind": "illustration",
        "path": "illustrations/ill_001.png",
        "sha256": ILLUSTRATION_SHA,
        "watermark": True,
        "qa": {"verdict": "pass", "attempts": 1},
    }


def _build(run_dir: Path, **overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "run_id": RUN_ID,
        "created_at": CREATED_AT,
        "sop": json.loads(
            (ROOT / "contracts" / "examples" / "sop.example.json").read_text("utf-8")
        ),
        "video": VideoMeta(SOURCE_SHA, 118.0, 1280, 720),
        "alignment": _alignment(),
        "deviations": (
            _deviation(
                "dev_001",
                "missed",
                "stp_05",
                61.0,
                71.5,
                expected=("torque wrench",),
            ),
            _deviation(
                "dev_002",
                "wrong_tool",
                "stp_04",
                72.4,
                81.0,
                expected=("torque wrench",),
                observed=("adjustable wrench",),
            ),
        ),
        "evidence": [
            *_evidence(run_dir, "dev_001", 1065, 71.0),
            *_evidence(run_dir, "dev_002", 1113, 74.2),
        ],
        "illustrations": {"dev_002": _illustration()},
    }
    defaults.update(overrides)
    return build_report(**defaults)  # type: ignore[arg-type]


def test_full_report_matches_the_contract(run_dir: Path) -> None:
    report = _build(run_dir)
    assert validate_payload("report", report) == []
    assert report["status"] == "done"
    assert report["degraded_stages"] == []
    assert [item["id"] for item in report["deviations"]] == ["dev_001", "dev_002"]
    assert report["summary"] == {
        "flagged": 2,
        "needs_review": 0,
        "dropped": 0,
        "by_type": {"missed": 1, "out_of_order": 0, "wrong_tool": 1},
    }
    assert report["deviations"][1]["illustration"]["watermark"] is True
    assert report["deviations"][0]["illustration"] is None
    assert report["deviations"][0]["illustration_unavailable_reason"] == (
        DEFAULT_ILLUSTRATION_REASON
    )


def test_not_recognized_report_is_valid_and_carries_the_message(run_dir: Path) -> None:
    decision = DomainDecision(
        recognized=False,
        status="not_recognized",
        message="This video does not look like the SOP.",
        deviations=(),
    )
    report = _build(run_dir, domain=decision)
    assert report["status"] == "not_recognized"
    assert report["deviations"] == []
    assert report["notice"] == "This video does not look like the SOP."
    assert report["summary"]["flagged"] == 0
    assert validate_payload("report", report) == []


def test_not_recognized_uses_a_default_notice(run_dir: Path) -> None:
    decision = DomainDecision(
        recognized=False, status="not_recognized", message=None, deviations=()
    )
    report = _build(run_dir, domain=decision)
    assert report["notice"] == NOT_RECOGNIZED_NOTICE


def test_missing_evidence_marks_the_deviation_unavailable(run_dir: Path) -> None:
    report = _build(run_dir, evidence=[], illustrations={})
    for deviation in report["deviations"]:
        assert deviation["evidence"] == []
        assert deviation["evidence_unavailable"] is True
        assert deviation["illustration"] is None
        assert deviation["illustration_unavailable_reason"]
    assert validate_payload("report", report) == []


def test_deviations_and_evidence_are_ordered_deterministically(run_dir: Path) -> None:
    evidence = [
        *_evidence(run_dir, "dev_001", 1065, 71.0),
        *_evidence(run_dir, "dev_001", 900, 60.5),
        *_evidence(run_dir, "dev_002", 1113, 74.2),
    ]
    shuffled = (
        _deviation("dev_002", "wrong_tool", "stp_04", 72.4, 81.0),
        _deviation("dev_001", "missed", "stp_05", 61.0, 71.5),
    )
    first = _build(run_dir, deviations=shuffled, evidence=evidence)
    second = _build(run_dir, deviations=tuple(reversed(shuffled)), evidence=evidence)
    assert first["deviations"] == second["deviations"]
    assert [item["id"] for item in first["deviations"]] == ["dev_001", "dev_002"]
    evidence_ids = [item["evidence_id"] for item in first["deviations"][0]["evidence"]]
    assert evidence_ids == sorted(evidence_ids)
    observed = first["lanes"]["observed"]
    assert [item["t_start"] for item in observed] == sorted(item["t_start"] for item in observed)


def test_template_explanations_are_short_and_use_mmss(run_dir: Path) -> None:
    report = _build(run_dir, evidence=[])
    missed = report["deviations"][0]["explanation"]
    wrong_tool = report["deviations"][1]["explanation"]
    assert format_mmss(72.4) == "01:12"
    assert "01:01 to 01:11" in missed
    assert "torque wrench" in wrong_tool and "adjustable wrench" in wrong_tool
    for text in (missed, wrong_tool):
        assert len(text.split()) <= 40
        assert text.count(".") <= 2


def test_supplied_explanations_replace_the_template(run_dir: Path) -> None:
    report = _build(run_dir, explanations={"dev_001": "Bolt 2 was never torqued at 01:01."})
    assert report["deviations"][0]["explanation"] == "Bolt 2 was never torqued at 01:01."


def test_overlong_explanation_is_rejected_by_the_contract(run_dir: Path) -> None:
    with pytest.raises(ReportError):
        _build(run_dir, explanations={"dev_001": "word " * 41})


def test_illustration_in_evidence_is_rejected(run_dir: Path) -> None:
    items = _evidence(run_dir, "dev_001", 1065, 71.0)
    items[0]["kind"] = "illustration"
    with pytest.raises(KindError):
        _build(run_dir, evidence=items)


def test_evidence_in_the_illustration_slot_is_rejected(run_dir: Path) -> None:
    illustration = _illustration()
    illustration["kind"] = "evidence"
    with pytest.raises(KindError):
        _build(run_dir, illustrations={"dev_002": illustration})


def test_degraded_run_reports_partial(run_dir: Path) -> None:
    report = _build(run_dir, degraded_stages=["scoring"])
    assert report["status"] == "partial"
    assert report["degraded_stages"] == ["scoring"]
    assert validate_payload("report", report) == []


def test_dropped_candidates_are_counted(run_dir: Path) -> None:
    report = _build(run_dir, dropped=3)
    assert report["summary"]["dropped"] == 3
    assert validate_payload("report", report) == []


def test_write_report_round_trips_through_the_validator(run_dir: Path) -> None:
    report = _build(run_dir)
    path = write_report(report, run_dir)
    kind, errors = validate_artifact_file(path)
    assert kind == "report"
    assert errors == []
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["run_id"] == RUN_ID
    assert on_disk["manifest_ref"] == "manifest.json"


def test_write_report_also_writes_a_valid_manifest(run_dir: Path) -> None:
    manifest = json.loads(
        (ROOT / "contracts" / "examples" / "manifest.example.json").read_text("utf-8")
    )
    path = write_report(_build(run_dir), run_dir, manifest=manifest)
    assert (run_dir / "manifest.json").is_file()
    assert validate_artifact_file(path)[1] == []


def test_write_report_rejects_an_invalid_manifest(run_dir: Path) -> None:
    manifest = json.loads(
        (ROOT / "contracts" / "examples" / "manifest.example.json").read_text("utf-8")
    )
    manifest["mode"] = "streaming"
    with pytest.raises(ReportError):
        write_report(_build(run_dir), run_dir, manifest=manifest)


def test_video_metadata_is_hashes_and_geometry_only(run_dir: Path) -> None:
    report = _build(run_dir)
    assert set(report["video"]) == {"sha256", "duration_s", "width", "height"}

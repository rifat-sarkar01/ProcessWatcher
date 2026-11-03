"""T-4.4: the illustrate stage generates, QAs and watermarks diagrams."""

from __future__ import annotations

import io
import json
import shutil
import uuid
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from pw.clients.errors import SpendCapExceeded
from pw.core.settings import Settings
from pw.pipeline.handlers import StageRun, StageServices, handle_illustrate

SCRATCH_ROOT = Path(__file__).resolve().parents[2] / ".uv" / "tests-tmp"
DEVIATION_ID = "dev_001"
STEP_ID = "stp_01"


def _png(size: tuple[int, int] = (64, 64)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format="PNG")
    return buffer.getvalue()


def _qa_body(
    *,
    verdict: str = "pass",
    matches_step: bool = True,
    correct_tool_shown: bool = True,
    text_legible: bool = True,
    people_visible: bool = False,
    reason: str = "",
) -> dict[str, Any]:
    payload = {
        "matches_step": matches_step,
        "correct_tool_shown": correct_tool_shown,
        "text_legible": text_legible,
        "hallucinated_labels": [],
        "people_visible": people_visible,
        "verdict": verdict,
        "reason": reason,
    }
    return {"output": [{"content": [{"type": "output_text", "text": json.dumps(payload)}]}]}


def _deviation() -> dict[str, Any]:
    return {
        "id": DEVIATION_ID,
        "type": "missed",
        "status": "flagged",
        "severity": "high",
        "step_id": STEP_ID,
        "t_start": 1.0,
        "t_end": 2.0,
        "track_ids": ["trk_001"],
        "confidence": 0.9,
        "margin": 0.3,
        "relates_to_step_id": None,
        "expected_tools": ["screwdriver"],
        "observed_tools": [],
    }


def _graph() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "sop_id": "sop_00000000",
        "title": "Test",
        "source": {"kind": "md", "sha256": "a" * 64},
        "steps": [
            {
                "id": STEP_ID,
                "idx": 1,
                "text": "Remove the cover.",
                "action": "remove",
                "tools": ["screwdriver"],
                "parts": ["cover"],
                "ordering": "strict",
                "group_id": None,
                "critical": True,
                "visual_check": None,
            }
        ],
        "vocabulary": {"sam_concepts": ["hand", "screwdriver"]},
        "warnings": [],
    }


class Calls:
    def __init__(self, image: Callable[[], bytes] | None = None) -> None:
        self.image = image or _png
        self.references: list[bytes | None] = []

    def __call__(self, prompt: str, reference: bytes | None) -> bytes:
        self.references.append(reference)
        return self.image()


@pytest.fixture()
def run_dir() -> Iterator[Path]:
    root = SCRATCH_ROOT / f"illustrate-{uuid.uuid4().hex}"
    for name in ("stages", "evidence", "illustrations"):
        (root / name).mkdir(parents=True)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _stage_run(
    run_dir: Path,
    *,
    services: StageServices,
    disable: bool = False,
    with_reference: bool = True,
) -> StageRun:
    evidence: list[dict[str, Any]] = []
    if with_reference:
        reference = run_dir / "evidence" / "dev_001_f000001.png"
        reference.write_bytes(_png((120, 90)))
        evidence.append(
            {
                "evidence_id": "evd_001",
                "deviation_id": DEVIATION_ID,
                "kind": "evidence",
                "output_path": reference.relative_to(run_dir).as_posix(),
            }
        )
    settings = Settings(
        mode="replay",
        meta_api_key="",
        access_code="",
        spend_cap_usd=1.0,
        runs_dir=run_dir,
        disable_illustrations=disable,
    )
    return StageRun(
        name="illustrate",
        run_id="run_00000000000000000000000000",
        mode="replay",
        created_at="2026-11-02T00:00:00Z",
        run_dir=run_dir,
        stages_dir=run_dir / "stages",
        video=run_dir / "video.mp4",
        sop=run_dir / "sop.md",
        artifacts={
            "verify": {"deviations": [_deviation()]},
            "sop_compile": _graph(),
            "evidence": {"evidence": evidence},
        },
        services=services,
        settings=settings,
        frames=lambda _index: None,
    )


def test_a_passing_illustration_is_written_and_keyed_by_deviation(run_dir: Path) -> None:
    calls = Calls()
    quires: list[Mapping[str, Any]] = []

    def qa(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        quires.append(payload)
        return _qa_body()

    payload = handle_illustrate(
        _stage_run(run_dir, services=StageServices(illustrator=calls, qa=qa))
    )

    assert payload["disabled"] is False
    block = payload["illustrations"][DEVIATION_ID]
    assert set(block) == {"id", "kind", "path", "sha256", "watermark", "qa"}
    assert block["kind"] == "illustration"
    assert block["watermark"] is True
    assert block["qa"] == {"verdict": "pass", "attempts": 1}
    assert (run_dir / block["path"]).is_file()
    assert len(calls.references) == 1 and calls.references[0] is not None
    assert len(quires) == 1


def test_generation_failure_degrades_to_a_reason(run_dir: Path) -> None:
    def broken(_prompt: str, _reference: bytes | None) -> bytes:
        raise RuntimeError("image down")

    payload = handle_illustrate(
        _stage_run(
            run_dir,
            services=StageServices(illustrator=broken, qa=lambda _payload: _qa_body()),
        )
    )

    assert payload["illustrations"] == {}
    reason = payload["reasons"][DEVIATION_ID]
    assert reason.startswith("illustration_unavailable")
    assert len(reason) <= 200


def test_qa_failure_drops_the_illustration_after_regenerations(run_dir: Path) -> None:
    calls = Calls()

    payload = handle_illustrate(
        _stage_run(
            run_dir,
            services=StageServices(
                illustrator=calls,
                qa=lambda _payload: _qa_body(verdict="fail", matches_step=False, reason="wrong"),
            ),
        )
    )

    assert payload["illustrations"] == {}
    assert payload["reasons"][DEVIATION_ID].startswith("illustration_unavailable")
    assert len(calls.references) == 3


def test_the_disable_switch_makes_no_calls(run_dir: Path) -> None:
    calls = Calls()

    payload = handle_illustrate(
        _stage_run(
            run_dir,
            services=StageServices(illustrator=calls, qa=lambda _payload: _qa_body()),
            disable=True,
        )
    )

    assert payload["disabled"] is True
    assert payload["illustrations"] == {}
    assert calls.references == []


def test_without_a_model_caller_the_stage_is_a_no_op(run_dir: Path) -> None:
    payload = handle_illustrate(_stage_run(run_dir, services=StageServices()))

    assert payload["disabled"] is True
    assert payload["illustrations"] == {}


def test_a_spend_cap_during_generation_propagates(run_dir: Path) -> None:
    def capped(_prompt: str, _reference: bytes | None) -> bytes:
        raise SpendCapExceeded(0.9, 0.5, 1.0)

    with pytest.raises(SpendCapExceeded):
        handle_illustrate(
            _stage_run(
                run_dir,
                services=StageServices(illustrator=capped, qa=lambda _payload: _qa_body()),
            )
        )

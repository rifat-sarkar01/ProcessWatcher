"""Read-only demo pack routes (`04_TRD` §11): frozen cases, no model calls.

The gallery lists the three checked-in cases and serves the files each `case.json`
records, so `PW_MODE=demo` can run with the network switched off.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from pw.demo.pack import CASE_MANIFEST
from pw.security.errors import PathNotAllowed
from pw.security.paths import resolve_artifact

router = APIRouter(prefix="/demo", tags=["demo"])


def _cases_dir(request: Request) -> Path:
    return cast(Path, request.app.state.demo_cases_dir)


def _summary(case_dir: Path) -> dict[str, Any] | None:
    manifest_path = case_dir / CASE_MANIFEST
    if not manifest_path.is_file():
        return None
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    summary: dict[str, Any] = {
        "case_id": payload.get("case_id", case_dir.name),
        "title": payload.get("title", ""),
        "description": payload.get("description", ""),
        "source_run": payload.get("source_run", ""),
    }
    report_path = case_dir / "report.json"
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        deviations = report.get("deviations", [])
        summary["status"] = report.get("status")
        summary["deviation_count"] = len(deviations)
        summary["duration_s"] = report.get("video", {}).get("duration_s")
        summary["deviations"] = [
            {"type": item.get("type"), "step_id": item.get("step_id"), "status": item.get("status")}
            for item in deviations
        ]
    return summary


def _case_dir(request: Request, case_id: str) -> Path:
    if not case_id or "/" in case_id or "\\" in case_id or case_id in {".", ".."}:
        raise PathNotAllowed("invalid case id")
    return _cases_dir(request) / case_id


@router.get("/cases")
def list_cases(request: Request) -> dict[str, Any]:
    root = _cases_dir(request)
    cases = [
        summary
        for path in sorted(root.glob("*/" + CASE_MANIFEST))
        if (summary := _summary(path.parent)) is not None
    ]
    return {"cases": cases}


@router.get("/cases/{case_id}")
def get_case(request: Request, case_id: str) -> dict[str, Any]:
    """Full case: metadata plus the frozen `report.json` the review core renders."""
    case_dir = _case_dir(request, case_id)
    manifest_path = case_dir / CASE_MANIFEST
    report_path = case_dir / "report.json"
    if not manifest_path.is_file() or not report_path.is_file():
        raise PathNotAllowed("demo case not found")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return {
        "case_id": payload.get("case_id", case_id),
        "title": payload.get("title", ""),
        "description": payload.get("description", ""),
        "source_run": payload.get("source_run", ""),
        "duration_s": report.get("video", {}).get("duration_s"),
        "deviation_count": len(report.get("deviations", [])),
        "media": {"analysis": "media/analysis.mp4"},
        "report": report,
    }


@router.get("/cases/{case_id}/files/{path:path}")
def get_case_file(request: Request, case_id: str, path: str) -> FileResponse:
    return _serve(request, case_id, path)


@router.get("/cases/{case_id}/{path:path}")
def get_case_artifact(request: Request, case_id: str, path: str) -> FileResponse:
    """Mirror the run artifact layout (`media/analysis.mp4`, `evidence/*.png`)."""
    return _serve(request, case_id, path)


def _serve(request: Request, case_id: str, path: str) -> FileResponse:
    root = _case_dir(request, case_id)
    resolved = resolve_artifact(root, path)
    if not resolved.is_file():
        raise PathNotAllowed("demo file not found")
    return FileResponse(resolved)


__all__ = ["router"]

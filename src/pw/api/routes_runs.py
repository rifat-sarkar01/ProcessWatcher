"""Run routes: upload, background fake run, status, report and artifact serving.

All routes sit behind the access-code guard. Runs execute on the fake pipeline until
T-3.9 wires the real stages; the route contract does not change with that swap.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, cast

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from pw.api.errors import InvalidRequest, RunNotFound, RunNotReady
from pw.pipeline.orchestrator import run_pipeline
from pw.pipeline.runstore import (
    REPORT_NAME,
    RunPaths,
    RunStoreError,
    list_runs,
    new_run_id,
    open_run,
)
from pw.pipeline.stages import FAKE_STAGES
from pw.security.access import require_access_code
from pw.security.errors import FileTooLarge, PathNotAllowed, SecurityError
from pw.security.paths import resolve_artifact
from pw.security.ratelimit import RateLimiter
from pw.security.uploads import (
    UploadCaps,
    sanitise_filename,
    validate_sop_upload,
    validate_video_upload,
)

UPLOAD_BLOCK = 1024 * 1024


@dataclass(frozen=True, slots=True)
class ApiSettings:
    runs_dir: Path
    caps: UploadCaps
    limiter: RateLimiter


router = APIRouter(prefix="/runs", tags=["runs"], dependencies=[Depends(require_access_code)])


def _settings(request: Request) -> ApiSettings:
    return cast(ApiSettings, request.app.state.settings)


def _rate_limit(request: Request) -> None:
    settings = _settings(request)
    settings.limiter.check(request.client.host if request.client else "unknown")


def _open(request: Request, run_id: str) -> RunPaths:
    try:
        return open_run(_settings(request).runs_dir, run_id)
    except RunStoreError as exc:
        raise RunNotFound(str(exc)) from exc


def _status(paths: RunPaths) -> str:
    return "done" if (paths.root / REPORT_NAME).is_file() else "running"


def _created_at(paths: RunPaths) -> str:
    return datetime.fromtimestamp(paths.root.stat().st_mtime, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _save_upload(upload: UploadFile, target: Path, max_bytes: int) -> None:
    total = 0
    with target.open("wb") as out:
        while chunk := upload.file.read(UPLOAD_BLOCK):
            total += len(chunk)
            if total > max_bytes:
                raise FileTooLarge(f"file exceeds the {max_bytes // (1024 * 1024)} MB limit")
            out.write(chunk)


def _execute(run_id: str, video: Path, sop: Path, runs_dir: Path, scratch: Path) -> None:
    try:
        run_pipeline(video=video, sop=sop, mode="fake", runs_dir=runs_dir, run_id=run_id)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _store_sop(
    request_sop: UploadFile | None,
    sop_text: str | None,
    scratch: Path,
    caps: UploadCaps,
) -> Path:
    if sop_text is not None:
        if not sop_text.strip():
            raise InvalidRequest("the SOP is empty")
        target = scratch / "sop.md"
        target.write_text(sop_text, encoding="utf-8")
        validate_sop_upload(target, caps=caps)
        return target
    if request_sop is None:
        raise InvalidRequest("attach a SOP file or provide sop_text")
    target = scratch / sanitise_filename(request_sop.filename or "sop.md")
    _save_upload(request_sop, target, caps.max_bytes)
    validate_sop_upload(target, caps=caps)
    return target


@router.get("")
def get_runs(request: Request) -> list[dict[str, object]]:
    return [summary.to_artifact() for summary in list_runs(_settings(request).runs_dir)]


@router.post("", status_code=202, dependencies=[Depends(_rate_limit)])
def create_run(
    request: Request,
    background: BackgroundTasks,
    video: Annotated[UploadFile, File()],
    sop: Annotated[UploadFile | None, File()] = None,
    sop_text: Annotated[str | None, Form()] = None,
) -> JSONResponse:
    settings = _settings(request)
    run_id = new_run_id()
    scratch = settings.runs_dir / ".uploads" / run_id
    scratch.mkdir(parents=True, exist_ok=True)

    try:
        video_path = scratch / sanitise_filename(video.filename or "video.mp4")
        _save_upload(video, video_path, settings.caps.max_bytes)
        validate_video_upload(video_path, caps=settings.caps)
        sop_path = _store_sop(sop, sop_text, scratch, settings.caps)
    except SecurityError:
        # A rejected upload must not leave its part-written copy behind.
        shutil.rmtree(scratch, ignore_errors=True)
        raise

    background.add_task(_execute, run_id, video_path, sop_path, settings.runs_dir, scratch)
    return JSONResponse({"run_id": run_id, "status": "queued"}, status_code=202)


@router.get("/{run_id}")
def get_run(request: Request, run_id: str) -> dict[str, Any]:
    paths = _open(request, run_id)
    return {
        "run_id": paths.run_id,
        "status": _status(paths),
        "created_at": _created_at(paths),
        "cost_usd": 0.0,
        "stages": [
            {
                "name": stage.name,
                "status": "done" if (paths.stages / stage.artifact).is_file() else "pending",
            }
            for stage in FAKE_STAGES
        ],
    }


@router.get("/{run_id}/report")
def get_report(request: Request, run_id: str) -> dict[str, Any]:
    paths = _open(request, run_id)
    target = paths.root / REPORT_NAME
    if not target.is_file():
        raise RunNotReady("the run has not finished yet")
    return cast(dict[str, Any], json.loads(target.read_text(encoding="utf-8")))


@router.get("/{run_id}/artifacts/{path:path}")
def get_artifact(request: Request, run_id: str, path: str) -> FileResponse:
    paths = _open(request, run_id)
    resolved = resolve_artifact(paths.root, path)
    if not resolved.is_file():
        raise PathNotAllowed("artifact not found")
    return FileResponse(resolved)


__all__ = ["ApiSettings", "router"]

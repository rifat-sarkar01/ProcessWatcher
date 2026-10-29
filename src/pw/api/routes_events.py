"""SSE progress for a run: stage replay, live stage transitions, heartbeats.

The stream observes the run store (stage artifacts + `report.json`); it never imports
pipeline internals beyond the static stage list, so T-3.9 can change the runner
without changing the event contract.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from pw.api.errors import RunNotFound
from pw.api.routes_runs import ApiSettings
from pw.pipeline.runstore import REPORT_NAME, RunPaths, RunStoreError, open_run
from pw.pipeline.stages import FAKE_STAGES
from pw.security.access import require_access_code

POLL_S = 0.2
HEARTBEAT_S = 15.0
STREAM_TIMEOUT_S = 600.0

router = APIRouter(prefix="/runs", tags=["events"], dependencies=[Depends(require_access_code)])


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, sort_keys=True)}\n\n"


def _stage_payload(name: str, status: str, *, pct: float, elapsed_s: float) -> dict[str, Any]:
    return {
        "stage": name,
        "status": status,
        "pct": pct,
        "elapsed_s": round(elapsed_s, 3),
        "cost_usd": 0.0,
    }


async def _stream(paths: RunPaths) -> AsyncIterator[str]:
    started = time.monotonic()
    last_beat = started
    completed: set[str] = set()
    announced: str | None = None

    while True:
        root_started = paths.root.stat().st_mtime
        for stage in FAKE_STAGES:
            if stage.name in completed:
                continue
            artifact = paths.stages / stage.artifact
            if not artifact.is_file():
                break
            completed.add(stage.name)
            elapsed = max(0.0, artifact.stat().st_mtime - root_started)
            yield _sse("stage", _stage_payload(stage.name, "done", pct=100.0, elapsed_s=elapsed))

        if (paths.root / REPORT_NAME).is_file():
            yield _sse("done", {"status": "done"})
            return

        next_stage = next(
            (stage.name for stage in FAKE_STAGES if stage.name not in completed), None
        )
        if next_stage is not None and announced != next_stage:
            announced = next_stage
            yield _sse(
                "stage",
                _stage_payload(
                    next_stage, "running", pct=0.0, elapsed_s=time.monotonic() - started
                ),
            )

        now = time.monotonic()
        if now - last_beat >= HEARTBEAT_S:
            last_beat = now
            yield _sse("heartbeat", {"elapsed_s": round(now - started, 3)})
        if now - started >= STREAM_TIMEOUT_S:
            return
        await asyncio.sleep(POLL_S)


@router.get("/{run_id}/events")
def get_events(request: Request, run_id: str) -> StreamingResponse:
    settings = cast(ApiSettings, request.app.state.settings)
    try:
        paths = open_run(settings.runs_dir, run_id)
    except RunStoreError as exc:
        raise RunNotFound(str(exc)) from exc
    return StreamingResponse(
        _stream(paths),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


__all__ = ["HEARTBEAT_S", "POLL_S", "STREAM_TIMEOUT_S", "router"]

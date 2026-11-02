"""`PATCH /runs/{id}/review`: store one latest human decision per deviation (FR-11).

Decisions never change model output. The route validates the deviation against
`report.json`, keeps the latest decision per deviation, writes a contract-valid
`review.json` and returns it. Notes are plain text and bounded to 500 characters.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from pw.api.errors import InvalidRequest, RunNotFound, RunNotReady
from pw.api.routes_runs import ApiSettings
from pw.data.validate import validate_payload
from pw.pipeline.runstore import REPORT_NAME, RunStoreError, open_run
from pw.security.access import require_access_code

REVIEW_NAME = "review.json"
NOTE_MAX = 500
DECISIONS = frozenset({"accepted", "dismissed"})
_LOCK = threading.Lock()

router = APIRouter(prefix="/runs", tags=["review"], dependencies=[Depends(require_access_code)])


def _settings(request: Request) -> ApiSettings:
    return cast(ApiSettings, request.app.state.settings)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _report_deviation_ids(path: Path) -> set[str]:
    if not path.is_file():
        raise RunNotReady("The report is not ready yet.")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RunNotReady("The report is not readable.") from error
    return {
        str(item["id"])
        for item in report.get("deviations", ())
        if isinstance(item, dict) and "id" in item
    }


def _existing_decisions(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    decisions = payload.get("decisions") if isinstance(payload, dict) else None
    if not isinstance(decisions, list):
        return []
    return [item for item in decisions if isinstance(item, dict) and "deviation_id" in item]


async def _body(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise InvalidRequest("the request body must be JSON") from error
    if not isinstance(payload, dict):
        raise InvalidRequest("the request body must be an object")
    return payload


@router.patch("/{run_id}/review")
async def review_run(request: Request, run_id: str) -> JSONResponse:
    settings = _settings(request)
    body = await _body(request)
    deviation_id = body.get("deviation_id")
    decision = body.get("decision")
    note = body.get("note", "")
    if not isinstance(deviation_id, str) or not deviation_id:
        raise InvalidRequest("deviation_id is required")
    if decision not in DECISIONS:
        raise InvalidRequest("decision must be accepted or dismissed")
    if not isinstance(note, str):
        raise InvalidRequest("note must be a string")
    if len(note) > NOTE_MAX:
        raise InvalidRequest(f"note is longer than {NOTE_MAX} characters")

    try:
        paths = open_run(settings.runs_dir, run_id)
    except RunStoreError as error:
        raise RunNotFound(str(error)) from error
    known = _report_deviation_ids(paths.root / REPORT_NAME)
    if deviation_id not in known:
        raise RunNotFound(f"unknown deviation: {deviation_id}")

    entry = {
        "deviation_id": deviation_id,
        "decision": decision,
        "note": note,
        "decided_at": _now(),
    }
    target = paths.root / REVIEW_NAME
    with _LOCK:
        decisions = _existing_decisions(target)
        replaced = False
        for index, existing in enumerate(decisions):
            if existing.get("deviation_id") == deviation_id:
                decisions[index] = entry
                replaced = True
                break
        if not replaced:
            decisions.append(entry)
        payload = {"schema_version": "1.0.0", "decisions": decisions}
        errors = validate_payload("review", payload)
        if errors:
            raise InvalidRequest("; ".join(errors))
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(target)
    return JSONResponse(payload)


__all__ = ["NOTE_MAX", "REVIEW_NAME", "router"]

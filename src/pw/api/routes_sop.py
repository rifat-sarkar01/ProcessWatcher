"""`POST /sop/compile`: preview the step graph before starting a run (FR-02).

Accepts JSON `{sop_text}` or multipart (`sop` file and/or `sop_text`), validates the
upload with the same caps as a run, compiles through `pw.clients`, and returns
`{step_graph, vocabulary, warnings}`. The compiler is injectable via
`app.state.sop_compiler` so tests and replay setups never touch the network.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from pw.api.errors import InvalidRequest
from pw.api.routes_runs import ApiSettings
from pw.clients import WONDER_MODEL, build_clients, extract_text
from pw.core.ledger import RunLedger
from pw.core.settings import load_settings
from pw.security.access import require_access_code
from pw.security.errors import FileTooLarge
from pw.security.uploads import validate_sop_upload
from pw.sop.compiler import CompileError, compile_sop
from pw.sop.ingest import SopSource, from_text, read_sop

router = APIRouter(prefix="/sop", tags=["sop"], dependencies=[Depends(require_access_code)])


def _settings(request: Request) -> ApiSettings:
    return cast(ApiSettings, request.app.state.settings)


def _rate_limit(request: Request) -> None:
    settings = _settings(request)
    settings.limiter.check(request.client.host if request.client else "unknown")


def _text_payload(prompt: str) -> dict[str, Any]:
    return {
        "model": WONDER_MODEL,
        "temperature": 0,
        "reasoning": {"effort": "low"},
        "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
    }


def _default_compiler(request: Request) -> Callable[[str], str]:
    state = request.app.state
    existing = getattr(state, "sop_compiler", None)
    if existing is not None:
        return cast(Callable[[str], str], existing)
    settings = load_settings()
    clients = getattr(state, "sop_clients", None)
    if clients is None:
        settings_api = _settings(request)
        ledger = RunLedger(
            settings_api.runs_dir / "compile-ledger.json",
            cap_usd=settings.spend_cap_usd,
        )
        clients = build_clients(mode=settings.mode, ledger=ledger, api_key=settings.meta_api_key)
        state.sop_clients = clients

    def compiler(prompt: str) -> str:
        return extract_text(clients.wonder.create_response(_text_payload(prompt)).body) or ""

    return compiler


async def _source_from(request: Request) -> SopSource:
    content_type = request.headers.get("content-type", "")
    caps = _settings(request).caps
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        uploaded = form.get("sop")
        text = form.get("sop_text")
        if isinstance(text, str) and text.strip():
            return from_text(text)
        if uploaded is None or isinstance(uploaded, str):
            raise InvalidRequest("attach a SOP file or provide sop_text")
        data = await uploaded.read()
        if len(data) > caps.max_bytes:
            raise FileTooLarge(f"file exceeds the {caps.max_bytes // (1024 * 1024)} MB limit")
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / (uploaded.filename or "sop.md")
            target.write_bytes(data)
            validate_sop_upload(target, caps=caps)
            return read_sop(target)

    try:
        payload = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise InvalidRequest("the request body must be JSON or multipart") from error
    if not isinstance(payload, Mapping):
        raise InvalidRequest("the request body must be an object")
    text = payload.get("sop_text")
    if not isinstance(text, str) or not text.strip():
        raise InvalidRequest("provide a non-empty sop_text")
    return from_text(text)


@router.post("/compile", dependencies=[Depends(_rate_limit)])
async def compile_preview(request: Request) -> JSONResponse:
    source = await _source_from(request)
    try:
        result = compile_sop(source, compiler=_default_compiler(request))
    except CompileError as error:
        raise InvalidRequest(str(error)[:500]) from error
    except ValueError as error:
        raise InvalidRequest(str(error)[:500]) from error
    graph = result.graph
    vocabulary = graph.get("vocabulary")
    return JSONResponse(
        {
            "step_graph": graph,
            "vocabulary": (
                list(vocabulary.get("sam_concepts", ())) if isinstance(vocabulary, Mapping) else []
            ),
            "warnings": list(graph.get("warnings", ())),
        }
    )


__all__ = ["router"]

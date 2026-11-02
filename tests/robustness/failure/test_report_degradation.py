"""Pipeline-level failure handling: retries degrade into valid reports, caps skip work."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from support import (
    ScriptedTransport,
    error_body,
    handlers,
    pipeline_settings,
    retry_policy,
)

from pw.clients import build_clients
from pw.clients.errors import SpendCapExceeded
from pw.core.ledger import RunLedger
from pw.data.validate import validate_payload
from pw.illustrate.generator import generate_illustrations, illustrations_disabled
from pw.pipeline.handlers import StageServices
from pw.pipeline.orchestrator import run_pipeline


def _client_ledger(scratch: Path) -> RunLedger:
    return RunLedger(scratch / "client-ledger.json", cap_usd=1.0)


def _run(
    tiny_video: Path,
    tiny_sop: Path,
    scratch: Path,
    *,
    services: StageServices,
    **settings: Any,
) -> Any:
    runs = scratch / "runs"
    return run_pipeline(
        video=tiny_video,
        sop=tiny_sop,
        mode="replay",
        runs_dir=runs,
        settings=pipeline_settings(runs, **settings),
        services=services,
    )


@pytest.mark.unit
def test_verifier_outage_retries_then_keeps_findings_in_a_valid_report(
    tiny_video: Path, tiny_sop: Path, scratch: Path
) -> None:
    transport = ScriptedTransport([error_body(503, "verification offline")])
    clients = build_clients(
        mode="live",
        ledger=_client_ledger(scratch),
        transport=transport,
        policy=retry_policy(),
        cache_dir=scratch / "cache",
    )

    result = _run(
        tiny_video, tiny_sop, scratch, services=StageServices(handlers=handlers(), clients=clients)
    )

    report = json.loads((result.run_dir / "report.json").read_text(encoding="utf-8"))
    verify = json.loads((result.run_dir / "stages" / "verify.json").read_text(encoding="utf-8"))

    assert result.cap_reached is False
    assert result.degraded == ()
    assert report["status"] == "done"
    assert verify["deviations"], "the stub run must produce at least one finding"
    assert all(record["ran"] is False for record in verify["verifiers"].values())
    assert all(
        record["note"].startswith("verifier_unavailable: ServerError")
        for record in verify["verifiers"].values()
    )
    assert all(deviation["verifier"]["ran"] is False for deviation in report["deviations"])
    assert validate_payload("report", report) == []

    # Every attempt was a 503 and each deviation cost one bounded retry cycle.
    assert transport.calls >= 4 * len(verify["deviations"])
    assert transport.calls % 4 == 0
    assert _client_ledger(scratch).entries == ()


@pytest.mark.unit
def test_disable_verifier_skips_the_model_and_records_the_switch(
    tiny_video: Path, tiny_sop: Path, scratch: Path
) -> None:
    calls: list[str] = []

    def verifier(prompt: str) -> str:
        calls.append(prompt)
        raise AssertionError("the verifier must not be called when the switch is on")

    result = _run(
        tiny_video,
        tiny_sop,
        scratch,
        services=StageServices(handlers=handlers(), verifier=verifier),
        disable_verifier=True,
    )

    report = json.loads((result.run_dir / "report.json").read_text(encoding="utf-8"))
    verify = json.loads((result.run_dir / "stages" / "verify.json").read_text(encoding="utf-8"))

    assert calls == []
    assert verify["verifiers"]
    assert all(record["ran"] is False for record in verify["verifiers"].values())
    assert all(record["note"] == "PW_DISABLE_VERIFIER" for record in verify["verifiers"].values())
    assert report["status"] == "done"
    assert validate_payload("report", report) == []


@pytest.mark.unit
def test_spend_cap_skips_model_stages_and_still_writes_a_partial_report(
    tiny_video: Path, tiny_sop: Path, scratch: Path
) -> None:
    verifier_calls: list[str] = []

    def capped(_run: Any) -> dict[str, Any]:
        raise SpendCapExceeded(0.9, 0.5, 1.0)

    def verifier(prompt: str) -> str:
        verifier_calls.append(prompt)
        return '{"occurred": false, "confidence": 0.8, "note": "checked"}'

    result = _run(
        tiny_video,
        tiny_sop,
        scratch,
        services=StageServices(handlers=handlers(verify=capped), verifier=verifier),
    )

    statuses = {stage.name: stage.status for stage in result.stages}
    report = json.loads((result.run_dir / "report.json").read_text(encoding="utf-8"))
    manifest = json.loads((result.run_dir / "manifest.json").read_text(encoding="utf-8"))

    assert result.cap_reached is True
    assert verifier_calls == []
    assert statuses["score"] == "ok"
    assert statuses["verify"] == "skipped"
    assert statuses["illustrate"] == "skipped"
    assert statuses["evidence"] == "ok"
    assert report["status"] == "partial"
    assert {"verify", "illustrate"} <= set(report["degraded_stages"])
    assert validate_payload("report", report) == []
    assert manifest["ledger"]["cap_reached"] is True
    assert validate_payload("manifest", manifest) == []


@pytest.mark.unit
def test_concurrent_spend_reservations_never_overshoot_the_cap(scratch: Path) -> None:
    ledger = RunLedger(scratch / "ledger.json", cap_usd=1.0)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        barrier.wait()
        try:
            with ledger.budget(0.6):
                time.sleep(0.05)
            outcome = "reserved"
        except SpendCapExceeded:
            outcome = "capped"
        with lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(outcomes) == ["capped", "reserved"]
    assert ledger.total_usd == 0.0


@pytest.mark.unit
def test_disable_illustrations_never_calls_the_image_model() -> None:
    def call(_prompt: str, _reference: bytes | None) -> bytes:
        raise AssertionError("illustrations must not be generated when disabled")

    deviations = [SimpleNamespace(id="dev_001", step_id="stp_01", type="missed")]
    result = generate_illustrations(
        deviations,
        {"steps": [{"id": "stp_01", "idx": 1, "text": "Power down.", "tools": []}]},
        call=call,
        disabled=True,
    )

    assert result.items == ()
    assert result.disabled is True
    assert result.calls == 0
    assert illustrations_disabled({"PW_DISABLE_ILLUSTRATIONS": "true"}) is True
    assert illustrations_disabled({"PW_DISABLE_ILLUSTRATIONS": "off"}) is False
    assert illustrations_disabled({}) is False

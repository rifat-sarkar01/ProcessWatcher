"""API health and run listing for the walking skeleton."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from pw.api.main import create_app
from pw.pipeline.orchestrator import run_pipeline


def test_healthz_reports_ok(runs_dir: Path) -> None:
    client = TestClient(create_app(runs_dir=runs_dir))
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_runs_lists_a_finished_fake_run(tiny_video: Path, tiny_sop: Path, runs_dir: Path) -> None:
    run = run_pipeline(video=tiny_video, sop=tiny_sop, mode="fake", runs_dir=runs_dir)
    client = TestClient(create_app(runs_dir=runs_dir))
    response = client.get("/runs")
    assert response.status_code == 200
    payload = response.json()
    assert [item["run_id"] for item in payload] == [run.run_id]
    assert set(payload[0]) == {"run_id", "status", "created_at", "cost_usd"}
    assert payload[0]["status"] == "done"


def test_runs_is_empty_without_runs(runs_dir: Path) -> None:
    client = TestClient(create_app(runs_dir=runs_dir))
    assert client.get("/runs").json() == []

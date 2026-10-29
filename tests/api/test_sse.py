"""SSE progress: replay, live running stage, heartbeat, disconnect and guards."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import pw.api.routes_events as routes_events
from pw.pipeline.stages import STAGE_ORDER

ACCESS = {"X-Access-Code": "test-access-code"}
UNKNOWN_RUN = "run_01J9ZQ8M3K4V7B2C5D6E8F0GHJ"


def upload(client: TestClient, video: Path) -> str:
    with video.open("rb") as handle:
        response = client.post(
            "/runs",
            files={"video": (video.name, handle, "video/mp4")},
            data={"sop_text": "1. Tighten.\n"},
            headers=ACCESS,
        )
    return response.json()["run_id"]


def parse_sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    for block in body.strip().split("\n\n"):
        name = None
        data: dict[str, Any] = {}
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line.removeprefix("event: ")
            elif line.startswith("data: "):
                data = json.loads(line.removeprefix("data: "))
        if name is not None:
            events.append((name, data))
    return events


def _read_stream(client: TestClient, run_id: str) -> tuple[Any, str]:
    with client.stream("GET", f"/runs/{run_id}/events", headers=ACCESS) as response:
        body = "".join(response.iter_text())
        return response, body


def test_replay_streams_every_stage_then_done(client: TestClient, clip: Path) -> None:
    run_id = upload(client, clip)
    response, body = _read_stream(client, run_id)
    assert response.status_code == 200
    events = parse_sse(body)
    stages = [data for name, data in events if name == "stage"]
    assert [event["stage"] for event in stages] == list(STAGE_ORDER)
    assert all(event["status"] == "done" for event in stages)
    assert all(event["pct"] == 100.0 for event in stages)
    assert all(event["cost_usd"] == 0.0 for event in stages)
    assert events[-1] == ("done", {"status": "done"})


def test_stream_uses_sse_framing(client: TestClient, clip: Path) -> None:
    run_id = upload(client, clip)
    response, body = _read_stream(client, run_id)
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: stage\ndata: " in body
    assert body.endswith("\n\n")


def test_live_run_announces_running_stage_and_heartbeats(
    client: TestClient, runs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routes_events, "POLL_S", 0.01)
    monkeypatch.setattr(routes_events, "HEARTBEAT_S", 0.02)
    monkeypatch.setattr(routes_events, "STREAM_TIMEOUT_S", 0.15)
    (runs_dir / UNKNOWN_RUN / "stages").mkdir(parents=True)

    _, body = _read_stream(client, UNKNOWN_RUN)
    events = parse_sse(body)
    stage_events = [data for name, data in events if name == "stage"]
    assert stage_events[0]["stage"] == STAGE_ORDER[0]
    assert stage_events[0]["status"] == "running"
    assert any(name == "heartbeat" for name, _ in events)
    assert not any(name == "done" for name, _ in events)


def test_disconnect_is_clean(
    client: TestClient, runs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routes_events, "POLL_S", 0.01)
    monkeypatch.setattr(routes_events, "STREAM_TIMEOUT_S", 0.2)
    (runs_dir / UNKNOWN_RUN / "stages").mkdir(parents=True)

    with client.stream("GET", f"/runs/{UNKNOWN_RUN}/events", headers=ACCESS) as response:
        assert response.status_code == 200
        for _ in response.iter_lines():
            break
    assert (runs_dir / UNKNOWN_RUN / "stages").is_dir()


def test_unknown_run_is_404(client: TestClient) -> None:
    response = client.get(f"/runs/{UNKNOWN_RUN}/events", headers=ACCESS)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "E-13"


def test_access_code_is_required(client: TestClient, runs_dir: Path) -> None:
    (runs_dir / UNKNOWN_RUN / "stages").mkdir(parents=True)
    assert client.get(f"/runs/{UNKNOWN_RUN}/events").status_code == 401

"""Run wiring: configured mode and the human-edited step-graph override."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

HEADERS = {"X-Access-Code": "test-access-code"}

GRAPH: dict[str, Any] = {
    "schema_version": "1.0.0",
    "sop_id": "sop_00000000",
    "title": "Edited procedure",
    "source": {"kind": "pasted", "sha256": "a" * 64},
    "steps": [
        {
            "id": "stp_01",
            "idx": 1,
            "text": "Power the unit down.",
            "action": "power down",
            "tools": [],
            "parts": ["power cable"],
            "ordering": "strict",
            "group_id": None,
            "critical": True,
            "visual_check": None,
        },
        {
            "id": "stp_02",
            "idx": 2,
            "text": "Remove the cover.",
            "action": "remove",
            "tools": ["screwdriver"],
            "parts": ["cover"],
            "ordering": "strict",
            "group_id": None,
            "critical": False,
            "visual_check": None,
        },
    ],
    "vocabulary": {"sam_concepts": ["hand", "screwdriver"]},
    "warnings": [],
}


def _upload(client: TestClient, video: Path, *, step_graph: str | None = None) -> Any:
    with video.open("rb") as handle:
        data: dict[str, str] = {"sop_text": "1. Power down.\n2. Remove the cover.\n"}
        if step_graph is not None:
            data["step_graph"] = step_graph
        return client.post(
            "/runs",
            files={"video": (video.name, handle, "video/mp4")},
            data=data,
            headers=HEADERS,
        )


def test_a_human_edited_step_graph_is_written_to_the_run(
    client: TestClient, clip: Path, runs_dir: Path
) -> None:
    response = _upload(client, clip, step_graph=json.dumps(GRAPH))

    assert response.status_code == 202
    run_id = response.json()["run_id"]
    stored = json.loads(
        (runs_dir / run_id / "stages" / "step_graph.json").read_text(encoding="utf-8")
    )
    assert stored == GRAPH


def test_malformed_step_graph_json_is_422(client: TestClient, clip: Path) -> None:
    response = _upload(client, clip, step_graph="{not json")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "E-04"


def test_invalid_step_graph_is_422(client: TestClient, clip: Path) -> None:
    response = _upload(client, clip, step_graph=json.dumps({"steps": []}))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "E-04"


def test_runs_use_the_configured_mode_and_pass_the_graph(
    client: TestClient,
    clip: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def spy(**kwargs: Any) -> None:
        captured.update(kwargs)

    monkeypatch.setattr("pw.api.routes_runs.run_pipeline", spy)

    response = _upload(client, clip, step_graph=json.dumps(GRAPH))

    assert response.status_code == 202
    assert captured["mode"] == "fake"
    assert captured["settings"] is not None
    assert captured["step_graph"] == GRAPH

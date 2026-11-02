"""T-5.3: SOP compile preview and review-decision endpoints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pw.data.validate import validate_payload
from pw.pipeline.runstore import new_run_id
from pw.sop.compiler import CompileError

ACCESS = {"X-Access-Code": "test-access-code"}
SOP_TEXT = "1. Unplug the power cable.\n2. Remove the cover.\n"

COMPILED: dict[str, Any] = {
    "title": "Cable check",
    "steps": [
        {
            "text": "Unplug the power cable.",
            "action": "unplug",
            "tools": ["hand"],
            "parts": ["power cable"],
            "ordering": "strict",
            "critical": True,
            "visual_check": None,
        },
        {
            "text": "Remove the cover.",
            "action": "remove",
            "tools": ["hand"],
            "parts": ["cover"],
            "ordering": "strict",
            "critical": False,
            "visual_check": None,
        },
    ],
}


def _compiler(prompt: str) -> str:
    return json.dumps(COMPILED)


def _auth(client: TestClient) -> None:
    client.app.state.sop_compiler = _compiler  # type: ignore[attr-defined]


def _run_with_report(runs_dir: Path) -> str:
    run_id = new_run_id()
    root = runs_dir / run_id
    (root / "stages").mkdir(parents=True)
    (root / "report.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "status": "done",
                "deviations": [{"id": "dev_001"}, {"id": "dev_002"}],
            }
        ),
        encoding="utf-8",
    )
    return run_id


@pytest.mark.unit
def test_compile_preview_accepts_json_text(client: TestClient) -> None:
    _auth(client)

    response = client.post("/sop/compile", json={"sop_text": SOP_TEXT}, headers=ACCESS)

    assert response.status_code == 200
    body = response.json()
    assert len(body["step_graph"]["steps"]) == 2
    assert body["vocabulary"][0] == "hand"
    assert body["warnings"] == []


@pytest.mark.unit
def test_compile_preview_accepts_a_multipart_file(
    client: TestClient, runs_dir: Path
) -> None:
    _auth(client)
    source = runs_dir / "procedure.md"
    source.write_text(SOP_TEXT, encoding="utf-8")

    with source.open("rb") as handle:
        response = client.post(
            "/sop/compile",
            files={"sop": (source.name, handle, "text/markdown")},
            headers=ACCESS,
        )

    assert response.status_code == 200
    assert response.json()["step_graph"]["sop_id"].startswith("sop_")


@pytest.mark.unit
def test_compile_preview_rejects_empty_text(client: TestClient) -> None:
    _auth(client)

    response = client.post("/sop/compile", json={"sop_text": "   "}, headers=ACCESS)

    assert response.status_code == 422
    assert "error" in response.json()


@pytest.mark.unit
def test_compile_preview_rejects_a_malformed_body(client: TestClient) -> None:
    _auth(client)

    response = client.post(
        "/sop/compile",
        content=b"{not json",
        headers={**ACCESS, "Content-Type": "application/json"},
    )

    assert response.status_code == 422


@pytest.mark.unit
def test_compile_failure_is_a_422(client: TestClient) -> None:
    def failing(prompt: str) -> str:
        raise CompileError("no usable steps", attempts=2, issues=("invalid_json",))

    client.app.state.sop_compiler = failing  # type: ignore[attr-defined]

    response = client.post("/sop/compile", json={"sop_text": SOP_TEXT}, headers=ACCESS)

    assert response.status_code == 422
    assert response.json()["error"]["code"]


@pytest.mark.unit
def test_compile_preview_requires_the_access_code(client: TestClient) -> None:
    _auth(client)

    assert client.post("/sop/compile", json={"sop_text": SOP_TEXT}).status_code == 401


@pytest.mark.unit
def test_review_accepts_a_decision_and_writes_review_json(
    client: TestClient, runs_dir: Path
) -> None:
    run_id = _run_with_report(runs_dir)

    response = client.patch(
        f"/runs/{run_id}/review",
        json={"deviation_id": "dev_001", "decision": "accepted", "note": "looks correct"},
        headers=ACCESS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decisions"][0]["deviation_id"] == "dev_001"
    assert payload["decisions"][0]["decision"] == "accepted"
    assert payload["decisions"][0]["decided_at"].endswith("Z")
    assert validate_payload("review", payload) == []
    stored = json.loads((runs_dir / run_id / "review.json").read_text(encoding="utf-8"))
    assert stored == payload


@pytest.mark.unit
def test_review_keeps_only_the_latest_decision_per_deviation(
    client: TestClient, runs_dir: Path
) -> None:
    run_id = _run_with_report(runs_dir)
    client.patch(
        f"/runs/{run_id}/review",
        json={"deviation_id": "dev_001", "decision": "accepted", "note": ""},
        headers=ACCESS,
    )

    response = client.patch(
        f"/runs/{run_id}/review",
        json={"deviation_id": "dev_001", "decision": "dismissed", "note": "revised"},
        headers=ACCESS,
    )

    decisions = response.json()["decisions"]
    assert len(decisions) == 1
    assert decisions[0]["decision"] == "dismissed"
    assert decisions[0]["note"] == "revised"


@pytest.mark.unit
def test_review_rejects_an_unknown_deviation(client: TestClient, runs_dir: Path) -> None:
    run_id = _run_with_report(runs_dir)

    response = client.patch(
        f"/runs/{run_id}/review",
        json={"deviation_id": "dev_099", "decision": "accepted"},
        headers=ACCESS,
    )

    assert response.status_code == 404


@pytest.mark.unit
def test_review_rejects_a_bad_decision_and_a_long_note(
    client: TestClient, runs_dir: Path
) -> None:
    run_id = _run_with_report(runs_dir)

    bad = client.patch(
        f"/runs/{run_id}/review",
        json={"deviation_id": "dev_001", "decision": "maybe"},
        headers=ACCESS,
    )
    long_note = client.patch(
        f"/runs/{run_id}/review",
        json={"deviation_id": "dev_001", "decision": "accepted", "note": "x" * 501},
        headers=ACCESS,
    )

    assert bad.status_code == 422
    assert long_note.status_code == 422


@pytest.mark.unit
def test_review_unknown_run_and_missing_report(
    client: TestClient, runs_dir: Path
) -> None:
    unknown = client.patch(
        f"/runs/{new_run_id()}/review",
        json={"deviation_id": "dev_001", "decision": "accepted"},
        headers=ACCESS,
    )
    empty_id = new_run_id()
    (runs_dir / empty_id / "stages").mkdir(parents=True)
    not_ready = client.patch(
        f"/runs/{empty_id}/review",
        json={"deviation_id": "dev_001", "decision": "accepted"},
        headers=ACCESS,
    )

    assert unknown.status_code == 404
    assert not_ready.status_code == 409


@pytest.mark.unit
def test_review_requires_the_access_code(client: TestClient, runs_dir: Path) -> None:
    run_id = _run_with_report(runs_dir)

    response = client.patch(
        f"/runs/{run_id}/review",
        json={"deviation_id": "dev_001", "decision": "accepted"},
    )

    assert response.status_code == 401

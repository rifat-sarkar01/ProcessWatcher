"""Demo routes: the frozen gallery lists cases and serves only pack files."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pw.api.main import create_app

SCRATCH_ROOT = Path(__file__).resolve().parents[2] / ".uv" / "tests-tmp"


def _case(root: Path, case_id: str) -> None:
    case = root / case_id
    (case / "media").mkdir(parents=True)
    (case / "report.json").write_text(
        json.dumps(
            {
                "status": "done",
                "deviations": [{"type": "missed", "step_id": "stp_04", "status": "flagged"}],
            }
        ),
        encoding="utf-8",
    )
    media = case / "media" / "analysis.mp4"
    media.write_bytes(b"fake-mp4")
    files = {"media/analysis.mp4": hashlib.sha256(media.read_bytes()).hexdigest()}
    (case / "case.json").write_text(
        json.dumps(
            {
                "case_id": case_id,
                "title": f"{case_id} title",
                "description": "frozen",
                "source_run": "run_test",
                "files": files,
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def client() -> Iterator[TestClient]:
    root = SCRATCH_ROOT / f"demo-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    for case_id in ("case_a", "case_b"):
        _case(root, case_id)
    try:
        yield TestClient(create_app(runs_dir=root / "runs", demo_cases_dir=root))
    finally:
        import shutil

        shutil.rmtree(root, ignore_errors=True)


@pytest.mark.unit
def test_list_cases(client: TestClient) -> None:
    response = client.get("/demo/cases")

    assert response.status_code == 200
    cases = response.json()["cases"]
    assert [case["case_id"] for case in cases] == ["case_a", "case_b"]
    assert cases[0]["deviation_count"] == 1


@pytest.mark.unit
def test_serve_case_media(client: TestClient) -> None:
    response = client.get("/demo/cases/case_a/media/analysis.mp4")

    assert response.status_code == 200
    assert response.content == b"fake-mp4"


@pytest.mark.unit
def test_refuses_traversal_and_unknown_cases(client: TestClient) -> None:
    assert client.get("/demo/cases/case_a/../case_b/case.json").status_code in {404, 422}
    assert client.get("/demo/cases/missing/media/analysis.mp4").status_code == 404

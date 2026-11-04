"""Demo routes: the frozen gallery lists cases and serves only pack files."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from pw.api.main import create_app
from pw.data.schemas import load_schemas

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRATCH_ROOT = REPO_ROOT / ".uv" / "tests-tmp"
EXAMPLE_REPORT = REPO_ROOT / "contracts" / "examples" / "report.p-a.example.json"
DEMO_CASE_SCHEMA = REPO_ROOT / "contracts" / "schemas" / "demo-case.schema.json"


def _case(root: Path, case_id: str) -> None:
    case = root / case_id
    (case / "media").mkdir(parents=True)
    (case / "report.json").write_text(EXAMPLE_REPORT.read_text(encoding="utf-8"), encoding="utf-8")
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
    assert cases[0]["deviation_count"] == 2
    assert cases[0]["duration_s"] == 118.0


@pytest.mark.unit
def test_get_case_returns_metadata_and_report(client: TestClient) -> None:
    response = client.get("/demo/cases/case_a")

    assert response.status_code == 200
    payload = response.json()
    assert payload["case_id"] == "case_a"
    assert payload["title"] == "case_a title"
    assert payload["duration_s"] == 118.0
    assert payload["deviation_count"] == 2
    assert payload["media"] == {"analysis": "media/analysis.mp4"}
    assert len(payload["report"]["deviations"]) == 2


@pytest.mark.unit
def test_get_case_matches_the_contract(client: TestClient) -> None:
    payload = client.get("/demo/cases/case_a").json()
    schemas = load_schemas()
    registry = Registry().with_resources(
        [
            (schema["$id"], Resource.from_contents(schema))
            for schema in schemas.values()
            if isinstance(schema.get("$id"), str)
        ]
    )
    schema = json.loads(DEMO_CASE_SCHEMA.read_text(encoding="utf-8"))

    Draft202012Validator(schema, registry=registry).validate(payload)


@pytest.mark.unit
def test_unknown_case_is_not_found(client: TestClient) -> None:
    assert client.get("/demo/cases/missing").status_code == 404


@pytest.mark.unit
def test_serve_case_media(client: TestClient) -> None:
    response = client.get("/demo/cases/case_a/media/analysis.mp4")

    assert response.status_code == 200
    assert response.content == b"fake-mp4"


@pytest.mark.unit
def test_refuses_traversal_and_unknown_cases(client: TestClient) -> None:
    assert client.get("/demo/cases/case_a/../case_b/case.json").status_code in {404, 422}
    assert client.get("/demo/cases/missing/media/analysis.mp4").status_code == 404

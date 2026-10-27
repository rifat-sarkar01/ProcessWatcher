"""Contract tests: schemas, committed examples and the cross-field invariants."""

from __future__ import annotations

import copy
import json
import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from pw.data import cli
from pw.data.schemas import EXAMPLE_FILENAMES, KINDS, default_contracts_dir, load_json
from pw.data.validate import validate_all, validate_payload

CONTRACTS_DIR = default_contracts_dir()
EXAMPLES_DIR = CONTRACTS_DIR / "examples"
SCRATCH_ROOT = Path(__file__).resolve().parents[2] / ".uv" / "tests-tmp"


def example(kind: str) -> dict[str, Any]:
    payload = load_json(EXAMPLES_DIR / EXAMPLE_FILENAMES[kind])
    assert isinstance(payload, dict)
    return copy.deepcopy(payload)


@pytest.fixture
def artifact_dir() -> Iterator[Path]:
    """Scratch directory for CLI tests.

    Deliberately not pytest's `tmp_path`: that factory relies on `tempfile.mkdtemp`,
    whose directories cannot be listed again on this Windows host (sandboxed ACLs),
    which breaks the tests for environmental reasons rather than product reasons.
    """
    path = SCRATCH_ROOT / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.mark.unit
@pytest.mark.parametrize("kind", KINDS)
def test_committed_examples_are_valid(kind: str) -> None:
    assert validate_payload(kind, example(kind)) == []


@pytest.mark.unit
def test_validate_all_reports_no_problems() -> None:
    assert validate_all() == []


@pytest.mark.unit
def test_validate_contracts_cli_prints_summary(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["validate-contracts"]) == 0
    assert "OK 3 schemas, 3 examples" in capsys.readouterr().out


@pytest.mark.unit
def test_empty_track_list_is_valid() -> None:
    payload = example("tracks")
    payload["tracks"] = []

    assert validate_payload("tracks", payload) == []


@pytest.mark.unit
def test_missing_required_field_is_rejected() -> None:
    payload = example("tracks")
    del payload["video"]["sha256"]

    errors = validate_payload("tracks", payload)

    assert any("sha256" in error for error in errors)


@pytest.mark.unit
def test_bad_enum_is_rejected() -> None:
    payload = example("timeline")
    payload["events"][0]["type"] = "teleport"

    errors = validate_payload("timeline", payload)

    assert any("teleport" in error for error in errors)


@pytest.mark.unit
def test_negative_time_is_rejected() -> None:
    payload = example("tracks")
    payload["tracks"][0]["frames"][0]["t"] = -1.0

    errors = validate_payload("tracks", payload)

    assert any("less than the minimum of 0" in error for error in errors)


@pytest.mark.unit
def test_non_monotonic_frames_are_rejected() -> None:
    payload = example("tracks")
    frames = payload["tracks"][0]["frames"]
    frames[1]["frame"], frames[2]["frame"] = frames[2]["frame"], frames[1]["frame"]
    frames[1]["t"], frames[2]["t"] = frames[2]["t"], frames[1]["t"]
    payload["tracks"][0]["last_t"] = frames[-1]["t"]

    errors = validate_payload("tracks", payload)

    assert any("strictly increasing" in error for error in errors)


@pytest.mark.unit
def test_unordered_group_requires_group_id() -> None:
    payload = example("sop")
    payload["steps"][2]["group_id"] = None

    errors = validate_payload("sop", payload)

    assert any("group_id" in error for error in errors)


@pytest.mark.unit
def test_vocabulary_must_include_hand() -> None:
    payload = example("sop")
    payload["vocabulary"]["sam_concepts"] = ["screwdriver", "ssd"]

    errors = validate_payload("sop", payload)

    assert any("does not contain" in error for error in errors)


@pytest.mark.unit
def test_duplicate_track_ids_are_rejected() -> None:
    payload = example("tracks")
    payload["tracks"][1]["id"] = payload["tracks"][0]["id"]

    errors = validate_payload("tracks", payload)

    assert any("duplicate track id" in error for error in errors)


@pytest.mark.unit
def test_unsorted_events_are_rejected() -> None:
    payload = example("timeline")
    payload["events"][1]["t_start"], payload["events"][2]["t_start"] = (
        payload["events"][2]["t_start"],
        payload["events"][1]["t_start"],
    )

    errors = validate_payload("timeline", payload)

    assert any("sorted by t_start" in error for error in errors)


@pytest.mark.unit
def test_unknown_event_reference_in_segment_is_rejected() -> None:
    payload = example("timeline")
    payload["segments"][0]["event_ids"] = ["evt_999"]

    errors = validate_payload("timeline", payload)

    assert any("unknown event id" in error for error in errors)


@pytest.mark.unit
def test_unknown_kind_raises() -> None:
    with pytest.raises(ValueError, match="unknown artifact kind"):
        validate_payload("report", {})


@pytest.mark.unit
def test_validate_artifact_cli_ok(artifact_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = artifact_dir / "step_graph.json"
    path.write_text(json.dumps(example("sop")), encoding="utf-8")

    assert cli.main(["validate-artifact", str(path)]) == 0
    assert "OK" in capsys.readouterr().out


@pytest.mark.unit
def test_validate_artifact_cli_invalid_returns_one(
    artifact_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = example("timeline")
    payload["events"][0]["confidence"] = 1.5
    path = artifact_dir / "timeline.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert cli.main(["validate-artifact", str(path)]) == 1
    assert "FAILED" in capsys.readouterr().err


@pytest.mark.unit
def test_validate_artifact_cli_unreadable_returns_two(
    artifact_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["validate-artifact", str(artifact_dir / "missing.json")]) == 2
    assert "ERROR" in capsys.readouterr().err

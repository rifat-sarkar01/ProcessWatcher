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
from pw.data.schemas import (
    EXAMPLE_FILENAMES,
    EXAMPLE_PATTERNS,
    KINDS,
    default_contracts_dir,
    load_json,
)
from pw.data.validate import validate_all, validate_payload

CONTRACTS_DIR = default_contracts_dir()
EXAMPLES_DIR = CONTRACTS_DIR / "examples"
SCRATCH_ROOT = Path(__file__).resolve().parents[2] / ".uv" / "tests-tmp"
REPORT_FIXTURES = (
    "report.p-a.example.json",
    "report.p-b.example.json",
    "report.p-c.example.json",
)


def example(kind: str, filename: str | None = None) -> dict[str, Any]:
    payload = load_json(EXAMPLES_DIR / (filename or EXAMPLE_FILENAMES[kind]))
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
@pytest.mark.parametrize(
    ("kind", "path"),
    [
        (kind, path)
        for kind in KINDS
        for path in sorted(EXAMPLES_DIR.glob(EXAMPLE_PATTERNS[kind][0]))
    ],
    ids=[
        f"{kind}-{path.name}"
        for kind in KINDS
        for path in sorted(EXAMPLES_DIR.glob(EXAMPLE_PATTERNS[kind][0]))
    ],
)
def test_committed_examples_are_valid(kind: str, path: Path) -> None:
    assert validate_payload(kind, load_json(path)) == []


@pytest.mark.unit
@pytest.mark.parametrize("filename", REPORT_FIXTURES)
def test_report_fixtures_are_valid(filename: str) -> None:
    assert validate_payload("report", example("report", filename)) == []


@pytest.mark.unit
def test_report_embedded_step_graph_is_validated() -> None:
    payload = example("report", REPORT_FIXTURES[0])
    payload["sop"]["steps"][0]["id"] = "step-one"

    errors = validate_payload("report", payload)

    assert any("step-one" in error for error in errors)


@pytest.mark.unit
def test_validate_all_reports_no_problems() -> None:
    assert validate_all() == []


@pytest.mark.unit
def test_validate_contracts_cli_prints_summary(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["validate-contracts"]) == 0
    assert "OK 8 schemas, 12 examples" in capsys.readouterr().out


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
        validate_payload("not_a_contract", {})


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


# --- evidence / illustration provenance (FR-09, FR-10) ---------------------------


@pytest.mark.unit
def test_illustration_inside_evidence_is_rejected() -> None:
    payload = example("report", REPORT_FIXTURES[0])
    illustration = payload["deviations"][1]["illustration"]
    payload["deviations"][1]["evidence"].append(illustration)

    errors = validate_payload("report", payload)

    assert any("evidence.1" in error for error in errors)


@pytest.mark.unit
def test_illustration_must_carry_a_watermark() -> None:
    payload = example("report", REPORT_FIXTURES[0])
    payload["deviations"][1]["illustration"]["watermark"] = False

    errors = validate_payload("report", payload)

    assert any("watermark" in error for error in errors)


@pytest.mark.unit
def test_missing_illustration_requires_a_reason() -> None:
    payload = example("report", REPORT_FIXTURES[0])
    payload["deviations"][0]["illustration_unavailable_reason"] = None

    errors = validate_payload("report", payload)

    assert any("illustration_unavailable_reason" in error for error in errors)


# --- traceability invariants (NFR-04) -------------------------------------------


@pytest.mark.unit
def test_deviation_without_track_refs_is_rejected() -> None:
    payload = example("report", REPORT_FIXTURES[0])
    payload["deviations"][0]["track_ids"] = []

    errors = validate_payload("report", payload)

    assert any("track_ids" in error for error in errors)


@pytest.mark.unit
def test_deviation_without_step_id_is_rejected() -> None:
    payload = example("report", REPORT_FIXTURES[0])
    del payload["deviations"][0]["step_id"]

    errors = validate_payload("report", payload)

    assert any("step_id" in error for error in errors)


@pytest.mark.unit
def test_deviation_step_must_exist_in_the_embedded_sop() -> None:
    payload = example("report", REPORT_FIXTURES[0])
    payload["deviations"][0]["step_id"] = "stp_99"

    errors = validate_payload("report", payload)

    assert any("unknown step id" in error for error in errors)


@pytest.mark.unit
def test_evidence_without_reason_is_rejected() -> None:
    payload = example("report", REPORT_FIXTURES[0])
    payload["deviations"][0]["evidence"] = []
    payload["deviations"][0]["evidence_unavailable"] = False

    errors = validate_payload("report", payload)

    assert any("evidence_unavailable" in error for error in errors)


# --- report status invariants (docs/05_Schema.md §11) ---------------------------


@pytest.mark.unit
def test_not_recognized_requires_no_deviations() -> None:
    payload = example("report", REPORT_FIXTURES[2])
    payload["deviations"] = example("report", REPORT_FIXTURES[0])["deviations"]

    errors = validate_payload("report", payload)

    assert any("not_recognized" in error for error in errors)


@pytest.mark.unit
def test_done_requires_no_degraded_stages() -> None:
    payload = example("report", REPORT_FIXTURES[0])
    payload["degraded_stages"] = ["verify"]

    errors = validate_payload("report", payload)

    assert any("degraded_stages" in error for error in errors)


@pytest.mark.unit
def test_summary_counts_must_match_deviations() -> None:
    payload = example("report", REPORT_FIXTURES[0])
    payload["summary"]["flagged"] = 5

    errors = validate_payload("report", payload)

    assert any("summary.flagged" in error for error in errors)


# --- review, alignment and thresholds invariants --------------------------------


@pytest.mark.unit
def test_review_duplicate_decision_is_rejected() -> None:
    payload = example("review")
    payload["decisions"][1]["deviation_id"] = payload["decisions"][0]["deviation_id"]

    errors = validate_payload("review", payload)

    assert any("duplicate decision" in error for error in errors)


@pytest.mark.unit
def test_likelihood_probabilities_must_sum_to_one() -> None:
    payload = example("likelihoods")
    payload["segments"][0]["step_probs"] = {"stp_01": 0.2, "none": 0.2}

    errors = validate_payload("likelihoods", payload)

    assert any("sum to" in error for error in errors)


@pytest.mark.unit
def test_alignment_interval_times_must_be_ordered() -> None:
    payload = example("alignment")
    payload["intervals"][0]["t_end"] = payload["intervals"][0]["t_start"] - 1.0

    errors = validate_payload("alignment", payload)

    assert any("before t_start" in error for error in errors)


@pytest.mark.unit
def test_thresholds_reject_unknown_keys() -> None:
    payload = example("thresholds")
    payload["deviation"]["tau_magic"] = 0.5

    errors = validate_payload("thresholds", payload)

    assert any("tau_magic" in error for error in errors)


@pytest.mark.unit
def test_thresholds_reject_out_of_range_probabilities() -> None:
    payload = example("thresholds")
    payload["deviation"]["tau_flag"] = 1.5

    errors = validate_payload("thresholds", payload)

    assert any("tau_flag" in error for error in errors)

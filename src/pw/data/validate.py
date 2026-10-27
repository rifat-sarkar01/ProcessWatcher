"""Validate artifacts against their JSON Schema plus the cross-field invariants.

JSON Schema covers shape and enums; it cannot express "frames strictly increasing",
"events sorted by t_start", "an illustration may never appear in evidence[]" or
"summary counts match the deviations". Those live here.
See docs/05_Schema.md §11 (cross-field invariants).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource

from pw.data.schemas import (
    KINDS,
    SCHEMA_NAMES,
    default_contracts_dir,
    example_files,
    load_json,
    load_schema,
    load_schemas,
)

TIME_TOLERANCE_S = 1e-3
"""Times are seconds with millisecond precision (AGENTS.md §4)."""

MIN_ACTIVITY_SEGMENT_S = 1.0
MAX_ACTIVITY_SEGMENT_S = 20.0
MAX_EXPLANATION_WORDS = 40
PROB_SUM_TOLERANCE = 0.02


def _schema_registry(contracts_dir: Path | None) -> Registry[bool | Mapping[str, Any]]:
    """Registry so cross-file `$ref`s (report -> sop) resolve from the contracts dir."""
    schemas = load_schemas(contracts_dir)
    resources: list[tuple[str, Resource[Any]]] = []
    for schema in schemas.values():
        schema_id = schema.get("$id")
        if isinstance(schema_id, str):
            resources.append((schema_id, Resource.from_contents(schema)))
    return cast(
        "Registry[bool | Mapping[str, Any]]",
        Registry().with_resources(resources),
    )


def _schema_errors(
    schema: dict[str, Any],
    payload: Any,
    registry: Registry[bool | Mapping[str, Any]],
) -> list[str]:
    validator = Draft202012Validator(schema, registry=registry)
    errors = sorted(validator.iter_errors(payload), key=lambda err: list(err.absolute_path))
    formatted: list[str] = []
    for err in errors:
        where = ".".join(str(part) for part in err.absolute_path) or "<root>"
        formatted.append(f"{where}: {err.message}")
    return formatted


def _check_sop(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for index, step in enumerate(payload["steps"]):
        step_id = str(step["id"])
        if step_id in seen:
            errors.append(f"steps[{index}].id: duplicate step id {step_id!r}")
        seen.add(step_id)
        if int(step["idx"]) != index + 1:
            errors.append(f"steps[{index}].idx: expected {index + 1}, got {step['idx']}")
    return errors


def _check_tracks(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    video = payload["video"]
    duration_s = float(video["duration_s"])
    frame_count = int(video["frame_count"])

    seen: set[str] = set()
    for index, track in enumerate(payload["tracks"]):
        track_id = str(track["id"])
        if track_id in seen:
            errors.append(f"tracks[{index}].id: duplicate track id {track_id!r}")
        seen.add(track_id)

        first_t = float(track["first_t"])
        last_t = float(track["last_t"])
        if first_t > last_t:
            errors.append(f"tracks[{index}]: first_t ({first_t}) is after last_t ({last_t})")

        previous_frame: int | None = None
        frames: list[dict[str, Any]] = list(track["frames"])
        for frame_index, frame in enumerate(frames):
            frame_no = int(frame["frame"])
            if previous_frame is not None and frame_no <= previous_frame:
                errors.append(
                    f"tracks[{index}].frames[{frame_index}].frame: must be strictly increasing "
                    f"({frame_no} after {previous_frame})"
                )
            previous_frame = frame_no
            if frame_no >= frame_count:
                errors.append(
                    f"tracks[{index}].frames[{frame_index}].frame: {frame_no} is outside the video "
                    f"({frame_count} frames)"
                )
            if float(frame["t"]) > duration_s + TIME_TOLERANCE_S:
                errors.append(
                    f"tracks[{index}].frames[{frame_index}].t: {frame['t']} s is past the video "
                    f"duration ({duration_s} s)"
                )
            x0, y0, x1, y1 = (float(value) for value in frame["box"])
            if not (x0 < x1 and y0 < y1):
                errors.append(
                    f"tracks[{index}].frames[{frame_index}].box: expected x0 < x1 and y0 < y1, "
                    f"got [{x0}, {y0}, {x1}, {y1}]"
                )

        if frames:
            if abs(first_t - float(frames[0]["t"])) > TIME_TOLERANCE_S:
                errors.append(
                    f"tracks[{index}].first_t: {first_t} s does not match the first frame "
                    f"({frames[0]['t']} s)"
                )
            if abs(last_t - float(frames[-1]["t"])) > TIME_TOLERANCE_S:
                errors.append(
                    f"tracks[{index}].last_t: {last_t} s does not match the last frame "
                    f"({frames[-1]['t']} s)"
                )
    return errors


def _check_timeline(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    seen_events: set[str] = set()
    previous_start: float | None = None
    for index, event in enumerate(payload["events"]):
        event_id = str(event["id"])
        if event_id in seen_events:
            errors.append(f"events[{index}].id: duplicate event id {event_id!r}")
        seen_events.add(event_id)

        start = float(event["t_start"])
        end = float(event["t_end"])
        if end < start:
            errors.append(f"events[{index}]: t_end ({end}) is before t_start ({start})")
        if previous_start is not None and start < previous_start - TIME_TOLERANCE_S:
            errors.append(
                f"events[{index}].t_start: events must be sorted by t_start "
                f"({start} after {previous_start})"
            )
        previous_start = start

    previous_end: float | None = None
    for index, segment in enumerate(payload["segments"]):
        start = float(segment["t_start"])
        end = float(segment["t_end"])
        if end <= start:
            errors.append(
                f"segments[{index}]: t_end ({end}) must be greater than t_start ({start})"
            )
        if previous_end is not None and start < previous_end - TIME_TOLERANCE_S:
            errors.append(
                f"segments[{index}]: overlaps the previous segment (starts at {start}, "
                f"previous ended at {previous_end})"
            )
        previous_end = end

        if segment["kind"] == "activity":
            length = end - start
            if not (
                MIN_ACTIVITY_SEGMENT_S - TIME_TOLERANCE_S
                <= length
                <= MAX_ACTIVITY_SEGMENT_S + TIME_TOLERANCE_S
            ):
                errors.append(
                    f"segments[{index}]: activity segment is {length:.3f} s, expected "
                    f"{MIN_ACTIVITY_SEGMENT_S:g}-{MAX_ACTIVITY_SEGMENT_S:g} s"
                )

        for event_id in segment["event_ids"]:
            if str(event_id) not in seen_events:
                errors.append(f"segments[{index}].event_ids: unknown event id {event_id!r}")
    return errors


def _check_identities(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for index, identity in enumerate(payload["identities"]):
        track_id = str(identity["track_id"])
        if track_id in seen:
            errors.append(f"identities[{index}].track_id: duplicate track id {track_id!r}")
        seen.add(track_id)
    return errors


def _check_likelihoods(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for index, segment in enumerate(payload["segments"]):
        total = sum(float(value) for value in segment["step_probs"].values())
        if abs(total - 1.0) > PROB_SUM_TOLERANCE:
            errors.append(
                f"segments[{index}].step_probs: probabilities sum to {total:.3f}, "
                f"expected 1.0 +/- {PROB_SUM_TOLERANCE}"
            )
    return errors


def _check_alignment(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    seen_intervals: set[str] = set()
    for index, interval in enumerate(payload["intervals"]):
        interval_id = str(interval["id"])
        if interval_id in seen_intervals:
            errors.append(f"intervals[{index}].id: duplicate interval id {interval_id!r}")
        seen_intervals.add(interval_id)
        if float(interval["t_end"]) < float(interval["t_start"]):
            errors.append(
                f"intervals[{index}]: t_end ({interval['t_end']}) is before t_start "
                f"({interval['t_start']})"
            )
    return errors


def _check_alignment_any(payload: dict[str, Any]) -> list[str]:
    """`alignment.schema.json` holds three artifacts; dispatch on their shape."""
    if "identities" in payload:
        return _check_identities(payload)
    if "segments" in payload:
        return _check_likelihoods(payload)
    if "intervals" in payload:
        return _check_alignment(payload)
    return []


def _check_report(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    status = str(payload["status"])
    deviations: list[dict[str, Any]] = list(payload["deviations"])
    summary = payload["summary"]
    duration_s = float(payload["video"]["duration_s"])

    step_ids = {str(step["id"]) for step in payload["sop"]["steps"]}

    if status == "not_recognized" and deviations:
        errors.append("status: not_recognized requires an empty deviations list")
    if status == "done" and payload["degraded_stages"]:
        errors.append("status: done requires an empty degraded_stages list")

    seen: set[str] = set()
    counts = {"flagged": 0, "needs_review": 0}
    by_type = {"missed": 0, "out_of_order": 0, "wrong_tool": 0}
    for index, deviation in enumerate(deviations):
        deviation_id = str(deviation["id"])
        if deviation_id in seen:
            errors.append(f"deviations[{index}].id: duplicate deviation id {deviation_id!r}")
        seen.add(deviation_id)

        step_id = str(deviation["step_id"])
        if step_id not in step_ids:
            errors.append(f"deviations[{index}].step_id: unknown step id {step_id!r}")
        relates_to = deviation.get("relates_to_step_id")
        if relates_to is not None and str(relates_to) not in step_ids:
            errors.append(f"deviations[{index}].relates_to_step_id: unknown step id {relates_to!r}")

        start = float(deviation["t_start"])
        end = float(deviation["t_end"])
        if end < start:
            errors.append(f"deviations[{index}]: t_end ({end}) is before t_start ({start})")
        if end > duration_s + 0.05:
            errors.append(
                f"deviations[{index}].t_end: {end} s is past the video duration ({duration_s} s)"
            )

        explanation = str(deviation["explanation"])
        if len(explanation.split()) > MAX_EXPLANATION_WORDS:
            errors.append(
                f"deviations[{index}].explanation: {len(explanation.split())} words, "
                f"max {MAX_EXPLANATION_WORDS}"
            )

        evidence: list[dict[str, Any]] = list(deviation["evidence"])
        if not evidence and not bool(deviation["evidence_unavailable"]):
            errors.append(
                f"deviations[{index}].evidence: empty evidence requires evidence_unavailable = true"
            )
        for evidence_index, item in enumerate(evidence):
            if str(item["kind"]) != "evidence":
                errors.append(
                    f"deviations[{index}].evidence[{evidence_index}].kind: must be 'evidence'"
                )
            if str(item["deviation_id"]) != deviation_id:
                errors.append(
                    f"deviations[{index}].evidence[{evidence_index}].deviation_id: "
                    f"{item['deviation_id']!r} does not match {deviation_id!r}"
                )

        illustration = deviation.get("illustration")
        reason = deviation.get("illustration_unavailable_reason")
        if illustration is None and not reason:
            errors.append(
                f"deviations[{index}]: without an illustration, "
                f"illustration_unavailable_reason must explain why"
            )
        if illustration is not None and str(illustration["kind"]) != "illustration":
            errors.append(f"deviations[{index}].illustration.kind: must be 'illustration'")

        if str(deviation["status"]) == "flagged":
            counts["flagged"] += 1
        else:
            counts["needs_review"] += 1
        deviation_type = str(deviation["type"])
        if deviation_type in by_type:
            by_type[deviation_type] += 1

    if int(summary["flagged"]) != counts["flagged"]:
        errors.append(
            f"summary.flagged: {summary['flagged']} does not match {counts['flagged']} flagged "
            f"deviation(s)"
        )
    if int(summary["needs_review"]) != counts["needs_review"]:
        errors.append(
            f"summary.needs_review: {summary['needs_review']} does not match "
            f"{counts['needs_review']} needs_review deviation(s)"
        )
    for deviation_type, count in by_type.items():
        if int(summary["by_type"][deviation_type]) != count:
            errors.append(
                f"summary.by_type.{deviation_type}: {summary['by_type'][deviation_type]} does not "
                f"match {count} deviation(s)"
            )

    if status == "not_recognized":
        zeros = (
            int(summary["flagged"]) == 0
            and int(summary["needs_review"]) == 0
            and all(int(summary["by_type"][key]) == 0 for key in by_type)
        )
        if not zeros:
            errors.append("summary: not_recognized requires zeroed counts")
    return errors


def _check_manifest(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    created_at = str(payload["created_at"])
    finished_at = str(payload["finished_at"])
    if finished_at < created_at:
        errors.append(f"finished_at: {finished_at} is before created_at {created_at}")
    return errors


def _check_review(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for index, decision in enumerate(payload["decisions"]):
        deviation_id = str(decision["deviation_id"])
        if deviation_id in seen:
            errors.append(
                f"decisions[{index}].deviation_id: duplicate decision for {deviation_id!r} "
                f"(one latest decision per deviation)"
            )
        seen.add(deviation_id)
    return errors


def _check_thresholds(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    timeline = payload["timeline"]
    if float(timeline["seg_min_s"]) > float(timeline["seg_max_s"]):
        errors.append("timeline.seg_min_s: must not exceed seg_max_s")
    deviation = payload["deviation"]
    if float(deviation["tau_review"]) > float(deviation["tau_flag"]):
        errors.append("deviation.tau_review: must not exceed tau_flag")
    return errors


_SEMANTIC_CHECKS = {
    "sop": _check_sop,
    "tracks": _check_tracks,
    "timeline": _check_timeline,
    "identities": _check_identities,
    "likelihoods": _check_likelihoods,
    "alignment": _check_alignment_any,
    "report": _check_report,
    "manifest": _check_manifest,
    "review": _check_review,
    "thresholds": _check_thresholds,
}


def validate_payload(
    kind: str,
    payload: Any,
    contracts_dir: Path | None = None,
) -> list[str]:
    """Return a list of human-readable errors; an empty list means valid."""
    schema = load_schema(kind, contracts_dir)
    registry = _schema_registry(contracts_dir)
    errors = _schema_errors(schema, payload, registry)
    if errors:
        return [f"{kind}: {error}" for error in errors]
    if not isinstance(payload, dict):  # pragma: no cover - schema already enforced this
        return [f"{kind}: <root>: expected an object"]
    semantic = _SEMANTIC_CHECKS[kind](payload)
    return [f"{kind}: {error}" for error in semantic]


def artifact_kind(path: Path | str) -> str | None:
    """Infer the artifact kind from a file name, or None when it is not a known kind."""
    name = Path(path).name.lower()
    if "step_graph" in name or name.startswith("sop"):
        return "sop"
    if "tracks" in name:
        return "tracks"
    if "timeline" in name:
        return "timeline"
    if "identities" in name:
        return "identities"
    if "likelihoods" in name:
        return "likelihoods"
    if "alignment" in name:
        return "alignment"
    if name.startswith("report"):
        return "report"
    if name.startswith("manifest"):
        return "manifest"
    if name.startswith("review"):
        return "review"
    if "threshold" in name:
        return "thresholds"
    return None


def validate_artifact_file(
    path: Path | str,
    kind: str | None = None,
    contracts_dir: Path | None = None,
) -> tuple[str, list[str]]:
    """Validate one artifact file. Returns `(kind, errors)`."""
    resolved = kind if kind is not None else artifact_kind(path)
    if resolved is None:
        raise ValueError(
            f"cannot infer the artifact kind from {Path(path).name!r}; pass --kind explicitly"
        )
    payload = load_json(Path(path))
    return resolved, validate_payload(resolved, payload, contracts_dir)


def validate_all(contracts_dir: Path | None = None) -> list[str]:
    """Validate every schema (meta-schema) and every committed example."""
    base = contracts_dir if contracts_dir is not None else default_contracts_dir()
    errors: list[str] = []

    for schema_name in SCHEMA_NAMES:
        try:
            schema = load_schema(schema_name, base)
        except (OSError, ValueError) as exc:
            errors.append(f"{schema_name}: {exc}")
            continue
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            errors.append(f"{schema_name}: invalid JSON Schema: {exc.message}")

    for kind in KINDS:
        files = example_files(kind, base)
        if not files:
            errors.append(f"{kind}: no example files found")
            continue
        for path in files:
            errors.extend(validate_payload(kind, load_json(path), base))

    return errors


def iter_kinds() -> Iterable[str]:
    """The artifact kinds covered by the contract suite."""
    return KINDS

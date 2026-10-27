"""Validate artifacts against their JSON Schema plus the cross-field invariants.

JSON Schema covers shape and enums; it cannot express "frames strictly increasing",
"events sorted by t_start" or "segments do not overlap", so those live here.
See docs/05_Schema.md §11 (cross-field invariants).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from pw.data.schemas import (
    EXAMPLE_FILENAMES,
    KINDS,
    default_contracts_dir,
    load_json,
    load_schema,
)

TIME_TOLERANCE_S = 1e-3
"""Times are seconds with millisecond precision (AGENTS.md §4)."""

MIN_ACTIVITY_SEGMENT_S = 1.0
MAX_ACTIVITY_SEGMENT_S = 20.0


def _schema_errors(schema: dict[str, Any], payload: Any) -> list[str]:
    validator = Draft202012Validator(schema)
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


_SEMANTIC_CHECKS = {
    "sop": _check_sop,
    "tracks": _check_tracks,
    "timeline": _check_timeline,
}


def validate_payload(
    kind: str,
    payload: Any,
    contracts_dir: Path | None = None,
) -> list[str]:
    """Return a list of human-readable errors; an empty list means valid."""
    schema = load_schema(kind, contracts_dir)
    errors = _schema_errors(schema, payload)
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
    for kind in KINDS:
        try:
            schema = load_schema(kind, base)
        except (OSError, ValueError) as exc:
            errors.append(f"{kind}: {exc}")
            continue
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            errors.append(f"{kind}: invalid JSON Schema: {exc.message}")
            continue

        example_path = base / "examples" / EXAMPLE_FILENAMES[kind]
        if not example_path.is_file():
            errors.append(f"{kind}: missing example {example_path}")
            continue
        errors.extend(validate_payload(kind, load_json(example_path), base))
    return errors


def iter_kinds() -> Iterable[str]:
    """The artifact kinds covered by this task's contracts."""
    return KINDS

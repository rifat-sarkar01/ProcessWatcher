"""Prompt construction for segment → step scoring (TRD §6.6, ADR-002).

The prompt is deterministic and budgeted: step text, event excerpts and the identity
legend are clipped to fixed character limits so the same inputs always produce the same
request. Images are set-of-mark keyframes rendered elsewhere; this module only encodes
them and writes the numbered legend that maps a badge to a track id.
"""

from __future__ import annotations

import base64
import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from PIL import Image

from pw.evidence.render import FrameOverlay

NONE = "none"
PROMPT_VERSION = "score-v1"
MAX_PROMPT_CHARS = 6000
MAX_ACTION_CHARS = 200
MAX_LIST_CHARS = 120
MAX_EVENTS_CHARS = 1500
MAX_RATIONALE_CHARS = 400
MAX_KEYFRAMES = 4
MAX_IMAGES_PER_CALL = 24


@dataclass(frozen=True, slots=True)
class StepDescription:
    step_id: str
    action: str
    tools: tuple[str, ...] = ()
    parts: tuple[str, ...] = ()
    critical: bool = False


@dataclass(frozen=True, slots=True)
class SegmentDescription:
    segment_id: str
    t_start: float
    t_end: float
    event_ids: tuple[str, ...] = ()
    salient_tracks: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EventDescription:
    event_id: str
    kind: str
    t_start: float
    t_end: float
    tracks: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TrackPoint:
    frame: int
    t: float
    box: tuple[float, float, float, float]
    poly: tuple[tuple[float, float], ...] = ()


@dataclass(frozen=True, slots=True)
class TrackSample:
    track_id: str
    concept: str
    frames: tuple[TrackPoint, ...]


@dataclass(frozen=True, slots=True)
class Keyframe:
    frame: int
    image: Image.Image
    overlays: tuple[FrameOverlay, ...]


@dataclass(frozen=True, slots=True)
class PromptSegment:
    segment: SegmentDescription
    keyframes: tuple[Keyframe, ...] = ()


def clip(text: str, limit: int) -> str:
    """Deterministic truncation with an ellipsis marker."""
    clean = " ".join(text.split())
    return clean if len(clean) <= limit else clean[: max(0, limit - 1)].rstrip() + "…"


def _step_line(step: StepDescription) -> str:
    tools = clip(", ".join(step.tools) or "-", MAX_LIST_CHARS)
    parts = clip(", ".join(step.parts) or "-", MAX_LIST_CHARS)
    marker = " (critical)" if step.critical else ""
    return (
        f"{step.step_id}{marker} {clip(step.action, MAX_ACTION_CHARS)} "
        f"| tools: {tools} | parts: {parts}"
    )


def _event_line(event: EventDescription, labels: Mapping[str, str]) -> str:
    tracks = ", ".join(
        f"{track} ({labels[track]})" if track in labels else track for track in event.tracks
    )
    return f"{event.event_id} {event.kind} {event.t_start:.2f}-{event.t_end:.2f}s [{tracks}]"


def _events_excerpt(
    segment: SegmentDescription,
    events: Sequence[EventDescription],
    labels: Mapping[str, str],
) -> str:
    wanted = set(segment.event_ids)
    lines = [
        event
        for event in events
        if event.event_id in wanted or segment.t_start <= event.t_start <= segment.t_end
    ]
    if not lines:
        return "(no events)"
    text = "\n".join(_event_line(event, labels) for event in lines)
    return clip(text, MAX_EVENTS_CHARS)


def _legend(overlays: Sequence[FrameOverlay], labels: Mapping[str, str]) -> str:
    entries = []
    for number, overlay in enumerate(overlays, start=1):
        label = labels.get(overlay.track_id)
        suffix = f"={label}" if label else ""
        entries.append(f"#{number} {overlay.track_id} {overlay.concept}{suffix}")
    return "; ".join(entries) or "(no tracked objects)"


def build_text(
    batch: Sequence[PromptSegment],
    steps: Sequence[StepDescription],
    events: Sequence[EventDescription],
    identities: Mapping[str, str],
) -> str:
    lines = [
        "You score short segments of a recorded procedure against its SOP steps.",
        "For each segment, assign a probability from 0 to 1 to every step id and to "
        f"'{NONE}' (no step / idle). The probabilities for one segment must sum to 1.",
        "Attached images are numbered set-of-mark keyframes; badges inside an image match "
        "the legend below. Use them only as evidence, never invent tracks.",
        "",
        "Steps:",
        *(_step_line(step) for step in steps),
        "",
        "Segments:",
    ]
    image_number = 0
    for item in batch:
        segment = item.segment
        lines.append(
            f"- {segment.segment_id}: {segment.t_start:.2f}-{segment.t_end:.2f}s, "
            f"tracks: {', '.join(segment.salient_tracks) or '-'}"
        )
        lines.append("  events:")
        lines.extend(
            f"    {line}" for line in _events_excerpt(segment, events, identities).splitlines()
        )
        if item.keyframes:
            for keyframe in item.keyframes:
                image_number += 1
                lines.append(
                    f"  image {image_number}: frame {keyframe.frame}; "
                    f"{_legend(keyframe.overlays, identities)}"
                )
        else:
            lines.append("  (no keyframes available)")
    lines.extend(
        [
            "",
            "Return one entry per segment, in order. observed_tools may list only track ids "
            "that appear in the legends; rationale_short must be at most "
            f"{MAX_RATIONALE_CHARS} characters.",
        ]
    )
    return clip("\n".join(lines), MAX_PROMPT_CHARS)


def score_schema(steps: Sequence[StepDescription], count: int) -> dict[str, Any]:
    step_props = {step.step_id: {"type": "number", "minimum": 0, "maximum": 1} for step in steps}
    step_props[NONE] = {"type": "number", "minimum": 0, "maximum": 1}
    return {
        "type": "object",
        "properties": {
            "segments": {
                "type": "array",
                "minItems": count,
                "maxItems": count,
                "items": {
                    "type": "object",
                    "properties": {
                        "segment_id": {"type": "string"},
                        "step_probs": {
                            "type": "object",
                            "properties": step_props,
                            "required": list(step_props),
                            "additionalProperties": False,
                        },
                        "observed_tools": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "track": {"type": "string"},
                                    "label": {"type": "string", "minLength": 1},
                                    "confidence": {
                                        "type": "number",
                                        "minimum": 0,
                                        "maximum": 1,
                                    },
                                },
                                "required": ["track", "label", "confidence"],
                                "additionalProperties": False,
                            },
                        },
                        "rationale_short": {"type": "string", "maxLength": MAX_RATIONALE_CHARS},
                    },
                    "required": [
                        "segment_id",
                        "step_probs",
                        "observed_tools",
                        "rationale_short",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["segments"],
        "additionalProperties": False,
    }


def build_payload(
    batch: Sequence[PromptSegment],
    steps: Sequence[StepDescription],
    events: Sequence[EventDescription] = (),
    identities: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if not batch:
        raise ValueError("a scoring request needs at least one segment")
    text = build_text(batch, steps, events, identities or {})
    content: list[dict[str, Any]] = [{"type": "input_text", "text": text}]
    for item in batch:
        for keyframe in item.keyframes:
            buffer = io.BytesIO()
            keyframe.image.convert("RGB").save(buffer, format="PNG")
            encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
            content.append({"type": "input_image", "image_url": "data:image/png;base64," + encoded})
    return {
        "model": "muse-wonder-1.0",
        "temperature": 0,
        "reasoning": {"effort": "low"},
        "text": {
            "format": {
                "type": "json_schema",
                "name": "segment_scoring",
                "schema": score_schema(steps, len(batch)),
                "strict": True,
            }
        },
        "input": [{"role": "user", "content": content}],
    }


__all__ = [
    "MAX_ACTION_CHARS",
    "MAX_EVENTS_CHARS",
    "MAX_IMAGES_PER_CALL",
    "MAX_KEYFRAMES",
    "MAX_LIST_CHARS",
    "MAX_PROMPT_CHARS",
    "MAX_RATIONALE_CHARS",
    "NONE",
    "PROMPT_VERSION",
    "EventDescription",
    "Keyframe",
    "PromptSegment",
    "SegmentDescription",
    "StepDescription",
    "TrackPoint",
    "TrackSample",
    "build_payload",
    "build_text",
    "clip",
    "score_schema",
]

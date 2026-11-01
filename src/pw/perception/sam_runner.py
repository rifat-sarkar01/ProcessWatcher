"""SAM 3.1 chunk runner: per-chunk calls, record parsing, resume and partial chunks.

Each chunk is cut to a standalone clip (frame-exact) and sent once per concept group.
Responses are parsed into `pw.perception.stitch.ChunkTrack`s carrying global analysis
frame indices, then written to `stages/tracks_raw/<chunk_id>.json`. A rerun skips
complete chunks; partial/failed chunks are retried. Masks stay opaque until T-2.4.
"""

from __future__ import annotations

import base64
import json
import math
import re
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pw.perception.chunking import (
    DEFAULT_FRAMES_PER_CHUNK,
    DEFAULT_OVERLAP_FRAMES,
    HAND_CONCEPT,
    MAX_OBJECTS_PER_REQUEST,
    AnalysisVideo,
    ChunkingError,
    ChunkParams,
    ChunkPlan,
    ffmpeg_cut,
    group_concepts,
    plan_chunks,
)
from pw.perception.stitch import ChunkFrame, ChunkTrack

SCHEMA_VERSION = "1.0.0"
STATUS_COMPLETE = "complete"
STATUS_PARTIAL = "partial"
STATUS_FAILED = "failed"

_FRAME_HEADER = re.compile(r"^<(\d+)f(?:;[^>]*)?>(.*)$")
_BOX_RECORD = re.compile(r"([0-9]+)<\|box;([^|]*)\|>")
_BOX_KEYS = ("x1", "y1", "x2", "y2", "w", "h")

SamCaller = Callable[[Mapping[str, Any]], Mapping[str, Any]]
ChunkCutter = Callable[[AnalysisVideo, ChunkPlan, Path], bytes]


@dataclass(frozen=True, slots=True)
class ChunkOutcome:
    chunk_id: str
    status: str
    path: Path
    calls: int
    skipped: bool = False
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ChunkRunResult:
    outcomes: tuple[ChunkOutcome, ...]

    @property
    def calls(self) -> int:
        return sum(outcome.calls for outcome in self.outcomes)

    @property
    def skipped(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.skipped)

    @property
    def failed(self) -> tuple[str, ...]:
        return tuple(
            outcome.chunk_id
            for outcome in self.outcomes
            if outcome.status in (STATUS_PARTIAL, STATUS_FAILED)
        )


def build_request(video_bytes: bytes, concepts: Sequence[str]) -> dict[str, Any]:
    if not concepts:
        raise ChunkingError("a SAM request needs at least one concept")
    url = "data:video/mp4;base64," + base64.b64encode(video_bytes).decode("ascii")
    return {
        "model": "sam-3.1",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": ", ".join(concepts)},
                    {"type": "input_video", "video_url": url},
                ],
            }
        ],
        "metadata": {"mask_encoding": "one_bit"},
    }


def parse_response(
    body: Mapping[str, Any],
    *,
    plan: ChunkPlan,
    concepts: Sequence[str],
    times: Sequence[float],
) -> tuple[ChunkTrack, ...]:
    """Parse SAM records into chunk-local tracks with global frame indices."""
    text = _output_text(body)
    by_track: dict[str, tuple[str, dict[int, ChunkFrame]]] = {}
    for raw_line in text.splitlines():
        header = _FRAME_HEADER.match(raw_line.strip())
        if header is None:
            continue
        local_frame = int(header.group(1))
        global_frame = plan.frame_start + local_frame
        if global_frame >= len(times):
            continue
        for record in _BOX_RECORD.finditer(header.group(2)):
            object_id = int(record.group(1))
            if object_id >= len(concepts):
                continue
            parsed = _parse_box(record.group(2))
            if parsed is None:
                continue
            box, score = parsed
            concept = concepts[object_id]
            local_id = f"{concept}-{object_id}"
            frame = ChunkFrame(
                frame=global_frame, t=float(times[global_frame]), box=box, score=score
            )
            frames = by_track.setdefault(local_id, (concept, {}))[1]
            previous = frames.get(global_frame)
            if previous is None or frame.score > previous.score:
                frames[global_frame] = frame

    tracks: list[ChunkTrack] = []
    for local_id, (concept, frames) in sorted(by_track.items()):
        ordered = tuple(frames[index] for index in sorted(frames))
        if ordered:
            tracks.append(ChunkTrack(local_id=local_id, concept=concept, frames=ordered))
    return tuple(tracks)


def run_chunks(
    video: AnalysisVideo,
    *,
    concepts: Sequence[str],
    stage_dir: Path,
    call: SamCaller,
    params: ChunkParams | None = None,
    cutter: ChunkCutter | None = None,
    resume: bool = True,
) -> ChunkRunResult:
    settings = params or ChunkParams()
    groups = group_concepts(concepts, settings)
    plans = plan_chunks(video, settings)
    raw_dir = stage_dir / "tracks_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    cut = cutter or ffmpeg_cut
    outcomes: list[ChunkOutcome] = []

    for plan in plans:
        artifact = raw_dir / f"{plan.chunk_id}.json"
        if resume and _is_complete(artifact):
            outcomes.append(
                ChunkOutcome(
                    chunk_id=plan.chunk_id,
                    status=STATUS_COMPLETE,
                    path=artifact,
                    calls=0,
                    skipped=True,
                )
            )
            continue

        errors: list[str] = []
        tracks: list[ChunkTrack] = []
        calls = 0
        chunk_bytes: bytes | None = None
        try:
            with tempfile.TemporaryDirectory(dir=raw_dir) as temporary:
                chunk_bytes = cut(video, plan, Path(temporary) / f"{plan.chunk_id}.mp4")
        except Exception as error:
            errors.append(f"{type(error).__name__}: {error}")

        if chunk_bytes is not None:
            for group in groups:
                calls += 1
                try:
                    body = call(build_request(chunk_bytes, group))
                    tracks.extend(
                        parse_response(body, plan=plan, concepts=group, times=video.times)
                    )
                except Exception as error:
                    errors.append(f"{type(error).__name__}: {error}")

        if chunk_bytes is None:
            status = STATUS_FAILED
        elif errors:
            status = STATUS_PARTIAL
        else:
            status = STATUS_COMPLETE

        payload = _artifact(plan, status=status, tracks=tracks, calls=calls, errors=errors)
        artifact.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        outcomes.append(
            ChunkOutcome(
                chunk_id=plan.chunk_id,
                status=status,
                path=artifact,
                calls=calls,
                error="; ".join(errors) if errors else None,
            )
        )
    return ChunkRunResult(outcomes=tuple(outcomes))


def _artifact(
    plan: ChunkPlan,
    *,
    status: str,
    tracks: Sequence[ChunkTrack],
    calls: int,
    errors: Sequence[str],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "chunk_id": plan.chunk_id,
        "status": status,
        "t_start": plan.t_start,
        "t_end": plan.t_end,
        "frame_start": plan.frame_start,
        "frame_end": plan.frame_end,
        "calls": calls,
        "errors": list(errors),
        "tracks": [
            {
                "local_id": track.local_id,
                "concept": track.concept,
                "frames": [
                    {
                        "frame": frame.frame,
                        "t": frame.t,
                        "box": list(frame.box),
                        "poly": [list(point) for point in frame.poly],
                        "score": frame.score,
                    }
                    for frame in track.frames
                ],
            }
            for track in tracks
        ],
    }


def _is_complete(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(payload, dict):
        return False
    return bool(payload.get("status") == STATUS_COMPLETE)


def _output_text(body: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for item in body.get("output") or ():
        if not isinstance(item, Mapping):
            continue
        for part in item.get("content") or ():
            if isinstance(part, Mapping) and part.get("type") == "output_text":
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
    return "\n".join(parts)


def _parse_box(fields: str) -> tuple[tuple[float, float, float, float], float] | None:
    values: dict[str, float] = {}
    for part in fields.split(";"):
        key, separator, value = part.partition("=")
        if not separator:
            continue
        try:
            values[key.strip()] = float(value.strip())
        except ValueError:
            return None
    if any(key not in values for key in _BOX_KEYS):
        return None
    width = values["w"]
    height = values["h"]
    if not math.isfinite(width) or not math.isfinite(height) or width <= 0 or height <= 0:
        return None
    x1, y1, x2, y2 = (values[key] for key in _BOX_KEYS[:4])
    box = (
        _clamp(x1 / width),
        _clamp(y1 / height),
        _clamp((x2 + 1) / width),
        _clamp((y2 + 1) / height),
    )
    confidence = values.get("c", 1.0)
    score = _clamp(confidence) if math.isfinite(confidence) else 1.0
    return box, score


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


__all__ = [
    "DEFAULT_FRAMES_PER_CHUNK",
    "DEFAULT_OVERLAP_FRAMES",
    "HAND_CONCEPT",
    "MAX_OBJECTS_PER_REQUEST",
    "SCHEMA_VERSION",
    "STATUS_COMPLETE",
    "STATUS_FAILED",
    "STATUS_PARTIAL",
    "AnalysisVideo",
    "ChunkCutter",
    "ChunkOutcome",
    "ChunkParams",
    "ChunkPlan",
    "ChunkRunResult",
    "ChunkingError",
    "SamCaller",
    "build_request",
    "ffmpeg_cut",
    "group_concepts",
    "parse_response",
    "plan_chunks",
    "run_chunks",
]

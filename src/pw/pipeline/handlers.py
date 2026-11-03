"""Real pipeline stages: model-backed handlers that degrade instead of crashing.

Each handler receives a `StageRun` (run metadata plus the artifacts produced so far)
and returns a JSON payload for its stage artifact. Model calls go through `pw.clients`
or an injected callable, so `replay` runs from the client cache and tests can drive the
whole DAG with fakes. A handler that raises is isolated by the orchestrator: the stage
records a fallback artifact (marked `degraded`) and the report is built as `partial`.
"""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from PIL import Image

from pw.align.aligner import Alignment, AlignParams, Interval, Segment, StepSpec, align
from pw.align.deviations import (
    Deviation,
    HeldTool,
    IntervalObservation,
    TrackActivity,
    TrackIdentity,
    derive_deviations,
)
from pw.align.domain_guard import DomainDecision, apply_domain_guard
from pw.align.explain import explain_deviation
from pw.align.prompts import StepDescription
from pw.align.scorer import score_segments, timeline_parts, tracks_from_payload
from pw.align.verifier import VerifierParams, verify_deviations
from pw.clients import WONDER_MODEL, Clients
from pw.clients.errors import SpendCapExceeded
from pw.core.settings import Settings
from pw.data.validate import validate_payload
from pw.evidence.labeling import watermark_illustration
from pw.evidence.provenance import write_evidence
from pw.evidence.selector import FrameProvider as EvidenceFrameProvider
from pw.evidence.selector import Track as EvidenceTrack
from pw.evidence.selector import TrackSample as EvidenceSample
from pw.evidence.selector import select_all
from pw.illustrate.generator import (
    Illustration,
    IllustrationCaller,
    client_caller,
    generate_illustrations,
)
from pw.illustrate.qa import QACaller, QAOutcome, run_qa_loop
from pw.ingest.normalise import normalise_video, sha256_file, validate_source
from pw.ingest.probe import probe_video
from pw.ingest.timebase import pts_times
from pw.perception.chunking import AnalysisVideo
from pw.perception.identity import (
    IdentitiesFile,
    TrackFrame,
    TrackObservation,
    identify_tracks,
    read_identities,
    write_identities,
)
from pw.perception.sam_runner import run_chunks
from pw.perception.stitch import ChunkFrame, ChunkTrack, ChunkTracks, stitch_chunks
from pw.pipeline.concurrency import ModelLimiter
from pw.report.build import VideoMeta, build_report
from pw.sop.compiler import compile_sop
from pw.sop.ingest import read_sop
from pw.timeline.events import extract_events
from pw.timeline.features import FrameSample, Track
from pw.timeline.segments import build_segments, build_timeline

SCHEMA_VERSION = "1.0.0"
Payload = dict[str, Any]
FrameProvider = Callable[[int], Image.Image | None]
JsonCaller = Callable[[Mapping[str, Any]], Mapping[str, Any]]
TextCaller = Callable[[str], str]
StageHandler = Callable[["StageRun"], Payload]


class StageError(RuntimeError):
    """A stage cannot run with the inputs it was given."""


@dataclass
class StageServices:
    """Injected callables; `None` means "build it from `clients` when needed"."""

    compiler: TextCaller | None = None
    sam: JsonCaller | None = None
    identity: JsonCaller | None = None
    scorer: JsonCaller | None = None
    writer: TextCaller | None = None
    verifier: TextCaller | None = None
    illustrator: IllustrationCaller | None = None
    qa: QACaller | None = None
    frames: FrameProvider | None = None
    clients: Clients | None = None
    handlers: Mapping[str, StageHandler] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StageRun:
    name: str
    run_id: str
    mode: str
    created_at: str
    run_dir: Path
    stages_dir: Path
    video: Path
    sop: Path
    artifacts: Mapping[str, Payload]
    services: StageServices
    settings: Settings | None
    frames: FrameProvider
    degraded: tuple[str, ...] = ()


def _wonder_text(prompt: str) -> Payload:
    return {
        "model": WONDER_MODEL,
        "temperature": 0,
        "reasoning": {"effort": "low"},
        "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
    }


def _text_caller(services: StageServices, name: str) -> TextCaller:
    provided = getattr(services, name)
    if provided is not None:
        return cast(TextCaller, provided)
    if services.clients is None:
        raise StageError(f"{name} callable is unavailable in this mode")

    def call(prompt: str) -> str:
        assert services.clients is not None
        result = services.clients.wonder.create_response(_wonder_text(prompt), operation=name)
        return result.text or ""

    return call


def _json_caller(services: StageServices) -> JsonCaller:
    if services.clients is None:
        raise StageError("model caller is unavailable in this mode")

    def call(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        assert services.clients is not None
        return services.clients.wonder.create_response(payload).body

    return call


def _box(values: Sequence[Any]) -> tuple[float, float, float, float]:
    if len(values) != 4:
        raise StageError(f"box must have four numbers, got {len(values)}")
    x1, y1, x2, y2 = (float(value) for value in values)
    return (x1, y1, x2, y2)


def _require(payloads: Mapping[str, Payload], name: str) -> Payload:
    payload = payloads.get(name)
    if payload is None:
        raise StageError(f"missing input artifact: {name}")
    return payload


def _steps(graph: Payload) -> list[Mapping[str, Any]]:
    steps = graph.get("steps")
    if not isinstance(steps, list):
        raise StageError("step graph has no steps")
    return [step for step in steps if isinstance(step, Mapping)]


def _vocabulary(graph: Payload) -> list[str]:
    labels: list[str] = []
    for step in _steps(graph):
        for key in ("tools", "parts"):
            for value in step.get(key, ()):
                text = str(value).strip()
                if text and text.casefold() not in {item.casefold() for item in labels}:
                    labels.append(text)
    vocabulary = graph.get("vocabulary")
    if isinstance(vocabulary, Mapping):
        for concept in vocabulary.get("sam_concepts", ()):
            text = str(concept).strip()
            if text and text.casefold() not in {item.casefold() for item in labels}:
                labels.append(text)
    return labels


def _step_specs(graph: Payload) -> list[StepSpec]:
    return [
        StepSpec(
            step_id=str(step.get("id")),
            idx=int(step.get("idx", position)),
            critical=step.get("critical") is True,
            group_id=str(step["group_id"]) if step.get("group_id") else None,
        )
        for position, step in enumerate(_steps(graph), start=1)
    ]


def _step_descriptions(graph: Payload) -> list[StepDescription]:
    return [
        StepDescription(
            step_id=str(step.get("id")),
            action=str(step.get("action") or step.get("text") or ""),
            tools=tuple(str(tool) for tool in step.get("tools", ())),
            parts=tuple(str(part) for part in step.get("parts", ())),
            critical=step.get("critical") is True,
        )
        for step in _steps(graph)
    ]


def _tools_by_step(graph: Payload) -> dict[str, list[str]]:
    return {
        str(step.get("id")): [str(tool) for tool in step.get("tools", ())] for step in _steps(graph)
    }


def _step_text(graph: Payload, step_id: str) -> tuple[int, str]:
    for step in _steps(graph):
        if str(step.get("id")) == step_id:
            return int(step.get("idx", 0)), str(step.get("text", ""))
    return 0, ""


def _analysis_from(ingest: Payload, run_dir: Path) -> AnalysisVideo:
    analysis = ingest.get("analysis")
    if not isinstance(analysis, Mapping):
        raise StageError("ingest artifact has no analysis block")
    path = Path(str(analysis.get("path")))
    if not path.is_absolute():
        path = run_dir / path
    if not path.is_file():
        raise StageError(f"analysis video is missing: {path}")
    return AnalysisVideo(
        path=path,
        fps=float(analysis["fps"]),
        times=tuple(pts_times(path)),
    )


# --- ingest -----------------------------------------------------------------


def handle_ingest(run: StageRun) -> Payload:
    info = probe_video(run.video)
    validate_source(run.video, info)
    analysis_path = run.run_dir / "media" / "analysis.mp4"
    normalised = normalise_video(run.video, analysis_path)
    analysis = AnalysisVideo.from_normalised(normalised)
    duration = round(analysis.times[-1] + 1.0 / analysis.fps, 4)
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run.run_id,
        "stage": "ingest",
        "mode": run.mode,
        "source": {
            "name": run.video.name,
            "sha256": sha256_file(run.video),
            "bytes": run.video.stat().st_size,
        },
        "analysis": {
            "path": str(analysis_path.resolve()),
            "fps": analysis.fps,
            "frame_count": analysis.frame_count,
        },
        "video": {
            "sha256": sha256_file(analysis_path),
            "duration_s": duration,
            "analysis_fps": analysis.fps,
            "width": normalised.info.width,
            "height": normalised.info.height,
            "frame_count": analysis.frame_count,
        },
        "degraded": False,
    }


# --- sop_compile ------------------------------------------------------------


def handle_sop_compile(run: StageRun) -> Payload:
    source = read_sop(run.sop)
    result = compile_sop(source, compiler=_text_caller(run.services, "compiler"))
    return result.graph


# --- perceive ---------------------------------------------------------------


def _load_chunks(paths: Sequence[Path]) -> list[ChunkTracks]:
    chunks: list[ChunkTracks] = []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        tracks: list[ChunkTrack] = []
        for raw in payload.get("tracks", ()):
            frames = tuple(
                ChunkFrame(
                    frame=int(frame["frame"]),
                    t=float(frame["t"]),
                    box=_box(frame["box"]),
                    poly=tuple(
                        (float(point[0]), float(point[1])) for point in frame.get("poly", ())
                    ),
                    score=float(frame.get("score", 1.0)),
                )
                for frame in raw.get("frames", ())
            )
            if frames:
                tracks.append(
                    ChunkTrack(
                        local_id=str(raw["local_id"]),
                        concept=str(raw["concept"]),
                        frames=frames,
                    )
                )
        chunks.append(
            ChunkTracks(
                chunk_id=str(payload.get("chunk_id", path.stem)),
                t_start=float(payload.get("t_start", 0.0)),
                t_end=float(payload.get("t_end", 0.0)),
                tracks=tuple(tracks),
            )
        )
    return chunks


def handle_perceive(run: StageRun) -> Payload:
    analysis = _analysis_from(_require(run.artifacts, "ingest"), run.run_dir)
    graph = _require(run.artifacts, "sop_compile")
    concepts = _vocabulary(graph)
    sam = run.services.sam
    if sam is None:
        if run.services.clients is None:
            raise StageError("SAM caller is unavailable in this mode")

        def sam(payload: Mapping[str, Any]) -> Mapping[str, Any]:
            assert run.services.clients is not None
            return run.services.clients.sam.segment(payload).body

    with ModelLimiter() as limiter:
        outcome = run_chunks(
            analysis,
            concepts=concepts,
            stage_dir=run.stages_dir,
            call=sam,
            resume=True,
            limiter=limiter,
        )
    chunks = _load_chunks([item.path for item in outcome.outcomes])
    stitched = stitch_chunks(chunks)
    ingest = _require(run.artifacts, "ingest")
    payload = stitched.to_artifact(run_id=run.run_id, video=dict(ingest["video"]))
    errors = validate_payload("tracks", payload)
    if errors:
        raise StageError("; ".join(errors))
    payload["degraded"] = bool(outcome.failed)
    return payload


# --- timeline ---------------------------------------------------------------


def _timeline_tracks(payload: Payload) -> list[Track]:
    tracks: list[Track] = []
    for raw in payload.get("tracks", ()):
        frames = tuple(
            FrameSample(
                frame=int(frame["frame"]),
                t=float(frame["t"]),
                box=_box(frame["box"]),
                poly=tuple((float(point[0]), float(point[1])) for point in frame.get("poly", ())),
                score=float(frame.get("score", 1.0)),
            )
            for frame in raw.get("frames", ())
        )
        if frames:
            tracks.append(Track(id=str(raw["id"]), concept=str(raw["concept"]), frames=frames))
    return tracks


def handle_timeline(run: StageRun) -> Payload:
    ingest = _require(run.artifacts, "ingest")
    tracks = _timeline_tracks(_require(run.artifacts, "perceive"))
    events = extract_events(tracks)
    duration = float(ingest["video"]["duration_s"])
    segments = build_segments(events, duration_s=duration)
    return build_timeline(events, segments, run.run_id)


# --- identify ---------------------------------------------------------------


def _identity_tracks(payload: Payload) -> list[TrackObservation]:
    tracks: list[TrackObservation] = []
    for raw in payload.get("tracks", ()):
        frames = tuple(
            TrackFrame(
                frame=int(frame["frame"]),
                box=_box(frame["box"]),
                score=float(frame.get("score", 1.0)),
            )
            for frame in raw.get("frames", ())
        )
        if frames:
            tracks.append(
                TrackObservation(
                    track_id=str(raw["id"]),
                    concept=str(raw["concept"]),
                    frames=frames,
                )
            )
    return tracks


def handle_identify(run: StageRun) -> Payload:
    graph = _require(run.artifacts, "sop_compile")
    tracks = _identity_tracks(_require(run.artifacts, "perceive"))
    target = run.stages_dir / "identities.json"
    existing = read_identities(target)
    identity_call = run.services.identity or _json_caller(run.services)
    with ModelLimiter() as limiter:
        result = identify_tracks(
            tracks,
            frame_provider=run.frames,
            vocabulary=_vocabulary(graph),
            call=identity_call,
            existing=existing,
            limiter=limiter,
        )
    payload = IdentitiesFile(identities=result.identities, run_id=run.run_id).to_payload()
    write_identities(target, IdentitiesFile(result.identities, run_id=run.run_id))
    return payload


# --- score ------------------------------------------------------------------


def handle_score(run: StageRun) -> Payload:
    graph = _require(run.artifacts, "sop_compile")
    timeline = _require(run.artifacts, "timeline")
    tracks = _require(run.artifacts, "perceive")
    segments, events = timeline_parts(timeline)
    identities = {
        track_id: result.label
        for track_id, result in read_identities(run.stages_dir / "identities.json").items()
    }
    scorer = run.services.scorer or _json_caller(run.services)
    result = score_segments(
        segments,
        _step_descriptions(graph),
        tracks=tracks_from_payload(tracks),
        events=events,
        frame_provider=run.frames,
        call=scorer,
        identities=identities,
    )
    path = run.stages_dir / "likelihoods.json"
    result.write(path, run_id=run.run_id)
    return cast(Payload, json.loads(path.read_text(encoding="utf-8")))


# --- align ------------------------------------------------------------------


def _segments_for_alignment(timeline: Payload, likelihoods: Payload) -> list[Segment]:
    bounds = {
        str(segment["id"]): (float(segment["t_start"]), float(segment["t_end"]))
        for segment in timeline.get("segments", ())
    }
    probs = {
        str(item["segment_id"]): {
            str(key): float(value) for key, value in item["step_probs"].items()
        }
        for item in likelihoods.get("segments", ())
    }
    segments: list[Segment] = []
    for segment_id, (start, end) in bounds.items():
        if segment_id in probs:
            segments.append(
                Segment(segment_id=segment_id, t_start=start, t_end=end, probs=probs[segment_id])
            )
    return segments


def _alignment_from_payload(payload: Payload) -> Alignment:
    params = payload.get("params")
    return Alignment(
        path=tuple(
            (str(item["segment_id"]), str(item["step_id"])) for item in payload.get("path", ())
        ),
        intervals=tuple(
            Interval(
                id=str(item["id"]),
                step_id=str(item["step_id"]),
                t_start=float(item["t_start"]),
                t_end=float(item["t_end"]),
                segment_ids=tuple(str(value) for value in item.get("segment_ids", ())),
                mean_prob=float(item["mean_prob"]),
                margin=float(item["margin"]),
            )
            for item in payload.get("intervals", ())
        ),
        total_cost=float(payload["cost"]["total"]),
        per_segment_cost=float(payload["cost"]["per_segment"]),
        coverage=float(payload["cost"]["coverage"]),
        params=AlignParams(**dict(params)) if isinstance(params, Mapping) else AlignParams(),
    )


def _decision(alignment: Alignment) -> DomainDecision:
    return apply_domain_guard(alignment)


def handle_align(run: StageRun) -> Payload:
    timeline = _require(run.artifacts, "timeline")
    likelihoods = _require(run.artifacts, "score")
    graph = _require(run.artifacts, "sop_compile")
    aligned = align(_segments_for_alignment(timeline, likelihoods), _step_specs(graph))
    decision = _decision(aligned)
    payload = aligned.to_artifact(run_id=run.run_id)
    cost = payload["cost"]
    if isinstance(cost, dict):
        cost["total"] = max(0.0, float(cost["total"]))
        cost["per_segment"] = max(0.0, float(cost["per_segment"]))
    payload["status"] = "ok" if decision.recognized else "procedure_not_recognized"
    errors = validate_payload("alignment", payload)
    if errors:
        raise StageError("; ".join(errors))
    return payload


# --- deviations -------------------------------------------------------------


def _activity(tracks: Payload, duration_s: float) -> list[TrackActivity]:
    """Track presence, extended to the analysed duration: a track last seen before the
    final frame still exists when a deviation window ends at the video boundary."""
    activity: list[TrackActivity] = []
    for raw in tracks.get("tracks", ()):
        frames = raw.get("frames") or ()
        if not frames:
            continue
        activity.append(
            TrackActivity(
                track_id=str(raw["id"]),
                t_start=min(0.0, float(frames[0]["t"])),
                t_end=max(duration_s, float(frames[-1]["t"])),
            )
        )
    return activity


def _windows(
    events: Sequence[Mapping[str, Any]], kind: str
) -> list[tuple[frozenset[str], float, float]]:
    open_windows: dict[frozenset[str], float] = {}
    windows: list[tuple[frozenset[str], float, float]] = []
    for event in events:
        if event.get("type") not in {f"{kind}_start", f"{kind}_end"}:
            continue
        key = frozenset(str(value) for value in event.get("tracks", ()))
        t = float(event.get("t_start", 0.0))
        if event["type"] == f"{kind}_start":
            open_windows[key] = min(t, open_windows.get(key, t))
        elif key in open_windows:
            windows.append((key, open_windows.pop(key), max(t, event.get("t_start", t))))
    for key, start in open_windows.items():
        windows.append((key, start, start))
    return windows


def _observations(
    timeline: Payload, alignment: Alignment, tracks: Payload
) -> list[IntervalObservation]:
    events = [event for event in timeline.get("events", ()) if isinstance(event, Mapping)]
    contacts = _windows(events, "contact")
    holds = _windows(events, "hold")
    concepts = {str(raw["id"]): str(raw["concept"]) for raw in tracks.get("tracks", ())}
    observations: list[IntervalObservation] = []
    for interval in alignment.intervals:
        contact_s = 0.0
        for _, start, end in contacts:
            overlap = min(end, interval.t_end) - max(start, interval.t_start)
            contact_s = max(contact_s, overlap)
        held: list[HeldTool] = []
        for key, start, end in holds:
            overlap = min(end, interval.t_end) - max(start, interval.t_start)
            if overlap <= 0:
                continue
            for track_id in key:
                if concepts.get(track_id) != "hand":
                    held.append(HeldTool(track_id=track_id, held_s=round(overlap, 4)))
        observations.append(
            IntervalObservation(
                interval_id=interval.id,
                contact_s=round(max(0.0, contact_s), 4),
                held=tuple(held),
            )
        )
    return observations


def _deviation_payload(deviation: Deviation) -> Payload:
    return {
        "id": deviation.id,
        "type": deviation.type,
        "status": deviation.status,
        "severity": deviation.severity,
        "step_id": deviation.step_id,
        "t_start": deviation.t_start,
        "t_end": deviation.t_end,
        "track_ids": list(deviation.track_ids),
        "confidence": deviation.confidence,
        "margin": deviation.margin,
        "relates_to_step_id": deviation.relates_to_step_id,
        "expected_tools": list(deviation.expected_tools),
        "observed_tools": list(deviation.observed_tools),
    }


def _deviations_from_payload(payload: Payload) -> tuple[Deviation, ...]:
    return tuple(
        Deviation(
            id=str(item["id"]),
            type=item["type"],
            status=item["status"],
            severity=item["severity"],
            step_id=str(item["step_id"]),
            t_start=float(item["t_start"]),
            t_end=float(item["t_end"]),
            track_ids=tuple(str(value) for value in item["track_ids"]),
            confidence=float(item["confidence"]),
            margin=float(item["margin"]),
            relates_to_step_id=item.get("relates_to_step_id"),
            expected_tools=tuple(str(value) for value in item.get("expected_tools", ())),
            observed_tools=tuple(str(value) for value in item.get("observed_tools", ())),
        )
        for item in payload.get("deviations", ())
    )


def handle_deviations(run: StageRun) -> Payload:
    alignment = _alignment_from_payload(_require(run.artifacts, "align"))
    decision = _decision(alignment)
    payload: Payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run.run_id,
        "status": decision.status,
        "deviations": [],
    }
    if decision.recognized:
        graph = _require(run.artifacts, "sop_compile")
        timeline = _require(run.artifacts, "timeline")
        tracks = _require(run.artifacts, "perceive")
        ingest = _require(run.artifacts, "ingest")
        identities = {
            track_id: TrackIdentity(label=result.label, confidence=result.confidence)
            for track_id, result in read_identities(run.stages_dir / "identities.json").items()
        }
        found = derive_deviations(
            alignment,
            _segments_for_alignment(timeline, _require(run.artifacts, "score")),
            _step_specs(graph),
            identities=identities,
            tools_by_step=_tools_by_step(graph),
            activity=_activity(tracks, float(ingest["video"]["duration_s"])),
            observations=_observations(timeline, alignment, tracks),
        )
        payload["deviations"] = [_deviation_payload(deviation) for deviation in found]
    return payload


# --- verify -----------------------------------------------------------------


def handle_verify(run: StageRun) -> Payload:
    graph = _require(run.artifacts, "sop_compile")
    deviations = _deviations_from_payload(_require(run.artifacts, "deviations"))
    enabled = run.settings is None or not run.settings.disable_verifier
    try:
        verifier = _text_caller(run.services, "verifier")
    except StageError:
        verifier = _failing_verifier
    result = verify_deviations(
        deviations, verifier=verifier, params=VerifierParams(enabled=enabled)
    )
    explanations: dict[str, str] = {}
    if run.services.writer is not None or run.services.clients is not None:
        writer = _text_caller(run.services, "writer")
        for deviation in result.deviations:
            index, text = _step_text(graph, deviation.step_id)
            explanation = explain_deviation(
                deviation,
                writer=writer,
                vocabulary=_vocabulary(graph),
                step_index=index,
                step_text=text,
            )
            explanations[deviation.id] = explanation.text
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run.run_id,
        "deviations": [_deviation_payload(deviation) for deviation in result.deviations],
        "verifiers": result.verifiers,
        "explanations": explanations,
    }


def _failing_verifier(prompt: str) -> str:
    raise StageError("verifier is disabled in this mode")


# --- evidence ---------------------------------------------------------------


def _required_frames(provider: FrameProvider) -> Callable[[int], Image.Image]:
    def get(index: int) -> Image.Image:
        image = provider(index)
        if image is None:
            raise StageError(f"frame {index} could not be decoded")
        return image

    return get


def handle_evidence(run: StageRun) -> Payload:
    ingest = _require(run.artifacts, "ingest")
    alignment = _alignment_from_payload(_require(run.artifacts, "align"))
    deviations = _deviations_from_payload(_require(run.artifacts, "verify"))
    payload = _require(run.artifacts, "perceive")
    tracks = [
        EvidenceTrack(
            track_id=str(raw["id"]),
            concept=str(raw["concept"]),
            frames=tuple(
                EvidenceSample(
                    frame=int(frame["frame"]),
                    t=float(frame["t"]),
                    box=_box(frame["box"]),
                    poly=tuple(
                        (float(point[0]), float(point[1])) for point in frame.get("poly", ())
                    ),
                    score=float(frame.get("score", 1.0)),
                )
                for frame in raw.get("frames", ())
            ),
        )
        for raw in payload.get("tracks", ())
        if raw.get("frames")
    ]
    selections = select_all(
        deviations,
        tracks=tracks,
        alignment=alignment,
        frames=cast(EvidenceFrameProvider, _required_frames(run.frames)),
    )
    items = write_evidence(
        selections,
        run_dir=run.run_dir,
        source_sha256=str(ingest["video"]["sha256"]),
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run.run_id,
        "available": any(selection.available for selection in selections),
        "evidence": list(items),
        "reasons": {
            selection.deviation_id: selection.reason for selection in selections if selection.reason
        },
    }


# --- illustrate -------------------------------------------------------------


def _illustration_payload(
    run: StageRun,
    illustrations: Mapping[str, Any],
    reasons: Mapping[str, str],
    *,
    disabled: bool,
) -> Payload:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run.run_id,
        "illustrations": dict(illustrations),
        "reasons": dict(reasons),
        "disabled": disabled,
    }


def _illustration_references(evidence: Mapping[str, Any], run_dir: Path) -> dict[str, bytes]:
    references: dict[str, bytes] = {}
    for item in evidence.get("evidence", ()):
        if not isinstance(item, Mapping):
            continue
        deviation_id = item.get("deviation_id")
        relative = item.get("output_path")
        if not isinstance(deviation_id, str) or not isinstance(relative, str):
            continue
        path = run_dir / relative
        if path.is_file():
            references[deviation_id] = path.read_bytes()
    return references


def _write_illustration(run: StageRun, item: Illustration, qa: QAOutcome) -> dict[str, Any]:
    assert item.image is not None and qa.image is not None
    target_dir = run.run_dir / "illustrations"
    target_dir.mkdir(parents=True, exist_ok=True)
    image = Image.open(io.BytesIO(qa.image)).convert("RGB")
    marked = watermark_illustration(image)
    path = target_dir / f"{item.id}.png"
    marked.save(path)
    return {
        "kind": "illustration",
        "path": path.relative_to(run.run_dir).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "watermark": True,
        "qa": qa.to_report(),
    }


def handle_illustrate(run: StageRun) -> Payload:
    """Generate, QA and watermark one diagram per flagged step (T-4.3/T-4.4)."""
    verified = _deviations_from_payload(_require(run.artifacts, "verify"))
    graph = _require(run.artifacts, "sop_compile")
    disabled = run.settings.disable_illustrations if run.settings is not None else None
    if disabled:
        return _illustration_payload(run, {}, {}, disabled=True)

    image_call = run.services.illustrator
    qa_call = run.services.qa
    clients = run.services.clients
    if image_call is None and clients is not None:
        image_call = client_caller(clients.image)
    if qa_call is None and clients is not None:

        def wonder_qa(payload: Mapping[str, Any]) -> Mapping[str, Any]:
            return clients.wonder.create_response(payload).body

        qa_call = wonder_qa
    if image_call is None or qa_call is None:
        return _illustration_payload(run, {}, {}, disabled=True)

    cap_errors: list[SpendCapExceeded] = []

    def call_image(prompt: str, reference: bytes | None) -> bytes:
        try:
            return image_call(prompt, reference)
        except SpendCapExceeded as error:
            cap_errors.append(error)
            raise

    def call_qa(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            return qa_call(payload)
        except SpendCapExceeded as error:
            cap_errors.append(error)
            raise

    references = _illustration_references(run.artifacts.get("evidence") or {}, run.run_dir)
    generated = generate_illustrations(
        verified,
        graph,
        call=call_image,
        references=references,
        cache_dir=run.stages_dir / "illustration_cache",
        disabled=False,
    )
    if cap_errors:
        raise cap_errors[0]

    steps = {
        str(step.get("id")): step for step in graph.get("steps", ()) if isinstance(step, Mapping)
    }
    illustrations: dict[str, Any] = {}
    reasons: dict[str, str] = {}
    for item in generated.items:
        if item.image is None:
            for deviation_id in item.deviation_ids:
                reasons[deviation_id] = item.reason or "illustration_unavailable: generation failed"
            continue
        step = steps.get(item.step_id)
        if step is None:
            for deviation_id in item.deviation_ids:
                reasons[deviation_id] = "illustration_unavailable: step missing"
            continue

        reference = next(
            (
                references[deviation_id]
                for deviation_id in item.deviation_ids
                if deviation_id in references
            ),
            None,
        )

        def regenerate(
            _attempt: int,
            prompt: str = item.prompt,
            source: bytes | None = reference,
        ) -> bytes | None:
            try:
                return image_call(prompt, source)
            except SpendCapExceeded as error:
                cap_errors.append(error)
                return None
            except Exception:  # a failed regeneration degrades, like the first call
                return None

        outcome = run_qa_loop(step, first_image=item.image, regenerate=regenerate, call=call_qa)
        if cap_errors:
            raise cap_errors[0]
        if outcome.verdict != "pass" or outcome.image is None:
            reason = outcome.reason or "illustration_unavailable: qa failed"
            for deviation_id in item.deviation_ids:
                reasons[deviation_id] = reason
            continue

        block = _write_illustration(run, item, outcome)
        for deviation_id in item.deviation_ids:
            illustrations[deviation_id] = {
                "id": f"ill_{len(illustrations) + 1:03d}",
                **block,
            }
    return _illustration_payload(run, illustrations, reasons, disabled=False)


# --- report -----------------------------------------------------------------


def handle_report(run: StageRun) -> Payload:
    graph = _require(run.artifacts, "sop_compile")
    ingest = _require(run.artifacts, "ingest")
    alignment = _alignment_from_payload(_require(run.artifacts, "align"))
    verify = _require(run.artifacts, "verify")
    evidence_payload = _require(run.artifacts, "evidence")
    illustrate = _require(run.artifacts, "illustrate")
    decision = _decision(alignment)
    video = ingest["video"]
    report = build_report(
        run_id=run.run_id,
        created_at=run.created_at,
        sop=graph,
        video=VideoMeta(
            sha256=str(video["sha256"]),
            duration_s=float(video["duration_s"]),
            width=int(video["width"]),
            height=int(video["height"]),
        ),
        alignment=alignment,
        deviations=_deviations_from_payload(verify),
        evidence=[
            item for item in evidence_payload.get("evidence", ()) if isinstance(item, Mapping)
        ],
        explanations=dict(verify.get("explanations", {})),
        verifiers=dict(verify.get("verifiers", {})),
        illustrations=dict(illustrate.get("illustrations", {})),
        illustration_reasons=dict(illustrate.get("reasons", {})),
        domain=None if decision.recognized else decision,
        degraded_stages=run.degraded,
    )
    return report


REAL_HANDLERS: dict[str, StageHandler] = {
    "ingest": handle_ingest,
    "sop_compile": handle_sop_compile,
    "perceive": handle_perceive,
    "timeline": handle_timeline,
    "identify": handle_identify,
    "score": handle_score,
    "align": handle_align,
    "deviations": handle_deviations,
    "verify": handle_verify,
    "evidence": handle_evidence,
    "illustrate": handle_illustrate,
    "report": handle_report,
}


def fallback_payload(stage: str, run: StageRun) -> Payload | None:
    """Shape-preserving empty artifact for a failed stage; `None` means fatal."""
    video: Payload = {}
    ingest = run.artifacts.get("ingest")
    if ingest is not None:
        video = dict(ingest.get("video", {}))
    if stage == "perceive":
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": run.run_id,
            "video": video,
            "tracks": [],
            "degraded": True,
        }
    if stage == "timeline":
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": run.run_id,
            "events": [],
            "segments": [],
        }
    if stage == "identify":
        return {"schema_version": SCHEMA_VERSION, "run_id": run.run_id, "identities": []}
    if stage == "score":
        return {"schema_version": SCHEMA_VERSION, "run_id": run.run_id, "segments": []}
    if stage == "align":
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": run.run_id,
            "path": [],
            "intervals": [],
            "cost": {"total": 0.0, "per_segment": 0.0, "coverage": 0.0},
            "params": AlignParams().as_dict(),
            "status": "procedure_not_recognized",
        }
    if stage == "deviations":
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": run.run_id,
            "status": "not_recognized",
            "deviations": [],
        }
    if stage == "verify":
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": run.run_id,
            "deviations": [],
            "verifiers": {},
            "explanations": {},
        }
    if stage == "evidence":
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": run.run_id,
            "available": False,
            "evidence": [],
            "reasons": {},
        }
    if stage == "illustrate":
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": run.run_id,
            "illustrations": {},
            "reasons": {},
            "disabled": True,
        }
    return None


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


__all__ = [
    "REAL_HANDLERS",
    "FrameProvider",
    "StageError",
    "StageHandler",
    "StageRun",
    "StageServices",
    "fallback_payload",
    "handle_align",
    "handle_deviations",
    "handle_evidence",
    "handle_identify",
    "handle_illustrate",
    "handle_ingest",
    "handle_perceive",
    "handle_report",
    "handle_score",
    "handle_sop_compile",
    "handle_timeline",
    "handle_verify",
    "utc_now",
]

"""Pipeline runner: the fake skeleton and the real, degrading stage DAG.

Each stage output lands in `runs/<id>/stages/<artifact>` next to a `<stage>.key` file
holding `sha256(stage_version ‖ input hashes ‖ config hash)`. A rerun with the same key
is a no-op, as `docs/04_TRD.md` §3 requires. Real runs route every model call through
`pw.clients`; a failed stage writes a shape-preserving fallback marked `degraded`, is
listed in the report's `degraded_stages`, and never crashes the run. `SpendCapExceeded`
stops the model-backed stages, keeps the deterministic ones and still writes a partial
report (02_AppFlow E-08).
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import Any

from pw import __version__
from pw.clients import DEFAULT_BASE_URL, build_clients
from pw.clients.errors import SpendCapExceeded
from pw.core.ledger import RunLedger
from pw.core.settings import ConfigError, Settings, load_settings
from pw.data.validate import validate_payload
from pw.pipeline.frames import VideoFrames
from pw.pipeline.handlers import (
    REAL_HANDLERS,
    FrameProvider,
    StageError,
    StageRun,
    StageServices,
    fallback_payload,
    utc_now,
)
from pw.pipeline.runstore import (
    REPORT_NAME,
    RunPaths,
    create_run,
    runs_root,
)
from pw.pipeline.stages import (
    FAKE_STAGES,
    SCHEMA_VERSION,
    STAGE_VERSION,
    StageContext,
    StageSpec,
    fake_artifact,
)

logger = logging.getLogger("pw.pipeline")

MODEL_STAGES = frozenset({"perceive", "identify", "score", "verify", "illustrate"})
FATAL_STAGES = frozenset({"ingest", "sop_compile", "report"})
MANIFEST_NAME = "manifest.json"
MODEL_MODELS = (
    {
        "name": "muse-wonder-1.0",
        "version_or_date": "2026-11-02",
        "endpoint": f"{DEFAULT_BASE_URL}/responses",
    },
    {
        "name": "sam-3.1",
        "version_or_date": "3.1",
        "endpoint": f"{DEFAULT_BASE_URL}/responses",
    },
)
ProgressCallback = Callable[[dict[str, Any]], None]


class PipelineError(Exception):
    """A typed pipeline failure; `exit_code` is the CLI exit status."""

    def __init__(self, message: str, *, exit_code: int = 2) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(frozen=True, slots=True)
class StageOutcome:
    name: str
    artifact: Path
    key: str
    cached: bool
    status: str = "ok"
    cost_usd: float = 0.0
    duration_ms: int = 0


@dataclass(frozen=True, slots=True)
class RunResult:
    run_id: str
    run_dir: Path
    stages: tuple[StageOutcome, ...]
    degraded: tuple[str, ...] = ()
    cap_reached: bool = False

    @property
    def cached(self) -> int:
        return sum(1 for stage in self.stages if stage.cached)


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _payload_hash(payload: Mapping[str, Any]) -> str:
    return sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def stage_key(
    stage: StageSpec,
    *,
    mode: str,
    video_hash: str,
    sop_hash: str,
    artifacts: Mapping[str, Mapping[str, Any]],
    graph_hash: str = "",
) -> str:
    material = {
        "stage_version": STAGE_VERSION,
        "stage": stage.name,
        "mode": mode,
        "video": video_hash,
        "sop": sop_hash,
        "inputs": {name: _payload_hash(artifacts[name]) for name in stage.depends},
    }
    if graph_hash:
        material["graph_hash"] = graph_hash
    return sha256(json.dumps(material, sort_keys=True).encode("utf-8")).hexdigest()


def _cached(artifact: Path, key_file: Path, key: str) -> bool:
    if not artifact.is_file() or not key_file.is_file():
        return False
    return key_file.read_text(encoding="utf-8").strip() == key


def _write_payload(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise StageError(f"{path} is not a JSON object")
    return payload


def _emit(callback: ProgressCallback | None, event: Mapping[str, Any]) -> None:
    if callback is not None:
        callback(dict(event))


def _git_commit() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown0"
    value = completed.stdout.strip()
    return value if len(value) >= 7 else "unknown0"


def _config_hash() -> str:
    path = Path(__file__).resolve().parents[3] / "config" / "thresholds.json"
    if path.is_file():
        return sha256(path.read_bytes()).hexdigest()
    return sha256(b"defaults-v1").hexdigest()


def _models() -> list[dict[str, str]]:
    return [dict(model) for model in MODEL_MODELS]


def _manifest_status(status: str) -> str:
    if status == "ok":
        return "ok"
    return "skipped" if status == "skipped" else "failed"


def build_manifest(
    *,
    run_id: str,
    created_at: str,
    finished_at: str,
    mode: str,
    inputs: Mapping[str, Any],
    outcomes: list[StageOutcome],
    ledger: RunLedger,
    cap_reached: bool,
) -> dict[str, Any]:
    entries = ledger.entries
    by_model: dict[str, float] = {}
    for entry in entries:
        by_model[entry.model] = round(by_model.get(entry.model, 0.0) + entry.usd, 8)
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "created_at": created_at,
        "finished_at": finished_at,
        "mode": mode,
        "inputs": dict(inputs),
        "models": _models(),
        "config_sha256": _config_hash(),
        "stages": [
            {
                "stage": outcome.name,
                "status": _manifest_status(outcome.status),
                "started_at": finished_at,
                "duration_ms": outcome.duration_ms,
                "cache_hit": outcome.cached,
                "cost_usd": round(outcome.cost_usd, 8),
            }
            for outcome in outcomes
        ],
        "ledger": {
            "total_usd": round(sum(entry.usd for entry in entries), 8),
            "by_model": by_model,
            "calls": len(entries),
            "cache_hits": sum(1 for entry in entries if entry.cache_hit),
            "spend_cap_usd": ledger.cap_usd,
            "cap_reached": cap_reached,
        },
        "dropped_candidates": 0,
        "git_commit": _git_commit(),
        "app_version": __version__,
    }


def _build_settings(mode: str, settings: Settings | None) -> Settings | None:
    if settings is not None:
        return settings
    if mode == "fake":
        return None
    try:
        return load_settings()
    except ConfigError as error:
        raise PipelineError(str(error), exit_code=2) from error


def _build_services(
    mode: str,
    settings: Settings | None,
    services: StageServices,
    ledger: RunLedger,
) -> StageServices:
    if mode == "fake" or services.clients is not None:
        return services
    api_key = settings.meta_api_key if settings is not None else ""
    if mode == "live" and not api_key:
        raise PipelineError("live mode needs META_API_KEY; set it in .env", exit_code=2)
    try:
        clients = build_clients(mode=mode, ledger=ledger, api_key=api_key)
    except Exception as error:  # missing key / unsupported mode surfaces as a typed error
        raise PipelineError(str(error), exit_code=2) from error
    return replace(services, clients=clients)


def run_pipeline(
    *,
    video: Path,
    sop: Path,
    mode: str = "fake",
    runs_dir: Path | None = None,
    run_id: str | None = None,
    services: StageServices | None = None,
    settings: Settings | None = None,
    on_event: ProgressCallback | None = None,
    step_graph: Mapping[str, Any] | None = None,
) -> RunResult:
    """Run the stage DAG for `video` + `sop`; raise `PipelineError` on bad input.

    `step_graph` is a human-edited SOP graph (05_Schema §14). It replaces the
    `sop_compile` handler for this run and is folded into every stage key, so an
    overridden graph and a compiled one never share a cache entry.
    """
    source_video = Path(video)
    source_sop = Path(sop)
    if not source_video.is_file():
        raise PipelineError(f"video not found: {source_video}", exit_code=2)
    if not source_sop.is_file():
        raise PipelineError(f"sop not found: {source_sop}", exit_code=2)
    override = dict(step_graph) if step_graph is not None else None
    if override is not None:
        errors = validate_payload("sop", override)
        if errors:
            raise PipelineError("; ".join(errors), exit_code=2)
    graph_hash = _payload_hash(override) if override is not None else ""
    resolved = _build_settings(mode, settings)

    root_dir = runs_dir if runs_dir is not None else runs_root()
    paths: RunPaths = create_run(root_dir, video=source_video, sop=source_sop, run_id=run_id)
    video_hash = _file_hash(source_video)
    sop_hash = _file_hash(source_sop)

    if mode == "fake":
        return _run_fake(
            paths=paths,
            video=source_video,
            sop=source_sop,
            video_hash=video_hash,
            sop_hash=sop_hash,
            on_event=on_event,
            step_graph=override,
            graph_hash=graph_hash,
        )
    return _run_real(
        paths=paths,
        video=source_video,
        sop=source_sop,
        video_hash=video_hash,
        sop_hash=sop_hash,
        mode=mode,
        settings=resolved,
        services=services or StageServices(),
        on_event=on_event,
        step_graph=override,
        graph_hash=graph_hash,
    )


def _run_fake(
    *,
    paths: RunPaths,
    video: Path,
    sop: Path,
    video_hash: str,
    sop_hash: str,
    on_event: ProgressCallback | None,
    step_graph: Mapping[str, Any] | None,
    graph_hash: str,
) -> RunResult:
    artifacts: dict[str, dict[str, Any]] = {}
    outcomes: list[StageOutcome] = []
    for stage in FAKE_STAGES:
        artifact_path = paths.stages / stage.artifact
        key_file = paths.stages / f"{stage.name}.key"
        key = stage_key(
            stage,
            mode="fake",
            video_hash=video_hash,
            sop_hash=sop_hash,
            artifacts=artifacts,
            graph_hash=graph_hash,
        )
        cached = _cached(artifact_path, key_file, key)
        _emit(on_event, {"event": "stage", "stage": stage.name, "status": "running"})
        if cached:
            artifacts[stage.name] = _read_payload(artifact_path)
        else:
            payload = (
                dict(step_graph)
                if stage.name == "sop_compile" and step_graph is not None
                else fake_artifact(
                    stage,
                    StageContext(
                        run_id=paths.run_id,
                        mode="fake",
                        video=video,
                        sop=sop,
                        artifacts=artifacts,
                    ),
                )
            )
            _write_payload(artifact_path, payload)
            key_file.write_text(key + "\n", encoding="utf-8")
            artifacts[stage.name] = payload
        outcomes.append(StageOutcome(stage.name, artifact_path, key, cached))
        _emit(
            on_event,
            {
                "event": "stage",
                "stage": stage.name,
                "status": "cached" if cached else "done",
            },
        )

    shutil.copyfile(paths.stages / "report.json", paths.root / REPORT_NAME)
    return RunResult(paths.run_id, paths.root, tuple(outcomes))


def _run_real(
    *,
    paths: RunPaths,
    video: Path,
    sop: Path,
    video_hash: str,
    sop_hash: str,
    mode: str,
    settings: Settings | None,
    services: StageServices,
    on_event: ProgressCallback | None,
    step_graph: Mapping[str, Any] | None,
    graph_hash: str,
) -> RunResult:
    created_at = utc_now()
    cap = settings.spend_cap_usd if settings is not None else 3.0
    ledger = RunLedger(paths.root / "ledger.json", cap_usd=cap)
    services = _build_services(mode, settings, services, ledger)
    if step_graph is not None:
        override = dict(step_graph)

        def _override(_run: StageRun) -> dict[str, Any]:
            return dict(override)

        services = replace(
            services,
            handlers={**services.handlers, "sop_compile": _override},
        )
    frames: FrameProvider = services.frames or VideoFrames(Path("."))
    artifacts: dict[str, dict[str, Any]] = {}
    outcomes: list[StageOutcome] = []
    degraded: list[str] = []
    cap_reached = False

    for stage in FAKE_STAGES:
        artifact_path = paths.stages / stage.artifact
        key_file = paths.stages / f"{stage.name}.key"
        key = stage_key(
            stage,
            mode=mode,
            video_hash=video_hash,
            sop_hash=sop_hash,
            artifacts=artifacts,
            graph_hash=graph_hash,
        )
        started = time.monotonic()
        spend_before = ledger.total_usd
        _emit(on_event, {"event": "stage", "stage": stage.name, "status": "running"})

        if _cached(artifact_path, key_file, key):
            artifacts[stage.name] = _read_payload(artifact_path)
            outcomes.append(StageOutcome(stage.name, artifact_path, key, True, "ok", 0.0, 0))
            _emit(on_event, {"event": "stage", "stage": stage.name, "status": "cached"})
            continue

        status = "ok"
        payload: dict[str, Any] | None = None
        reason: str | None = None

        run = _stage_run(
            stage,
            paths,
            video,
            sop,
            artifacts,
            services,
            settings,
            frames,
            tuple(degraded),
            created_at,
            mode,
        )
        if cap_reached and stage.name in MODEL_STAGES:
            status = "skipped"
            reason = "spend cap reached"
            payload = fallback_payload(stage.name, run)
        else:
            handler = services.handlers.get(stage.name) or REAL_HANDLERS.get(stage.name)
            if handler is None:
                raise PipelineError(f"no handler for stage {stage.name}", exit_code=2)
            try:
                payload = handler(run)
            except SpendCapExceeded as error:
                cap_reached = True
                status = "skipped"
                reason = f"spend cap reached: {error}"
                payload = fallback_payload(stage.name, run)
            except Exception as error:  # a failed stage degrades, it does not crash
                logger.warning("stage %s failed: %s", stage.name, error)
                status = "failed"
                reason = f"{type(error).__name__}: {error}"
                payload = fallback_payload(stage.name, run)
                if stage.name in FATAL_STAGES or payload is None:
                    raise PipelineError(
                        f"stage {stage.name} failed: {reason}", exit_code=1
                    ) from error

        if payload is None:
            raise PipelineError(f"stage {stage.name} produced no artifact", exit_code=1)
        _write_payload(artifact_path, payload)
        if status == "ok":
            key_file.write_text(key + "\n", encoding="utf-8")
        elif stage.name == "report":
            raise PipelineError(f"report stage failed: {reason}", exit_code=1)
        artifacts[stage.name] = payload
        if status != "ok":
            degraded.append(stage.name)
        cost = round(max(0.0, ledger.total_usd - spend_before), 8)
        duration_ms = int((time.monotonic() - started) * 1000)
        outcomes.append(
            StageOutcome(stage.name, artifact_path, key, False, status, cost, duration_ms)
        )
        _emit(
            on_event,
            {
                "event": "stage",
                "stage": stage.name,
                "status": status if status != "ok" else "done",
                "reason": reason,
                "cost_usd": cost,
            },
        )

    report = artifacts.get("report")
    if report is None:
        raise PipelineError("pipeline finished without a report", exit_code=1)
    manifest = build_manifest(
        run_id=paths.run_id,
        created_at=created_at,
        finished_at=utc_now(),
        mode=mode,
        inputs={
            "video_sha256": video_hash,
            "sop_sha256": sop_hash,
            "step_graph_sha256": _payload_hash(artifacts["sop_compile"]),
            "edited_by_user": step_graph is not None,
        },
        outcomes=outcomes,
        ledger=ledger,
        cap_reached=cap_reached,
    )
    errors = validate_payload("manifest", manifest)
    if errors:
        raise PipelineError("; ".join(errors), exit_code=1)
    (paths.root / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    shutil.copyfile(paths.stages / "report.json", paths.root / REPORT_NAME)
    if services.clients is not None:
        services.clients.close()
    return RunResult(
        paths.run_id,
        paths.root,
        tuple(outcomes),
        tuple(degraded),
        cap_reached,
    )


def _stage_run(
    stage: StageSpec,
    paths: RunPaths,
    video: Path,
    sop: Path,
    artifacts: Mapping[str, dict[str, Any]],
    services: StageServices,
    settings: Settings | None,
    frames: FrameProvider,
    degraded: tuple[str, ...],
    created_at: str,
    mode: str,
) -> StageRun:
    provider = services.frames
    if provider is None:
        ingest = artifacts.get("ingest")
        analysis = ingest.get("analysis") if ingest is not None else None
        path = analysis.get("path") if isinstance(analysis, Mapping) else None
        if isinstance(path, str) and Path(path).is_file():
            provider = VideoFrames(Path(path))
        else:
            provider = frames
    return StageRun(
        name=stage.name,
        run_id=paths.run_id,
        mode=mode,
        created_at=created_at,
        run_dir=paths.root,
        stages_dir=paths.stages,
        video=video,
        sop=sop,
        artifacts=artifacts,
        services=services,
        settings=settings,
        frames=provider,
        degraded=degraded,
    )


__all__ = [
    "FAKE_STAGES",
    "MANIFEST_NAME",
    "MODEL_STAGES",
    "PipelineError",
    "RunResult",
    "StageOutcome",
    "StageServices",
    "build_manifest",
    "run_pipeline",
    "stage_key",
]

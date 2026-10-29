"""Fake pipeline runner: stage DAG, content-hash cache and run-store writes.

Each stage output lands in `runs/<id>/stages/<artifact>` next to a `<stage>.key` file
holding `sha256(stage_version ‖ input hashes ‖ config hash)`. A rerun with the same key
is a no-op, as `docs/04_TRD.md` §3 requires.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

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


@dataclass(frozen=True, slots=True)
class RunResult:
    run_id: str
    run_dir: Path
    stages: tuple[StageOutcome, ...]

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
) -> str:
    material = {
        "stage_version": STAGE_VERSION,
        "stage": stage.name,
        "mode": mode,
        "video": video_hash,
        "sop": sop_hash,
        "inputs": {name: _payload_hash(artifacts[name]) for name in stage.depends},
    }
    return sha256(json.dumps(material, sort_keys=True).encode("utf-8")).hexdigest()


def _cached(artifact: Path, key_file: Path, key: str) -> bool:
    if not artifact.is_file() or not key_file.is_file():
        return False
    return key_file.read_text(encoding="utf-8").strip() == key


def run_pipeline(
    *,
    video: Path,
    sop: Path,
    mode: str = "fake",
    runs_dir: Path | None = None,
    run_id: str | None = None,
) -> RunResult:
    """Run the fake stage DAG for `video` + `sop`; raise `PipelineError` on bad input."""
    if mode != "fake":
        raise PipelineError(
            f"mode {mode!r} needs the model clients (T-0.7/T-3.9); use --mode fake",
            exit_code=2,
        )
    source_video = Path(video)
    source_sop = Path(sop)
    if not source_video.is_file():
        raise PipelineError(f"video not found: {source_video}", exit_code=2)
    if not source_sop.is_file():
        raise PipelineError(f"sop not found: {source_sop}", exit_code=2)

    root_dir = runs_dir if runs_dir is not None else runs_root()
    paths: RunPaths = create_run(root_dir, video=source_video, sop=source_sop, run_id=run_id)
    video_hash = _file_hash(source_video)
    sop_hash = _file_hash(source_sop)

    artifacts: dict[str, dict[str, Any]] = {}
    outcomes: list[StageOutcome] = []
    for stage in FAKE_STAGES:
        artifact_path = paths.stages / stage.artifact
        key_file = paths.stages / f"{stage.name}.key"
        key = stage_key(
            stage,
            mode=mode,
            video_hash=video_hash,
            sop_hash=sop_hash,
            artifacts=artifacts,
        )
        cached = _cached(artifact_path, key_file, key)
        if cached:
            artifacts[stage.name] = json.loads(artifact_path.read_text(encoding="utf-8"))
        else:
            payload = fake_artifact(
                stage,
                StageContext(
                    run_id=paths.run_id,
                    mode=mode,
                    video=source_video,
                    sop=source_sop,
                    artifacts=artifacts,
                ),
            )
            artifact_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            key_file.write_text(key + "\n", encoding="utf-8")
            artifacts[stage.name] = payload
        outcomes.append(StageOutcome(stage.name, artifact_path, key, cached))

    shutil.copyfile(paths.stages / "report.json", paths.root / REPORT_NAME)
    return RunResult(paths.run_id, paths.root, tuple(outcomes))


__all__ = [
    "FAKE_STAGES",
    "SCHEMA_VERSION",
    "PipelineError",
    "RunResult",
    "StageOutcome",
    "run_pipeline",
    "stage_key",
]

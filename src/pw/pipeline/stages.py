"""The 12-stage DAG used by the fake walking skeleton.

Stage names follow the TRD pipeline (`ingest → sop_compile → perceive → timeline →
identify → score → align → verify → evidence → illustrate → report`) with a separate
`deviations` stage. T-3.9 replaces the fake payloads with real stage modules; the DAG
and artifact names stay.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

STAGE_VERSION = "0.1.0"
SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class StageSpec:
    name: str
    artifact: str
    depends: tuple[str, ...]


FAKE_STAGES: tuple[StageSpec, ...] = (
    StageSpec("ingest", "ingest.json", ()),
    StageSpec("sop_compile", "step_graph.json", ()),
    StageSpec("perceive", "tracks.json", ("ingest",)),
    StageSpec("timeline", "timeline.json", ("perceive",)),
    StageSpec("identify", "identities.json", ("perceive",)),
    StageSpec("score", "likelihoods.json", ("timeline", "sop_compile")),
    StageSpec("align", "alignment.json", ("score",)),
    StageSpec("deviations", "deviations.json", ("align", "identify")),
    StageSpec("verify", "verify.json", ("deviations",)),
    StageSpec("evidence", "evidence.json", ("verify", "deviations")),
    StageSpec("illustrate", "illustrations.json", ("verify", "deviations")),
    StageSpec("report", "report.json", ("evidence", "illustrate", "verify")),
)

STAGE_ORDER: tuple[str, ...] = tuple(stage.name for stage in FAKE_STAGES)


@dataclass(frozen=True, slots=True)
class StageContext:
    run_id: str
    mode: str
    video: Path
    sop: Path
    artifacts: Mapping[str, Mapping[str, Any]]


def fake_artifact(stage: StageSpec, context: StageContext) -> dict[str, Any]:
    """Stub payload: enough provenance for the skeleton, no model output."""
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": context.run_id,
        "stage": stage.name,
        "mode": context.mode,
        "stub": True,
        "depends": list(stage.depends),
        "inputs": [input_stage.artifact for input_stage in _inputs(stage)],
    }


def _inputs(stage: StageSpec) -> list[StageSpec]:
    by_name = {candidate.name: candidate for candidate in FAKE_STAGES}
    return [by_name[name] for name in stage.depends]


__all__ = [
    "FAKE_STAGES",
    "SCHEMA_VERSION",
    "STAGE_ORDER",
    "STAGE_VERSION",
    "StageContext",
    "StageSpec",
    "fake_artifact",
]

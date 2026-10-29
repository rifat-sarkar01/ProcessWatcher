"""Filesystem run store: run ids, `runs/<id>/…` layout and run summaries.

Layout per `docs/05_Schema.md` §12: `input/`, `stages/`, `media/`, `evidence/`,
`illustrations/`, with `report.json` at the run root.
"""

from __future__ import annotations

import os
import re
import secrets
import shutil
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

RUN_ID_PATTERN = r"^run_[0-9A-HJKMNP-TV-Z]{26}$"
_RUN_ID_RE = re.compile(RUN_ID_PATTERN)
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
LAYOUT = ("input", "stages", "media", "evidence", "illustrations")
REPORT_NAME = "report.json"


class RunStoreError(ValueError):
    """A run id or run directory is invalid or missing."""


@dataclass(frozen=True, slots=True)
class RunPaths:
    run_id: str
    root: Path

    @property
    def input(self) -> Path:
        return self.root / "input"

    @property
    def stages(self) -> Path:
        return self.root / "stages"

    @property
    def media(self) -> Path:
        return self.root / "media"

    @property
    def evidence(self) -> Path:
        return self.root / "evidence"

    @property
    def illustrations(self) -> Path:
        return self.root / "illustrations"


@dataclass(frozen=True, slots=True)
class RunSummary:
    run_id: str
    status: str
    created_at: str
    cost_usd: float

    def to_artifact(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "created_at": self.created_at,
            "cost_usd": self.cost_usd,
        }


def _encode(value: int, length: int) -> str:
    chars = []
    for _ in range(length):
        chars.append(_ALPHABET[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def new_run_id(*, now_ms: int | None = None, randomness: int | None = None) -> str:
    """Return a `run_` + ULID (48-bit ms timestamp + 80 bits of randomness)."""
    milliseconds = int(time.time() * 1000) if now_ms is None else now_ms
    entropy = secrets.randbits(80) if randomness is None else randomness
    return f"run_{_encode(milliseconds, 10)}{_encode(entropy, 16)}"


def validate_run_id(run_id: str) -> str:
    if not _RUN_ID_RE.match(run_id):
        raise RunStoreError(f"invalid run id: {run_id!r}")
    return run_id


def runs_root(path: Path | None = None) -> Path:
    """Default runs directory: `PW_RUNS_DIR` when set, else `./runs`."""
    if path is not None:
        return path
    configured = os.environ.get("PW_RUNS_DIR")
    return Path(configured) if configured else Path("runs")


def create_run(
    runs_dir: Path,
    *,
    video: Path,
    sop: Path,
    run_id: str | None = None,
) -> RunPaths:
    """Create the run directory tree and copy inputs under neutral names."""
    identifier = validate_run_id(run_id) if run_id is not None else new_run_id()
    root = runs_dir / identifier
    paths = RunPaths(identifier, root)
    for name in LAYOUT:
        (root / name).mkdir(parents=True, exist_ok=True)
    _copy_input(video, paths.input / f"video{video.suffix.lower()}")
    _copy_input(sop, paths.input / f"sop{sop.suffix.lower()}")
    return paths


def _copy_input(source: Path, target: Path) -> None:
    if target.exists() and target.stat().st_size == source.stat().st_size:
        return
    shutil.copyfile(source, target)


def open_run(runs_dir: Path, run_id: str) -> RunPaths:
    validate_run_id(run_id)
    root = runs_dir / run_id
    if not root.is_dir():
        raise RunStoreError(f"run not found: {run_id}")
    return RunPaths(run_id, root)


def _status(paths: RunPaths) -> str:
    if (paths.root / REPORT_NAME).is_file():
        return "done"
    if any(paths.stages.glob("*.json")):
        return "running"
    return "queued"


def _created_at(root: Path) -> str:
    return datetime.fromtimestamp(root.stat().st_mtime, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def list_runs(runs_dir: Path) -> list[RunSummary]:
    """List runs newest first; unknown directories are ignored."""
    if not runs_dir.is_dir():
        return []
    summaries = [
        RunSummary(
            run_id=entry.name,
            status=_status(RunPaths(entry.name, entry)),
            created_at=_created_at(entry),
            cost_usd=0.0,
        )
        for entry in runs_dir.iterdir()
        if entry.is_dir() and _RUN_ID_RE.match(entry.name)
    ]
    summaries.sort(key=lambda summary: (summary.created_at, summary.run_id), reverse=True)
    return summaries


__all__ = [
    "LAYOUT",
    "REPORT_NAME",
    "RUN_ID_PATTERN",
    "RunPaths",
    "RunStoreError",
    "RunSummary",
    "create_run",
    "list_runs",
    "new_run_id",
    "open_run",
    "runs_root",
    "validate_run_id",
]

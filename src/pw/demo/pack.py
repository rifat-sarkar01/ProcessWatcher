"""Frozen demo cases (T-7.1): copy finished runs into `demo/cases/<id>/` with checksums.

The demo pack is served read-only with `PW_MODE=demo`, so it must contain every artifact
the report references and no model can be called. Only real-frame evidence is copied.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CASE_MANIFEST = "case.json"
_COPY_DIRS = ("evidence", "illustrations", "stages")
_COPY_FILES = ("report.json", "manifest.json", "ledger.json")
_STAGE_FILES = ("tracks.json", "timeline.json", "alignment.json", "deviations.json")


class DemoError(ValueError):
    """Demo pack construction or verification failed."""


@dataclass(frozen=True, slots=True)
class CaseSpec:
    case_id: str
    run_dir: Path
    title: str
    description: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _files(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != CASE_MANIFEST
    }


def _copy_run(run_dir: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name in _COPY_FILES:
        source = run_dir / name
        if source.is_file():
            shutil.copy2(source, target / name)
    stages = target / "stages"
    stages.mkdir(exist_ok=True)
    for name in _STAGE_FILES:
        source = run_dir / "stages" / name
        if source.is_file():
            shutil.copy2(source, stages / name)
    for name in ("evidence", "illustrations"):
        source = run_dir / name
        if source.is_dir():
            shutil.copytree(source, target / name, dirs_exist_ok=True)
    analysis = run_dir / "media" / "analysis.mp4"
    if analysis.is_file():
        media = target / "media"
        media.mkdir(exist_ok=True)
        shutil.copy2(analysis, media / "analysis.mp4")


def build_case(spec: CaseSpec, cases_dir: Path) -> Path:
    if not (spec.run_dir / "report.json").is_file():
        raise DemoError(f"{spec.run_dir}: no report.json")
    target = cases_dir / spec.case_id
    if target.exists():
        shutil.rmtree(target)
    _copy_run(spec.run_dir, target)
    payload: dict[str, Any] = {
        "case_id": spec.case_id,
        "title": spec.title,
        "description": spec.description,
        "source_run": spec.run_dir.name,
        "files": _files(target),
    }
    (target / CASE_MANIFEST).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return target


def build_from_specs(specs: list[CaseSpec], cases_dir: Path) -> list[Path]:
    if not specs:
        raise DemoError("no demo cases given")
    return [build_case(spec, cases_dir) for spec in specs]


def verify_cases(cases_dir: Path) -> tuple[int, list[str]]:
    cases = sorted(path for path in cases_dir.glob("*/" + CASE_MANIFEST))
    errors: list[str] = []
    for manifest_path in cases:
        case_dir = manifest_path.parent
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errors.append(f"{case_dir.name}: {exc}")
            continue
        files = payload.get("files")
        if not isinstance(files, dict):
            errors.append(f"{case_dir.name}: files must be an object")
            continue
        for name, digest in sorted(files.items()):
            path = case_dir / name
            if not path.is_file():
                errors.append(f"{case_dir.name}: missing {name}")
            elif _sha256(path) != digest:
                errors.append(f"{case_dir.name}: checksum mismatch {name}")
        for name in _files(case_dir):
            if name not in files:
                errors.append(f"{case_dir.name}: unlisted file {name}")
    return len(cases), errors


__all__ = [
    "CASE_MANIFEST",
    "CaseSpec",
    "DemoError",
    "build_case",
    "build_from_specs",
    "verify_cases",
]

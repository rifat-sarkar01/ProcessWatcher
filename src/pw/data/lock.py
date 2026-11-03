"""Held-out lock: freeze the held-out manifest and ground truth before tuning.

The clips themselves stay outside git (they are 461 MB and git-ignored), so the lock
commits `bench/heldout/manifest.json` — which carries every clip's sha256 — plus every
`bench/heldout/gt/*.json`. `pw-data verify-lock` recomputes those hashes; any edit,
addition or removal is a violation (docs/06_Plan.md T-1.8).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LOCK_FILENAME = "HELDOUT.lock"
LOCK_SCHEMA_VERSION = "1.0"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tracked_files(bench_dir: Path) -> list[Path]:
    """Return the files protected by the lock, relative to `bench_dir` order."""
    split_dir = bench_dir / "heldout"
    files = [split_dir / "manifest.json"]
    files.extend(sorted((split_dir / "gt").glob("*.json")))
    return [path for path in files if path.is_file()]


def _relative(path: Path, bench_dir: Path) -> str:
    return path.relative_to(bench_dir).as_posix()


def compute_files(bench_dir: Path) -> dict[str, str]:
    return {_relative(path, bench_dir): _sha256(path) for path in tracked_files(bench_dir)}


def write_lock(bench_dir: Path, commit: str, created_at: str | None = None) -> Path:
    """Write `bench/HELDOUT.lock` for the current held-out files."""
    files = compute_files(bench_dir)
    if not files:
        raise ValueError("no held-out files to lock")
    payload = {
        "schema_version": LOCK_SCHEMA_VERSION,
        "created_at": created_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": commit,
        "files": files,
    }
    path = bench_dir / LOCK_FILENAME
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _load_lock(bench_dir: Path) -> dict[str, Any]:
    path = bench_dir / LOCK_FILENAME
    if not path.is_file():
        raise FileNotFoundError(f"held-out lock not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: lock root must be an object")
    return payload


def verify_lock(bench_dir: Path) -> list[str]:
    """Return human-readable violations; an empty list means the lock is intact."""
    try:
        payload = _load_lock(bench_dir)
    except (OSError, ValueError) as exc:
        return [f"LOCK VIOLATION: {exc}"]

    locked = payload.get("files")
    if not isinstance(locked, dict):
        return ["LOCK VIOLATION: lock.files must be an object"]

    current = compute_files(bench_dir)
    errors: list[str] = []
    for name, digest in sorted(locked.items()):
        if name not in current:
            errors.append(f"LOCK VIOLATION: removed held-out file {name}")
        elif current[name] != digest:
            errors.append(f"LOCK VIOLATION: changed held-out file {name}")
    for name in sorted(set(current) - set(locked)):
        errors.append(f"LOCK VIOLATION: added held-out file {name}")
    return errors


__all__ = ["LOCK_FILENAME", "compute_files", "tracked_files", "verify_lock", "write_lock"]

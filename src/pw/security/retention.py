"""24 h retention purge for filesystem runs; demo cases are exempt."""

from __future__ import annotations

import shutil
import time
from collections.abc import Sequence
from pathlib import Path

RETENTION_S = 24 * 60 * 60


def purge_expired(
    runs_dir: Path,
    *,
    now: float | None = None,
    max_age_s: float = RETENTION_S,
    exempt: Sequence[Path] = (),
) -> list[str]:
    """Delete run directories older than `max_age_s`; return the purged names."""
    root = Path(runs_dir)
    if not root.is_dir():
        return []
    moment = time.time() if now is None else now
    keep_roots = [Path(path).resolve() for path in exempt]

    purged: list[str] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        resolved = entry.resolve()
        if any(resolved == kept or resolved.is_relative_to(kept) for kept in keep_roots):
            continue
        if moment - entry.stat().st_mtime > max_age_s:
            shutil.rmtree(entry, ignore_errors=True)
            purged.append(entry.name)
    return purged


__all__ = ["RETENTION_S", "purge_expired"]

"""Traversal-safe artifact resolution with a directory allowlist (`05_Schema.md` §13)."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

from pw.security.errors import PathNotAllowed

ALLOWED_DIRS = frozenset({"evidence", "illustrations", "media"})
ALLOWED_ROOT_FILES = frozenset({"report.json", "manifest.json", "ledger.json", "review.json"})
_DRIVE = re.compile(r"^[A-Za-z]:")


def resolve_artifact(run_dir: Path, relative: str) -> Path:
    """Resolve `relative` under `run_dir`, refusing traversal and non-servable paths."""
    if not isinstance(relative, str) or "\x00" in relative:
        raise PathNotAllowed("invalid artifact path")
    decoded = unquote(relative).replace("\\", "/")
    if decoded.startswith("/") or _DRIVE.match(decoded):
        raise PathNotAllowed("absolute paths are not served")
    parts = PurePosixPath(decoded).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise PathNotAllowed("invalid artifact path")

    root = Path(run_dir).resolve()
    resolved = root.joinpath(*parts).resolve()
    if not resolved.is_relative_to(root):
        raise PathNotAllowed("artifact path escapes the run")
    inner = resolved.relative_to(root)
    if len(inner.parts) == 1 and inner.name in ALLOWED_ROOT_FILES:
        return resolved
    if len(inner.parts) >= 2 and inner.parts[0] in ALLOWED_DIRS:
        return resolved
    raise PathNotAllowed("artifact path is not servable")


__all__ = ["ALLOWED_DIRS", "ALLOWED_ROOT_FILES", "resolve_artifact"]

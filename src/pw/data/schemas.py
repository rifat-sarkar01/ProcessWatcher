"""Contract registry: which artifact kind maps to which schema file and examples."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Artifact kinds (what `pw-data validate-artifact --kind` accepts).
KINDS: tuple[str, ...] = (
    "sop",
    "tracks",
    "timeline",
    "identities",
    "likelihoods",
    "alignment",
    "report",
    "manifest",
    "review",
    "thresholds",
)

# Contract files (one per schema). Several artifact kinds may share a file.
SCHEMA_FILES: dict[str, str] = {
    "sop": "sop.schema.json",
    "tracks": "tracks.schema.json",
    "timeline": "timeline.schema.json",
    "alignment": "alignment.schema.json",
    "report": "report.schema.json",
    "manifest": "manifest.schema.json",
    "review": "review.schema.json",
    "thresholds": "thresholds.schema.json",
}

SCHEMA_NAMES: tuple[str, ...] = tuple(SCHEMA_FILES)

KIND_TO_SCHEMA: dict[str, str] = {
    "sop": "sop",
    "tracks": "tracks",
    "timeline": "timeline",
    "identities": "alignment",
    "likelihoods": "alignment",
    "alignment": "alignment",
    "report": "report",
    "manifest": "manifest",
    "review": "review",
    "thresholds": "thresholds",
}

# Examples: one or more glob patterns per artifact kind (relative to contracts/examples).
EXAMPLE_PATTERNS: dict[str, tuple[str, ...]] = {
    "sop": ("sop.example.json",),
    "tracks": ("tracks.example.json",),
    "timeline": ("timeline.example.json",),
    "identities": ("identities.example.json",),
    "likelihoods": ("likelihoods.example.json",),
    "alignment": ("alignment.example.json",),
    "report": ("report.*.example.json",),
    "manifest": ("manifest.example.json",),
    "review": ("review.example.json",),
    "thresholds": ("thresholds.example.json",),
}

# Backwards-compatible single-file view used by tests and docs.
EXAMPLE_FILENAMES: dict[str, str] = {
    kind: patterns[0] for kind, patterns in EXAMPLE_PATTERNS.items()
}

CONTRACTS_DIR_ENV = "PW_CONTRACTS_DIR"


def default_contracts_dir() -> Path:
    """Return the contracts directory: `PW_CONTRACTS_DIR`, else `<repo>/contracts`."""
    override = os.environ.get(CONTRACTS_DIR_ENV)
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[3] / "contracts"


def load_json(path: Path) -> Any:
    """Read a UTF-8 JSON file. Raises OSError/ValueError with the path in the message."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON ({exc.msg} at line {exc.lineno})") from exc


def _schema_path(schema_name: str, contracts_dir: Path | None) -> Path:
    filename = SCHEMA_FILES.get(schema_name)
    if filename is None:
        expected = ", ".join(SCHEMA_NAMES)
        raise ValueError(f"unknown schema {schema_name!r} (expected one of: {expected})")
    base = contracts_dir if contracts_dir is not None else default_contracts_dir()
    return base / filename


def load_schema(kind: str, contracts_dir: Path | None = None) -> dict[str, Any]:
    """Load the JSON Schema for an artifact kind (several kinds share one file)."""
    schema_name = KIND_TO_SCHEMA.get(kind)
    if schema_name is None:
        expected = ", ".join(KINDS)
        raise ValueError(f"unknown artifact kind {kind!r} (expected one of: {expected})")

    path = _schema_path(schema_name, contracts_dir)
    if not path.is_file():
        raise FileNotFoundError(f"contract schema not found: {path}")

    schema = load_json(path)
    if not isinstance(schema, dict):
        raise ValueError(f"{path}: schema root must be a JSON object")
    return schema


def load_schemas(contracts_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load every contract schema, keyed by schema name."""
    schemas: dict[str, dict[str, Any]] = {}
    for name in SCHEMA_NAMES:
        schemas[name] = load_schema(name, contracts_dir)
    return schemas


def example_files(kind: str, contracts_dir: Path | None = None) -> list[Path]:
    """Return the committed example files for a kind, sorted for determinism."""
    base = (contracts_dir if contracts_dir is not None else default_contracts_dir()) / "examples"
    found: list[Path] = []
    for pattern in EXAMPLE_PATTERNS.get(kind, ()):
        found.extend(sorted(base.glob(pattern)))
    return found

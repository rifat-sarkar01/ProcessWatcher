"""Contract registry: which artifact kind maps to which schema and example file."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

KINDS: tuple[str, ...] = ("sop", "tracks", "timeline")

SCHEMA_FILENAMES: dict[str, str] = {
    "sop": "sop.schema.json",
    "tracks": "tracks.schema.json",
    "timeline": "timeline.schema.json",
}

EXAMPLE_FILENAMES: dict[str, str] = {
    "sop": "sop.example.json",
    "tracks": "tracks.example.json",
    "timeline": "timeline.example.json",
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


def load_schema(kind: str, contracts_dir: Path | None = None) -> dict[str, Any]:
    """Load and return the JSON Schema for `kind`."""
    filename = SCHEMA_FILENAMES.get(kind)
    if filename is None:
        expected = ", ".join(KINDS)
        raise ValueError(f"unknown artifact kind {kind!r} (expected one of: {expected})")

    base = contracts_dir if contracts_dir is not None else default_contracts_dir()
    path = base / filename
    if not path.is_file():
        raise FileNotFoundError(f"contract schema not found: {path}")

    schema = load_json(path)
    if not isinstance(schema, dict):
        raise ValueError(f"{path}: schema root must be a JSON object")
    return schema

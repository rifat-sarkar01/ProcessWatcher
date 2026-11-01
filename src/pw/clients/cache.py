"""Request-hash response cache: record in `live`, serve in `replay`/`demo`.

The cache holds only the request descriptor and the JSON response. Headers (and thus
`Authorization`) are never written, so a leaked cache directory cannot leak the key.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pw.clients.transport import FilePart

CACHE_VERSION = 1


def canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def key_for_json(path: str, payload: Mapping[str, Any]) -> str:
    return _hash(f"POST {path}\n{canonical_json(payload)}")


def key_for_multipart(path: str, fields: Mapping[str, str], files: Sequence[FilePart]) -> str:
    parts = [f"POST {path}", canonical_json(fields)]
    for part in files:
        digest = hashlib.sha256(part.content).hexdigest()
        parts.append(f"{part.field}\0{part.filename}\0{part.content_type}\0{digest}")
    return _hash("\n".join(parts))


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def default_cache_dir(environ: Mapping[str, str] | None = None) -> Path:
    source = os.environ if environ is None else environ
    configured = (source.get("PW_CACHE_DIR") or "").strip()
    return Path(configured) if configured else Path(".cache") / "pw"


@dataclass(frozen=True, slots=True)
class CacheHit:
    response: Mapping[str, Any]
    path: Path


class ResponseCache:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path_for(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def read(self, key: str) -> CacheHit | None:
        path = self.path_for(key)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        response = payload.get("response")
        if not isinstance(response, dict):
            return None
        return CacheHit(response=response, path=path)

    def write(
        self,
        key: str,
        *,
        path: str,
        request: Mapping[str, Any],
        response: Mapping[str, Any],
    ) -> Path:
        target = self.path_for(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": CACHE_VERSION,
            "request_sha256": key,
            "path": path,
            "request": dict(request),
            "response": dict(response),
        }
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, target)
        return target


__all__ = [
    "CACHE_VERSION",
    "CacheHit",
    "ResponseCache",
    "canonical_json",
    "default_cache_dir",
    "key_for_json",
    "key_for_multipart",
]

"""Muse Image illustration generator (FR-10, ADR-003).

One illustration per flagged step (deduped), built from the step text, its tools/parts
and the deviation types. Edit-with-reference is the default because it keeps the real
frame's layout; text-only generation is the fallback. Every image is cached by request
hash and watermarked at write time, so an illustration can never be mistaken for
evidence. Failures are recorded as `illustration_unavailable`, never raised.
"""

from __future__ import annotations

import hashlib
import io
import os
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from pw.clients.image import ImageClient, ImageInput
from pw.evidence.labeling import watermark_illustration
from pw.illustrate.prompts import PROMPT_VERSION, build_prompt, prompt_sha256

SCHEMA_VERSION = "1.0.0"
ILLUSTRATION_KIND = "illustration"
UNAVAILABLE = "illustration_unavailable"
DEFAULT_DIR = "illustrations"
IllustrationCaller = Callable[[str, bytes | None], bytes]
_TRUE = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True, slots=True)
class Illustration:
    id: str
    step_id: str
    deviation_ids: tuple[str, ...]
    mode: str
    prompt: str
    prompt_sha256: str
    image: bytes | None
    reason: str | None = None
    from_cache: bool = False


@dataclass(frozen=True, slots=True)
class IllustrationSet:
    items: tuple[Illustration, ...]
    disabled: bool = False
    calls: int = 0
    cache_hits: int = 0

    @property
    def available(self) -> int:
        return sum(1 for item in self.items if item.image is not None)

    def write(self, run_dir: Path, *, subdir: str = DEFAULT_DIR) -> tuple[dict[str, Any], ...]:
        """Watermark each image, save it under `run_dir/illustrations` and describe it."""
        target_dir = Path(run_dir) / subdir
        payloads: list[dict[str, Any]] = []
        for item in self.items:
            if item.image is None:
                continue
            target_dir.mkdir(parents=True, exist_ok=True)
            image = Image.open(io.BytesIO(item.image)).convert("RGB")
            marked = watermark_illustration(image)
            path = target_dir / f"{item.id}.png"
            marked.save(path)
            payloads.append(
                {
                    "id": item.id,
                    "step_id": item.step_id,
                    "deviation_ids": list(item.deviation_ids),
                    "kind": ILLUSTRATION_KIND,
                    "path": path.relative_to(Path(run_dir)).as_posix(),
                    "sha256": _sha256(path.read_bytes()),
                    "watermark": True,
                    "mode": item.mode,
                    "prompt_version": PROMPT_VERSION,
                    "prompt_sha256": item.prompt_sha256,
                }
            )
        return tuple(payloads)


def illustrations_disabled(environ: Mapping[str, str] | None = None) -> bool:
    source = os.environ if environ is None else environ
    return (source.get("PW_DISABLE_ILLUSTRATIONS") or "").strip().lower() in _TRUE


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _cache_key(prompt: str, reference: bytes | None) -> str:
    material = f"{PROMPT_VERSION}\n{prompt}\n{_sha256(reference) if reference else 'text-only'}"
    return _sha256(material.encode("utf-8"))


def _reference_for(deviation_ids: Sequence[str], references: Mapping[str, bytes]) -> bytes | None:
    for deviation_id in deviation_ids:
        reference = references.get(deviation_id)
        if reference:
            return reference
    return None


def _group_by_step(
    deviations: Sequence[Any],
) -> list[tuple[str, list[str], list[str]]]:
    grouped: dict[str, tuple[list[str], list[str]]] = {}
    order: list[str] = []
    for deviation in deviations:
        step_id = str(deviation.step_id)
        if step_id not in grouped:
            grouped[step_id] = ([], [])
            order.append(step_id)
        ids, kinds = grouped[step_id]
        ids.append(str(deviation.id))
        if deviation.type not in kinds:
            kinds.append(str(deviation.type))
    return [(step_id, grouped[step_id][0], grouped[step_id][1]) for step_id in order]


def generate_illustrations(
    deviations: Sequence[Any],
    sop: Mapping[str, Any],
    *,
    call: IllustrationCaller,
    references: Mapping[str, bytes] | None = None,
    cache: MutableMapping[str, bytes] | None = None,
    cache_dir: Path | None = None,
    disabled: bool | None = None,
    max_items: int | None = None,
) -> IllustrationSet:
    """Return one illustration per flagged step; never raises for a model failure."""
    if disabled is None:
        disabled = illustrations_disabled()
    if disabled:
        return IllustrationSet(items=(), disabled=True)

    steps = {
        str(step.get("id")): step for step in sop.get("steps", ()) if isinstance(step, Mapping)
    }
    refs = dict(references or {})
    items: list[Illustration] = []
    calls = 0
    cache_hits = 0
    for step_id, deviation_ids, kinds in _group_by_step(deviations):
        if max_items is not None and len(items) >= max_items:
            break
        step = steps.get(step_id)
        if step is None:
            continue
        prompt = build_prompt(step, deviation_types=kinds)
        reference = _reference_for(deviation_ids, refs)
        key = _cache_key(prompt, reference)
        digest = prompt_sha256(prompt)
        illustration_id = f"ill_{len(items) + 1:03d}"

        if cache is not None and key in cache:
            cache_hits += 1
            items.append(
                Illustration(
                    id=illustration_id,
                    step_id=step_id,
                    deviation_ids=tuple(deviation_ids),
                    mode="edit" if reference else "generate",
                    prompt=prompt,
                    prompt_sha256=digest,
                    image=cache[key],
                    from_cache=True,
                )
            )
            continue
        if cache_dir is not None:
            stored = Path(cache_dir) / f"{key}.png"
            if stored.is_file():
                cache_hits += 1
                image = stored.read_bytes()
                if cache is not None:
                    cache[key] = image
                items.append(
                    Illustration(
                        id=illustration_id,
                        step_id=step_id,
                        deviation_ids=tuple(deviation_ids),
                        mode="edit" if reference else "generate",
                        prompt=prompt,
                        prompt_sha256=digest,
                        image=image,
                        from_cache=True,
                    )
                )
                continue

        calls += 1
        try:
            image = call(prompt, reference)
        except Exception as error:  # API failure degrades to a reason, never a crash
            items.append(
                Illustration(
                    id=illustration_id,
                    step_id=step_id,
                    deviation_ids=tuple(deviation_ids),
                    mode="edit" if reference else "generate",
                    prompt=prompt,
                    prompt_sha256=digest,
                    image=None,
                    reason=f"{UNAVAILABLE}: {type(error).__name__}",
                )
            )
            continue
        if not image:
            items.append(
                Illustration(
                    id=illustration_id,
                    step_id=step_id,
                    deviation_ids=tuple(deviation_ids),
                    mode="edit" if reference else "generate",
                    prompt=prompt,
                    prompt_sha256=digest,
                    image=None,
                    reason=f"{UNAVAILABLE}: empty image response",
                )
            )
            continue

        if cache is not None:
            cache[key] = image
        if cache_dir is not None:
            Path(cache_dir).mkdir(parents=True, exist_ok=True)
            (Path(cache_dir) / f"{key}.png").write_bytes(image)
        items.append(
            Illustration(
                id=illustration_id,
                step_id=step_id,
                deviation_ids=tuple(deviation_ids),
                mode="edit" if reference else "generate",
                prompt=prompt,
                prompt_sha256=digest,
                image=image,
            )
        )
    return IllustrationSet(tuple(items), disabled=False, calls=calls, cache_hits=cache_hits)


def client_caller(client: ImageClient) -> IllustrationCaller:
    """Adapter from the typed client to the generator's `(prompt, reference)` shape."""

    def call(prompt: str, reference: bytes | None) -> bytes:
        if reference is not None:
            result = client.edit(prompt, [ImageInput(reference, "reference.png")])
        else:
            result = client.generate(prompt)
        return result.images[0]

    return call


__all__ = [
    "DEFAULT_DIR",
    "ILLUSTRATION_KIND",
    "PROMPT_VERSION",
    "SCHEMA_VERSION",
    "UNAVAILABLE",
    "Illustration",
    "IllustrationCaller",
    "IllustrationSet",
    "client_caller",
    "generate_illustrations",
    "illustrations_disabled",
]

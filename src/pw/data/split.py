"""Validate a bench split: manifest, clip hashes and per-clip ground truth.

`pw-data validate --split dev|heldout` proves the labelled footage is complete and
internally consistent before any model runs (docs/06_Plan.md T-1.4/T-1.5).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from pw.data.sopcheck import golden_step_ids, validate_gt

SPLIT_CLIP_COUNTS = {"dev": 15, "heldout": 9}
MIN_DURATION_S = 20.0
MAX_DURATION_S = 180.0
_CLIP_ID = re.compile(r"^[A-C][0-9]{1,2}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PROCEDURES = {"A", "B", "C"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_split(split: str, bench_dir: Path) -> tuple[int, int, list[str]]:
    """Return (clips, ground truths, errors) for a bench split."""
    if split not in SPLIT_CLIP_COUNTS:
        return 0, 0, [f"unknown split {split!r} (expected dev or heldout)"]

    split_dir = bench_dir / split
    manifest_path = split_dir / "manifest.json"
    if not manifest_path.is_file():
        return 0, 0, [f"split manifest not found: {manifest_path}"]

    try:
        payload = _load_json(manifest_path)
    except (OSError, ValueError) as exc:
        return 0, 0, [f"{manifest_path}: {exc}"]

    errors: list[str] = []
    if not isinstance(payload, dict):
        return 0, 0, [f"{manifest_path}: root must be an object"]
    if payload.get("split") != split:
        errors.append(f"manifest.split: expected {split!r}, got {payload.get('split')!r}")
    clips = payload.get("clips")
    if not isinstance(clips, list):
        return 0, 0, [*errors, "manifest.clips: expected a list"]

    expected = SPLIT_CLIP_COUNTS[split]
    if len(clips) != expected:
        errors.append(f"manifest.clips: expected {expected} clips, found {len(clips)}")

    seen_ids: set[str] = set()
    gt_ok = 0
    for index, raw in enumerate(clips):
        where = f"clips[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{where}: expected an object")
            continue

        clip_id = str(raw.get("clip_id", ""))
        if not _CLIP_ID.match(clip_id):
            errors.append(f"{where}.clip_id: {clip_id!r} does not match A1..C99")
        if clip_id in seen_ids:
            errors.append(f"{where}.clip_id: duplicate clip id {clip_id!r}")
        seen_ids.add(clip_id)

        procedure = raw.get("procedure")
        if procedure not in _PROCEDURES:
            errors.append(f"{where}.procedure: expected A, B or C, got {procedure!r}")

        sha = str(raw.get("sha256", ""))
        if not _SHA256.match(sha):
            errors.append(f"{where}.sha256: expected 64 lowercase hex characters")

        duration = raw.get("duration_s")
        if not isinstance(duration, (int, float)) or isinstance(duration, bool):
            errors.append(f"{where}.duration_s: expected a number")
            duration_value = 0.0
        else:
            duration_value = float(duration)
            if not MIN_DURATION_S <= duration_value <= MAX_DURATION_S:
                errors.append(
                    f"{where}.duration_s: {duration_value} s is outside "
                    f"{MIN_DURATION_S:.0f}-{MAX_DURATION_S:.0f} s"
                )

        storage_ref = raw.get("storage_ref")
        if not isinstance(storage_ref, str) or not storage_ref:
            errors.append(f"{where}.storage_ref: expected a relative path")
        else:
            video = split_dir / storage_ref
            if not video.is_file():
                errors.append(f"{where}.storage_ref: clip not found at {video}")
            elif _sha256(video) != sha:
                errors.append(f"{where}.sha256: does not match {storage_ref}")

        gt_rel = raw.get("gt_path")
        if not isinstance(gt_rel, str) or not gt_rel:
            errors.append(f"{where}.gt_path: expected a relative path")
            continue
        gt_path = split_dir / gt_rel
        if not gt_path.is_file():
            errors.append(f"{where}.gt_path: ground truth not found at {gt_path}")
            continue

        try:
            gt = _load_json(gt_path)
        except (OSError, ValueError) as exc:
            errors.append(f"{gt_path}: {exc}")
            continue

        golden_path = bench_dir / "golden" / f"P-{procedure}.json"
        if not golden_path.is_file():
            errors.append(f"{where}: missing golden graph {golden_path.name}")
            continue
        gt_errors = [
            f"{gt_rel}: {error}"
            for error in validate_gt(gt, golden_step_ids(golden_path), bench_dir)
        ]
        if isinstance(gt, dict) and gt.get("clip_id") != clip_id:
            gt_errors.append(f"{gt_rel}.clip_id: {gt.get('clip_id')!r} does not match {clip_id!r}")
        if isinstance(gt, dict):
            for field, items in (
                ("steps", gt.get("steps", [])),
                ("deviations", gt.get("deviations", [])),
            ):
                for item_index, item in enumerate(items if isinstance(items, list) else []):
                    if not isinstance(item, dict):
                        continue
                    end = item.get("t_end")
                    if isinstance(end, (int, float)) and float(end) > duration_value + 0.05:
                        gt_errors.append(
                            f"{gt_rel}.{field}[{item_index}].t_end: {end} s is past the clip "
                            f"duration ({duration_value} s)"
                        )
        errors.extend(gt_errors)
        if not gt_errors:
            gt_ok += 1

    return len(clips), gt_ok, errors


__all__ = ["SPLIT_CLIP_COUNTS", "validate_split"]

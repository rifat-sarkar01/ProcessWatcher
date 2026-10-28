"""Provenance for evidence frames and clips.

Every evidence item records the source hash, the analysis frame index, the render
parameters hash and the output hash. `pw verify-evidence` re-renders each item from
the analysis copy and compares perceptual hashes, so a swapped frame, an edited
output or a different render configuration cannot pass as the original.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from pw.evidence.clip import ClipResult
from pw.evidence.render import FrameOverlay, draw_timestamp, render_overlay
from pw.evidence.selector import EvidenceParams, EvidenceSelection
from pw.ingest import probe_video, sha256_file

RENDER_VERSION = "evidence-render-v1"
PHASH_SIZE = 8
PHASH_TOLERANCE_BITS = 8
DEFAULT_OUTPUT_DIR = "evidence"


@dataclass(frozen=True, slots=True)
class EvidenceCheck:
    evidence_id: str
    ok: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class VerifyResult:
    checks: tuple[EvidenceCheck, ...]

    @property
    def verified(self) -> int:
        return sum(1 for check in self.checks if check.ok)

    @property
    def total(self) -> int:
        return len(self.checks)

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    def summary(self) -> str:
        label = "VERIFIED" if self.ok else "FAILED"
        return f"{label} {self.verified}/{self.total}"


def render_params(
    evidence: EvidenceParams | None = None,
    *,
    alpha: int = 96,
    labels: bool = True,
    timestamp: bool = True,
) -> dict[str, Any]:
    """Everything that changes the pixels of a rendered evidence frame."""
    settings = evidence or EvidenceParams()
    return {
        "render_version": RENDER_VERSION,
        "alpha": alpha,
        "labels": labels,
        "timestamp": timestamp,
        "max_frames": settings.max_frames,
        "min_spacing_s": settings.min_spacing_s,
        "area_weight": settings.area_weight,
        "sharpness_weight": settings.sharpness_weight,
        "visibility_weight": settings.visibility_weight,
    }


def params_hash(params: Mapping[str, Any] | None = None) -> str:
    """Stable SHA-256 of the render parameters (sorted keys, no whitespace)."""
    payload = json.dumps(dict(params or render_params()), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def dhash(image: Image.Image, *, size: int = PHASH_SIZE) -> str:
    """Difference hash: `size*size` bits as lowercase hex."""
    if size < 2:
        raise ValueError(f"hash size must be at least 2: {size}")
    grey = image.convert("L").resize((size + 1, size), Image.Resampling.BILINEAR)
    pixels = list(grey.tobytes())
    bits = 0
    for row in range(size):
        base = row * (size + 1)
        for column in range(size):
            bits = (bits << 1) | int(pixels[base + column] < pixels[base + column + 1])
    width = (size * size + 3) // 4
    return f"{bits:0{width}x}"


def phash_distance(left: str, right: str) -> int:
    """Hamming distance between two hexadecimal perceptual hashes."""
    if len(left) != len(right):
        raise ValueError(f"hash width differs: {len(left)} != {len(right)}")
    return bin(int(left, 16) ^ int(right, 16)).count("1")


def write_evidence(
    selections: Sequence[EvidenceSelection],
    *,
    run_dir: Path,
    source_sha256: str,
    params: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Save every selected frame under `run_dir/evidence` and describe each one."""
    settings = dict(params or render_params())
    digest = params_hash(settings)
    items: list[dict[str, Any]] = []
    counter = 1
    for selection in selections:
        for frame in selection.frames:
            evidence_id = f"evd_{counter:03d}"
            target = (
                run_dir
                / DEFAULT_OUTPUT_DIR
                / evidence_id
                / f"{frame.deviation_id}_f{frame.frame_index:06d}.png"
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            frame.image.save(target)
            items.append(
                {
                    "evidence_id": evidence_id,
                    "deviation_id": frame.deviation_id,
                    "kind": "evidence",
                    "source_sha256": source_sha256,
                    "frame_index": frame.frame_index,
                    "t": frame.t,
                    "render_version": str(settings["render_version"]),
                    "params_hash": digest,
                    "output_path": target.relative_to(run_dir).as_posix(),
                    "output_sha256": sha256_file(target),
                    "phash": dhash(frame.image),
                    "track_ids": list(frame.track_ids),
                }
            )
            counter += 1
    return tuple(items)


def clip_entry(clip: ClipResult, *, run_dir: Path) -> dict[str, Any]:
    """The `clip` block of an evidence item."""
    return {
        "path": clip.path.resolve().relative_to(run_dir.resolve()).as_posix(),
        "sha256": sha256_file(clip.path),
        "t_start": clip.t_start,
        "t_end": clip.t_end,
    }


def build_manifest(
    items: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
    source_sha256: str,
    params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    settings = dict(params or render_params())
    return {
        "run_id": run_id,
        "render_version": str(settings["render_version"]),
        "params_hash": params_hash(settings),
        "params": settings,
        "source_sha256": source_sha256,
        "items": [dict(item) for item in items],
    }


def _read_frames(video: Path, indices: Iterable[int]) -> dict[int, Image.Image]:
    """Decode the requested analysis frame indices, stopping after the last one."""
    wanted = set(indices)
    if not wanted:
        return {}
    info = probe_video(video)
    frame_bytes = info.width * info.height * 3
    last = max(wanted)
    decoder = subprocess.Popen(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(video),
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
    )
    assert decoder.stdout is not None
    assert decoder.stderr is not None
    frames: dict[int, Image.Image] = {}
    try:
        for index in range(last + 1):
            buffer = decoder.stdout.read(frame_bytes)
            if len(buffer) < frame_bytes:
                break
            if index in wanted:
                frames[index] = Image.frombytes("RGB", (info.width, info.height), buffer)
    finally:
        decoder.stdout.close()
        decoder.wait(timeout=600)
        decoder.stderr.close()
    return frames


def _load_overlays(run_dir: Path) -> tuple[dict[int, tuple[FrameOverlay, ...]], int, int] | None:
    tracks_path = run_dir / "stages" / "tracks.json"
    if not tracks_path.is_file():
        return None
    payload = json.loads(tracks_path.read_text(encoding="utf-8"))
    frames: dict[int, list[FrameOverlay]] = {}
    for track in payload.get("tracks", []):
        for entry in track["frames"]:
            box = entry["box"]
            frames.setdefault(int(entry["frame"]), []).append(
                FrameOverlay(
                    track_id=str(track["id"]),
                    concept=str(track["concept"]),
                    box=(float(box[0]), float(box[1]), float(box[2]), float(box[3])),
                    poly=tuple((float(x), float(y)) for x, y in entry.get("poly", ())),
                )
            )
    video = payload.get("video", {})
    return (
        {index: tuple(items) for index, items in frames.items()},
        int(video.get("width", 0)),
        int(video.get("height", 0)),
    )


def _verify_item(
    item: Mapping[str, Any],
    *,
    run_dir: Path,
    source_sha256: str,
    expected_params_hash: str,
    overlays: Mapping[int, Sequence[FrameOverlay]],
    analysis: Path,
) -> EvidenceCheck:
    evidence_id = str(item.get("evidence_id", "?"))
    if item.get("kind") != "evidence":
        return EvidenceCheck(evidence_id, False, "wrong_kind")
    if item.get("source_sha256") != source_sha256:
        return EvidenceCheck(evidence_id, False, "source_mismatch")
    if item.get("params_hash") != expected_params_hash:
        return EvidenceCheck(evidence_id, False, "params_mismatch")

    output = Path(str(item.get("output_path", "")))
    if not output.is_absolute():
        output = run_dir / output
    if not output.is_file():
        return EvidenceCheck(evidence_id, False, "output_missing")
    if sha256_file(output) != item.get("output_sha256"):
        return EvidenceCheck(evidence_id, False, "output_mismatch")

    frame_index = int(item["frame_index"])
    image = _read_frames(analysis, [frame_index]).get(frame_index)
    if image is None:
        return EvidenceCheck(evidence_id, False, "frame_missing")
    rendered = draw_timestamp(
        render_overlay(image, overlays.get(frame_index, ())), float(item["t"])
    )
    distance = phash_distance(dhash(rendered), str(item.get("phash", "")))
    if distance > PHASH_TOLERANCE_BITS:
        return EvidenceCheck(evidence_id, False, "phash_mismatch")
    return EvidenceCheck(evidence_id, True)


def _all_failed(items: Sequence[Mapping[str, Any]], reason: str) -> VerifyResult:
    return VerifyResult(
        tuple(EvidenceCheck(str(item.get("evidence_id", "?")), False, reason) for item in items)
    )


def verify_report(
    report: Mapping[str, Any],
    *,
    video: Path,
    run_dir: Path,
    params: Mapping[str, Any] | None = None,
) -> VerifyResult:
    """Re-render every evidence item in a report and compare it with the record."""
    items: list[Mapping[str, Any]] = []
    for deviation in report.get("deviations", []):
        items.extend(deviation.get("evidence", []))
    if not items:
        return VerifyResult(())

    loaded = _load_overlays(run_dir)
    if loaded is None:
        return _all_failed(items, "tracks_missing")
    overlays, width, height = loaded
    analysis = run_dir / "media" / "analysis.mp4"
    if not analysis.is_file():
        return _all_failed(items, "analysis_missing")
    info = probe_video(analysis)
    if (width and height) and (info.width, info.height) != (width, height):
        return _all_failed(items, "analysis_missing")

    checks: list[EvidenceCheck] = []
    expected_digest = params_hash(params)
    source_sha = sha256_file(video)
    for item in items:
        checks.append(
            _verify_item(
                item,
                run_dir=run_dir,
                source_sha256=source_sha,
                expected_params_hash=expected_digest,
                overlays=overlays,
                analysis=analysis,
            )
        )
    return VerifyResult(tuple(checks))


def verify_cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pw verify-evidence", description="Re-render report evidence and compare hashes."
    )
    parser.add_argument("report", type=Path, help="path to runs/<id>/report.json")
    parser.add_argument("--video", type=Path, required=True, help="source video the run used")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR cannot read {args.report}: {exc}", file=sys.stderr)
        return 2
    if not args.video.is_file():
        print(f"ERROR video not found: {args.video}", file=sys.stderr)
        return 2

    result = verify_report(report, video=args.video, run_dir=args.report.parent)
    print(result.summary())
    for check in result.checks:
        if not check.ok:
            print(f"  {check.evidence_id}: {check.reason}", file=sys.stderr)
    return 0 if result.ok else 1


__all__ = [
    "RENDER_VERSION",
    "EvidenceCheck",
    "VerifyResult",
    "build_manifest",
    "clip_entry",
    "dhash",
    "params_hash",
    "phash_distance",
    "render_params",
    "verify_cli",
    "verify_report",
    "write_evidence",
]

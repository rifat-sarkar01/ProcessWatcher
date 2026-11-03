"""Perception sanity gate on a bench split (T-2.10).

Reads finished pipeline runs (tracks + timeline artifacts) and checks three things per clip:
hand coverage ≥ 90% of analysis frames, stitching fragmentation ≤ 1.5, and tool
`hold_start` events inside a ground-truth step window ± 2 s for ≥ 80% of events.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MIN_HAND_COVERAGE = 0.90
MAX_FRAGMENTATION = 1.5
MIN_PICKUP_HIT_RATE = 0.80
PICKUP_TOLERANCE_S = 2.0
_NON_TOOL_CONCEPTS = {"hand", "keyboard", "keycaps", "keyboard frame", "work surface"}


@dataclass(frozen=True, slots=True)
class ClipCheck:
    clip_id: str
    run_id: str | None
    hand_coverage: float
    fragmentation: float
    pickup_hit_rate: float
    passed: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PerceptionCheck:
    split: str
    mode: str
    clips: tuple[ClipCheck, ...]

    @property
    def passed(self) -> int:
        return sum(1 for clip in self.clips if clip.passed)

    @property
    def required(self) -> int:
        return max(1, math.ceil(0.8 * len(self.clips)))

    @property
    def ok(self) -> bool:
        return self.passed >= self.required


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def _runs_by_clip(runs_dir: Path, mode: str) -> dict[str, Path]:
    """Map video sha256 → newest run directory for runs recorded in `mode`."""
    by_hash: dict[str, tuple[str, Path]] = {}
    for run_dir in sorted(runs_dir.glob("run_*")):
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = _load(manifest_path)
        except (OSError, ValueError):
            continue
        if manifest.get("mode") != mode:
            continue
        video_hash = manifest.get("inputs", {}).get("video_sha256")
        if not isinstance(video_hash, str):
            continue
        created = str(manifest.get("created_at", ""))
        previous = by_hash.get(video_hash)
        if previous is None or created > previous[0]:
            by_hash[video_hash] = (created, run_dir)
    return {sha: run_dir for sha, (_, run_dir) in by_hash.items()}


def _hand_coverage(tracks: dict[str, Any]) -> float:
    frames: set[int] = set()
    for track in tracks.get("tracks", []):
        if track.get("concept") != "hand":
            continue
        frames.update(int(frame["frame"]) for frame in track.get("frames", []))
    frame_count = int(tracks["video"]["frame_count"])
    return len(frames) / frame_count if frame_count else 0.0


def _fragmentation(tracks: dict[str, Any], instances: dict[str, Any]) -> float:
    stitching = tracks.get("stitching")
    if isinstance(stitching, dict) and isinstance(
        stitching.get("fragmentation_ratio"), (int, float)
    ):
        return float(stitching["fragmentation_ratio"])
    expected = sum(int(value) for value in instances.values())
    actual = len(tracks.get("tracks", []))
    return actual / expected if expected else float("inf")


def _pickup_hit_rate(
    tracks: dict[str, Any], timeline: dict[str, Any], windows: list[tuple[float, float]]
) -> float:
    concept_by_track = {
        str(track["id"]): str(track.get("concept")) for track in tracks.get("tracks", [])
    }
    pickups = [
        event
        for event in timeline.get("events", [])
        if event.get("type") == "hold_start"
        and any(
            concept_by_track.get(str(track_id)) not in _NON_TOOL_CONCEPTS
            for track_id in event.get("tracks", [])
        )
    ]
    if not pickups:
        return 0.0
    hits = 0
    for event in pickups:
        start = float(event["t_start"])
        end = float(event["t_end"])
        if any(
            start <= window_end + PICKUP_TOLERANCE_S and end >= window_start - PICKUP_TOLERANCE_S
            for window_start, window_end in windows
        ):
            hits += 1
    return hits / len(pickups)


def check_clip(gt: dict[str, Any], run_dir: Path) -> ClipCheck:
    run_id = run_dir.name
    stages = run_dir / "stages"
    reasons: list[str] = []
    try:
        tracks = _load(stages / "tracks.json")
        timeline = _load(stages / "timeline.json")
    except (OSError, ValueError) as exc:
        return ClipCheck(gt["clip_id"], run_id, 0.0, float("inf"), 0.0, False, (str(exc),))

    hand = _hand_coverage(tracks)
    fragmentation = _fragmentation(tracks, gt.get("instances", {}))
    windows = [(float(step["t_start"]), float(step["t_end"])) for step in gt.get("steps", [])]
    pickups = _pickup_hit_rate(tracks, timeline, windows)

    if hand < MIN_HAND_COVERAGE:
        reasons.append(f"hand coverage {hand:.1%} < {MIN_HAND_COVERAGE:.0%}")
    if fragmentation > MAX_FRAGMENTATION:
        reasons.append(f"fragmentation {fragmentation:.2f} > {MAX_FRAGMENTATION}")
    if pickups < MIN_PICKUP_HIT_RATE:
        reasons.append(f"tool pick-up hit rate {pickups:.1%} < {MIN_PICKUP_HIT_RATE:.0%}")
    return ClipCheck(
        gt["clip_id"], run_id, hand, fragmentation, pickups, not reasons, tuple(reasons)
    )


def perception_check(*, split: str, mode: str, bench_dir: Path, runs_dir: Path) -> PerceptionCheck:
    split_dir = bench_dir / split
    manifest = _load(split_dir / "manifest.json")
    runs = _runs_by_clip(runs_dir, mode)
    checks: list[ClipCheck] = []
    for clip in manifest["clips"]:
        gt = _load(split_dir / clip["gt_path"])
        run_dir = runs.get(str(clip["sha256"]))
        if run_dir is None:
            checks.append(
                ClipCheck(
                    str(clip["clip_id"]),
                    None,
                    0.0,
                    float("inf"),
                    0.0,
                    False,
                    (f"no {mode} run for this clip",),
                )
            )
            continue
        checks.append(check_clip(gt, run_dir))
    return PerceptionCheck(split=split, mode=mode, clips=tuple(checks))


def render_markdown(result: PerceptionCheck) -> str:
    lines = [
        f"# Perception check — {result.split} ({result.mode})",
        "",
        f"**{'PASS' if result.ok else 'FAIL'} {result.passed}/{len(result.clips)}** "
        f"(required {result.required})",
        "",
        "| Clip | Run | Hand coverage | Fragmentation | Pick-up hit rate | Result |",
        "|---|---|---|---|---|---|",
    ]
    for clip in result.clips:
        hand = f"{clip.hand_coverage:.1%}" if clip.run_id else "—"
        frag = f"{clip.fragmentation:.2f}" if clip.run_id else "—"
        pickup = f"{clip.pickup_hit_rate:.1%}" if clip.run_id else "—"
        verdict = "PASS" if clip.passed else "FAIL"
        lines.append(
            f"| {clip.clip_id} | {clip.run_id or '—'} | {hand} | {frag} | {pickup} | {verdict} |"
        )
    exceptions = [clip for clip in result.clips if not clip.passed]
    lines.extend(["", "## Exceptions", ""])
    if not exceptions:
        lines.append("None.")
    else:
        for clip in exceptions:
            lines.append(f"- **{clip.clip_id}**: {'; '.join(clip.reasons)}")
    return "\n".join(lines) + "\n"


__all__ = [
    "ClipCheck",
    "PerceptionCheck",
    "check_clip",
    "perception_check",
    "render_markdown",
]

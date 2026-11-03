"""Threshold calibration on DEV only (T-3.10).

Reclassifies stored deviation confidences under a grid of `tau_review`/`tau_flag`,
scores each pair against the dev ground truth, keeps the best F1 subject to
≤ 0.3 false flags per compliant clip, and freezes `config/thresholds.json`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pw.bench.metrics import (
    BenchMetrics,
    Deviation,
    aggregate,
    evaluate_clip,
    from_ground_truth,
)
from pw.data.lock import verify_lock
from pw.data.schemas import load_json

TAU_FLAG_GRID = tuple(round(0.50 + 0.05 * index, 2) for index in range(9))
TAU_REVIEW_GRID = tuple(round(0.20 + 0.05 * index, 2) for index in range(9))
MAX_FALSE_FLAGS = 0.3


class TuneError(ValueError):
    """Calibration cannot proceed (missing runs, bad lock, no candidate)."""


@dataclass(frozen=True, slots=True)
class RawPrediction:
    step_id: str
    kind: str
    t_start: float
    t_end: float
    confidence: float


@dataclass(frozen=True, slots=True)
class ClipSample:
    clip_id: str
    compliant: bool
    truths: tuple[Deviation, ...]
    predictions: tuple[RawPrediction, ...]


def _load_runs_by_sha(runs_dir: Path) -> dict[str, Path]:
    by_sha: dict[str, tuple[str, Path]] = {}
    for run_dir in sorted(runs_dir.glob("run_*")):
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        manifest = load_json(manifest_path)
        video_hash = manifest.get("inputs", {}).get("video_sha256")
        if not isinstance(video_hash, str):
            continue
        created = str(manifest.get("created_at", ""))
        previous = by_sha.get(video_hash)
        if previous is None or created > previous[0]:
            by_sha[video_hash] = (created, run_dir)
    return {sha: path for sha, (_, path) in by_sha.items()}


def _raw_predictions(run_dir: Path) -> tuple[RawPrediction, ...]:
    path = run_dir / "stages" / "deviations.json"
    payload = load_json(path)
    return tuple(
        RawPrediction(
            step_id=str(item["step_id"]),
            kind=str(item["type"]),
            t_start=float(item["t_start"]),
            t_end=float(item["t_end"]),
            confidence=float(item["confidence"]),
        )
        for item in payload.get("deviations", ())
    )


def load_dev_samples(bench_dir: Path, runs_dir: Path) -> list[ClipSample]:
    manifest = load_json(bench_dir / "dev" / "manifest.json")
    runs = _load_runs_by_sha(runs_dir)
    samples: list[ClipSample] = []
    missing: list[str] = []
    for clip in manifest["clips"]:
        run_dir = runs.get(str(clip["sha256"]))
        if run_dir is None:
            missing.append(str(clip["clip_id"]))
            continue
        gt = load_json(bench_dir / "dev" / clip["gt_path"])
        samples.append(
            ClipSample(
                clip_id=str(clip["clip_id"]),
                compliant=bool(gt["compliant"]),
                truths=tuple(from_ground_truth(gt)),
                predictions=_raw_predictions(run_dir),
            )
        )
    if missing:
        raise TuneError(f"no run for {len(missing)} dev clip(s): {', '.join(missing)}")
    return samples


def evaluate_thresholds(
    samples: list[ClipSample], *, tau_review: float, tau_flag: float
) -> BenchMetrics:
    if tau_review > tau_flag:
        raise TuneError("tau_review must not exceed tau_flag")
    clip_metrics = []
    for sample in samples:
        predictions = []
        for raw in sample.predictions:
            if raw.confidence < tau_review:
                continue
            status = "flagged" if raw.confidence >= tau_flag else "needs_review"
            predictions.append(
                Deviation(raw.step_id, raw.kind, raw.t_start, raw.t_end, status=status)
            )
        clip_metrics.append(
            evaluate_clip(
                sample.clip_id,
                predictions,
                sample.truths,
                compliant=sample.compliant,
            )
        )
    return aggregate(clip_metrics)


def choose_thresholds(samples: list[ClipSample]) -> tuple[float, float, BenchMetrics]:
    best = choose_thresholds_with_status(samples)
    if best is None or not best[3]:
        raise TuneError("no threshold pair satisfies the false-flags constraint")
    return best[0], best[1], best[2]


def choose_thresholds_with_status(
    samples: list[ClipSample],
) -> tuple[float, float, BenchMetrics, bool] | None:
    """Best constrained pair; when none exists, the best-F1 pair with `met=False`."""
    best: tuple[float, float, BenchMetrics] | None = None
    best_any: tuple[float, float, BenchMetrics] | None = None
    for tau_flag in TAU_FLAG_GRID:
        for tau_review in TAU_REVIEW_GRID:
            if tau_review > tau_flag:
                continue
            metrics = evaluate_thresholds(samples, tau_review=tau_review, tau_flag=tau_flag)
            if best_any is None or metrics.overall.f1 > best_any[2].overall.f1:
                best_any = (tau_review, tau_flag, metrics)
            if metrics.false_flags_per_compliant_clip > MAX_FALSE_FLAGS:
                continue
            if best is None or metrics.overall.f1 > best[2].overall.f1:
                best = (tau_review, tau_flag, metrics)
    if best is not None:
        return best[0], best[1], best[2], True
    if best_any is None:
        return None
    return best_any[0], best_any[1], best_any[2], False


def tune(*, bench_dir: Path, runs_dir: Path) -> tuple[float, float, BenchMetrics, bool]:
    lock_errors = verify_lock(bench_dir)
    if lock_errors:
        raise TuneError("; ".join(lock_errors))
    samples = load_dev_samples(bench_dir, runs_dir)
    chosen = choose_thresholds_with_status(samples)
    if chosen is None:
        raise TuneError("no threshold pair could be evaluated")
    return chosen


def write_thresholds(path: Path, *, tau_review: float, tau_flag: float) -> str:
    template = load_json(Path("contracts/examples/thresholds.example.json"))
    payload: dict[str, Any] = dict(template)
    deviation = dict(payload["deviation"])
    deviation["tau_review"] = tau_review
    deviation["tau_flag"] = tau_flag
    payload["deviation"] = deviation
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")
    return text


def render_report(
    *,
    tau_review: float,
    tau_flag: float,
    metrics: BenchMetrics,
    lock_ok: bool,
    constraint_met: bool = True,
) -> str:
    return (
        "# Threshold calibration — dev\n\n"
        f"- chosen `tau_review = {tau_review:.2f}` · `tau_flag = {tau_flag:.2f}`\n"
        f"- overall P = {metrics.overall.precision:.3f} · R = {metrics.overall.recall:.3f} "
        f"· F1 = {metrics.overall.f1:.3f}\n"
        f"- false flags per compliant clip = {metrics.false_flags_per_compliant_clip:.2f} "
        f"(limit {MAX_FALSE_FLAGS}; {'met' if constraint_met else 'NOT met'})\n"
        f"- needs-review rate = {metrics.needs_review_rate:.1%} · timestamp MAE = "
        f"{metrics.timestamp_mae_s:.2f} s\n"
        f"- held-out lock: {'OK' if lock_ok else 'VIOLATION'} (dev only; no held-out tuning)\n"
        + (
            ""
            if constraint_met
            else (
                "\nThe false-flag constraint is unreachable on this dev set: late short steps "
                "(wipe frame / inspect) are systematically under-detected, so every compliant "
                "clip carries a high-confidence `missed` finding. The table above is the "
                "best-F1 pair; the run is reported, not silently relaxed.\n"
            )
        )
    )


__all__ = [
    "ClipSample",
    "RawPrediction",
    "TuneError",
    "choose_thresholds",
    "choose_thresholds_with_status",
    "evaluate_thresholds",
    "load_dev_samples",
    "render_report",
    "tune",
    "write_thresholds",
]

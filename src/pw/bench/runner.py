"""PW-Bench runner (T-1.7): split manifest → predictor → metrics → result files.

`oracle` replays the ground truth and must score F1 1.00; `empty` predicts nothing and
must score recall 0. The `full` and baseline predictors are registered names for later
cards, so they fail fast with exit code 3 instead of pretending to work. No dev clips
are needed for the runner itself: tests point `--bench-dir` at a synthetic split.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol

from pw import __version__
from pw.bench.metrics import (
    FLAGGED,
    TOLERANCE_S,
    BenchMetrics,
    ClipMetrics,
    CostSummary,
    Deviation,
    Prf,
    aggregate,
    evaluate_clip,
    from_ground_truth,
    summarise_costs,
)
from pw.data.schemas import load_json
from pw.data.sopcheck import golden_step_ids, validate_gt
from pw.pipeline.runstore import new_run_id

SCHEMA_VERSION = "1.0.0"
SPLITS = ("dev", "heldout")
IMPLEMENTED_PREDICTORS = ("oracle", "empty")
DECLARED_PREDICTORS = ("full", "baseline_a", "baseline_b")


class BenchError(ValueError):
    """A bench run cannot proceed; `exit_code` is the CLI status."""

    def __init__(self, message: str, *, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(frozen=True, slots=True)
class ClipRef:
    clip_id: str
    procedure: str
    duration_s: float
    gt_path: Path
    storage_ref: str | None = None
    sha256: str = ""


@dataclass(frozen=True, slots=True)
class SplitManifest:
    split: str
    path: Path
    clips: tuple[ClipRef, ...]


@dataclass(frozen=True, slots=True)
class ClipPrediction:
    deviations: tuple[Deviation, ...] = ()
    cost_usd: float = 0.0
    latency_s: float = 0.0


@dataclass(frozen=True, slots=True)
class BenchRun:
    run_id: str
    run_dir: Path
    summary: dict[str, Any]
    per_clip: tuple[dict[str, Any], ...]


class Predictor(Protocol):
    @property
    def name(self) -> str: ...

    def predict(self, clip: ClipRef, truth: Mapping[str, Any]) -> ClipPrediction: ...


@dataclass(frozen=True, slots=True)
class OraclePredictor:
    """Replay the ground truth as flagged deviations."""

    name: str = "oracle"

    def predict(self, clip: ClipRef, truth: Mapping[str, Any]) -> ClipPrediction:
        deviations = tuple(
            replace(deviation, status=FLAGGED) for deviation in from_ground_truth(truth)
        )
        return ClipPrediction(deviations=deviations)


@dataclass(frozen=True, slots=True)
class EmptyPredictor:
    """Predict nothing: recall must be 0 and a compliant clip must have 0 false flags."""

    name: str = "empty"

    def predict(self, clip: ClipRef, truth: Mapping[str, Any]) -> ClipPrediction:
        return ClipPrediction()


def _latest_run_for(clip: ClipRef, runs_dir: Path) -> Path | None:
    if not clip.sha256:
        return None
    found: tuple[str, Path] | None = None
    for run_dir in runs_dir.glob("run_*"):
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = load_json(manifest_path)
        except (OSError, ValueError):
            continue
        video_hash = manifest.get("inputs", {}).get("video_sha256")
        if video_hash != clip.sha256:
            continue
        created = str(manifest.get("created_at", ""))
        if found is None or created > found[0]:
            found = (created, run_dir)
    return found[1] if found else None


@dataclass(frozen=True, slots=True)
class FullPredictor:
    """Replay the deviations of the latest finished pipeline run for each clip."""

    runs_dir: Path = Path("runs")
    name: str = "full"

    def predict(self, clip: ClipRef, truth: Mapping[str, Any]) -> ClipPrediction:
        del truth
        run_dir = _latest_run_for(clip, self.runs_dir)
        if run_dir is None:
            raise BenchError(f"no run for clip {clip.clip_id} ({clip.sha256[:12]})", exit_code=1)
        report = load_json(run_dir / "report.json")
        deviations = tuple(
            Deviation(
                step_id=str(item["step_id"]),
                kind=str(item["type"]),
                t_start=float(item["t_start"]),
                t_end=float(item["t_end"]),
                status=str(item["status"]),
            )
            for item in report.get("deviations", ())
        )
        manifest = load_json(run_dir / "manifest.json")
        cost = float(manifest.get("ledger", {}).get("total_usd", 0.0))
        return ClipPrediction(deviations=deviations, cost_usd=cost)


def build_predictor(name: str, *, runs_dir: Path = Path("runs")) -> Predictor:
    if name == "oracle":
        return OraclePredictor()
    if name == "empty":
        return EmptyPredictor()
    if name == "full":
        return FullPredictor(runs_dir=runs_dir)
    if name in DECLARED_PREDICTORS:
        raise BenchError(
            f"predictor {name!r} is declared but not implemented yet (T-3.12/T-3.9)",
            exit_code=3,
        )
    expected = ", ".join((*IMPLEMENTED_PREDICTORS, *DECLARED_PREDICTORS))
    raise BenchError(f"unknown predictor {name!r}; expected one of {expected}", exit_code=2)


def load_split_manifest(bench_dir: Path, split: str) -> SplitManifest:
    if split not in SPLITS:
        raise BenchError(f"split must be one of {', '.join(SPLITS)}; got {split!r}", exit_code=2)
    path = Path(bench_dir) / split / "manifest.json"
    if not path.is_file():
        raise BenchError(f"split manifest not found: {path}", exit_code=2)
    try:
        payload = load_json(path)
    except (OSError, ValueError) as error:
        raise BenchError(str(error), exit_code=1) from error
    if not isinstance(payload, Mapping):
        raise BenchError(f"{path}: manifest root must be an object", exit_code=1)
    if payload.get("split") != split:
        raise BenchError(f"{path}: split is {payload.get('split')!r}, expected {split!r}")
    raw_clips = payload.get("clips")
    if not isinstance(raw_clips, list) or not raw_clips:
        raise BenchError(f"{path}: clips must be a non-empty list", exit_code=1)

    clips: list[ClipRef] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_clips):
        if not isinstance(raw, Mapping):
            raise BenchError(f"{path}: clips[{index}] must be an object", exit_code=1)
        clip_id = str(raw.get("clip_id") or "").strip()
        if not clip_id:
            raise BenchError(f"{path}: clips[{index}] has no clip_id", exit_code=1)
        if clip_id in seen:
            raise BenchError(f"{path}: duplicate clip_id {clip_id!r}", exit_code=1)
        seen.add(clip_id)
        procedure = str(raw.get("procedure") or "").strip()
        if procedure not in {"A", "B", "C"}:
            raise BenchError(f"{path}: clips[{index}] procedure must be A, B or C", exit_code=1)
        try:
            duration_s = float(raw["duration_s"])
        except (KeyError, TypeError, ValueError) as error:
            raise BenchError(
                f"{path}: clips[{index}] has no numeric duration_s", exit_code=1
            ) from error
        if duration_s <= 0:
            raise BenchError(f"{path}: clips[{index}] duration_s must be positive", exit_code=1)
        gt_value = raw.get("gt_path") or f"gt/{clip_id}.json"
        gt_path = Path(str(gt_value))
        if not gt_path.is_absolute():
            gt_path = path.parent / gt_path
        storage = raw.get("storage_ref")
        clips.append(
            ClipRef(
                clip_id=clip_id,
                procedure=procedure,
                duration_s=duration_s,
                gt_path=gt_path,
                storage_ref=str(storage) if storage is not None else None,
                sha256=str(raw.get("sha256", "")),
            )
        )
    return SplitManifest(split=split, path=path, clips=tuple(clips))


def load_truth(clip: ClipRef, bench_dir: Path) -> dict[str, Any]:
    try:
        payload = load_json(clip.gt_path)
    except (OSError, ValueError) as error:
        raise BenchError(str(error), exit_code=1) from error
    if not isinstance(payload, dict):
        raise BenchError(f"{clip.gt_path}: ground truth must be an object", exit_code=1)
    if payload.get("clip_id") != clip.clip_id:
        raise BenchError(
            f"{clip.gt_path}: clip_id is {payload.get('clip_id')!r}, expected {clip.clip_id!r}",
            exit_code=1,
        )
    golden = Path(bench_dir) / "golden" / f"P-{clip.procedure}.json"
    if not golden.is_file():
        raise BenchError(f"golden step graph not found: {golden}", exit_code=1)
    try:
        steps = golden_step_ids(golden)
    except (OSError, ValueError) as error:
        raise BenchError(str(error), exit_code=1) from error
    errors = validate_gt(payload, steps, bench_dir)
    if errors:
        raise BenchError("; ".join(errors), exit_code=1)
    return payload


def run_bench(
    *,
    split: str,
    predictor: str,
    bench_dir: Path = Path("bench"),
    results_dir: Path = Path("results"),
    config_path: Path | None = None,
    mode: str = "replay",
    run_id: str | None = None,
    tolerance_s: float = TOLERANCE_S,
    runs_dir: Path = Path("runs"),
) -> BenchRun:
    split_manifest = load_split_manifest(bench_dir, split)
    engine = build_predictor(predictor, runs_dir=runs_dir)
    config_sha256 = _config_hash(config_path)
    truths = {clip.clip_id: load_truth(clip, bench_dir) for clip in split_manifest.clips}

    identifier = run_id or new_run_id()
    run_dir = Path(results_dir) / identifier
    if run_dir.exists():
        raise BenchError(f"result directory already exists: {run_dir}", exit_code=1)
    created_at = _utc_now()

    metrics: list[ClipMetrics] = []
    per_clip: list[dict[str, Any]] = []
    costs: list[float] = []
    latencies: list[float] = []
    for clip in split_manifest.clips:
        truth = truths[clip.clip_id]
        prediction = engine.predict(clip, truth)
        clip_metrics = evaluate_clip(
            clip.clip_id,
            prediction.deviations,
            from_ground_truth(truth),
            compliant=bool(truth["compliant"]),
            tolerance_s=tolerance_s,
        )
        metrics.append(clip_metrics)
        costs.append(prediction.cost_usd)
        latencies.append(prediction.latency_s)
        per_clip.append(
            {
                "clip_id": clip.clip_id,
                "procedure": clip.procedure,
                "compliant": bool(truth["compliant"]),
                "duration_s": clip.duration_s,
                "overall": _prf(clip_metrics.overall),
                "by_type": {kind: _prf(value) for kind, value in clip_metrics.by_type.items()},
                "flagged": clip_metrics.flagged,
                "needs_review": clip_metrics.needs_review,
                "matched_errors_s": [round(value, 6) for value in clip_metrics.matched_errors_s],
                "cost_usd": round(prediction.cost_usd, 8),
                "latency_s": round(prediction.latency_s, 6),
            }
        )

    bench_metrics = aggregate(metrics)
    cost_summary = summarise_costs(
        costs, [clip.duration_s for clip in split_manifest.clips], latencies
    )
    summary = _summary(
        run_id=identifier,
        split=split,
        predictor=predictor,
        mode=mode,
        created_at=created_at,
        metrics=bench_metrics,
        costs=cost_summary,
    )
    summary["config_sha256"] = config_sha256
    summary["git_commit"] = _git_commit()

    run_dir.mkdir(parents=True)
    summary_path = _write_json(run_dir / "summary.json", summary)
    per_clip_path = _write_json(run_dir / "per_clip.json", {"clips": per_clip})
    table_path = run_dir / "table.md"
    table_path.write_text(
        _table(split, predictor, bench_metrics, cost_summary, per_clip), encoding="utf-8"
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "run_id": identifier,
        "split": split,
        "predictor": predictor,
        "mode": mode,
        "created_at": created_at,
        "finished_at": _utc_now(),
        "config_sha256": config_sha256,
        "split_manifest_sha256": _file_hash(split_manifest.path),
        "clip_count": len(split_manifest.clips),
        "files": {
            "summary.json": _file_hash(summary_path),
            "per_clip.json": _file_hash(per_clip_path),
            "table.md": _file_hash(table_path),
        },
        "git_commit": _git_commit(),
        "app_version": __version__,
    }
    _write_json(run_dir / "manifest.json", manifest)
    return BenchRun(identifier, run_dir.resolve(), summary, tuple(per_clip))


def _summary(
    *,
    run_id: str,
    split: str,
    predictor: str,
    mode: str,
    created_at: str,
    metrics: BenchMetrics,
    costs: CostSummary,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "split": split,
        "predictor": predictor,
        "mode": mode,
        "created_at": created_at,
        "clips": metrics.clips,
        "overall": _prf(metrics.overall),
        "by_type": {kind: _prf(value) for kind, value in metrics.by_type.items()},
        "false_flags_per_compliant_clip": round(metrics.false_flags_per_compliant_clip, 6),
        "timestamp_mae_s": round(metrics.timestamp_mae_s, 6),
        "needs_review_rate": round(metrics.needs_review_rate, 6),
        "costs": {
            "total_usd": round(costs.total_usd, 8),
            "per_video_minute": round(costs.per_video_minute, 8),
            "mean_latency_s": round(costs.mean_latency_s, 6),
        },
    }


def _prf(value: Prf) -> dict[str, float | int]:
    return {
        "tp": value.tp,
        "fp": value.fp,
        "fn": value.fn,
        "precision": round(value.precision, 6),
        "recall": round(value.recall, 6),
        "f1": round(value.f1, 6),
    }


def _table(
    split: str,
    predictor: str,
    metrics: BenchMetrics,
    costs: CostSummary,
    per_clip: Sequence[Mapping[str, Any]],
) -> str:
    lines = [
        "# PW-Bench",
        "",
        f"- split: `{split}`",
        f"- predictor: `{predictor}`",
        f"- clips: {metrics.clips}",
        "",
        "| metric | value |",
        "|---|---|",
        f"| precision | {metrics.overall.precision:.4f} |",
        f"| recall | {metrics.overall.recall:.4f} |",
        f"| F1 | {metrics.overall.f1:.4f} |",
        f"| false flags / compliant clip | {metrics.false_flags_per_compliant_clip:.4f} |",
        f"| timestamp MAE (s) | {metrics.timestamp_mae_s:.4f} |",
        f"| needs-review rate | {metrics.needs_review_rate:.4f} |",
        f"| cost / video minute (USD) | {costs.per_video_minute:.6f} |",
        f"| mean latency (s) | {costs.mean_latency_s:.4f} |",
        "",
        "| clip | P | R | F1 | flagged | needs_review | cost_usd |",
        "|---|---|---|---|---|---|---|",
    ]
    for clip in per_clip:
        overall = clip["overall"]
        lines.append(
            f"| {clip['clip_id']} | {overall['precision']:.4f} | {overall['recall']:.4f} | "
            f"{overall['f1']:.4f} | {clip['flagged']} | {clip['needs_review']} | "
            f"{clip['cost_usd']:.6f} |"
        )
    return "\n".join(lines) + "\n"


def _config_hash(config_path: Path | None) -> str:
    if config_path is None:
        return sha256(b"defaults-v1").hexdigest()
    path = Path(config_path)
    if not path.is_file():
        raise BenchError(f"config not found: {path}", exit_code=2)
    return _file_hash(path)


def _write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_commit() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown0"
    value = completed.stdout.strip()
    return value if len(value) >= 7 else "unknown0"


__all__ = [
    "DECLARED_PREDICTORS",
    "IMPLEMENTED_PREDICTORS",
    "SCHEMA_VERSION",
    "SPLITS",
    "BenchError",
    "BenchRun",
    "ClipPrediction",
    "ClipRef",
    "EmptyPredictor",
    "FullPredictor",
    "OraclePredictor",
    "Predictor",
    "SplitManifest",
    "build_predictor",
    "load_split_manifest",
    "load_truth",
    "run_bench",
]

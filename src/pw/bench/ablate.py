"""Dev ablation table (T-6.1) from finished pipeline runs.

Rows: full, no_verifier, oracle, empty, baseline A and baseline B. The two baselines
are not implemented in this submission; the analysis section says so instead of
inventing numbers. Full-vs-oracle bootstrap CIs are computed over clips.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from pw.bench.metrics import (
    BenchMetrics,
    Deviation,
    Prf,
    aggregate,
    evaluate_clip,
    from_ground_truth,
)
from pw.data.schemas import load_json

BOOTSTRAP_RESAMPLES = 1000


@dataclass(frozen=True, slots=True)
class AblationRow:
    name: str
    metrics: BenchMetrics | None
    note: str = ""


@dataclass(frozen=True, slots=True)
class AblationResult:
    split: str
    rows: tuple[AblationRow, ...]
    full_ci: tuple[float, float] | None
    cost_per_min: float
    latency_s: float


def _runs_by_sha(runs_dir: Path) -> dict[str, Path]:
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


def _deviations(path: Path) -> tuple[Deviation, ...]:
    payload = load_json(path)
    return tuple(
        Deviation(
            step_id=str(item["step_id"]),
            kind=str(item["type"]),
            t_start=float(item["t_start"]),
            t_end=float(item["t_end"]),
            status=str(item["status"]),
        )
        for item in payload.get("deviations", ())
    )


def _metrics(
    rows: list[tuple[str, bool, tuple[Deviation, ...], tuple[Deviation, ...]]],
) -> BenchMetrics:
    return aggregate(
        [
            evaluate_clip(clip_id, predictions, truths, compliant=compliant)
            for clip_id, compliant, truths, predictions in rows
        ]
    )


def bootstrap_f1(
    counts: list[tuple[int, int, int]],
    *,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = 7,
) -> tuple[float, float]:
    """95% CI of F1 by resampling clips (tp, fp, fn) with replacement."""
    rng = random.Random(seed)
    values: list[float] = []
    for _ in range(resamples):
        total = Prf(0, 0, 0)
        for _ in counts:
            tp, fp, fn = counts[rng.randrange(len(counts))]
            total = total + Prf(tp, fp, fn)
        values.append(total.f1)
    values.sort()
    return values[int(0.025 * len(values))], values[int(0.975 * len(values))]


def _sample_rows(
    bench_dir: Path, split: str, runs_dir: Path
) -> tuple[list[tuple[str, bool, tuple[Deviation, ...]]], list[Path], list[float], list[float]]:
    manifest = load_json(bench_dir / split / "manifest.json")
    runs = _runs_by_sha(runs_dir)
    clips: list[tuple[str, bool, tuple[Deviation, ...]]] = []
    run_dirs: list[Path] = []
    costs: list[float] = []
    latencies: list[float] = []
    for clip in manifest["clips"]:
        run_dir = runs.get(str(clip["sha256"]))
        if run_dir is None:
            raise ValueError(f"no run for clip {clip['clip_id']}")
        gt = load_json(bench_dir / split / clip["gt_path"])
        clips.append((str(clip["clip_id"]), bool(gt["compliant"]), tuple(from_ground_truth(gt))))
        run_dirs.append(run_dir)
        run_manifest = load_json(run_dir / "manifest.json")
        costs.append(float(run_manifest.get("ledger", {}).get("total_usd", 0.0)))
        stages = run_manifest.get("stages", [])
        latencies.append(sum(float(stage.get("duration_ms", 0)) for stage in stages) / 1000.0)
    return clips, run_dirs, costs, latencies


def run_ablation(*, bench_dir: Path, runs_dir: Path, split: str = "dev") -> AblationResult:
    clips, run_dirs, costs, latencies = _sample_rows(bench_dir, split, runs_dir)
    full_rows: list[tuple[str, bool, tuple[Deviation, ...], tuple[Deviation, ...]]] = []
    no_verifier_rows: list[tuple[str, bool, tuple[Deviation, ...], tuple[Deviation, ...]]] = []
    oracle_rows: list[tuple[str, bool, tuple[Deviation, ...], tuple[Deviation, ...]]] = []
    empty_rows: list[tuple[str, bool, tuple[Deviation, ...], tuple[Deviation, ...]]] = []
    for (clip_id, compliant, truths), run_dir in zip(clips, run_dirs, strict=True):
        full_preds = _deviations(run_dir / "report.json")
        pre_verify = _deviations(run_dir / "stages" / "deviations.json")
        full_rows.append((clip_id, compliant, truths, full_preds))
        no_verifier_rows.append((clip_id, compliant, truths, pre_verify))
        oracle_rows.append(
            (
                clip_id,
                compliant,
                truths,
                tuple(
                    Deviation(truth.step_id, truth.kind, truth.t_start, truth.t_end, "flagged")
                    for truth in truths
                ),
            )
        )
        empty_rows.append((clip_id, compliant, truths, tuple()))

    full_metrics = _metrics(full_rows)
    overall_counts = [
        (row.overall.tp, row.overall.fp, row.overall.fn)
        for row in (
            evaluate_clip(clip_id, predictions, truths, compliant=compliant)
            for clip_id, compliant, truths, predictions in full_rows
        )
    ]
    duration_min = (
        sum(
            float(load_json(run_dir / "stages" / "tracks.json")["video"]["duration_s"])
            for run_dir in run_dirs
        )
        / 60.0
    )
    total_cost = sum(costs)
    rows = (
        AblationRow("full", full_metrics),
        AblationRow("no_verifier", _metrics(no_verifier_rows)),
        AblationRow("no_aligner (greedy argmax)", None, "not run: needs a re-decode"),
        AblationRow("no_identity_vote", None, "not run: needs per-call identity votes"),
        AblationRow("baseline_a (raw video, Wonder)", None, "not run: T-3.12 not implemented"),
        AblationRow("baseline_b (keyframes, Wonder)", None, "not run: T-3.12 not implemented"),
        AblationRow("oracle", _metrics(oracle_rows)),
        AblationRow("empty", _metrics(empty_rows)),
    )
    return AblationResult(
        split=split,
        rows=rows,
        full_ci=bootstrap_f1(overall_counts),
        cost_per_min=total_cost / duration_min if duration_min else 0.0,
        latency_s=sum(latencies) / len(latencies) if latencies else 0.0,
    )


def render_report(result: AblationResult) -> str:
    lines = [
        f"# Dev ablation — {result.split}",
        "",
        "| Row | P | R | F1 | False flags / compliant clip | Note |",
        "|---|---|---|---|---|---|",
    ]
    for row in result.rows:
        if row.metrics is None:
            lines.append(f"| {row.name} | — | — | — | — | {row.note} |")
            continue
        metrics = row.metrics
        lines.append(
            f"| {row.name} | {metrics.overall.precision:.3f} | {metrics.overall.recall:.3f} "
            f"| {metrics.overall.f1:.3f} | {metrics.false_flags_per_compliant_clip:.2f} |"
        )
    if result.full_ci:
        low, high = result.full_ci
        lines.extend(["", f"Full F1 95% CI: {low:.3f}-{high:.3f} (1000 clip resamples)."])
    lines.extend(
        [
            "",
            f"Cost: ${result.cost_per_min:.2f}/video-minute · mean wall time: "
            f"{result.latency_s / 60:.1f} min/clip.",
            "",
            "## Analysis",
            "",
            "Full ≥ baseline B F1 + 0.10 cannot be claimed: the two Wonder baselines and the "
            "component recomputations (greedy aligner, identity vote) were not run in this "
            "submission. The full pipeline's false flags on compliant clips remain high "
            "because SAM tracks parts (keyboard, keycaps) next to tools; parts are now "
            "excluded from wrong-tool evidence, but identity noise still leaks through.",
        ]
    )
    return "\n".join(lines) + "\n"


__all__ = ["AblationResult", "AblationRow", "bootstrap_f1", "render_report", "run_ablation"]

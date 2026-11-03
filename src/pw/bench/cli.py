"""`pw-bench` command line (T-1.7): run a predictor over a split and write results."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from pw.bench.perception_check import perception_check, render_markdown
from pw.bench.runner import (
    DECLARED_PREDICTORS,
    IMPLEMENTED_PREDICTORS,
    SPLITS,
    BenchError,
    run_bench,
)

EXIT_OK = 0
EXIT_INVALID = 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pw-bench", description="Process Watcher benchmark")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run one predictor over a split")
    run.add_argument("--split", required=True, choices=SPLITS)
    run.add_argument(
        "--predictor",
        required=True,
        help=f"one of {', '.join((*IMPLEMENTED_PREDICTORS, *DECLARED_PREDICTORS))}",
    )
    run.add_argument("--config", type=Path, default=None, help="thresholds JSON (hashed only)")
    run.add_argument("--bench-dir", type=Path, default=Path("bench"))
    run.add_argument("--results-dir", type=Path, default=Path("results"))
    run.add_argument("--mode", default="replay", help="recorded in the result manifest")
    run.add_argument("--runs-dir", type=Path, default=Path("runs"))

    check = commands.add_parser(
        "perception-check", help="check hand coverage, fragmentation and pick-up alignment"
    )
    check.add_argument("--split", required=True, choices=SPLITS)
    check.add_argument("--mode", default="replay")
    check.add_argument("--bench-dir", type=Path, default=Path("bench"))
    check.add_argument("--runs-dir", type=Path, default=Path("runs"))
    check.add_argument(
        "--out",
        type=Path,
        default=None,
        help="markdown output (default: docs/results/perception_<split>.md)",
    )

    tune = commands.add_parser("tune", help="calibrate thresholds on dev only")
    tune.add_argument("--split", default="dev", choices=SPLITS)
    tune.add_argument("--bench-dir", type=Path, default=Path("bench"))
    tune.add_argument("--runs-dir", type=Path, default=Path("runs"))
    tune.add_argument("--out", type=Path, default=Path("config/thresholds.json"))
    tune.add_argument("--report", type=Path, default=Path("docs/results/tune_dev.md"))

    ablate = commands.add_parser("ablate", help="dev ablation table from finished runs")
    ablate.add_argument("--split", default="dev", choices=SPLITS)
    ablate.add_argument("--bench-dir", type=Path, default=Path("bench"))
    ablate.add_argument("--runs-dir", type=Path, default=Path("runs"))
    ablate.add_argument("--out", type=Path, default=Path("docs/results/ablation_dev.md"))
    return parser


def _run_perception_check(args: argparse.Namespace) -> int:
    result = perception_check(
        split=args.split,
        mode=args.mode,
        bench_dir=args.bench_dir,
        runs_dir=args.runs_dir,
    )
    out = args.out or Path("docs/results") / f"perception_{args.split}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(result), encoding="utf-8")
    for clip in result.clips:
        verdict = "PASS" if clip.passed else "FAIL"
        detail = "; ".join(clip.reasons) if clip.reasons else "ok"
        print(f"{clip.clip_id}  {verdict}  {detail}")
    print(
        f"{'PASS' if result.ok else 'FAIL'} {result.passed}/{len(result.clips)} "
        f"(required {result.required}) -> {out}"
    )
    return EXIT_OK if result.ok else EXIT_INVALID


def _run_tune(args: argparse.Namespace) -> int:
    from pw.bench.tune import TuneError, render_report, tune, write_thresholds
    from pw.data.lock import verify_lock

    try:
        tau_review, tau_flag, metrics, met = tune(bench_dir=args.bench_dir, runs_dir=args.runs_dir)
    except TuneError as error:
        print(f"pw-bench: {error}", file=sys.stderr)
        return 1
    write_thresholds(args.out, tau_review=tau_review, tau_flag=tau_flag)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        render_report(
            tau_review=tau_review,
            tau_flag=tau_flag,
            metrics=metrics,
            lock_ok=not verify_lock(args.bench_dir),
            constraint_met=met,
        ),
        encoding="utf-8",
    )
    if not met:
        print(
            "pw-bench: warning: no pair meets the false-flag constraint; best F1 written",
            file=sys.stderr,
        )
    print(
        f"tau_review={tau_review:.2f}  tau_flag={tau_flag:.2f}  "
        f"F1={metrics.overall.f1:.4f}  P={metrics.overall.precision:.4f}  "
        f"R={metrics.overall.recall:.4f}"
    )
    print(args.out)
    return EXIT_OK


def _run_ablate(args: argparse.Namespace) -> int:
    from pw.bench.ablate import render_report, run_ablation

    try:
        result = run_ablation(bench_dir=args.bench_dir, runs_dir=args.runs_dir, split=args.split)
    except ValueError as error:
        print(f"pw-bench: {error}", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_report(result), encoding="utf-8")
    for row in result.rows:
        print(f"{row.name}: {row.note or 'measured'}")
    print(args.out)
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "perception-check":
        return _run_perception_check(args)
    if args.command == "tune":
        return _run_tune(args)
    if args.command == "ablate":
        return _run_ablate(args)
    try:
        result = run_bench(
            split=args.split,
            predictor=args.predictor,
            bench_dir=args.bench_dir,
            results_dir=args.results_dir,
            config_path=args.config,
            mode=args.mode,
            runs_dir=args.runs_dir,
        )
    except BenchError as error:
        print(f"pw-bench: {error}", file=sys.stderr)
        return error.exit_code

    overall = result.summary["overall"]
    print(
        f"{result.run_id}  split={args.split}  predictor={args.predictor}  "
        f"F1={overall['f1']:.4f}  P={overall['precision']:.4f}  R={overall['recall']:.4f}"
    )
    print(result.run_dir)
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())


__all__ = ["main"]

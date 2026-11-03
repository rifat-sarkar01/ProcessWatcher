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
        f"(required {result.required}) → {out}"
    )
    return EXIT_OK if result.ok else EXIT_INVALID


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "perception-check":
        return _run_perception_check(args)
    try:
        result = run_bench(
            split=args.split,
            predictor=args.predictor,
            bench_dir=args.bench_dir,
            results_dir=args.results_dir,
            config_path=args.config,
            mode=args.mode,
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

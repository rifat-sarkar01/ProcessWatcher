"""`pw-bench` command line (T-1.7): run a predictor over a split and write results."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from pw.bench.runner import (
    DECLARED_PREDICTORS,
    IMPLEMENTED_PREDICTORS,
    SPLITS,
    BenchError,
    run_bench,
)

EXIT_OK = 0


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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
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

"""`pw-data` command line: contract, artifact, SOP and ground-truth validation."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from pw.data.schemas import KINDS, SCHEMA_NAMES, example_files, load_json
from pw.data.sopcheck import (
    golden_step_ids,
    validate_bench_sops,
    validate_gt,
)
from pw.data.validate import validate_all, validate_artifact_file

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2


def _configure_stdio() -> None:
    """Emit UTF-8 regardless of the Windows console code page.

    The summary line contains typographic characters (en dash, greater-or-equal)
    that cp1252 cannot encode; without this, `pw-data validate-sops` would crash on
    a default Windows console instead of reporting success.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (OSError, ValueError):  # pragma: no cover - depends on the console
            continue


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pw-data",
        description="Validate Process Watcher contracts (JSON Schema), artifacts and bench data.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    contracts = subparsers.add_parser(
        "validate-contracts",
        help="validate every contract schema and its committed example",
    )
    contracts.add_argument(
        "--contracts-dir",
        type=Path,
        default=None,
        help="contracts directory (default: <repo>/contracts or $PW_CONTRACTS_DIR)",
    )

    artifact = subparsers.add_parser(
        "validate-artifact",
        help="validate one artifact file (kind inferred from the file name unless --kind is given)",
    )
    artifact.add_argument("path", type=Path, help="artifact JSON file")
    artifact.add_argument("--kind", choices=KINDS, default=None, help="artifact kind override")
    artifact.add_argument(
        "--contracts-dir",
        type=Path,
        default=None,
        help="contracts directory (default: <repo>/contracts or $PW_CONTRACTS_DIR)",
    )

    sops = subparsers.add_parser(
        "validate-sops",
        help="validate the authored SOP markdown and their golden step graphs",
    )
    sops.add_argument(
        "--bench-dir",
        type=Path,
        default=None,
        help="bench directory (default: <repo>/bench or $PW_BENCH_DIR)",
    )

    gt = subparsers.add_parser(
        "validate-gt",
        help="validate one clip's ground truth against bench/gt.schema.json and its golden graph",
    )
    gt.add_argument("path", type=Path, help="ground-truth YAML/JSON file")
    gt.add_argument(
        "--golden",
        type=Path,
        required=True,
        help="golden step graph for the clip's procedure (bench/golden/P-X.json)",
    )
    gt.add_argument(
        "--bench-dir",
        type=Path,
        default=None,
        help="bench directory (default: <repo>/bench or $PW_BENCH_DIR)",
    )
    return parser


def _print_errors(errors: list[str], context: str) -> int:
    for error in errors:
        print(error, file=sys.stderr)
    print(f"FAILED {len(errors)} problem(s){context}", file=sys.stderr)
    return EXIT_INVALID


def _run_validate_contracts(contracts_dir: Path | None) -> int:
    errors = validate_all(contracts_dir)
    if errors:
        return _print_errors(errors, "")

    total_examples = sum(len(example_files(kind, contracts_dir)) for kind in KINDS)
    print(f"OK {len(SCHEMA_NAMES)} schemas, {total_examples} examples")
    return EXIT_OK


def _run_validate_artifact(path: Path, kind: str | None, contracts_dir: Path | None) -> int:
    try:
        resolved_kind, errors = validate_artifact_file(path, kind, contracts_dir)
    except (OSError, ValueError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return EXIT_USAGE

    if errors:
        return _print_errors(errors, f" in {path}")

    print(f"OK {path} ({resolved_kind})")
    return EXIT_OK


def _run_validate_sops(bench_dir: Path | None) -> int:
    sop_count, golden_count, errors = validate_bench_sops(bench_dir)
    if errors:
        return _print_errors(errors, "")

    print(
        f"{sop_count} SOPs, {golden_count} golden graphs valid; steps 8–12; critical ≥ 1; tools ≥ 3"
    )
    return EXIT_OK


def _run_validate_gt(path: Path, golden: Path, bench_dir: Path | None) -> int:
    try:
        payload = load_json(path)
        steps = golden_step_ids(golden)
    except (OSError, ValueError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return EXIT_USAGE

    errors = validate_gt(payload, steps, bench_dir)
    if errors:
        return _print_errors(errors, f" in {path}")

    print(f"OK {path} (ground truth)")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    _configure_stdio()
    args = _build_parser().parse_args(argv)

    if args.command == "validate-contracts":
        return _run_validate_contracts(args.contracts_dir)
    if args.command == "validate-artifact":
        return _run_validate_artifact(args.path, args.kind, args.contracts_dir)
    if args.command == "validate-sops":
        return _run_validate_sops(args.bench_dir)
    if args.command == "validate-gt":
        return _run_validate_gt(args.path, args.golden, args.bench_dir)

    print(f"unknown command: {args.command}", file=sys.stderr)  # pragma: no cover - argparse
    return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())

"""`pw-data` command line: contract and artifact validation."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from pw.data.schemas import KINDS
from pw.data.validate import validate_all, validate_artifact_file

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pw-data",
        description="Validate Process Watcher contracts (JSON Schema) and artifacts.",
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
    return parser


def _run_validate_contracts(contracts_dir: Path | None) -> int:
    errors = validate_all(contracts_dir)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        print(f"FAILED {len(errors)} problem(s)", file=sys.stderr)
        return EXIT_INVALID

    print(f"OK {len(KINDS)} schemas, {len(KINDS)} examples")
    return EXIT_OK


def _run_validate_artifact(path: Path, kind: str | None, contracts_dir: Path | None) -> int:
    try:
        resolved_kind, errors = validate_artifact_file(path, kind, contracts_dir)
    except (OSError, ValueError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return EXIT_USAGE

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        print(f"FAILED {len(errors)} problem(s) in {path}", file=sys.stderr)
        return EXIT_INVALID

    print(f"OK {path} ({resolved_kind})")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "validate-contracts":
        return _run_validate_contracts(args.contracts_dir)
    if args.command == "validate-artifact":
        return _run_validate_artifact(args.path, args.kind, args.contracts_dir)

    print(f"unknown command: {args.command}", file=sys.stderr)  # pragma: no cover - argparse
    return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())

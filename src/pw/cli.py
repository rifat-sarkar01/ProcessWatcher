"""`pw` command line: fake pipeline runs plus the existing evidence commands.

`overlay` and `verify-evidence` keep their original implementations; this module only
takes over the `pw` entry point and delegates the remaining arguments verbatim.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pw.evidence.overlay_cli import main as overlay_main
from pw.evidence.provenance import verify_cli as verify_main
from pw.pipeline.orchestrator import PipelineError, run_pipeline
from pw.pipeline.runstore import runs_root

EXIT_OK = 0
EXIT_USAGE = 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pw", description="Process Watcher commands")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run the fake walking-skeleton pipeline")
    run.add_argument("--mode", default="fake", help="live | replay | fake (fake only until T-3.9)")
    run.add_argument("--video", required=True, type=Path)
    run.add_argument("--sop", required=True, type=Path)
    run.add_argument("--runs-dir", type=Path, default=None)

    export = commands.add_parser("export", help="export a run report as HTML or PDF")
    export.add_argument("run_dir", type=Path)
    export.add_argument("--format", choices=("html", "pdf"), default="html")
    export.add_argument("--out", type=Path, default=None)

    commands.add_parser("overlay", add_help=False, help="render the debug overlay video")
    commands.add_parser("verify-evidence", add_help=False, help="verify evidence re-derivability")
    return parser


def _export(run_dir: Path, *, fmt: str, out: Path | None) -> int:
    from pw.report.export import ExportError, write_export

    report_path = run_dir / "report.json"
    if not report_path.is_file():
        print(f"pw: no report.json in {run_dir}", file=sys.stderr)
        return EXIT_USAGE
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        result = write_export(report, run_dir, fmt=fmt, out_dir=out)
    except (OSError, ValueError, ExportError) as error:
        print(f"pw: export failed: {error}", file=sys.stderr)
        return 1
    print(result.path)
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args, extras = parser.parse_known_args(argv)

    if args.command == "export":
        return _export(args.run_dir, fmt=args.format, out=args.out)
    if args.command == "overlay":
        return int(overlay_main(list(extras)))
    if args.command == "verify-evidence":
        return int(verify_main(list(extras)))

    root = args.runs_dir if args.runs_dir is not None else runs_root()
    try:
        result = run_pipeline(video=args.video, sop=args.sop, mode=args.mode, runs_dir=root)
    except PipelineError as error:
        print(f"pw: {error}", file=sys.stderr)
        return error.exit_code

    print(f"{result.run_id}  {len(result.stages)} stages  {result.cached} cached  {result.run_dir}")
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())


__all__ = ["main"]

"""`pw` command line: fake pipeline runs plus the existing evidence commands.

`overlay` and `verify-evidence` keep their original implementations; this module only
takes over the `pw` entry point and delegates the remaining arguments verbatim.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from pw.core.settings import (
    MODES,
    ConfigError,
    Settings,
    load_env_file,
    load_settings,
)
from pw.evidence.overlay_cli import main as overlay_main
from pw.evidence.provenance import verify_cli as verify_main
from pw.pipeline.orchestrator import PipelineError, RunResult, run_pipeline

EXIT_OK = 0
EXIT_USAGE = 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pw", description="Process Watcher commands")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run the walking-skeleton pipeline")
    run.add_argument(
        "--mode",
        default=None,
        choices=MODES,
        help="live | replay | fake | demo (default: PW_MODE, else replay)",
    )
    run.add_argument("--video", required=True, type=Path)
    run.add_argument("--sop", required=True, type=Path)
    run.add_argument("--runs-dir", type=Path, default=None)
    run.add_argument(
        "--profile",
        action="store_true",
        help="print per-stage wall time, cache hits and cost (T-6.6)",
    )

    commands.add_parser("config", help="print the loaded, redacted settings")

    demo_build = commands.add_parser("demo-build", help="freeze finished runs into demo cases")
    demo_build.add_argument("--spec", required=True, type=Path)
    demo_build.add_argument("--cases-dir", type=Path, default=Path("demo/cases"))

    demo_verify = commands.add_parser("demo-verify", help="verify demo case checksums")
    demo_verify.add_argument("--cases-dir", type=Path, default=Path("demo/cases"))

    export = commands.add_parser("export", help="export a run report as HTML or PDF")
    export.add_argument("run_dir", type=Path)
    export.add_argument("--format", choices=("html", "pdf"), default="html")
    export.add_argument("--out", type=Path, default=None)

    openapi = commands.add_parser("openapi", help="export the OpenAPI document")
    openapi.add_argument("--check", action="store_true", help="fail if it is out of date")
    openapi.add_argument("--out", type=Path, default=Path("openapi.json"))

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


def _openapi(target: Path, *, check: bool) -> int:
    from pw.api.main import create_app

    text = json.dumps(create_app().openapi(), indent=2) + "\n"
    if check:
        if not target.is_file() or target.read_text(encoding="utf-8") != text:
            print(f"pw: {target} is out of date; run `pw openapi`", file=sys.stderr)
            return 1
        return EXIT_OK
    target.write_text(text, encoding="utf-8")
    print(target)
    return EXIT_OK


def _demo_build(spec_path: Path, cases_dir: Path) -> int:
    from pw.demo.pack import CaseSpec, DemoError, build_from_specs

    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        cases = [
            CaseSpec(
                case_id=str(item["case_id"]),
                run_dir=Path(item["run_dir"]),
                title=str(item["title"]),
                description=str(item["description"]),
            )
            for item in spec["cases"]
        ]
        built = build_from_specs(cases, cases_dir)
    except (OSError, ValueError, KeyError, DemoError) as error:
        print(f"pw: {error}", file=sys.stderr)
        return EXIT_USAGE
    for path in built:
        print(path)
    return EXIT_OK


def _demo_verify(cases_dir: Path) -> int:
    from pw.demo.pack import verify_cases

    count, errors = verify_cases(cases_dir)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f"{count}/{count} cases OK")
    return EXIT_OK


def _config() -> int:
    try:
        settings = load_settings()
    except ConfigError as error:
        print(f"pw: {error}", file=sys.stderr)
        return EXIT_USAGE
    print(json.dumps(settings.describe(), indent=2))
    return EXIT_OK


def _profile(result: RunResult, elapsed_ms: int) -> None:
    total_cost = sum(stage.cost_usd for stage in result.stages)
    print(
        f"profile: wall_ms={elapsed_ms} stages={len(result.stages)} "
        f"cached={result.cached} cost_usd={total_cost:.6f}"
    )
    print(f"{'stage':<14}{'status':<9}{'cached':<8}{'duration_ms':>12}{'cost_usd':>12}")
    for stage in result.stages:
        print(
            f"{stage.name:<14}{stage.status:<9}{'yes' if stage.cached else 'no':<8}"
            f"{stage.duration_ms:>12}{stage.cost_usd:>12.6f}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    load_env_file()
    parser = _build_parser()
    args, extras = parser.parse_known_args(argv)

    if args.command == "config":
        return _config()
    if args.command == "demo-build":
        return _demo_build(args.spec, args.cases_dir)
    if args.command == "demo-verify":
        return _demo_verify(args.cases_dir)
    if args.command == "export":
        return _export(args.run_dir, fmt=args.format, out=args.out)
    if args.command == "openapi":
        return _openapi(args.out, check=args.check)
    if args.command == "overlay":
        return int(overlay_main(list(extras)))
    if args.command == "verify-evidence":
        return int(verify_main(list(extras)))

    try:
        settings: Settings = load_settings()
    except ConfigError as error:
        print(f"pw: {error}", file=sys.stderr)
        return EXIT_USAGE
    mode = args.mode or settings.mode
    root = args.runs_dir if args.runs_dir is not None else settings.runs_dir
    started = time.monotonic()
    try:
        result = run_pipeline(video=args.video, sop=args.sop, mode=mode, runs_dir=root)
    except PipelineError as error:
        print(f"pw: {error}", file=sys.stderr)
        return error.exit_code
    elapsed_ms = int((time.monotonic() - started) * 1000)

    print(f"{result.run_id}  {len(result.stages)} stages  {result.cached} cached  {result.run_dir}")
    if args.profile:
        _profile(result, elapsed_ms)
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())


__all__ = ["main"]

"""`python -m pw.ingest <video>`: normalise a clip and print the analysis facts.

Used as the T-2.1 smoke check: it prints `fps=15` and a frame count that should be
within ±1 of `duration_s * 15` for the produced CFR copy.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pw.ingest.errors import IngestError
from pw.ingest.normalise import DEFAULT_FPS, normalise_video
from pw.ingest.probe import probe_video


@contextmanager
def _output_dir(explicit: Path | None) -> Iterator[Path]:
    """Use `--out` when given, otherwise a throwaway directory.

    `ignore_cleanup_errors` matters on locked-down hosts: a cleanup failure must not
    turn a successful ingest into a traceback.
    """
    if explicit is not None:
        explicit.mkdir(parents=True, exist_ok=True)
        yield explicit
        return

    with tempfile.TemporaryDirectory(prefix="pw-ingest-", ignore_cleanup_errors=True) as workdir:
        yield Path(workdir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pw.ingest", description="Probe and normalise a video.")
    parser.add_argument("path", type=Path, help="source video file")
    parser.add_argument(
        "--fps", type=int, default=DEFAULT_FPS, help="analysis frame rate (default 15)"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="directory for the normalised copy (default: a throwaway temp directory)",
    )
    args = parser.parse_args(argv)

    try:
        source_info = probe_video(args.path)
        with _output_dir(args.out) as workdir:
            result = normalise_video(args.path, workdir / "analysis.mp4", fps=args.fps)
    except FileNotFoundError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2
    except IngestError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    info = result.info
    print(f"source={args.path}")
    print(f"source_fps={source_info.fps:g} source_size={source_info.width}x{source_info.height}")
    print(f"fps={result.fps:g}")
    print(f"size={info.width}x{info.height}")
    print(f"duration_s={info.duration_s:.3f}")
    if info.frame_count is None:
        print("frame_count=unknown")
    else:
        print(f"frame_count={info.frame_count}")
    print(f"sha256={result.source_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

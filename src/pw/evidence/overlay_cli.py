"""`pw overlay runs/<id> --out overlay.mp4`: burn stitched tracks onto the analysis video.

Decoding, drawing and encoding are streamed frame by frame so a long clip never has to
fit in memory. The video base is `media/analysis.mp4` because `tracks.json` frame
indices refer to that CFR copy; timestamps come from real PTS values, never frame/fps.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from pw.evidence.render import FrameOverlay, draw_timestamp, render_overlay
from pw.ingest import ProbeError, probe_video, pts_times

ENCODE_TIMEOUT_S = 600


class OverlayError(Exception):
    """The run could not be rendered (missing stage, bad tracks, ffmpeg failure)."""


@dataclass(frozen=True, slots=True)
class RunVideo:
    width: int
    height: int
    fps: float
    frames: dict[int, tuple[FrameOverlay, ...]]


def _overlay_from_frame(track: dict[str, Any], frame: dict[str, Any]) -> FrameOverlay:
    box = frame["box"]
    poly = frame.get("poly", ())
    return FrameOverlay(
        track_id=str(track["id"]),
        concept=str(track["concept"]),
        box=(float(box[0]), float(box[1]), float(box[2]), float(box[3])),
        poly=tuple((float(point[0]), float(point[1])) for point in poly),
    )


def load_run(run_dir: Path) -> tuple[Path, RunVideo]:
    """Read `media/analysis.mp4` and `stages/tracks.json` from a run directory."""
    video = run_dir / "media" / "analysis.mp4"
    tracks_path = run_dir / "stages" / "tracks.json"
    if not video.is_file():
        raise FileNotFoundError(f"analysis video not found: {video}")
    if not tracks_path.is_file():
        raise FileNotFoundError(f"tracks artifact not found: {tracks_path}")

    payload = json.loads(tracks_path.read_text(encoding="utf-8"))
    meta = payload["video"]
    frames: dict[int, list[FrameOverlay]] = {}
    for track in payload.get("tracks", []):
        for frame in track["frames"]:
            frames.setdefault(int(frame["frame"]), []).append(_overlay_from_frame(track, frame))

    return video, RunVideo(
        width=int(meta["width"]),
        height=int(meta["height"]),
        fps=float(meta["analysis_fps"]),
        frames={index: tuple(items) for index, items in frames.items()},
    )


def _timestamps(video: Path) -> list[float]:
    times = sorted(pts_times(video))
    if not times:
        raise OverlayError(f"no presentation timestamps in {video}")
    return times


def render_video(video: Path, run: RunVideo, destination: Path) -> int:
    """Stream the analysis video through the renderer into `destination`."""
    info = probe_video(video)
    if (info.width, info.height) != (run.width, run.height):
        raise OverlayError(
            f"tracks say {run.width}x{run.height}, video is {info.width}x{info.height}"
        )

    times = _timestamps(video)
    frame_bytes = run.width * run.height * 3
    decoder = subprocess.Popen(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(video),
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoder = subprocess.Popen(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{run.width}x{run.height}",
            "-r",
            f"{run.fps:g}",
            "-i",
            "-",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(destination),
        ],
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
    )
    assert decoder.stdout is not None
    assert encoder.stdin is not None
    assert decoder.stderr is not None
    assert encoder.stderr is not None

    count = 0
    error: OverlayError | None = None
    try:
        while True:
            buffer = decoder.stdout.read(frame_bytes)
            if len(buffer) < frame_bytes:
                break
            image = Image.frombytes("RGB", (run.width, run.height), buffer)
            rendered = render_overlay(image, run.frames.get(count, ()))
            if count < len(times):
                rendered = draw_timestamp(rendered, times[count] - times[0])
            encoder.stdin.write(rendered.tobytes())
            count += 1
    except BrokenPipeError as exc:
        error = OverlayError("ffmpeg encoder stopped early")
        error.__cause__ = exc
    finally:
        encoder.stdin.close()
        encoder.wait(timeout=ENCODE_TIMEOUT_S)
        decoder.stdout.close()
        decoder.wait(timeout=ENCODE_TIMEOUT_S)
        decode_stderr = decoder.stderr.read().decode("utf-8", "replace").strip()
        encode_stderr = encoder.stderr.read().decode("utf-8", "replace").strip()

    if error is not None:
        raise error
    if decoder.returncode != 0:
        raise OverlayError(decode_stderr or "ffmpeg could not decode the analysis video")
    if encoder.returncode != 0:
        raise OverlayError(encode_stderr or "ffmpeg could not encode the overlay")
    if count == 0:
        raise OverlayError("no frames were decoded")
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pw", description="Process Watcher CLI.")
    commands = parser.add_subparsers(dest="command", required=True)
    overlay = commands.add_parser("overlay", help="burn tracks onto the analysis video")
    overlay.add_argument("run_dir", type=Path, help="run directory (runs/<run_id>)")
    overlay.add_argument("--out", type=Path, required=True, help="output mp4 path")
    args = parser.parse_args(argv)

    try:
        video, run = load_run(args.run_dir)
        frames = render_video(video, run, args.out)
    except FileNotFoundError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2
    except (OverlayError, ProbeError, OSError, ValueError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    print(f"wrote={args.out}")
    print(f"frames={frames}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

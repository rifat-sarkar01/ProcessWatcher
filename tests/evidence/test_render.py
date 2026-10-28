"""Render primitive tests: masks, labels, timestamps, set-of-mark and the overlay CLI."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import uuid
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest
from PIL import Image

from pw.evidence.overlay_cli import main
from pw.evidence.render import (
    FrameOverlay,
    colour_for,
    draw_caption,
    draw_timestamp,
    format_timestamp,
    label_boxes,
    render_overlay,
    render_set_of_mark,
)

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests" / "fixtures" / "evidence" / "golden_overlay.png"
BACKGROUND = (245, 245, 245)


@pytest.fixture
def scratch() -> Iterator[Path]:
    path = ROOT / ".uv" / "tests-tmp" / f"render-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def blank(width: int = 320, height: int = 240) -> Image.Image:
    return Image.new("RGB", (width, height), BACKGROUND)


def hand() -> FrameOverlay:
    return FrameOverlay(
        track_id="trk_001",
        concept="hand",
        box=(0.1, 0.1, 0.4, 0.6),
        poly=((0.1, 0.1), (0.4, 0.12), (0.38, 0.6), (0.12, 0.58)),
    )


def screwdriver() -> FrameOverlay:
    return FrameOverlay(
        track_id="trk_002",
        concept="screwdriver",
        box=(0.55, 0.2, 0.8, 0.5),
    )


def _dct(values: Sequence[float]) -> list[float]:
    size = len(values)
    return [
        sum(values[x] * math.cos(math.pi * (2 * x + 1) * u / (2 * size)) for x in range(size))
        for u in range(size)
    ]


def phash(image: Image.Image, *, size: int = 32, low: int = 8) -> list[bool]:
    """Pure-python perceptual hash: DCT over a 32x32 grey image, 8x8 low frequencies."""
    grey = image.convert("L").resize((size, size), Image.Resampling.LANCZOS)
    rows = [_dct([float(grey.getpixel((x, y))) for x in range(size)]) for y in range(size)]
    cols = [_dct([rows[y][x] for y in range(size)]) for x in range(size)]
    low_freq = [cols[x][y] for x in range(low) for y in range(low)][1:]
    median = sorted(low_freq)[len(low_freq) // 2]
    return [value > median for value in low_freq]


def distance(left: Sequence[bool], right: Sequence[bool]) -> int:
    return sum(a != b for a, b in zip(left, right, strict=True))


@pytest.mark.unit
def test_colour_is_stable_per_track_and_differs_between_tracks() -> None:
    assert colour_for("trk_001") == colour_for("trk_001")
    assert colour_for("trk_001") != colour_for("trk_002")
    assert all(0 <= channel <= 255 for channel in colour_for("trk_007"))


@pytest.mark.unit
def test_empty_track_list_returns_an_identical_frame() -> None:
    frame = blank()

    assert render_overlay(frame, []).tobytes() == frame.tobytes()


@pytest.mark.unit
def test_render_does_not_mutate_the_input_frame() -> None:
    frame = blank()
    before = frame.tobytes()

    render_overlay(frame, [hand(), screwdriver()])

    assert frame.tobytes() == before


@pytest.mark.unit
def test_polygon_overlay_changes_pixels_inside_the_mask_only() -> None:
    frame = blank()
    rendered = render_overlay(frame, [hand()])

    assert rendered.getpixel((80, 80)) != BACKGROUND
    assert rendered.getpixel((300, 220)) == BACKGROUND


@pytest.mark.unit
def test_box_is_used_when_no_polygon_is_present() -> None:
    frame = blank()
    rendered = render_overlay(frame, [screwdriver()])

    assert rendered.getpixel((220, 90)) != BACKGROUND
    assert rendered.getpixel((10, 10)) == BACKGROUND


@pytest.mark.unit
def test_golden_overlay_within_phash_distance() -> None:
    rendered = render_overlay(blank(), [hand()], labels=False)

    assert GOLDEN.is_file(), "golden fixture missing"
    golden = Image.open(GOLDEN).convert("RGB")
    assert distance(phash(rendered), phash(golden)) <= 4


@pytest.mark.unit
def test_labels_avoid_each_other_and_stay_inside_the_frame() -> None:
    close_pair = [
        FrameOverlay("trk_001", "hand", (0.1, 0.1, 0.4, 0.3)),
        FrameOverlay("trk_002", "screwdriver", (0.12, 0.12, 0.42, 0.32)),
    ]

    rects = label_boxes(close_pair, (320, 240))

    assert len(rects) == 2
    for rect in rects:
        assert 0 <= rect[0] < rect[2] <= 320
        assert 0 <= rect[1] < rect[3] <= 240
    first, second = rects
    assert (
        first[2] <= second[0]
        or second[2] <= first[0]
        or first[3] <= second[1]
        or second[3] <= first[1]
    ), "labels overlap"


@pytest.mark.unit
def test_render_with_labels_changes_pixels_near_the_box() -> None:
    frame = blank()

    with_labels = render_overlay(frame, [hand()])
    without = render_overlay(frame, [hand()], labels=False)

    assert with_labels.tobytes() != without.tobytes()


@pytest.mark.unit
def test_timestamp_formats_as_minutes_seconds_millis() -> None:
    assert format_timestamp(0.0) == "00:00.000"
    assert format_timestamp(72.345) == "01:12.345"
    assert format_timestamp(-3) == "00:00.000"


@pytest.mark.unit
def test_timestamp_burn_in_changes_the_top_corner_only() -> None:
    frame = blank()
    stamped = draw_timestamp(frame, 12.5)

    assert stamped.getpixel((12, 12)) != BACKGROUND
    assert stamped.getpixel((300, 220)) == BACKGROUND


@pytest.mark.unit
def test_caption_bar_sits_at_the_bottom_and_truncates_long_text() -> None:
    frame = blank()
    captioned = draw_caption(frame, "x" * 400)

    assert captioned.getpixel((10, 10)) == BACKGROUND
    assert captioned.getpixel((160, 230)) != BACKGROUND


@pytest.mark.unit
def test_set_of_mark_numbers_each_track() -> None:
    frame = blank()

    numbered = render_set_of_mark(frame, [hand(), screwdriver()])

    assert numbered.tobytes() != frame.tobytes()
    assert numbered.tobytes() != render_overlay(frame, [hand(), screwdriver()]).tobytes()


def _make_run(root: Path) -> Path:
    run_dir = root / "run_01J9ZQ8M3K4V7B2C5D6E8F0GHJ"
    (run_dir / "media").mkdir(parents=True)
    (run_dir / "stages").mkdir(parents=True)
    video = run_dir / "media" / "analysis.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=d=1:s=160x120:r=15",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(video),
        ],
        check=True,
        capture_output=True,
        shell=False,
        timeout=120,
    )
    frames = [
        {
            "frame": index,
            "t": index / 15,
            "box": [0.25, 0.25, 0.6, 0.75],
            "score": 0.9,
            "poly": [[0.26, 0.26], [0.59, 0.27], [0.58, 0.74], [0.27, 0.73]],
        }
        for index in range(15)
    ]
    payload = {
        "schema_version": "1.0.0",
        "run_id": run_dir.name,
        "video": {
            "sha256": "0" * 64,
            "duration_s": 1.0,
            "analysis_fps": 15,
            "width": 160,
            "height": 120,
            "frame_count": 15,
        },
        "tracks": [
            {
                "id": "trk_001",
                "concept": "hand",
                "first_t": 0.0,
                "last_t": 14 / 15,
                "frames": frames,
            }
        ],
    }
    (run_dir / "stages" / "tracks.json").write_text(json.dumps(payload), encoding="utf-8")
    return run_dir


@pytest.mark.unit
def test_overlay_cli_writes_a_video_with_the_source_duration(scratch: Path) -> None:
    run_dir = _make_run(scratch)
    output = scratch / "overlay.mp4"

    assert main(["overlay", str(run_dir), "--out", str(output)]) == 0

    assert output.is_file() and output.stat().st_size > 0
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
        shell=False,
        timeout=60,
    )
    assert abs(float(probe.stdout.strip()) - 1.0) <= 0.2


@pytest.mark.unit
def test_overlay_cli_reports_a_missing_run_with_exit_code_two(
    scratch: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(["overlay", str(scratch / "missing"), "--out", str(scratch / "o.mp4")])

    assert exit_code == 2
    assert "ERROR" in capsys.readouterr().err


@pytest.mark.unit
def test_overlay_cli_rejects_an_unknown_command() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["bogus"])

    assert excinfo.value.code == 2

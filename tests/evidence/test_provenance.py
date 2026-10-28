"""Clip windows, manifest hashes and `pw verify-evidence` tamper detection."""

from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import jsonschema
import pytest
from PIL import Image

from pw.evidence.clip import CLIP_MAX_S, CLIP_MIN_S, ClipError, clip_window, render_clip
from pw.evidence.provenance import (
    build_manifest,
    clip_entry,
    dhash,
    params_hash,
    phash_distance,
    render_params,
    verify_cli,
    verify_report,
    write_evidence,
)
from pw.evidence.render import FrameOverlay, draw_timestamp, render_overlay
from pw.evidence.selector import EvidenceFrame, EvidenceSelection
from pw.ingest import probe_video, pts_times, sha256_file

SCRATCH_ROOT = Path(__file__).resolve().parents[2] / ".uv" / "tests-tmp"
FRAME_INDEX = 30
FRAME_TIME = 2.0
BOX = (0.2, 0.2, 0.5, 0.6)


def _ffmpeg(*args: str) -> None:
    completed = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
        shell=False,
    )
    if completed.returncode != 0:  # pragma: no cover - fixture failure
        raise RuntimeError(f"ffmpeg failed: {completed.stderr.strip()}")


@pytest.fixture(scope="module")
def scratch() -> Iterator[Path]:
    path = SCRATCH_ROOT / f"evidence-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(scope="module")
def clip_video(scratch: Path) -> Path:
    target = scratch / "analysis.mp4"
    _ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "testsrc=d=6:s=160x120:r=15",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(target),
    )
    return target


def _run_dir(root: Path, video: Path, *, track: bool = True) -> tuple[Path, dict[str, object]]:
    run = root / f"run-{uuid.uuid4().hex[:8]}"
    (run / "media").mkdir(parents=True)
    shutil.copyfile(video, run / "media" / "analysis.mp4")
    if track:
        (run / "stages").mkdir()
        payload = {
            "video": {"width": 160, "height": 120, "analysis_fps": 15},
            "tracks": [
                {
                    "id": "trk_001",
                    "concept": "hand",
                    "frames": [{"frame": FRAME_INDEX, "t": FRAME_TIME, "box": list(BOX)}],
                }
            ],
        }
        (run / "stages" / "tracks.json").write_text(json.dumps(payload), encoding="utf-8")

    raw = _decode(run / "media" / "analysis.mp4")
    image = draw_timestamp(render_overlay(raw, [FrameOverlay("trk_001", "hand", BOX)]), FRAME_TIME)
    frame = EvidenceFrame(
        deviation_id="dev_001",
        frame_index=FRAME_INDEX,
        t=FRAME_TIME,
        track_ids=("trk_001",),
        score=0.9,
        image=image,
    )
    selection = EvidenceSelection("dev_001", (frame,), True, None)
    items = write_evidence([selection], run_dir=run, source_sha256=sha256_file(video))
    report: dict[str, object] = {
        "deviations": [{"id": "dev_001", "evidence": [dict(item) for item in items]}]
    }
    (run / "report.json").write_text(json.dumps(report), encoding="utf-8")
    return run, report


def _decode(video: Path) -> Image.Image:
    from pw.evidence.provenance import _read_frames

    frames = _read_frames(video, [FRAME_INDEX])
    assert FRAME_INDEX in frames
    return frames[FRAME_INDEX]


def test_clip_window_pads_around_a_short_deviation() -> None:
    start, end = clip_window(10.0, 10.4)
    assert end - start == pytest.approx(CLIP_MIN_S)
    assert start <= 10.0 < 10.4 <= end


def test_clip_window_caps_at_five_seconds() -> None:
    start, end = clip_window(0.0, 20.0, duration=60.0)
    assert end - start == pytest.approx(CLIP_MAX_S)
    assert start >= 0.0


def test_clip_window_fits_a_short_video() -> None:
    assert clip_window(0.2, 0.4, duration=2.0) == (0.0, 2.0)


def test_clip_window_rejects_invalid_bounds() -> None:
    with pytest.raises(ClipError):
        clip_window(2.0, 1.0)
    with pytest.raises(ClipError):
        clip_window(0.0, 1.0, min_s=6.0, max_s=5.0)
    with pytest.raises(ClipError):
        clip_window(-1.0, 0.0)


@pytest.mark.integration
def test_render_clip_cuts_a_playable_window(scratch: Path, clip_video: Path) -> None:
    window = clip_window(FRAME_TIME, FRAME_TIME + 0.2, duration=6.0)
    result = render_clip(
        clip_video,
        scratch / "clip.mp4",
        window=window,
        overlays={FRAME_INDEX: (FrameOverlay("trk_001", "hand", BOX),)},
    )
    info = probe_video(result.path)
    assert info.duration_s == pytest.approx(CLIP_MIN_S, abs=0.2)
    assert result.frames == pytest.approx(15 * CLIP_MIN_S, abs=2)
    assert len(pts_times(result.path)) == result.frames


def test_render_clip_rejects_an_empty_window(clip_video: Path, scratch: Path) -> None:
    with pytest.raises(ClipError):
        render_clip(clip_video, scratch / "empty.mp4", window=(2.0, 2.0))


def test_clip_entry_records_path_hash_and_span(scratch: Path, clip_video: Path) -> None:
    window = clip_window(FRAME_TIME, FRAME_TIME + 0.2, duration=6.0)
    result = render_clip(clip_video, scratch / "clip-entry.mp4", window=window)
    entry = clip_entry(result, run_dir=scratch)
    assert entry["sha256"] == sha256_file(result.path)
    assert entry["t_start"] == window[0]
    assert entry["t_end"] == window[1]
    assert entry["path"] == "clip-entry.mp4"


def test_dhash_is_deterministic_and_distance_is_zero(clip_video: Path) -> None:
    image = _decode(clip_video)
    assert dhash(image) == dhash(image)
    assert phash_distance(dhash(image), dhash(image)) == 0
    assert len(dhash(image)) == 16


def test_params_hash_changes_with_render_params() -> None:
    assert params_hash() == params_hash(render_params())
    assert params_hash(render_params(alpha=120)) != params_hash()


def test_untouched_run_verifies(scratch: Path, clip_video: Path) -> None:
    run, report = _run_dir(scratch, clip_video)
    result = verify_report(report, video=clip_video, run_dir=run)
    assert result.summary() == "VERIFIED 1/1"
    assert result.ok


def test_tampered_source_fails(scratch: Path, clip_video: Path) -> None:
    run, report = _run_dir(scratch, clip_video)
    other = scratch / "other-source.mp4"
    _ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "color=c=blue:d=6:s=160x120:r=15",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(other),
    )
    result = verify_report(report, video=other, run_dir=run)
    assert not result.ok
    assert [check.reason for check in result.checks] == ["source_mismatch"]


def test_changed_render_params_fail(scratch: Path, clip_video: Path) -> None:
    run, report = _run_dir(scratch, clip_video)
    result = verify_report(report, video=clip_video, run_dir=run, params=render_params(alpha=200))
    assert not result.ok
    assert [check.reason for check in result.checks] == ["params_mismatch"]


def test_tampered_output_fails(scratch: Path, clip_video: Path) -> None:
    run, report = _run_dir(scratch, clip_video)
    item = report["deviations"][0]["evidence"][0]  # type: ignore[index]
    output = run / str(item["output_path"])
    output.write_bytes(output.read_bytes()[:-1] + b"\x00")
    result = verify_report(report, video=clip_video, run_dir=run)
    assert [check.reason for check in result.checks] == ["output_mismatch"]


def test_missing_output_fails(scratch: Path, clip_video: Path) -> None:
    run, report = _run_dir(scratch, clip_video)
    item = report["deviations"][0]["evidence"][0]  # type: ignore[index]
    (run / str(item["output_path"])).unlink()
    result = verify_report(report, video=clip_video, run_dir=run)
    assert [check.reason for check in result.checks] == ["output_missing"]


def test_swapped_perceptual_hash_fails(scratch: Path, clip_video: Path) -> None:
    run, report = _run_dir(scratch, clip_video)
    item = report["deviations"][0]["evidence"][0]  # type: ignore[index]
    item["phash"] = "f" * 16
    result = verify_report(report, video=clip_video, run_dir=run)
    assert [check.reason for check in result.checks] == ["phash_mismatch"]


def test_missing_tracks_fails(scratch: Path, clip_video: Path) -> None:
    run, report = _run_dir(scratch, clip_video)
    (run / "stages" / "tracks.json").unlink()
    result = verify_report(report, video=clip_video, run_dir=run)
    assert [check.reason for check in result.checks] == ["tracks_missing"]


def test_missing_analysis_copy_fails(scratch: Path, clip_video: Path) -> None:
    run, report = _run_dir(scratch, clip_video)
    (run / "media" / "analysis.mp4").unlink()
    result = verify_report(report, video=clip_video, run_dir=run)
    assert [check.reason for check in result.checks] == ["analysis_missing"]


def test_illustration_in_evidence_kind_is_rejected(scratch: Path, clip_video: Path) -> None:
    run, report = _run_dir(scratch, clip_video)
    report["deviations"][0]["evidence"][0]["kind"] = "illustration"  # type: ignore[index]
    result = verify_report(report, video=clip_video, run_dir=run)
    assert [check.reason for check in result.checks] == ["wrong_kind"]


def test_report_without_evidence_verifies_empty(scratch: Path, clip_video: Path) -> None:
    run, _ = _run_dir(scratch, clip_video)
    result = verify_report({"deviations": []}, video=clip_video, run_dir=run)
    assert result.summary() == "VERIFIED 0/0"


def test_manifest_records_source_and_params(scratch: Path, clip_video: Path) -> None:
    _run, report = _run_dir(scratch, clip_video)
    items = report["deviations"][0]["evidence"]  # type: ignore[index]
    manifest = build_manifest(items, run_id="r_demo", source_sha256=sha256_file(clip_video))
    assert manifest["source_sha256"] == sha256_file(clip_video)
    assert manifest["params_hash"] == params_hash()
    assert manifest["render_version"] == "evidence-render-v1"
    assert manifest["items"][0]["frame_index"] == FRAME_INDEX


def test_verify_cli_prints_verified_and_exits_zero(
    scratch: Path, clip_video: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run, _ = _run_dir(scratch, clip_video)
    code = verify_cli([str(run / "report.json"), "--video", str(clip_video)])
    assert code == 0
    assert capsys.readouterr().out.strip() == "VERIFIED 1/1"


def test_verify_cli_fails_on_tampering(
    scratch: Path, clip_video: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run, report = _run_dir(scratch, clip_video)
    report["deviations"][0]["evidence"][0]["source_sha256"] = "0" * 64  # type: ignore[index]
    (run / "report.json").write_text(json.dumps(report), encoding="utf-8")
    code = verify_cli([str(run / "report.json"), "--video", str(clip_video)])
    assert code == 1
    captured = capsys.readouterr()
    assert captured.out.strip() == "FAILED 0/1"
    assert "source_mismatch" in captured.err


def test_pw_entry_point_dispatches_verify_evidence(
    scratch: Path, clip_video: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from pw.evidence.overlay_cli import main

    run, _ = _run_dir(scratch, clip_video)
    code = main(["verify-evidence", str(run / "report.json"), "--video", str(clip_video)])
    assert code == 0
    assert "VERIFIED 1/1" in capsys.readouterr().out


def test_evidence_item_matches_the_contract(scratch: Path, clip_video: Path) -> None:
    _run, report = _run_dir(scratch, clip_video)
    schema = json.loads(
        (Path(__file__).resolve().parents[2] / "contracts" / "report.schema.json").read_text(
            encoding="utf-8"
        )
    )
    item_schema = {"$defs": schema["$defs"], **schema["$defs"]["evidence_item"]}
    for item in report["deviations"][0]["evidence"]:  # type: ignore[index]
        jsonschema.validate(item, item_schema)

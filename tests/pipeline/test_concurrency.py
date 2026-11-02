"""T-6.6: bounded per-model fan-out, deterministic results and the profile flag.

The tests drive the limiter and the two fan-out seams (SAM chunks, Wonder identity) with
fakes, so they prove the caps and result stability without footage or live calls.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from PIL import Image, ImageDraw

import pw.cli as cli
from pw.perception.chunking import AnalysisVideo, ChunkParams
from pw.perception.identity import TrackFrame, TrackObservation, identify_tracks
from pw.perception.sam_runner import run_chunks
from pw.pipeline.concurrency import ConcurrencyError, ConcurrencyLimits, ModelLimiter


class Probe:
    """Record the peak number of calls in flight and add a little overlap."""

    def __init__(self, delay_s: float = 0.02) -> None:
        self.delay_s = delay_s
        self.calls = 0
        self.peak = 0
        self._active = 0
        self._lock = threading.Lock()

    def enter(self) -> None:
        with self._lock:
            self._active += 1
            self.calls += 1
            self.peak = max(self.peak, self._active)

    def leave(self) -> None:
        with self._lock:
            self._active -= 1

    def pause(self) -> None:
        time.sleep(self.delay_s)


def _video(frames: int = 40) -> AnalysisVideo:
    return AnalysisVideo(
        path=Path("unused.mp4"),
        fps=15.0,
        times=tuple(index / 15.0 for index in range(frames)),
    )


def _cut(_video: AnalysisVideo, _plan: Any, _destination: Path) -> bytes:
    return b"chunk-bytes"


def _sam_body() -> dict[str, Any]:
    text = "<0f>0<|box;x1=0;y1=0;x2=9;y2=9;w=10;h=10;c=0.9|>"
    return {"output": [{"content": [{"type": "output_text", "text": text}]}]}


def _textured(size: tuple[int, int] = (120, 90)) -> Image.Image:
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    for y in range(0, size[1], 8):
        for x in range(0, size[0], 8):
            if (x // 8 + y // 8) % 2:
                draw.rectangle((x, y, x + 7, y + 7), fill="black")
    return image


def _identity_body(payload: dict[str, Any]) -> dict[str, Any]:
    crops = len(payload["input"][0]["content"]) - 1
    text = json.dumps({"crops": [{"label": "screwdriver", "confidence": 0.9}] * crops})
    return {"output": [{"content": [{"type": "output_text", "text": text}]}]}


def test_limiter_never_exceeds_the_model_limit_and_preserves_order() -> None:
    probe = Probe()

    def work(value: int) -> int:
        probe.enter()
        try:
            probe.pause()
            return value * 2
        finally:
            probe.leave()

    with ModelLimiter(ConcurrencyLimits(sam=2)) as limiter:
        results = limiter.map("sam", work, range(8))

    assert results == [value * 2 for value in range(8)]
    assert probe.peak == 2


def test_limiter_releases_permits_after_an_error() -> None:
    def boom(value: int) -> int:
        if value == 0:
            raise RuntimeError("first call fails")
        return value

    with ModelLimiter(ConcurrencyLimits(sam=1)) as limiter:
        with pytest.raises(RuntimeError):
            limiter.map("sam", boom, [0, 1])
        assert limiter.map("sam", lambda value: value * 2, [2, 3]) == [4, 6]


def test_limiter_rejects_unknown_models_and_bad_limits() -> None:
    with ModelLimiter() as limiter, pytest.raises(ConcurrencyError):
        limiter.map("video", lambda value: value, [1])
    with pytest.raises(ConcurrencyError):
        ConcurrencyLimits(image=0)


def test_sam_chunks_are_bounded_and_match_the_sequential_artifacts(runs_dir: Path) -> None:
    video = _video()
    params = ChunkParams(frames_per_chunk=10, overlap_frames=0)
    sequential_dir = runs_dir / "sequential"
    limited_dir = runs_dir / "limited"
    probe = Probe()

    def call(_payload: dict[str, Any]) -> dict[str, Any]:
        probe.enter()
        try:
            probe.pause()
            return _sam_body()
        finally:
            probe.leave()

    sequential = run_chunks(
        video,
        concepts=["hand"],
        stage_dir=sequential_dir,
        call=lambda _payload: _sam_body(),
        params=params,
        cutter=_cut,
    )
    with ModelLimiter(ConcurrencyLimits(sam=2)) as limiter:
        limited = run_chunks(
            video,
            concepts=["hand"],
            stage_dir=limited_dir,
            call=call,
            params=params,
            cutter=_cut,
            limiter=limiter,
        )

    assert len(limited.outcomes) == len(sequential.outcomes) == 4
    assert probe.peak == 2
    assert [item.chunk_id for item in limited.outcomes] == [
        item.chunk_id for item in sequential.outcomes
    ]
    for expected, actual in zip(sequential.outcomes, limited.outcomes, strict=True):
        assert json.loads(expected.path.read_text(encoding="utf-8")) == json.loads(
            actual.path.read_text(encoding="utf-8")
        )

    # A rerun is served by the chunk cache and makes no calls (warm cache path).
    calls_before = probe.calls
    with ModelLimiter(ConcurrencyLimits(sam=2)) as limiter:
        resumed = run_chunks(
            video,
            concepts=["hand"],
            stage_dir=limited_dir,
            call=call,
            params=params,
            cutter=_cut,
            limiter=limiter,
        )
    assert all(item.skipped for item in resumed.outcomes)
    assert probe.calls == calls_before


def test_identity_fan_out_is_bounded_and_matches_sequential_results() -> None:
    tracks = [
        TrackObservation(
            f"trk_{index:03d}",
            "screwdriver",
            tuple(TrackFrame(frame, (0.2, 0.2, 0.6, 0.6)) for frame in range(3)),
        )
        for index in range(4)
    ]
    vocabulary = ["screwdriver", "wrench"]
    probe = Probe()

    def call(payload: dict[str, Any]) -> dict[str, Any]:
        probe.enter()
        try:
            probe.pause()
            return _identity_body(payload)
        finally:
            probe.leave()

    sequential = identify_tracks(
        tracks,
        frame_provider=lambda _frame: _textured(),
        vocabulary=vocabulary,
        call=_identity_body,
    )
    with ModelLimiter(ConcurrencyLimits(wonder=2)) as limiter:
        limited = identify_tracks(
            tracks,
            frame_provider=lambda _frame: _textured(),
            vocabulary=vocabulary,
            call=call,
            limiter=limiter,
        )

    assert probe.peak == 2
    assert [item.to_payload() for item in limited.identities] == [
        item.to_payload() for item in sequential.identities
    ]
    assert [item.track_id for item in limited.identities] == [
        "trk_000",
        "trk_001",
        "trk_002",
        "trk_003",
    ]


def test_run_profile_prints_every_stage(
    tiny_video: Path,
    tiny_sop: Path,
    runs_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = cli.main(
        [
            "run",
            "--mode",
            "fake",
            "--video",
            str(tiny_video),
            "--sop",
            str(tiny_sop),
            "--runs-dir",
            str(runs_dir),
            "--profile",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "profile:" in output
    assert "stages=12" in output
    assert "wall_ms=" in output
    for stage in ("ingest", "sop_compile", "perceive", "report"):
        assert stage in output

"""Partial SAM output: bad records are dropped, good tracks and artifacts survive."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from pw.clients.errors import MalformedResponseError
from pw.data.validate import validate_payload
from pw.perception.chunking import AnalysisVideo
from pw.perception.sam_runner import STATUS_COMPLETE, STATUS_PARTIAL, run_chunks
from pw.perception.stitch import ChunkFrame, ChunkTrack, ChunkTracks, stitch_chunks

GOOD_FRAMES = (
    "<0f> 0<|box;x1=40;y1=40;x2=59;y2=59;w=100;h=100;c=0.9|>",
    "<1f> 0<|box;x1=41;y1=41;x2=59;y2=59;w=100;h=100;c=0.8|>",
)
GARBAGE = "<2f> 0<|box;x1=not-a-number|>"
VIDEO_META = {
    "sha256": "c" * 64,
    "duration_s": 2.0,
    "analysis_fps": 15.0,
    "width": 320,
    "height": 240,
    "frame_count": 30,
}


def _body(lines: str) -> dict[str, Any]:
    return {"output": [{"content": [{"type": "output_text", "text": lines}]}]}


def _video(path: Path) -> AnalysisVideo:
    return AnalysisVideo(path=path, fps=15.0, times=tuple(index / 15.0 for index in range(30)))


def _stitched_artifact(outcome_path: Path) -> dict[str, Any]:
    payload = json.loads(outcome_path.read_text(encoding="utf-8"))
    tracks = tuple(
        ChunkTrack(
            local_id=str(track["local_id"]),
            concept=str(track["concept"]),
            frames=tuple(
                ChunkFrame(
                    frame=int(frame["frame"]),
                    t=float(frame["t"]),
                    box=tuple(frame["box"]),
                    score=float(frame["score"]),
                )
                for frame in track["frames"]
            ),
        )
        for track in payload["tracks"]
    )
    chunk = ChunkTracks(
        chunk_id=str(payload["chunk_id"]),
        t_start=float(payload["t_start"]),
        t_end=float(payload["t_end"]),
        tracks=tracks,
    )
    return stitch_chunks([chunk]).to_artifact(
        run_id="run_01J9ZQ8M3K4V7B2C5D6E8F0GHJ", video=VIDEO_META
    )


@pytest.mark.unit
def test_partial_sam_response_keeps_the_good_track_and_a_valid_artifact(
    tiny_video: Path, scratch: Path
) -> None:
    def call(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        concept = payload["input"][0]["content"][0]["text"]
        if concept == "cable":
            raise MalformedResponseError("truncated SAM payload", model="sam-3.1")
        return _body("\n".join([*GOOD_FRAMES, GARBAGE]))

    result = run_chunks(
        _video(tiny_video),
        concepts=("hand", "cable"),
        stage_dir=scratch,
        call=call,
        cutter=lambda _video, _plan, _path: b"chunk-bytes",
        resume=False,
    )

    outcome = result.outcomes[0]
    assert outcome.status == STATUS_PARTIAL
    assert outcome.calls == 2
    assert "MalformedResponseError" in (outcome.error or "")

    payload = json.loads(outcome.path.read_text(encoding="utf-8"))
    assert [track["concept"] for track in payload["tracks"]] == ["hand"]
    assert [frame["frame"] for frame in payload["tracks"][0]["frames"]] == [0, 1]

    artifact = _stitched_artifact(outcome.path)
    assert validate_payload("tracks", artifact) == []
    assert [track["concept"] for track in artifact["tracks"]] == ["hand"]


@pytest.mark.unit
def test_garbled_sam_text_is_ignored_not_fatal(tiny_video: Path, scratch: Path) -> None:
    result = run_chunks(
        _video(tiny_video),
        concepts=("hand",),
        stage_dir=scratch,
        call=lambda _payload: _body(GARBAGE),
        cutter=lambda _video, _plan, _path: b"chunk-bytes",
        resume=False,
    )

    outcome = result.outcomes[0]
    assert outcome.status == STATUS_COMPLETE
    artifact = _stitched_artifact(outcome.path)
    assert validate_payload("tracks", artifact) == []
    assert artifact["tracks"] == []

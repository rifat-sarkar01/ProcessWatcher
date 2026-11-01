"""T-2.2: chunk planning, concept grouping, SAM parsing, resume and partial chunks."""

from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from pw.clients.cache import ResponseCache
from pw.clients.sam import SamClient
from pw.clients.transport import RawResponse
from pw.core.ledger import RunLedger
from pw.perception.chunking import (
    AnalysisVideo,
    ChunkingError,
    ChunkParams,
    ChunkPlan,
    group_concepts,
    plan_chunks,
)
from pw.perception.sam_runner import (
    STATUS_COMPLETE,
    STATUS_PARTIAL,
    build_request,
    parse_response,
    run_chunks,
)

SCRATCH_ROOT = Path(__file__).resolve().parents[2] / ".uv" / "tests-tmp"
FPS = 15.0


def _video(frames: int) -> AnalysisVideo:
    return AnalysisVideo(
        path=Path("analysis.mp4"),
        fps=FPS,
        times=tuple(round(index / FPS, 4) for index in range(frames)),
    )


def _line(
    local_frame: int,
    object_id: int = 0,
    *,
    x1: int = 10,
    y1: int = 20,
    x2: int = 30,
    y2: int = 40,
    w: int = 100,
    h: int = 100,
    c: float = 0.9,
) -> str:
    box = f"x1={x1};y1={y1};x2={x2};y2={y2};w={w};h={h};c={c}"
    return f"<{local_frame}f>{object_id}<|box;{box}|><|mask;x=0;y=0;data=2,2,!!|>"


def _body(lines: Sequence[str], *, frames: int | None = None) -> dict[str, object]:
    usage: dict[str, int] = {}
    if frames is not None:
        usage["video_frames_processed"] = frames
    return {
        "output": [{"content": [{"type": "output_text", "text": "\n".join(lines)}]}],
        "usage": usage,
    }


def _cut(video: AnalysisVideo, plan: ChunkPlan, destination: Path) -> bytes:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(b"chunk-video")
    return b"chunk-video"


class _Caller:
    def __init__(self, fail_calls: Sequence[int] = (), lines: Sequence[str] | None = None) -> None:
        self.fail_calls = set(fail_calls)
        self.payloads: list[Mapping[str, object]] = []
        self.lines = list(lines) if lines is not None else [_line(0)]

    def __call__(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        index = len(self.payloads)
        self.payloads.append(payload)
        if index in self.fail_calls:
            raise TimeoutError("simulated timeout after retries")
        return _body(self.lines)


@pytest.fixture()
def scratch() -> Path:
    root = SCRATCH_ROOT / f"chunks-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_plan_is_frame_based_with_overlap() -> None:
    plans = plan_chunks(_video(400), ChunkParams(frames_per_chunk=150, overlap_frames=15))
    assert [plan.chunk_id for plan in plans] == ["chk_00", "chk_01", "chk_02"]
    assert [plan.frame_start for plan in plans] == [0, 135, 270]
    assert [plan.frame_end for plan in plans] == [149, 284, 399]
    assert plans[0].t_start == 0.0
    assert plans[-1].t_end == pytest.approx(399 / FPS)


def test_clip_shorter_than_a_chunk_is_one_chunk() -> None:
    plans = plan_chunks(_video(60), ChunkParams(frames_per_chunk=150, overlap_frames=15))
    assert len(plans) == 1
    assert (plans[0].frame_start, plans[0].frame_end) == (0, 59)


def test_one_request_per_concept_and_hand_is_always_tracked() -> None:
    concepts = [f"tool_{index}" for index in range(20)]
    groups = group_concepts(concepts)
    assert len(groups) == 21
    assert all(len(group) == 1 for group in groups)
    assert groups[0] == ("hand",)
    assert {group[0] for group in groups[1:]} == set(concepts)
    assert "hand" not in concepts


def test_hand_is_not_duplicated() -> None:
    groups = group_concepts(["hand", "screwdriver", "hand"])
    assert groups == (("hand",), ("screwdriver",))


def test_invalid_parameters_are_rejected() -> None:
    with pytest.raises(ChunkingError):
        ChunkParams(frames_per_chunk=10, overlap_frames=10)
    with pytest.raises(ChunkingError):
        ChunkParams(max_objects=17)
    with pytest.raises(ChunkingError):
        AnalysisVideo(path=Path("x.mp4"), fps=15.0, times=(1.0, 1.0))


def test_runner_writes_global_frames_and_normalised_boxes(scratch: Path) -> None:
    caller = _Caller(lines=[_line(0, 0)])
    result = run_chunks(
        _video(400),
        concepts=["hand"],
        stage_dir=scratch,
        call=caller,
        params=ChunkParams(frames_per_chunk=150, overlap_frames=15),
        cutter=_cut,
    )
    assert [outcome.status for outcome in result.outcomes] == [STATUS_COMPLETE] * 3
    assert result.calls == 3
    files = sorted((scratch / "tracks_raw").glob("chk_*.json"))
    assert len(files) == 3
    payload = json.loads(files[1].read_text(encoding="utf-8"))
    assert payload["frame_start"] == 135
    track = payload["tracks"][0]
    assert track["concept"] == "hand"
    assert track["local_id"] == "hand-0"
    frame = track["frames"][0]
    assert frame["frame"] == 135
    assert frame["t"] == pytest.approx(135 / FPS)
    assert frame["box"] == pytest.approx([0.1, 0.2, 0.31, 0.41])
    assert frame["score"] == pytest.approx(0.9)


def test_request_uses_one_bit_masks_and_one_noun_per_call(scratch: Path) -> None:
    caller = _Caller()
    run_chunks(
        _video(30),
        concepts=["screwdriver", "ssd"],
        stage_dir=scratch,
        call=caller,
        cutter=_cut,
    )
    assert [payload["input"][0]["content"][0]["text"] for payload in caller.payloads] == [
        "hand",
        "screwdriver",
        "ssd",
    ]
    payload = caller.payloads[0]
    assert payload["model"] == "sam-3.1"
    assert payload["metadata"] == {"mask_encoding": "one_bit"}
    content = payload["input"][0]["content"]  # type: ignore[index]
    assert content[1]["video_url"].startswith("data:video/mp4;base64,")


def test_failed_chunk_is_partial_and_resumed(scratch: Path) -> None:
    failing = _Caller(fail_calls=[1])
    first = run_chunks(
        _video(400),
        concepts=["hand"],
        stage_dir=scratch,
        call=failing,
        params=ChunkParams(frames_per_chunk=150, overlap_frames=15),
        cutter=_cut,
    )
    assert first.failed == ("chk_01",)
    assert first.outcomes[1].status == STATUS_PARTIAL
    assert "TimeoutError" in (first.outcomes[1].error or "")

    retrying = _Caller()
    second = run_chunks(
        _video(400),
        concepts=["hand"],
        stage_dir=scratch,
        call=retrying,
        params=ChunkParams(frames_per_chunk=150, overlap_frames=15),
        cutter=_cut,
    )
    assert second.skipped == 2
    assert second.calls == 1
    assert len(retrying.payloads) == 1
    assert second.failed == ()


def test_resume_with_all_chunks_complete_makes_no_calls(scratch: Path) -> None:
    first = _Caller()
    run_chunks(_video(100), concepts=["hand"], stage_dir=scratch, call=first, cutter=_cut)
    second = _Caller()
    result = run_chunks(_video(100), concepts=["hand"], stage_dir=scratch, call=second, cutter=_cut)
    assert second.payloads == []
    assert result.skipped == 1
    assert result.calls == 0


def test_corrupt_artifact_is_rebuilt(scratch: Path) -> None:
    raw = scratch / "tracks_raw"
    raw.mkdir(parents=True)
    (raw / "chk_00.json").write_text("{not json", encoding="utf-8")
    caller = _Caller()
    result = run_chunks(_video(60), concepts=["hand"], stage_dir=scratch, call=caller, cutter=_cut)
    assert result.calls == 1
    assert (raw / "chk_00.json").read_text(encoding="utf-8").count('"complete"') == 1


def test_failed_concept_call_keeps_other_tracks(scratch: Path) -> None:
    caller = _Caller(fail_calls=[1])
    result = run_chunks(
        _video(60),
        concepts=[f"tool_{index}" for index in range(20)],
        stage_dir=scratch,
        call=caller,
        cutter=_cut,
    )
    assert result.calls == 21
    assert result.outcomes[0].status == STATUS_PARTIAL
    payload = json.loads(result.outcomes[0].path.read_text(encoding="utf-8"))
    assert payload["tracks"][0]["concept"] == "hand"
    assert len(payload["errors"]) == 1


def test_unknown_object_ids_are_ignored() -> None:
    plan = ChunkPlan("chk_00", 0, 10, 0.0, 10 / FPS)
    tracks = parse_response(
        _body([_line(0, 0), _line(0, 5)]),
        plan=plan,
        concepts=["hand"],
        times=_video(11).times,
    )
    assert [track.local_id for track in tracks] == ["hand-0"]


def test_build_request_requires_a_concept() -> None:
    with pytest.raises(ChunkingError):
        build_request(b"video", [])


class _RecordingTransport:
    def __init__(self, body: Mapping[str, object]) -> None:
        self.body = body
        self.calls = 0

    def post_json(
        self, path: str, payload: Mapping[str, object], *, timeout_s: float
    ) -> RawResponse:
        self.calls += 1
        return RawResponse(200, {}, json.dumps(self.body).encode("utf-8"))

    def post_multipart(
        self, *_: object, **__: object
    ) -> RawResponse:  # pragma: no cover - SAM never uses multipart
        raise AssertionError("unexpected multipart call")


def test_ledger_counts_one_entry_per_call_and_prices_video_frames(scratch: Path) -> None:
    body = _body([_line(0)], frames=75)
    transport = _RecordingTransport(body)
    ledger = RunLedger(scratch / "ledger.json", cap_usd=3.0)
    client = SamClient(
        mode="live",
        ledger=ledger,
        cache=ResponseCache(scratch / "cache"),
        transport=transport,
    )
    result = run_chunks(
        _video(400),
        concepts=["hand"],
        stage_dir=scratch,
        call=lambda payload: client.segment(payload).body,
        params=ChunkParams(frames_per_chunk=150, overlap_frames=15),
        cutter=_cut,
    )
    assert result.calls == 3
    assert transport.calls == 3
    assert len(ledger.entries) == 3
    assert {entry.sam_units for entry in ledger.entries} == {75}
    assert ledger.total_usd == pytest.approx(0.045)

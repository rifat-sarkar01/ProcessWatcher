"""T-3.4: strict-JSON parsing, median-of-k, batching, failure flags and the writer."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from pw.align.prompts import (
    MAX_PROMPT_CHARS,
    MAX_RATIONALE_CHARS,
    NONE,
    EventDescription,
    PromptSegment,
    SegmentDescription,
    StepDescription,
    TrackPoint,
    TrackSample,
    build_text,
)
from pw.align.scorer import (
    FLAG_PARTIAL,
    FLAG_UNAVAILABLE,
    FLAG_UNIFORM,
    ScorerError,
    normalise_probs,
    parse_batch_response,
    score_segments,
    timeline_parts,
    tracks_from_payload,
    uniform,
)
from pw.clients.errors import TransportTimeout
from pw.data.validate import validate_artifact_file

SCRATCH_ROOT = Path(__file__).resolve().parents[2] / ".uv" / "tests-tmp"
STEPS = (
    StepDescription("stp_01", "Power the PC down", tools=("hand",)),
    StepDescription("stp_02", "Remove the side panel", tools=("Phillips screwdriver",)),
    StepDescription("stp_03", "Remove the old SSD", parts=("SSD",), critical=True),
)
RUN_ID = "run_01ARZ3NDEKTSV4RRFFQ69G5FAV"


def _segment(segment_id: str = "seg_001") -> SegmentDescription:
    return SegmentDescription(segment_id, 0.0, 8.0, ("evt_001",), ("trk_001", "trk_002"))


def _payload(probs: dict[str, float], *, segment_id: str = "seg_001") -> dict[str, Any]:
    return {
        "segment_id": segment_id,
        "step_probs": {step.step_id: probs.get(step.step_id, 0.0) for step in STEPS}
        | {NONE: probs.get(NONE, 0.0)},
        "observed_tools": [],
        "rationale_short": "ok",
    }


def _body(*items: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps({"segments": list(items)})
    return {"output": [{"content": [{"type": "output_text", "text": text}]}]}


def _caller(*bodies: dict[str, Any]):
    calls: list[dict[str, Any]] = []

    def call(payload: MappingLike) -> dict[str, Any]:
        calls.append(dict(payload))
        body = bodies[len(calls) - 1] if len(calls) <= len(bodies) else bodies[-1]
        return body

    call.calls = calls  # type: ignore[attr-defined]
    return call


MappingLike = dict[str, Any]


@pytest.fixture()
def scratch() -> Path:
    root = SCRATCH_ROOT / f"scorer-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_parse_keeps_every_step_and_none() -> None:
    body = _body(_payload({"stp_01": 0.5, "stp_02": 0.3, NONE: 0.2}))
    parsed = parse_batch_response(body, expected_ids=["seg_001"], steps=STEPS)["seg_001"]
    assert parsed.step_probs["stp_01"] == pytest.approx(0.5)
    assert parsed.step_probs["stp_02"] == pytest.approx(0.3)
    assert parsed.step_probs["stp_03"] == 0.0
    assert sum(parsed.step_probs.values()) == pytest.approx(1.0)


def test_missing_steps_default_to_zero_then_normalise() -> None:
    body = _body(_payload({"stp_01": 2.0, NONE: 2.0}))
    parsed = parse_batch_response(body, expected_ids=["seg_001"], steps=STEPS)["seg_001"]
    assert parsed.step_probs["stp_01"] == pytest.approx(0.5)
    assert parsed.step_probs[NONE] == pytest.approx(0.5)
    assert parsed.step_probs["stp_02"] == 0.0


def test_all_zero_probabilities_fall_back_to_uniform() -> None:
    probs, flags = normalise_probs({}, STEPS)
    assert probs == uniform(STEPS)
    assert flags == (FLAG_UNIFORM,)


def test_uniform_covers_steps_plus_none() -> None:
    probs = uniform(STEPS)
    assert set(probs) == {"stp_01", "stp_02", "stp_03", NONE}
    assert sum(probs.values()) == pytest.approx(1.0)


def test_median_of_three_repeats() -> None:
    call = _caller(
        _body(_payload({"stp_01": 0.2, "stp_02": 0.8})),
        _body(_payload({"stp_01": 0.8, "stp_02": 0.2})),
        _body(_payload({"stp_01": 0.5, "stp_02": 0.5})),
    )
    result = score_segments([_segment()], STEPS, call=call)
    scored = result.segments[0]
    assert result.calls == 3
    assert scored.step_probs["stp_01"] == pytest.approx(0.5)
    assert scored.step_probs["stp_02"] == pytest.approx(0.5)
    assert scored.flags == ()


def test_all_repeats_failing_gives_uniform_and_flag() -> None:
    def call(payload: MappingLike) -> dict[str, Any]:
        raise TransportTimeout("deadline")

    result = score_segments([_segment()], STEPS, call=call)
    scored = result.segments[0]
    assert result.calls == 3
    assert scored.flags == (FLAG_UNAVAILABLE,)
    assert scored.step_probs == uniform(STEPS)
    assert scored.rationale_short == ""


def test_some_repeats_failing_flags_partial() -> None:
    calls = {"count": 0}

    def call(payload: MappingLike) -> dict[str, Any]:
        calls["count"] += 1
        if calls["count"] == 1:
            return _body(_payload({"stp_01": 0.7, "stp_02": 0.3}))
        raise TransportTimeout("deadline")

    result = score_segments([_segment()], STEPS, call=call)
    scored = result.segments[0]
    assert scored.flags == (FLAG_PARTIAL,)
    assert scored.step_probs["stp_01"] == pytest.approx(0.7)


def test_batching_groups_segments_in_one_call() -> None:
    first, second = _segment("seg_001"), _segment("seg_002")
    call = _caller(
        _body(
            _payload({"stp_01": 1.0}, segment_id="seg_001"),
            _payload({"stp_02": 1.0}, segment_id="seg_002"),
        )
    )
    result = score_segments([first, second], STEPS, call=call, batch_size=2)
    assert result.calls == 3
    payload = call.calls[0]  # type: ignore[attr-defined]
    schema = payload["text"]["format"]["schema"]["properties"]["segments"]
    assert schema["minItems"] == schema["maxItems"] == 2
    text = payload["input"][0]["content"][0]["text"]
    assert "seg_001" in text and "seg_002" in text
    assert [segment.segment_id for segment in result.segments] == ["seg_001", "seg_002"]


def test_overlong_prompt_is_truncated_deterministically() -> None:
    huge = StepDescription("stp_01", "do the thing " * 2000, tools=("tool",), parts=("part",))
    prompt = PromptSegment(SegmentDescription("seg_001", 0.0, 5.0))
    first = build_text([prompt], [huge], [], {})
    second = build_text([prompt], [huge], [], {})
    assert first == second
    assert len(first) <= MAX_PROMPT_CHARS


def test_keyframes_are_limited_and_rendered() -> None:
    track = TrackSample(
        "trk_001",
        "Phillips screwdriver",
        tuple(
            TrackPoint(frame=index, t=float(index), box=(0.2, 0.2, 0.5, 0.5), poly=())
            for index in range(10)
        ),
    )
    captured: list[dict[str, Any]] = []

    def call(payload: dict[str, Any]) -> dict[str, Any]:
        captured.append(payload)
        return _body(_payload({"stp_01": 1.0}))

    segment = SegmentDescription("seg_001", 0.0, 10.0, (), ("trk_001",))
    result = score_segments(
        [segment],
        STEPS,
        tracks=[track],
        frame_provider=lambda frame: Image.new("RGB", (64, 48), "white"),
        call=call,
    )
    assert result.calls == 3
    content = captured[0]["input"][0]["content"]
    assert len([part for part in content if part["type"] == "input_image"]) == 4
    assert "#1 trk_001 Phillips screwdriver" in content[0]["text"]


def test_text_only_when_no_tracks_are_available() -> None:
    captured: list[dict[str, Any]] = []

    def call(payload: dict[str, Any]) -> dict[str, Any]:
        captured.append(payload)
        return _body(_payload({"stp_01": 1.0}))

    score_segments([_segment()], STEPS, call=call)
    content = captured[0]["input"][0]["content"]
    assert [part["type"] for part in content] == ["input_text"]


def test_observed_tools_are_validated_and_clamped() -> None:
    item = _payload({"stp_01": 1.0})
    item["observed_tools"] = [
        {"track": "trk_004", "label": "SSD", "confidence": 1.7},
        {"track": "bad", "label": "SSD", "confidence": 0.5},
        {"track": "trk_005", "label": "", "confidence": 0.5},
    ]
    parsed = parse_batch_response(_body(item), expected_ids=["seg_001"], steps=STEPS)["seg_001"]
    assert len(parsed.observed_tools) == 1
    assert parsed.observed_tools[0].track == "trk_004"
    assert parsed.observed_tools[0].confidence == 1.0


def test_rationale_is_truncated() -> None:
    item = _payload({"stp_01": 1.0})
    item["rationale_short"] = "x" * 900
    parsed = parse_batch_response(_body(item), expected_ids=["seg_001"], steps=STEPS)["seg_001"]
    assert len(parsed.rationale_short) <= MAX_RATIONALE_CHARS


def test_response_must_cover_every_segment() -> None:
    with pytest.raises(ScorerError):
        parse_batch_response(
            _body(_payload({"stp_01": 1.0})),
            expected_ids=["seg_001", "seg_002"],
            steps=STEPS,
        )
    with pytest.raises(ScorerError):
        parse_batch_response(
            _body(_payload({"stp_01": 1.0}, segment_id="seg_999")),
            expected_ids=["seg_001"],
            steps=STEPS,
        )


def test_likelihoods_writer_validates_the_contract(scratch: Path) -> None:
    call = _caller(_body(_payload({"stp_01": 0.8, "stp_02": 0.2})))
    result = score_segments([_segment()], STEPS, call=call)
    path = result.write(scratch / "likelihoods.json", run_id=RUN_ID)
    kind, errors = validate_artifact_file(path, "likelihoods", None)
    assert kind == "likelihoods"
    assert errors == []
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["segments"][0]["step_probs"]["stp_01"] == pytest.approx(0.8)


def test_prompt_includes_events_and_identity_legend() -> None:
    event = EventDescription("evt_001", "hold_start", 1.0, 1.0, ("trk_001",))
    prompt = PromptSegment(_segment())
    text = build_text([prompt], STEPS, [event], {"trk_001": "SSD (0.9)"})
    assert "evt_001 hold_start" in text
    assert "trk_001 (SSD (0.9))" in text


def test_timeline_and_tracks_adapters() -> None:
    segments, events = timeline_parts(
        {
            "segments": [
                {
                    "id": "seg_001",
                    "t_start": 0.0,
                    "t_end": 2.0,
                    "salient_tracks": ["trk_001"],
                    "event_ids": ["evt_001"],
                    "kind": "activity",
                }
            ],
            "events": [
                {
                    "id": "evt_001",
                    "type": "hold_start",
                    "t_start": 1.0,
                    "t_end": 1.0,
                    "tracks": ["trk_001"],
                    "confidence": 0.9,
                }
            ],
        }
    )
    assert segments[0].segment_id == "seg_001"
    assert events[0].kind == "hold_start"
    tracks = tracks_from_payload(
        {
            "tracks": [
                {
                    "id": "trk_001",
                    "concept": "SSD",
                    "frames": [{"frame": 3, "t": 0.2, "box": [0.1, 0.1, 0.4, 0.4]}],
                }
            ]
        }
    )
    assert tracks[0].frames[0].frame == 3
    assert tracks[0].frames[0].box == (0.1, 0.1, 0.4, 0.4)

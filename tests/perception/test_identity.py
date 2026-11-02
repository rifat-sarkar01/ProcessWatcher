"""T-2.7: crop selection, one-call identity voting, unknown fallback and caching."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

import pytest
from PIL import Image, ImageDraw

from pw.clients.errors import TransportTimeout
from pw.data.validate import validate_artifact_file
from pw.perception.identity import (
    OTHER_LABEL,
    UNKNOWN_LABEL,
    IdentitiesFile,
    IdentityError,
    IdentityResult,
    TrackFrame,
    TrackObservation,
    Vote,
    aggregate_votes,
    build_payload,
    crop_box,
    identify_track,
    identify_tracks,
    parse_predictions,
    read_identities,
    select_crops,
    write_identities,
)

SCRATCH_ROOT = Path(__file__).resolve().parents[2] / ".uv" / "tests-tmp"
VOCABULARY = ["hand", "Phillips screwdriver", "SSD", "side panel"]


def _textured(size: tuple[int, int] = (120, 90)) -> Image.Image:
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    for y in range(0, size[1], 8):
        for x in range(0, size[0], 8):
            if (x // 8 + y // 8) % 2:
                draw.rectangle((x, y, x + 7, y + 7), fill="black")
    return image


def _flat(size: tuple[int, int] = (120, 90)) -> Image.Image:
    return Image.new("RGB", size, "white")


def _body(predictions: list[tuple[str, float]]) -> dict[str, Any]:
    text = json.dumps(
        {"crops": [{"label": label, "confidence": value} for label, value in predictions]}
    )
    return {"output": [{"content": [{"type": "output_text", "text": text}]}]}


def _track(
    frames: list[int], box: tuple[float, float, float, float] = (0.2, 0.2, 0.6, 0.6)
) -> TrackObservation:
    return TrackObservation(
        "trk_001", "Phillips screwdriver", tuple(TrackFrame(frame, box) for frame in frames)
    )


@pytest.fixture()
def scratch() -> Path:
    root = SCRATCH_ROOT / f"identity-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_consistent_labels_give_high_confidence() -> None:
    assert aggregate_votes([("SSD", 0.9), ("SSD", 0.9), ("SSD", 0.9)]) == (
        "SSD",
        0.9,
        (Vote("SSD", 3),),
    )


def test_split_vote_is_low_confidence() -> None:
    label, confidence, votes = aggregate_votes([("SSD", 0.9), ("SSD", 0.9), ("side panel", 0.9)])
    assert label == "SSD"
    assert confidence == pytest.approx(0.6)
    assert [(vote.label, vote.count) for vote in votes] == [("SSD", 2), ("side panel", 1)]


def test_other_label_is_accepted_and_voted() -> None:
    body = _body([("other", 0.8), ("other", 0.6), ("SSD", 0.4)])
    predictions = parse_predictions(body, vocabulary=VOCABULARY, count=3)
    assert aggregate_votes(predictions)[0] == OTHER_LABEL


def test_identify_track_votes_one_call() -> None:
    calls: list[dict[str, Any]] = []

    def call(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append(payload)
        return _body([("SSD", 0.9), ("SSD", 0.8), ("side panel", 0.5)])

    result = identify_track(
        _track([0, 1, 2]),
        others=[],
        frame_provider=lambda frame: _textured(),
        vocabulary=VOCABULARY,
        call=call,
    )
    assert len(calls) == 1
    assert result.label == "SSD"
    assert result.confidence == pytest.approx(round((2 / 3) * 0.85, 4))
    assert result.crop_frames == (0, 1, 2)


def test_api_failure_degrades_to_unknown() -> None:
    def call(payload: dict[str, Any]) -> dict[str, Any]:
        raise TransportTimeout("deadline")

    result = identify_track(
        _track([0]),
        others=[],
        frame_provider=lambda frame: _textured(),
        vocabulary=VOCABULARY,
        call=call,
    )
    assert result.label == UNKNOWN_LABEL
    assert result.confidence == 0.0
    assert result.crop_frames == (0,)


def test_malformed_response_degrades_to_unknown() -> None:
    def call(payload: dict[str, Any]) -> dict[str, Any]:
        return {"output": [{"content": [{"type": "output_text", "text": "not json"}]}]}

    result = identify_track(
        _track([0]),
        others=[],
        frame_provider=lambda frame: _textured(),
        vocabulary=VOCABULARY,
        call=call,
    )
    assert result.label == UNKNOWN_LABEL


def test_out_of_vocabulary_label_is_rejected() -> None:
    with pytest.raises(IdentityError):
        parse_predictions(_body([("hammer", 0.9)]), vocabulary=VOCABULARY, count=1)


def test_hand_tracks_are_never_identified() -> None:
    calls: list[dict[str, Any]] = []
    hand = TrackObservation("trk_000", "hand", (TrackFrame(0, (0.1, 0.1, 0.3, 0.3)),))
    tools = _track([0])

    def call(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append(payload)
        return _body([("SSD", 0.9)])

    result = identify_tracks(
        [hand, tools],
        frame_provider=lambda frame: _textured(),
        vocabulary=VOCABULARY,
        call=call,
    )
    assert [identity.track_id for identity in result.identities] == ["trk_001"]
    assert len(calls) == 1


def test_crop_selection_prefers_sharp_and_unoccluded_frames() -> None:
    track = _track([0, 1])
    occluder = TrackObservation("trk_002", "side panel", (TrackFrame(1, (0.2, 0.2, 0.6, 0.6)),))
    images = {0: _flat(), 1: _textured()}
    crops = select_crops(
        track,
        others=[occluder],
        frame_provider=lambda frame: images[frame],
        max_crops=2,
    )
    # Frame 1 is sharp but fully occluded, frame 0 is flat: both score 0, order by frame.
    assert [crop.frame for crop in crops] == [0, 1]
    assert crops[0].score == 0.0 or crops[1].score == 0.0

    unoccluded = select_crops(
        track,
        others=[],
        frame_provider=lambda frame: images[frame],
        max_crops=1,
    )
    assert unoccluded[0].frame == 1


def test_no_usable_crop_means_no_call() -> None:
    calls: list[dict[str, Any]] = []

    def call(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append(payload)
        return _body([("SSD", 0.9)])

    result = identify_track(
        _track([0]),
        others=[],
        frame_provider=lambda frame: None,
        vocabulary=VOCABULARY,
        call=call,
    )
    assert result.label == UNKNOWN_LABEL
    assert calls == []


def test_cached_identity_skips_the_call() -> None:
    calls: list[dict[str, Any]] = []

    def call(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append(payload)
        return _body([("SSD", 0.9)])

    cached = IdentityResult("trk_001", "SSD", 0.9, (Vote("SSD", 3),), (0, 1, 2))
    result = identify_tracks(
        [_track([0, 1, 2])],
        frame_provider=lambda frame: _textured(),
        vocabulary=VOCABULARY,
        call=call,
        existing={"trk_001": cached},
    )
    assert result.identities == (cached,)
    assert calls == []


def test_cached_unknown_is_retried() -> None:
    calls: list[dict[str, Any]] = []

    def call(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append(payload)
        return _body([("SSD", 0.9)])

    stale = IdentityResult("trk_001", UNKNOWN_LABEL, 0.0, (Vote(UNKNOWN_LABEL, 1),), ())
    result = identify_tracks(
        [_track([0])],
        frame_provider=lambda frame: _textured(),
        vocabulary=VOCABULARY,
        call=call,
        existing={"trk_001": stale},
    )
    assert len(calls) == 1
    assert result.identities[0].label == "SSD"


def test_payload_is_strict_and_carries_the_vocabulary() -> None:
    captured: list[dict[str, Any]] = []

    def call(payload: dict[str, Any]) -> dict[str, Any]:
        captured.append(payload)
        return _body([("SSD", 0.9)])

    identify_track(
        _track([0]),
        others=[],
        frame_provider=lambda frame: _textured(),
        vocabulary=VOCABULARY,
        call=call,
    )
    payload = captured[0]
    assert payload["model"] == "muse-wonder-1.0"
    assert payload["temperature"] == 0
    schema = payload["text"]["format"]["schema"]
    labels = schema["properties"]["crops"]["items"]["properties"]["label"]["enum"]
    assert labels == [*VOCABULARY, OTHER_LABEL]
    content = payload["input"][0]["content"]
    assert "Phillips screwdriver" in content[0]["text"]
    assert content[1]["image_url"].startswith("data:image/png;base64,")


def test_crop_box_pads_by_ten_percent() -> None:
    crop = crop_box((0.2, 0.2, 0.6, 0.6), _flat((100, 100)))
    assert crop.size == (48, 48)


def test_identities_artifact_round_trips_and_validates(scratch: Path) -> None:
    identity = IdentityResult("trk_001", "SSD", 0.85, (Vote("SSD", 2), Vote("other", 1)), (0, 4, 8))
    file = IdentitiesFile(identities=(identity,), run_id="run_01ARZ3NDEKTSV4RRFFQ69G5FAV")
    path = write_identities(scratch / "identities.json", file)
    assert read_identities(path) == {"trk_001": identity}
    kind, errors = validate_artifact_file(path, "identities", None)
    assert kind == "identities" and errors == []


def test_payload_requires_a_crop() -> None:
    with pytest.raises(IdentityError):
        build_payload([], VOCABULARY, concept="SSD")

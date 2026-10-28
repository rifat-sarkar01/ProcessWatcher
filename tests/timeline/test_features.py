"""Contact, hold hysteresis and normalised velocity on synthetic tracks."""

from __future__ import annotations

import pytest

from pw.timeline.features import (
    FeatureParams,
    FrameSample,
    Track,
    extract_features,
)

FPS = 15
OBJECT_BOX = (0.3, 0.3, 0.7, 0.7)
HAND_BOX = (0.35, 0.35, 0.55, 0.55)


def frame(index: int, box: tuple[float, float, float, float], score: float = 0.9) -> FrameSample:
    return FrameSample(frame=index, t=round(index / FPS, 4), box=box, score=score)


def series(
    box: tuple[float, float, float, float],
    indices: range,
    *,
    x_offset: float = 0.0,
    score: float = 0.9,
) -> list[FrameSample]:
    return [
        frame(index, (box[0] + x_offset * index, box[1], box[2] + x_offset * index, box[3]), score)
        for index in indices
    ]


def track(track_id: str, concept: str, frames: list[FrameSample]) -> Track:
    return Track(id=track_id, concept=concept, frames=tuple(frames))


def test_contact_and_hold_between_hand_and_static_object() -> None:
    features = extract_features(
        [
            track("trk_001", "hand", series(HAND_BOX, range(0, 16))),
            track("trk_002", "bolt", series(OBJECT_BOX, range(0, 16))),
        ]
    )
    assert len(features.contacts) == 1
    assert len(features.holds) == 1
    contact = features.contacts[0]
    assert (contact.hand_id, contact.object_id) == ("trk_001", "trk_002")
    assert contact.t_start == 0.0 and contact.t_end == pytest.approx(1.0)
    assert contact.fraction >= 0.2
    assert features.holds[0].confidence == pytest.approx(0.9)


def test_static_object_has_zero_velocity() -> None:
    features = extract_features([track("trk_002", "bolt", series(OBJECT_BOX, range(0, 10)))])
    assert {sample.velocity for sample in features.velocities} == {0.0}


def test_brief_touch_contact_without_hold() -> None:
    features = extract_features(
        [
            track("trk_001", "hand", series(HAND_BOX, range(0, 2))),
            track("trk_002", "bolt", series(OBJECT_BOX, range(0, 2))),
        ]
    )
    assert len(features.contacts) == 1
    assert features.holds == ()


def test_occlusion_flicker_is_bridged_into_one_hold() -> None:
    indices = list(range(0, 11)) + list(range(14, 21))
    features = extract_features(
        [
            track("trk_001", "hand", series(HAND_BOX, indices)),
            track("trk_002", "bolt", series(OBJECT_BOX, indices)),
        ]
    )
    assert len(features.contacts) == 1
    assert len(features.holds) == 1
    assert features.holds[0].t_end - features.holds[0].t_start > 1.0


def test_gap_longer_than_bridge_splits_the_hold() -> None:
    indices = list(range(0, 8)) + list(range(20, 28))
    features = extract_features(
        [
            track("trk_001", "hand", series(HAND_BOX, indices)),
            track("trk_002", "bolt", series(OBJECT_BOX, indices)),
        ]
    )
    assert len(features.holds) == 2


def test_two_hands_produce_independent_holds() -> None:
    features = extract_features(
        [
            track("trk_001", "hand", series(HAND_BOX, range(0, 16))),
            track("trk_002", "hand", series(HAND_BOX, range(0, 16))),
            track("trk_003", "bolt", series(OBJECT_BOX, range(0, 16))),
        ]
    )
    assert {hold.hand_id for hold in features.holds} == {"trk_001", "trk_002"}
    assert len(features.holds) == 2


def test_separated_tracks_have_no_interaction() -> None:
    far = (0.0, 0.0, 0.1, 0.1)
    features = extract_features(
        [
            track("trk_001", "hand", series(far, range(0, 10))),
            track("trk_002", "bolt", series(OBJECT_BOX, range(0, 10))),
        ]
    )
    assert features.contacts == ()
    assert features.holds == ()


def test_box_fallback_when_polygons_are_missing() -> None:
    features = extract_features(
        [
            track("trk_001", "hand", series(HAND_BOX, range(0, 10))),
            track("trk_002", "bolt", series(OBJECT_BOX, range(0, 10))),
        ]
    )
    assert features.contacts and features.contacts[0].fraction > 0.2


def test_polygons_take_precedence_and_can_prevent_contact() -> None:
    tiny = ((0.32, 0.32), (0.36, 0.32), (0.36, 0.36), (0.32, 0.36))
    object_poly = ((0.6, 0.6), (0.7, 0.6), (0.7, 0.7), (0.6, 0.7))
    hand = track(
        "trk_001",
        "hand",
        [FrameSample(index, index / FPS, HAND_BOX, tiny) for index in range(10)],
    )
    obj = track(
        "trk_002",
        "bolt",
        [FrameSample(index, index / FPS, OBJECT_BOX, object_poly) for index in range(10)],
    )
    assert extract_features([hand, obj]).contacts == ()


def test_velocity_is_normalised_by_the_frame_diagonal() -> None:
    moving = track("trk_002", "bolt", series(OBJECT_BOX, range(0, 8), x_offset=0.01))
    features = extract_features([moving])
    last = [sample for sample in features.velocities if sample.track_id == "trk_002"][-1]
    expected = (0.06 / (2**0.5)) / 0.4
    assert last.velocity == pytest.approx(expected, rel=0.05)
    assert all(sample.velocity >= 0 for sample in features.velocities)


def test_proximity_shrinks_as_the_hand_approaches() -> None:
    far = track("trk_001", "hand", series((0.05, 0.35, 0.25, 0.55), range(0, 5)))
    near = track("trk_001", "hand", series(HAND_BOX, range(5, 10)))
    obj = track("trk_002", "bolt", series(OBJECT_BOX, range(0, 10)))
    contact = extract_features([far, near, obj]).contacts[0]
    assert contact.proximity < 1.0


def test_invalid_inputs_are_rejected() -> None:
    with pytest.raises(ValueError):
        Track(id="trk_001", concept="hand", frames=())
    with pytest.raises(ValueError):
        Track(
            id="trk_001",
            concept="hand",
            frames=(frame(2, HAND_BOX), frame(1, HAND_BOX)),
        )
    with pytest.raises(ValueError):
        FeatureParams(contact_min=1.5)
    with pytest.raises(ValueError):
        FeatureParams(hold_on_s=0.6, bridge_s=0.5)


def test_hands_without_objects_produce_only_velocity() -> None:
    features = extract_features([track("trk_001", "hand", series(HAND_BOX, range(0, 5)))])
    assert features.contacts == () and features.holds == ()
    assert len(features.velocities) == 5

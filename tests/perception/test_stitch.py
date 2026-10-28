"""Cross-chunk stitching: overlap matching, gap re-association and provenance."""

from __future__ import annotations

import itertools

import pytest

from pw.data.validate import validate_payload
from pw.perception.stitch import (
    ChunkFrame,
    ChunkTrack,
    ChunkTracks,
    StitchParams,
    stitch_chunks,
)

FPS = 15
VIDEO = {
    "sha256": "c4a1f7e2b9d053816a2e4c6f8b0d1e3a5c7f9b2d4e6a8c0f1b3d5e7a9c2f4b6d",
    "duration_s": 2.0,
    "analysis_fps": FPS,
    "width": 320,
    "height": 240,
    "frame_count": 30,
}
RUN_ID = "run_01J9ZQ8M3K4V7B2C5D6E8F0GHJ"


def sample(index: int, box: tuple[float, float, float, float], score: float = 0.9) -> ChunkFrame:
    return ChunkFrame(frame=index, t=round(index / FPS, 4), box=box, score=score)


def track(local_id: str, concept: str, frames: list[ChunkFrame]) -> ChunkTrack:
    return ChunkTrack(local_id=local_id, concept=concept, frames=tuple(frames))


def chunk(chunk_id: str, t_start: float, t_end: float, tracks: list[ChunkTrack]) -> ChunkTracks:
    return ChunkTracks(chunk_id=chunk_id, t_start=t_start, t_end=t_end, tracks=tuple(tracks))


LEFT = (0.0, 0.4, 0.2, 0.6)
RIGHT = (0.8, 0.4, 1.0, 0.6)
MID = (0.5, 0.4, 0.7, 0.6)


def moving(centre: float) -> tuple[float, float, float, float]:
    return (round(centre - 0.1, 4), 0.4, round(centre + 0.1, 4), 0.6)


def crossing_chunks() -> list[ChunkTracks]:
    left_to_right = [0.10 + 0.04 * index for index in range(10)]
    right_to_left = [0.90 - 0.05 * index for index in range(10)]
    first = chunk(
        "chk_01",
        0.0,
        0.66,
        [
            track("a", "hand", [sample(i, moving(c)) for i, c in enumerate(left_to_right)]),
            track("b", "hand", [sample(i, moving(c)) for i, c in enumerate(right_to_left)]),
        ],
    )
    # overlap frames 8-14; the local ids are swapped relative to the objects
    second = chunk(
        "chk_02",
        0.53,
        1.0,
        [
            track("a", "hand", [sample(i, moving(0.45 + 0.04 * (i - 8))) for i in range(8, 15)]),
            track("b", "hand", [sample(i, moving(0.45 - 0.04 * (i - 8))) for i in range(8, 15)]),
        ],
    )
    return [first, second]


def centre(frame: ChunkFrame) -> float:
    return (frame.box[0] + frame.box[2]) / 2


def test_overlap_matching_keeps_persistent_ids_across_a_local_id_switch() -> None:
    result = stitch_chunks(crossing_chunks())
    assert [item.id for item in result.tracks] == ["trk_001", "trk_002"]
    assert result.merges == 2
    first = result.tracks[0]
    assert first.source_chunks == ("chk_01", "chk_02")
    assert centre(first.frames[0]) < 0.2
    assert centre(first.frames[-1]) > 0.6


def test_crossing_objects_are_never_swapped() -> None:
    result = stitch_chunks(crossing_chunks())
    a_track, b_track = result.tracks
    a_centres = [centre(frame) for frame in a_track.frames]
    b_centres = [centre(frame) for frame in b_track.frames]
    assert a_centres[-1] > 0.6 and b_centres[-1] < 0.3
    # the merged id must stay monotonically on one trajectory, never jump lanes
    assert all(later >= earlier for earlier, later in itertools.pairwise(a_centres))
    assert all(later <= earlier for earlier, later in itertools.pairwise(b_centres))
    assert a_centres[-1] - a_centres[0] > 0.4
    assert b_centres[0] - b_centres[-1] > 0.4


def test_different_concepts_are_never_merged() -> None:
    chunks = [
        chunk("chk_01", 0.0, 0.66, [track("a", "hand", [sample(i, LEFT) for i in range(10)])]),
        chunk(
            "chk_02",
            0.53,
            1.0,
            [track("a", "wrench", [sample(i, LEFT) for i in range(8, 15)])],
        ),
    ]
    result = stitch_chunks(chunks)
    assert len(result.tracks) == 2
    assert result.merges == 0


def test_occlusion_gap_is_bridged_by_appearance() -> None:
    chunks = [
        chunk("chk_01", 0.0, 0.6, [track("a", "bolt", [sample(i, LEFT) for i in range(0, 9)])]),
        chunk("chk_02", 1.5, 2.0, [track("a", "bolt", [sample(i, LEFT) for i in range(25, 30)])]),
    ]
    result = stitch_chunks(chunks, appearance=lambda track_id, frame: (1.0, 0.5, 0.25))
    assert len(result.tracks) == 1
    assert result.gaps_filled == 1
    assert result.tracks[0].source_chunks == ("chk_01", "chk_02")


def test_gap_without_appearance_provider_starts_a_new_track() -> None:
    chunks = [
        chunk("chk_01", 0.0, 0.6, [track("a", "bolt", [sample(i, LEFT) for i in range(0, 9)])]),
        chunk("chk_02", 1.5, 2.0, [track("a", "bolt", [sample(i, LEFT) for i in range(25, 30)])]),
    ]
    result = stitch_chunks(chunks)
    assert len(result.tracks) == 2
    assert result.gaps_filled == 0


def test_gap_longer_than_the_limit_is_not_bridged() -> None:
    chunks = [
        chunk("chk_01", 0.0, 0.2, [track("a", "bolt", [sample(i, LEFT) for i in range(0, 3)])]),
        chunk("chk_02", 1.8, 2.0, [track("a", "bolt", [sample(i, LEFT) for i in range(27, 30)])]),
    ]
    result = stitch_chunks(
        chunks,
        params=StitchParams(max_gap_s=0.5),
        appearance=lambda track_id, frame: (1.0, 0.0),
    )
    assert len(result.tracks) == 2


def test_dissimilar_appearance_does_not_bridge() -> None:
    vector = {"chk_01/a": (1.0, 0.0), "chk_02/a": (0.0, 1.0)}
    chunks = [
        chunk("chk_01", 0.0, 0.2, [track("a", "bolt", [sample(i, LEFT) for i in range(0, 3)])]),
        chunk("chk_02", 0.6, 1.0, [track("a", "bolt", [sample(i, LEFT) for i in range(9, 15)])]),
    ]

    def appearance(track_id: str, frame: ChunkFrame) -> tuple[float, ...]:
        if track_id.startswith("trk_"):
            return vector["chk_01/a"]
        return vector[track_id]

    result = stitch_chunks(chunks, appearance=appearance)
    assert len(result.tracks) == 2


def test_low_iou_overlap_does_not_merge() -> None:
    chunks = [
        chunk("chk_01", 0.0, 0.66, [track("a", "hand", [sample(i, LEFT) for i in range(10)])]),
        chunk(
            "chk_02",
            0.53,
            1.0,
            [track("b", "hand", [sample(i, MID) for i in range(9, 15)])],
        ),
    ]
    result = stitch_chunks(chunks)
    assert len(result.tracks) == 2
    assert result.merges == 0


def test_single_chunk_gets_ids_and_provenance() -> None:
    result = stitch_chunks(
        [chunk("chk_01", 0.0, 0.6, [track("z", "hand", [sample(i, LEFT) for i in range(6)])])]
    )
    assert [item.id for item in result.tracks] == ["trk_001"]
    assert result.tracks[0].source_chunks == ("chk_01",)


def test_empty_chunks_produce_an_empty_valid_artifact() -> None:
    result = stitch_chunks([chunk("chk_01", 0.0, 0.6, [])])
    artifact = result.to_artifact(run_id=RUN_ID, video=VIDEO)
    assert artifact["tracks"] == []
    assert validate_payload("tracks", artifact) == []


def test_artifact_matches_the_tracks_contract() -> None:
    result = stitch_chunks(crossing_chunks(), expected_instances=2)
    artifact = result.to_artifact(run_id=RUN_ID, video=VIDEO)
    assert validate_payload("tracks", artifact) == []
    assert artifact["stitching"] == {
        "fragmentation_ratio": 1.0,
        "merges": 2,
        "gaps_filled": 0,
    }
    assert artifact["tracks"][0]["source_chunks"] == ["chk_01", "chk_02"]
    indices = [frame["frame"] for frame in artifact["tracks"][0]["frames"]]
    assert indices == sorted(indices)


def test_fragmentation_ratio_exposes_over_segmentation() -> None:
    chunks = [
        chunk("chk_01", 0.0, 0.6, [track("a", "hand", [sample(i, LEFT) for i in range(6)])]),
        chunk("chk_02", 1.0, 1.4, [track("a", "hand", [sample(i, LEFT) for i in range(15, 21)])]),
        chunk("chk_03", 1.8, 2.0, [track("a", "hand", [sample(i, LEFT) for i in range(27, 30)])]),
    ]
    result = stitch_chunks(chunks, expected_instances=1)
    assert result.fragmentation_ratio == 3.0


def test_chunk_order_does_not_change_the_result() -> None:
    chunks = crossing_chunks()
    forward = stitch_chunks(chunks)
    backward = stitch_chunks(list(reversed(chunks)))
    assert [item.id for item in forward.tracks] == [item.id for item in backward.tracks]
    assert [item.frames for item in forward.tracks] == [item.frames for item in backward.tracks]


def test_invalid_tracks_and_params_are_rejected() -> None:
    with pytest.raises(ValueError):
        track("a", "hand", [])
    with pytest.raises(ValueError):
        track("a", "hand", [sample(2, LEFT), sample(1, LEFT)])
    with pytest.raises(ValueError):
        StitchParams(iou_threshold=1.5)
    with pytest.raises(ValueError):
        StitchParams(max_gap_s=-1.0)


def test_polygon_overlap_is_used_when_available() -> None:
    square = ((0.1, 0.1), (0.4, 0.1), (0.4, 0.4), (0.1, 0.4))
    shifted = ((0.2, 0.1), (0.5, 0.1), (0.5, 0.4), (0.2, 0.4))
    chunks = [
        chunk(
            "chk_01",
            0.0,
            0.66,
            [
                track(
                    "a",
                    "hand",
                    [ChunkFrame(i, i / FPS, (0.1, 0.1, 0.4, 0.4), square) for i in range(9)],
                )
            ],
        ),
        chunk(
            "chk_02",
            0.53,
            1.0,
            [
                track(
                    "b",
                    "hand",
                    [ChunkFrame(i, i / FPS, (0.2, 0.1, 0.5, 0.4), shifted) for i in range(8, 12)],
                )
            ],
        ),
    ]
    result = stitch_chunks(chunks)
    assert len(result.tracks) == 1
    assert result.merges == 1

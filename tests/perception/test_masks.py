"""T-2.4: SAM mask decoding, RLE/polygon round-trips, gap fill and coverage."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from PIL import Image

from pw.perception.masks import (
    Mask,
    MaskError,
    MaskFrame,
    MaskPayload,
    box_to_mask,
    coverage_report,
    decode_mask,
    encode_one_bit,
    fill_short_gaps,
    mask_iou,
    mask_or_box,
    mask_to_polygon,
    mask_to_rle,
    parse_mask_data,
    polygon_to_mask,
    rle_to_mask,
    smooth_masks,
)

SAM_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "spikes" / "sam"
_MASK_DATA = re.compile(r"data=([0-9]+),([0-9]+),([!~][^|]+)")


def _wire_mask(response: str, line_index: int = 0) -> MaskPayload:
    text = json.loads((SAM_FIXTURES / response).read_text(encoding="utf-8"))["output"][0][
        "content"
    ][0]["text"]
    match = _MASK_DATA.search(text.splitlines()[line_index])
    assert match is not None
    height, width, payload = int(match.group(1)), int(match.group(2)), match.group(3)
    encoding = "lossless" if payload.startswith("~") else "one_bit"
    return MaskPayload(encoding, payload, width, height)


def _png_mask(name: str) -> Mask:
    image = Image.open(SAM_FIXTURES / name).convert("L")
    data = bytes(1 if value >= 129 else 0 for value in image.tobytes())
    return Mask(image.width, image.height, data)


def test_decodes_one_bit_image_mask_to_the_reference_png() -> None:
    decoded = decode_mask(_wire_mask("image_response.json"))
    assert decoded.data == _png_mask("image_mask.png").data


def test_decodes_lossless_video_masks_to_the_reference_pngs() -> None:
    assert (
        decode_mask(_wire_mask("video_response.json", 0)).data
        == _png_mask("video_mask_frame_000.png").data
    )
    assert (
        decode_mask(_wire_mask("video_response.json", 40)).data
        == _png_mask("video_mask_frame_040.png").data
    )


def test_one_bit_decoding_is_canonical() -> None:
    payload = _wire_mask("image_response.json")
    decoded = decode_mask(payload)
    assert encode_one_bit(decoded) == payload.payload


def test_rle_round_trips_exactly() -> None:
    decoded = decode_mask(_wire_mask("image_response.json"))
    restored = rle_to_mask(mask_to_rle(decoded))
    assert restored.data == decoded.data
    assert mask_to_rle(decoded).counts[0] > 0


def test_polygon_round_trip_keeps_at_least_95_percent_iou() -> None:
    decoded = decode_mask(_wire_mask("image_response.json"))
    polygon = mask_to_polygon(decoded)
    assert 3 <= len(polygon) <= 64
    assert all(0.0 <= coordinate <= 1.0 for point in polygon for coordinate in point)
    rebuilt = polygon_to_mask(polygon, decoded.width, decoded.height)
    assert mask_iou(decoded, rebuilt) >= 0.95


def test_empty_mask_has_no_polygon_and_round_trips() -> None:
    empty = Mask(8, 8, bytes(64))
    assert mask_to_polygon(empty) == ()
    assert polygon_to_mask((), 8, 8).data == empty.data
    assert rle_to_mask(mask_to_rle(empty)).data == empty.data


def test_box_fallback_and_mask_preference() -> None:
    boxed = box_to_mask((0.25, 0.25, 0.75, 0.75), 8, 8)
    assert boxed.area == 16
    assert mask_or_box(None, (0.0, 0.0, 1.0, 1.0), 4, 4).area == 16
    real = Mask(8, 8, bytes([1]) * 64)
    assert mask_or_box(real, (0.0, 0.0, 0.1, 0.1), 8, 8) is real


def test_single_frame_gap_is_filled() -> None:
    first = Mask(4, 4, b"\x01" * 16)
    frames = [MaskFrame(0, first), MaskFrame(2, first)]
    filled = fill_short_gaps(frames)
    assert [frame.frame for frame in filled] == [0, 1, 2]
    assert filled[1].mask is first


def test_long_gap_is_kept() -> None:
    first = Mask(4, 4, b"\x01" * 16)
    frames = [MaskFrame(0, first), MaskFrame(5, first)]
    filled = fill_short_gaps(frames)
    assert [frame.frame for frame in filled] == [0, 5]


def test_gap_is_not_filled_without_a_mask() -> None:
    frames = [MaskFrame(0), MaskFrame(2)]
    assert [(frame.frame, frame.mask) for frame in fill_short_gaps(frames)] == [
        (0, None),
        (2, None),
    ]


def test_smoothing_removes_single_frame_noise() -> None:
    clean = bytes(16)
    noisy = bytearray(clean)
    noisy[5] = 1
    frames = [
        MaskFrame(0, Mask(4, 4, clean)),
        MaskFrame(1, Mask(4, 4, bytes(noisy))),
        MaskFrame(2, Mask(4, 4, clean)),
    ]
    smoothed = smooth_masks(frames)
    assert smoothed[1].mask is not None
    assert smoothed[1].mask.data == clean


def test_coverage_report_counts_present_and_masked_frames() -> None:
    mask = Mask(4, 4, b"\x01" * 8 + b"\x00" * 8)
    frames = [MaskFrame(0, mask), MaskFrame(1), MaskFrame(4, mask)]
    report = coverage_report(frames)
    assert report.span_frames == 5
    assert report.present_frames == 3
    assert report.masked_frames == 2
    assert report.coverage_ratio == pytest.approx(0.4)
    assert report.mean_area_ratio == pytest.approx(0.5)
    assert report.largest_gap == 2


def test_decodes_from_the_schema_mapping() -> None:
    payload = _wire_mask("image_response.json")
    mapping = {
        "encoding": payload.encoding,
        "data": f"{payload.height},{payload.width},{payload.payload}",
    }
    assert decode_mask(mapping).data == decode_mask(payload).data


def test_parse_mask_data_splits_dimensions() -> None:
    assert parse_mask_data("2,3,!abc") == (2, 3, "!abc")
    with pytest.raises(MaskError):
        parse_mask_data("nope")


def test_unsupported_or_truncated_payloads_are_rejected() -> None:
    with pytest.raises(MaskError):
        decode_mask(MaskPayload("raw", "!x", 2, 2))
    with pytest.raises(MaskError):
        decode_mask(MaskPayload("one_bit", "!abc", 2, 2))
    with pytest.raises(MaskError):
        encode_one_bit(Mask(2, 2, b"\x02\x00\x00\x00"))

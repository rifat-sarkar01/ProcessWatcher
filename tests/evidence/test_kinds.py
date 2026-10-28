"""Illustrations are labeled and may never masquerade as evidence."""

from __future__ import annotations

import inspect
import io

import pytest
from jsonschema.exceptions import ValidationError
from PIL import Image

from pw.evidence.labeling import (
    WATERMARK_TEXT,
    KindError,
    assert_evidence_kinds,
    watermark_illustration,
)


def _blank(size: tuple[int, int] = (320, 240)) -> Image.Image:
    return Image.new("RGB", size, (255, 255, 255))


def _dark_share(image: Image.Image, rows: int) -> float:
    grey = image.convert("L")
    pixels = list(grey.tobytes())
    width, height = grey.size
    band = pixels[(height - rows) * width :]
    return sum(1 for value in band if value < 64) / len(band)


def test_watermark_is_burned_into_the_bottom_band() -> None:
    original = _blank()
    marked = watermark_illustration(original)
    assert _dark_share(marked, 20) > 0.5
    assert _dark_share(original, 20) == 0.0
    assert marked.getpixel((0, 0)) == (255, 255, 255)


def test_watermark_label_is_the_fixed_constant() -> None:
    assert WATERMARK_TEXT == "AI ILLUSTRATION · NOT EVIDENCE"
    assert set(WATERMARK_TEXT)  # non-empty


def test_watermark_does_not_mutate_the_source_image() -> None:
    original = _blank()
    marked = watermark_illustration(original)
    assert marked is not original
    assert original.convert("L").getextrema() == (255, 255)


def test_watermark_cannot_be_switched_off() -> None:
    parameters = inspect.signature(watermark_illustration).parameters
    assert list(parameters) == ["image"]
    with pytest.raises(TypeError):
        watermark_illustration(_blank(), enabled=False)  # type: ignore[call-arg]


def test_watermark_is_deterministic_and_survives_an_encode_round_trip() -> None:
    original = _blank()
    first = watermark_illustration(original)
    second = watermark_illustration(original)
    assert first.tobytes() == second.tobytes()

    buffer = io.BytesIO()
    first.save(buffer, format="PNG")
    buffer.seek(0)
    with Image.open(buffer) as reloaded:
        decoded = reloaded.convert("RGB")
    assert _dark_share(decoded, 24) > 0.5


def test_watermark_fits_a_narrow_image() -> None:
    marked = watermark_illustration(_blank((80, 60)))
    assert _dark_share(marked, 2) > 0.5
    assert marked.size == (80, 60)


def test_illustration_in_evidence_is_rejected() -> None:
    with pytest.raises(KindError) as caught:
        assert_evidence_kinds([{"evidence_id": "evd_001", "kind": "illustration"}])
    assert isinstance(caught.value, ValidationError)
    assert "evidence[0].kind" in str(caught.value)


def test_evidence_in_the_illustration_slot_is_rejected() -> None:
    with pytest.raises(ValidationError):
        assert_evidence_kinds(
            [{"evidence_id": "evd_001", "kind": "evidence"}],
            illustration={"id": "ill_001", "kind": "evidence"},
        )


def test_missing_kind_is_rejected() -> None:
    with pytest.raises(ValidationError):
        assert_evidence_kinds([{"evidence_id": "evd_001"}])


def test_well_formed_report_kinds_pass() -> None:
    assert_evidence_kinds(
        [{"evidence_id": "evd_001", "kind": "evidence"}],
        illustration={"id": "ill_001", "kind": "illustration"},
    )
    assert_evidence_kinds([])
    assert_evidence_kinds([{"evidence_id": "evd_001", "kind": "evidence"}], illustration=None)

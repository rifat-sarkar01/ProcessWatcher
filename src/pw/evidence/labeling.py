"""Burn the AI-illustration provenance label and enforce evidence kinds.

Illustrations are generated pictures, never observations. Every diagram therefore
carries a burned-in `AI ILLUSTRATION · NOT EVIDENCE` label, and the report builder
refuses to place an illustration in `evidence[]` or evidence in the illustration slot.
The label has no off switch on purpose: provenance is not a render option.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from jsonschema.exceptions import ValidationError
from PIL import Image, ImageDraw, ImageFont

WATERMARK_TEXT = "AI ILLUSTRATION · NOT EVIDENCE"
WATERMARK_MIN_FONT = 9
WATERMARK_MAX_FONT = 28
EVIDENCE_KIND = "evidence"
ILLUSTRATION_KIND = "illustration"


class KindError(ValidationError):
    """An artifact carries a kind that is not allowed in its slot."""


def _font_that_fits(
    draw: ImageDraw.ImageDraw, text: str, width: int
) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    size = max(WATERMARK_MIN_FONT, min(WATERMARK_MAX_FONT, width // 24))
    font = ImageFont.load_default(size=size)
    while size > WATERMARK_MIN_FONT:
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= width:
            return font
        size -= 1
        font = ImageFont.load_default(size=size)
    return font


def watermark_illustration(image: Image.Image) -> Image.Image:
    """Return a copy with the provenance band burned into the bottom edge."""
    base = image.convert("RGB")
    draw = ImageDraw.Draw(base)
    font = _font_that_fits(draw, WATERMARK_TEXT, base.width - 24)
    _left, top, _right, bottom = draw.textbbox((0, 0), WATERMARK_TEXT, font=font)
    text_height = max(1, bottom - top)
    padding = max(6, text_height // 2)
    bar_height = text_height + 2 * padding
    y0 = max(0, base.height - bar_height)

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    band = ImageDraw.Draw(overlay)
    band.rectangle((0, y0, base.width, base.height), fill=(0, 0, 0, 200))
    band.text((12, y0 + padding - top), WATERMARK_TEXT, font=font, fill=(255, 255, 255, 255))
    return Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")


def _kind(item: Mapping[str, Any]) -> str | None:
    kind = item.get("kind")
    return str(kind) if kind is not None else None


def assert_evidence_kinds(
    evidence: Iterable[Mapping[str, Any]] = (),
    *,
    illustration: Mapping[str, Any] | None = None,
) -> None:
    """Reject an illustration in `evidence[]` or evidence in the illustration slot."""
    for index, item in enumerate(evidence):
        kind = _kind(item)
        if kind != EVIDENCE_KIND:
            raise KindError(f"evidence[{index}].kind must be '{EVIDENCE_KIND}', got {kind!r}")
    if illustration is not None and _kind(illustration) != ILLUSTRATION_KIND:
        raise KindError(
            f"illustration.kind must be '{ILLUSTRATION_KIND}', got {_kind(illustration)!r}"
        )


__all__ = [
    "EVIDENCE_KIND",
    "ILLUSTRATION_KIND",
    "WATERMARK_TEXT",
    "KindError",
    "assert_evidence_kinds",
    "watermark_illustration",
]

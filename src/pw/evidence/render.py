"""Pure image primitives for mask overlays and set-of-mark keyframes.

Every function returns a new frame: callers keep the original pixels (evidence is
always the real frame, never a mutated copy). Coordinates on the wire are normalised
to the frame, so the same track renders correctly at analysis and source resolution.
"""

from __future__ import annotations

import zlib
from collections.abc import Sequence
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

RGB = tuple[int, int, int]
Rect = tuple[int, int, int, int]

ALPHA = 96
LABEL_PADDING = 3

# Distinguishable on grey and on each other; assigned deterministically by track id.
PALETTE: tuple[RGB, ...] = (
    (214, 40, 40),
    (36, 71, 133),
    (20, 140, 120),
    (201, 148, 0),
    (232, 93, 4),
    (122, 63, 191),
    (0, 140, 186),
    (92, 145, 24),
    (226, 58, 111),
    (0, 121, 140),
)


@dataclass(frozen=True, slots=True)
class FrameOverlay:
    """One track's presence in one frame, in normalised coordinates."""

    track_id: str
    concept: str
    box: tuple[float, float, float, float]
    poly: tuple[tuple[float, float], ...] = ()


def colour_for(track_id: str) -> RGB:
    """Stable colour per global track id."""
    return PALETTE[zlib.crc32(track_id.encode("utf-8")) % len(PALETTE)]


def _pixel_box(box: tuple[float, float, float, float], size: tuple[int, int]) -> Rect:
    width, height = size
    x0, y0, x1, y1 = box
    left = max(0, min(width - 1, round(x0 * width)))
    top = max(0, min(height - 1, round(y0 * height)))
    right = max(left + 1, min(width, round(x1 * width)))
    bottom = max(top + 1, min(height, round(y1 * height)))
    return left, top, right, bottom


def _pixel_poly(
    poly: Sequence[tuple[float, float]], size: tuple[int, int]
) -> list[tuple[int, int]]:
    width, height = size
    return [
        (
            max(0, min(width - 1, round(x * width))),
            max(0, min(height - 1, round(y * height))),
        )
        for x, y in poly
    ]


def _font(size: int = 16) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)


def _label_text(overlay: FrameOverlay) -> str:
    return f"#{overlay.track_id} {overlay.concept}"


def _clamp_rect(rect: Rect, size: tuple[int, int]) -> Rect:
    width, height = size
    left, top, right, bottom = rect
    box_width = right - left
    box_height = bottom - top
    left = max(0, min(left, width - box_width))
    top = max(0, min(top, height - box_height))
    return left, top, left + box_width, top + box_height


def _intersects(left: Rect, right: Rect) -> bool:
    return not (
        left[2] <= right[0] or right[2] <= left[0] or left[3] <= right[1] or right[3] <= left[1]
    )


def _first_free(rect: Rect, placed: Sequence[Rect], size: tuple[int, int]) -> Rect:
    width, height = size
    box_width = rect[2] - rect[0]
    box_height = rect[3] - rect[1]
    step = 4
    for top in range(rect[1], max(rect[1], height - box_height) + 1, step):
        candidate = (rect[0], top, rect[0] + box_width, top + box_height)
        if not any(_intersects(candidate, other) for other in placed):
            return candidate
    for left in range(0, max(0, width - box_width) + 1, step):
        for top in range(0, max(0, height - box_height) + 1, step):
            candidate = (left, top, left + box_width, top + box_height)
            if not any(_intersects(candidate, other) for other in placed):
                return candidate
    return rect


def label_boxes(
    overlays: Sequence[FrameOverlay],
    size: tuple[int, int],
    *,
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont | None = None,
) -> list[Rect]:
    """Place `#id concept` labels above their boxes, nudging them so they stay readable."""
    chosen_font = font or _font()
    measure = ImageDraw.Draw(Image.new("RGB", size))
    placed: list[Rect] = []
    for overlay in overlays:
        text = _label_text(overlay)
        text_box = measure.textbbox((0, 0), text, font=chosen_font)
        text_width = int(text_box[2] - text_box[0]) + 2 * LABEL_PADDING
        text_height = int(text_box[3] - text_box[1]) + 2 * LABEL_PADDING
        left, top, _, bottom = _pixel_box(overlay.box, size)
        candidates = (
            _clamp_rect(
                (left, top - text_height - LABEL_PADDING, left + text_width, top - LABEL_PADDING),
                size,
            ),
            _clamp_rect((left, top, left + text_width, top + text_height), size),
            _clamp_rect(
                (
                    left,
                    bottom + LABEL_PADDING,
                    left + text_width,
                    bottom + LABEL_PADDING + text_height,
                ),
                size,
            ),
        )
        rect = next(
            (
                candidate
                for candidate in candidates
                if not any(_intersects(candidate, other) for other in placed)
            ),
            None,
        )
        if rect is None:
            rect = _first_free(candidates[0], placed, size)
        placed.append(rect)
    return placed


def _mask_layer(frame: Image.Image, overlays: Sequence[FrameOverlay], alpha: int) -> Image.Image:
    layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for overlay in overlays:
        colour = colour_for(overlay.track_id)
        if overlay.poly:
            draw.polygon(
                _pixel_poly(overlay.poly, frame.size),
                fill=(*colour, alpha),
                outline=(*colour, 255),
            )
        else:
            draw.rectangle(
                _pixel_box(overlay.box, frame.size),
                fill=(*colour, alpha),
                outline=(*colour, 255),
                width=2,
            )
    return layer


def render_overlay(
    frame: Image.Image,
    overlays: Sequence[FrameOverlay],
    *,
    alpha: int = ALPHA,
    labels: bool = True,
) -> Image.Image:
    """Draw translucent masks (or boxes) plus `#id concept` labels."""
    composed = Image.alpha_composite(frame.convert("RGBA"), _mask_layer(frame, overlays, alpha))
    if labels and overlays:
        draw = ImageDraw.Draw(composed)
        font = _font()
        rects = label_boxes(overlays, frame.size, font=font)
        for overlay, rect in zip(overlays, rects, strict=True):
            draw.rectangle(rect, fill=(0, 0, 0, 190))
            draw.text(
                (rect[0] + LABEL_PADDING, rect[1] + LABEL_PADDING),
                _label_text(overlay),
                fill=(255, 255, 255, 255),
                font=font,
            )
    return composed.convert("RGB")


def render_set_of_mark(
    frame: Image.Image, overlays: Sequence[FrameOverlay], *, alpha: int = ALPHA
) -> Image.Image:
    """Draw masks with one numbered badge per track (the scorer's keyframe format)."""
    composed = Image.alpha_composite(frame.convert("RGBA"), _mask_layer(frame, overlays, alpha))
    draw = ImageDraw.Draw(composed)
    font = _font(18)
    radius = 14
    for number, overlay in enumerate(overlays, start=1):
        left, top, right, bottom = _pixel_box(overlay.box, frame.size)
        centre_x = (left + right) // 2
        centre_y = (top + bottom) // 2
        draw.ellipse(
            (centre_x - radius, centre_y - radius, centre_x + radius, centre_y + radius),
            fill=(*colour_for(overlay.track_id), 255),
            outline=(255, 255, 255, 255),
            width=2,
        )
        text = str(number)
        text_box = draw.textbbox((0, 0), text, font=font)
        text_width = text_box[2] - text_box[0]
        text_height = text_box[3] - text_box[1]
        draw.text(
            (centre_x - text_width / 2 - text_box[0], centre_y - text_height / 2 - text_box[1]),
            text,
            fill=(255, 255, 255, 255),
            font=font,
        )
    return composed.convert("RGB")


def format_timestamp(seconds: float) -> str:
    """`mm:ss.mmm`, clamped at zero."""
    safe = max(0.0, seconds)
    minutes = int(safe // 60)
    return f"{minutes:02d}:{safe - minutes * 60:06.3f}"


def draw_timestamp(frame: Image.Image, seconds: float, *, corner: str = "top-left") -> Image.Image:
    """Burn `mm:ss.mmm` into a corner with a dark backing box."""
    if corner not in {"top-left", "top-right"}:
        raise ValueError(f"unsupported corner: {corner}")
    text = format_timestamp(seconds)
    font = _font(18)
    composed = frame.convert("RGBA")
    draw = ImageDraw.Draw(composed)
    text_box = draw.textbbox((0, 0), text, font=font)
    text_width = int(text_box[2] - text_box[0])
    text_height = int(text_box[3] - text_box[1])
    left = 8 if corner == "top-left" else frame.width - text_width - 16
    top = 8
    draw.rectangle(
        (left - 4, top - 2, left + text_width + 4, top + text_height + 4),
        fill=(0, 0, 0, 180),
    )
    draw.text((left, top), text, fill=(255, 255, 255, 255), font=font)
    return composed.convert("RGB")


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
    max_width: int,
) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    candidate = text
    while candidate and draw.textlength(candidate + "...", font=font) > max_width:
        candidate = candidate[:-1]
    return candidate + "..."


def draw_caption(frame: Image.Image, text: str) -> Image.Image:
    """Draw a bottom caption bar, truncating text that would overflow the frame."""
    font = _font(16)
    composed = frame.convert("RGBA")
    draw = ImageDraw.Draw(composed)
    text_box = draw.textbbox((0, 0), text, font=font)
    text_height = int(text_box[3] - text_box[1])
    bar_height = text_height + 16
    top = frame.height - bar_height
    draw.rectangle((0, top, frame.width, frame.height), fill=(0, 0, 0, 180))
    fitted = _fit_text(draw, text, font, frame.width - 24)
    draw.text((12, top + 8), fitted, fill=(255, 255, 255, 255), font=font)
    return composed.convert("RGB")

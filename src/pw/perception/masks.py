"""Mask utilities: SAM payload decoding, RLE, polygons, box fallback and temporal repair.

The range coder is a dependency-free port of the reference SAM mask codec (Copyright
(c) Meta Platforms, Inc. and affiliates, SAM License) fixed by ADR-001: base85 over the
85 allowed printable characters, a 5-character length prefix, then an adaptive range
coder; `!` is one-bit (`one_bit`) and `~` is lossless coverage (threshold >= 129).
Polygons are traced along pixel edges and simplified with Douglas-Peucker (<= 64 points,
normalised to the frame) for the UI; boxes are always accepted as a fallback.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

Point = tuple[float, float]

_EXCLUDED = frozenset({'"', "\\", ",", ";", "<", ">", "|"})
_ALPHABET = "".join(
    character for code in range(0x21, 0x7F) if (character := chr(code)) not in _EXCLUDED
)
_RADIX = 85
_PREFIX_LENGTH = 5
_CHARACTER_VALUES = [-1] * 128
for _index, _character in enumerate(_ALPHABET):
    _CHARACTER_VALUES[ord(_character)] = _index

_TOP = 1 << 24
_BOTTOM = 1 << 16
_MASK_8 = 0xFF
_MASK_16 = 0xFFFF
_MASK_32 = 0xFFFFFFFF
_INCREMENT = 14
_COUNT_LIMIT = 4096
_CONTEXT_COUNT = 1 << 12
_PADDING = 2
_SYMBOLS = 256
_TOTAL_INDEX = _SYMBOLS
_SPATIAL_MODES = 5
_ZERO_INCREMENT = 32
_ZERO_LIMIT = 16384
_ORDER_ONE_INCREMENT = 56
_ORDER_ONE_LIMIT = 8192
_ORDER_TWO_STEP = 14 * 44
_ORDER_TWO_LIMIT = 14 * 3584
_ORDER_ZERO_STEP = 2 * 16
_ORDER_ZERO_LIMIT = 2 * 2048
_ORDER_ZERO_INITIAL = 2
_ORDER_ONE_INITIAL = 1
_MAXIMUM_SAFE_INTEGER = (1 << 53) - 1
_LOSSLESS_THRESHOLD = 129
_MAX_POLYGON_POINTS = 64


class MaskError(ValueError):
    """A malformed or unsupported SAM mask payload."""


def _u8(value: int) -> int:
    return value & _MASK_8


def _u16(value: int) -> int:
    return value & _MASK_16


def _u32(value: int) -> int:
    return value & _MASK_32


def _i32(value: int) -> int:
    value &= _MASK_32
    return value if value < 1 << 31 else value - (1 << 32)


def _digit(character: str) -> int:
    code = ord(character)
    value = _CHARACTER_VALUES[code] if code < len(_CHARACTER_VALUES) else -1
    if value < 0 or value >= _RADIX:
        raise MaskError("Mask payload contains an invalid character.")
    return value


def _pack(values: Sequence[int]) -> str:
    length = len(values)
    remaining = length
    prefix = [""] * _PREFIX_LENGTH
    for index in range(_PREFIX_LENGTH - 1, -1, -1):
        prefix[index] = _ALPHABET[remaining % _RADIX]
        remaining //= _RADIX
    if remaining != 0:
        raise MaskError("Mask payload is too large.")
    output = list(prefix)
    offset = 0
    full = length - (length % 4)
    while offset < full:
        value = _u32(
            (values[offset] << 24)
            | (values[offset + 1] << 16)
            | (values[offset + 2] << 8)
            | values[offset + 3]
        )
        digits = [0] * 5
        for index in range(4, -1, -1):
            digits[index] = value % _RADIX
            value = (value - digits[index]) // _RADIX
        output.extend(_ALPHABET[digit] for digit in digits)
        offset += 4
    remainder = length - offset
    if remainder > 0:
        value = 0
        for index in range(4):
            value = _u32((value << 8) | (values[offset + index] if index < remainder else 0))
        digits = [0] * 5
        for index in range(4, -1, -1):
            digits[index] = value % _RADIX
            value = (value - digits[index]) // _RADIX
        output.extend(_ALPHABET[digits[index]] for index in range(remainder + 1))
    return "".join(output)


def _unpack(payload: str) -> bytes:
    if len(payload) < _PREFIX_LENGTH:
        raise MaskError("Mask payload is missing its length prefix.")
    length = 0
    for character in payload[:_PREFIX_LENGTH]:
        length = length * _RADIX + _digit(character)
    if length > _MAXIMUM_SAFE_INTEGER:
        raise MaskError("Mask payload length is unsupported.")
    remainder = length % 4
    expected = _PREFIX_LENGTH + (length // 4) * 5 + (0 if remainder == 0 else remainder + 1)
    if len(payload) != expected:
        raise MaskError("Mask payload length does not match its prefix.")
    output = bytearray(length)
    source = _PREFIX_LENGTH
    destination = 0
    full = length - remainder
    while destination < full:
        value = 0
        for index in range(5):
            value = value * _RADIX + _digit(payload[source + index])
        if value > _MASK_32:
            raise MaskError("Mask payload contains an out-of-range group.")
        source += 5
        output[destination] = (value >> 24) & _MASK_8
        output[destination + 1] = (value >> 16) & _MASK_8
        output[destination + 2] = (value >> 8) & _MASK_8
        output[destination + 3] = value & _MASK_8
        destination += 4
    if remainder > 0:
        value = 0
        for index in range(5):
            value = value * _RADIX + (
                _digit(payload[source + index]) if index < remainder + 1 else _RADIX - 1
            )
        if value > _MASK_32:
            raise MaskError("Mask payload contains an out-of-range tail.")
        for index in range(remainder):
            output[destination + index] = (value >> (24 - index * 8)) & _MASK_8
    if _pack(output) != payload:
        raise MaskError("Mask payload is not in canonical form.")
    return bytes(output)


class _RangeEncoder:
    __slots__ = ("_low", "_output", "_range")

    def __init__(self) -> None:
        self._low = 0
        self._range = _MASK_32
        self._output = bytearray()

    def encode(self, cumulative: int, frequency: int, total: int) -> None:
        scaled = self._range // total
        self._low = _u32(self._low + scaled * cumulative)
        self._range = scaled * frequency
        while True:
            if _u32(self._low ^ _u32(self._low + self._range)) < _TOP:
                pass
            elif self._range < _BOTTOM:
                self._range = _u32(-self._low) & (_BOTTOM - 1)
            else:
                break
            self._output.append((self._low >> 24) & _MASK_8)
            self._low = _u32(self._low << 8)
            self._range = _u32(self._range << 8)

    def finish(self) -> bytes:
        for _ in range(4):
            self._output.append((self._low >> 24) & _MASK_8)
            self._low = _u32(self._low << 8)
        return bytes(self._output)


class _RangeDecoder:
    __slots__ = ("_code", "_input", "_low", "_position", "_range", "_scaled")

    def __init__(self, input_: bytes) -> None:
        if len(input_) < 4:
            raise MaskError("Mask payload is missing its finalization.")
        self._input = input_
        self._position = 0
        self._low = 0
        self._range = _MASK_32
        self._code = 0
        self._scaled = 0
        for _ in range(4):
            self._code = _u32((self._code << 8) | self._read())

    def frequency(self, total: int) -> int:
        self._scaled = self._range // total
        if self._scaled == 0:
            raise MaskError("Mask payload has invalid coding state.")
        value = _u32(self._code - self._low) // self._scaled
        return total - 1 if value >= total else value

    def decode(self, cumulative: int, frequency: int) -> None:
        self._low = _u32(self._low + self._scaled * cumulative)
        self._range = self._scaled * frequency
        while True:
            if _u32(self._low ^ _u32(self._low + self._range)) < _TOP:
                pass
            elif self._range < _BOTTOM:
                self._range = _u32(-self._low) & (_BOTTOM - 1)
            else:
                break
            self._code = _u32((self._code << 8) | self._read())
            self._low = _u32(self._low << 8)
            self._range = _u32(self._range << 8)

    def _read(self) -> int:
        if self._position >= len(self._input):
            raise MaskError("Mask payload ended before decoding completed.")
        value = self._input[self._position]
        self._position += 1
        return value


def _get_order_two(counts_by_context: dict[int, list[int]], key: int) -> list[int]:
    counts = counts_by_context.get(key)
    if counts is None:
        counts = [0] * (_SYMBOLS + 1)
        counts_by_context[key] = counts
    return counts


def _paeth(left: int, up: int, upper_left: int) -> int:
    estimate = left + up - upper_left
    left_distance = abs(estimate - left)
    up_distance = abs(estimate - up)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= up_distance and left_distance <= upper_left_distance:
        return left
    return up if up_distance <= upper_left_distance else upper_left


def _predict_byte(output: bytearray, offset: int, x: int, y: int, mode: int, width: int) -> int:
    if mode < 0 or mode >= _SPATIAL_MODES:
        raise MaskError("Lossless mask payload uses an invalid predictor.")
    left = output[offset - 1] if x > 0 else 0
    up = output[offset - width] if y > 0 else 0
    if mode == 1:
        return up
    if mode == 2:
        return left
    if mode == 3:
        return (left + up) >> 1
    upper_left = output[offset - width - 1] if x > 0 and y > 0 else 0
    if mode == 0:
        return _paeth(left, up, upper_left)
    if upper_left >= max(left, up):
        return min(left, up)
    if upper_left <= min(left, up):
        return max(left, up)
    return left + up - upper_left


def _unzig(value: int, prediction: int) -> int:
    delta = -((value + 1) >> 1) if value & 1 else value >> 1
    return _u8(prediction + delta)


def _zero_context(residuals: bytearray, offset: int, x: int, y: int, width: int) -> int:
    left = int(residuals[offset - 1] == 0) if x > 0 else 1
    up = int(residuals[offset - width] == 0) if y > 0 else 1
    upper_left = int(residuals[offset - width - 1] == 0) if x > 0 and y > 0 else 1
    upper_right = int(residuals[offset - width + 1] == 0) if y > 0 and x < width - 1 else 1
    return left | (up << 1) | (upper_left << 2) | (upper_right << 3)


def _decode_lossless(payload: str, width: int, height: int) -> bytearray:
    if not payload.startswith("~"):
        raise MaskError("lossless mask payloads must start with ~.")
    packed = _unpack(payload[1:])
    if len(packed) < 5:
        raise MaskError("Lossless mask payload is truncated.")
    selector = packed[0]
    decoder = _RangeDecoder(packed[1:])
    length = width * height
    output = bytearray(length)
    residuals = bytearray(length)
    zero_counts = [1] * 32
    order_one = [_ORDER_ONE_INITIAL] * (_SYMBOLS * _SYMBOLS)
    order_one_totals = [_SYMBOLS * _ORDER_ONE_INITIAL] * _SYMBOLS
    order_zero = [_ORDER_ZERO_INITIAL] * _SYMBOLS
    order_zero_total = _SYMBOLS * _ORDER_ZERO_INITIAL
    order_two: dict[int, list[int]] = {}
    previous = 0
    for offset in range(length):
        x = offset % width
        y = offset // width
        zero_offset = _zero_context(residuals, offset, x, y, width) << 1
        zero = zero_counts[zero_offset]
        nonzero = zero_counts[zero_offset + 1]
        zero_frequency = decoder.frequency(zero + nonzero)
        bit = 0 if zero_frequency < zero else 1
        decoder.decode(0 if bit == 0 else zero, zero if bit == 0 else nonzero)
        zero_counts[zero_offset + bit] = _u32(zero_counts[zero_offset + bit] + _ZERO_INCREMENT)
        if zero_counts[zero_offset] + zero_counts[zero_offset + 1] >= _ZERO_LIMIT:
            zero_counts[zero_offset] = (zero_counts[zero_offset] >> 1) or 1
            zero_counts[zero_offset + 1] = (zero_counts[zero_offset + 1] >> 1) or 1
        symbol = 0
        if bit == 1:
            above = residuals[offset - width] if offset >= width else 0
            second = _get_order_two(order_two, (previous << 8) | above)
            first_offset = previous << 8
            excluded_zero = second[0] + order_one[first_offset] + order_zero[0]
            total = (
                second[_TOTAL_INDEX] + order_one_totals[previous] + order_zero_total - excluded_zero
            )
            target = decoder.frequency(total)
            cumulative = 0
            symbol = 1
            frequency = second[1] + order_one[first_offset + 1] + order_zero[1]
            while cumulative + frequency <= target:
                cumulative += frequency
                symbol += 1
                if symbol >= _SYMBOLS:
                    raise MaskError("Lossless mask payload is malformed.")
                frequency = second[symbol] + order_one[first_offset + symbol] + order_zero[symbol]
            decoder.decode(cumulative, frequency)
            second[symbol] = _u16(second[symbol] + _ORDER_TWO_STEP)
            second[_TOTAL_INDEX] = _u16(second[_TOTAL_INDEX] + _ORDER_TWO_STEP)
            if second[_TOTAL_INDEX] >= _ORDER_TWO_LIMIT:
                total_after_scaling = 0
                for value in range(_SYMBOLS):
                    second[value] >>= 1
                    total_after_scaling += second[value]
                second[_TOTAL_INDEX] = _u16(total_after_scaling)
            order_one[first_offset + symbol] = _u16(
                order_one[first_offset + symbol] + _ORDER_ONE_INCREMENT
            )
            order_one_totals[previous] = _i32(order_one_totals[previous] + _ORDER_ONE_INCREMENT)
            if order_one_totals[previous] >= _ORDER_ONE_LIMIT:
                total_after_scaling = 0
                for value in range(_SYMBOLS):
                    scaled = (order_one[first_offset + value] >> 1) or 1
                    order_one[first_offset + value] = scaled
                    total_after_scaling += scaled
                order_one_totals[previous] = _i32(total_after_scaling)
            order_zero[symbol] = _u16(order_zero[symbol] + _ORDER_ZERO_STEP)
            order_zero_total += _ORDER_ZERO_STEP
            if order_zero_total >= _ORDER_ZERO_LIMIT:
                total_after_scaling = 0
                for value in range(_SYMBOLS):
                    order_zero[value] >>= 1
                    total_after_scaling += order_zero[value]
                order_zero_total = total_after_scaling
        residuals[offset] = symbol
        output[offset] = _unzig(symbol, _predict_byte(output, offset, x, y, selector, width))
        previous = symbol
    return output


def _context_at(raster: bytearray, position: int, prior: int, earlier: int) -> int:
    return (
        raster[position - 1]
        | (raster[position - 2] << 1)
        | (raster[prior - 2] << 2)
        | (raster[prior - 1] << 3)
        | (raster[prior] << 4)
        | (raster[prior + 1] << 5)
        | (raster[prior + 2] << 6)
        | (raster[earlier - 2] << 7)
        | (raster[earlier - 1] << 8)
        | (raster[earlier] << 9)
        | (raster[earlier + 1] << 10)
        | (raster[earlier + 2] << 11)
    )


def _update_counts(counts: list[int], offset: int, bit: int) -> None:
    counts[offset + bit] = _u16(counts[offset + bit] + _INCREMENT)
    if counts[offset] + counts[offset + 1] >= _COUNT_LIMIT:
        counts[offset] = (counts[offset] >> 1) or 1
        counts[offset + 1] = (counts[offset + 1] >> 1) or 1


def encode_one_bit(mask: Mask) -> str:
    """Encode a 0/1 raster as a canonical `one_bit` payload (used to verify decoding)."""
    encoder = _RangeEncoder()
    counts = [1] * (_CONTEXT_COUNT * 2)
    width, height = mask.width, mask.height
    padded_width = width + 2 * _PADDING
    padded = bytearray(padded_width * (height + _PADDING))
    for y in range(height):
        row = (y + _PADDING) * padded_width + _PADDING
        for x in range(width):
            position = row + x
            context = _context_at(
                padded, position, position - padded_width, position - 2 * padded_width
            )
            offset = context << 1
            zero = counts[offset]
            one = counts[offset + 1]
            bit = mask.data[y * width + x]
            if bit not in (0, 1):
                raise MaskError("Mask raster is not binary.")
            if bit == 0:
                encoder.encode(0, zero, zero + one)
            else:
                encoder.encode(zero, one, zero + one)
            padded[position] = bit
            _update_counts(counts, offset, bit)
    return f"!{_pack(encoder.finish())}"


def _decode_one_bit(payload: str, width: int, height: int) -> bytearray:
    decoder = _RangeDecoder(_unpack(payload[1:]))
    counts = [1] * (_CONTEXT_COUNT * 2)
    padded_width = width + 2 * _PADDING
    padded = bytearray(padded_width * (height + _PADDING))
    output = bytearray(width * height)
    for y in range(height):
        row = (y + _PADDING) * padded_width + _PADDING
        for x in range(width):
            position = row + x
            context = _context_at(
                padded, position, position - padded_width, position - 2 * padded_width
            )
            offset = context << 1
            zero = counts[offset]
            one = counts[offset + 1]
            value = decoder.frequency(zero + one)
            bit = 0 if value < zero else 1
            if bit == 0:
                decoder.decode(0, zero)
            else:
                decoder.decode(zero, one)
            padded[position] = bit
            output[y * width + x] = bit
            _update_counts(counts, offset, bit)
    return output


@dataclass(frozen=True, slots=True)
class MaskPayload:
    encoding: str
    payload: str
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class Mask:
    width: int
    height: int
    data: bytes

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise MaskError("Mask dimensions must be positive.")
        if len(self.data) != self.width * self.height:
            raise MaskError("Mask raster length does not match its dimensions.")

    @property
    def area(self) -> int:
        return sum(self.data)

    @property
    def area_ratio(self) -> float:
        return self.area / (self.width * self.height)

    def pixel(self, x: int, y: int) -> int:
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return 0
        return self.data[y * self.width + x]


def decode_mask(mask: MaskPayload | Mapping[str, Any]) -> Mask:
    """Decode a SAM mask; accepts `MaskPayload` or a schema `{encoding, data}` mapping."""
    payload = mask if isinstance(mask, MaskPayload) else _payload_from_mapping(mask)
    if payload.encoding not in ("one_bit", "lossless"):
        raise MaskError(f"Unsupported mask encoding: {payload.encoding}.")
    width, height = payload.width, payload.height
    if width * height > _MAXIMUM_SAFE_INTEGER:
        raise MaskError("Mask dimensions produce an unsafe decoded area.")
    expected_prefix = "!" if payload.encoding == "one_bit" else "~"
    if not payload.payload.startswith(expected_prefix):
        raise MaskError(f"{payload.encoding} mask payloads must start with {expected_prefix}.")
    try:
        if payload.encoding == "lossless":
            coverage = _decode_lossless(payload.payload, width, height)
            return Mask(
                width, height, bytes(int(value >= _LOSSLESS_THRESHOLD) for value in coverage)
            )
        raster = _decode_one_bit(payload.payload, width, height)
        if encode_one_bit(Mask(width, height, bytes(raster))) != payload.payload:
            raise MaskError("Mask payload is not canonical or has invalid finalization.")
        return Mask(width, height, bytes(raster))
    except MaskError:
        raise
    except Exception as error:
        raise MaskError("Mask payload could not be decoded.") from error


def parse_mask_data(data: str) -> tuple[int, int, str]:
    """Split a SAM `data=H,W,payload` string into `(height, width, payload)`."""
    height, separator, rest = data.partition(",")
    width, separator2, payload = rest.partition(",")
    if not separator or not separator2:
        raise MaskError("Mask data must be H,W,payload.")
    try:
        height_value, width_value = int(height), int(width)
    except ValueError as error:
        raise MaskError("Mask data has non-integer dimensions.") from error
    return height_value, width_value, payload


def _payload_from_mapping(mask: Mapping[str, Any]) -> MaskPayload:
    encoding = str(mask.get("encoding", ""))
    if "data" in mask and "width" not in mask:
        height, width, payload = parse_mask_data(str(mask["data"]))
        return MaskPayload(encoding or _encoding_from_payload(payload), payload, width, height)
    payload = str(mask.get("payload", ""))
    return MaskPayload(
        encoding or _encoding_from_payload(payload),
        payload,
        int(mask.get("width", 0)),
        int(mask.get("height", 0)),
    )


def _encoding_from_payload(payload: str) -> str:
    if payload.startswith("!"):
        return "one_bit"
    if payload.startswith("~"):
        return "lossless"
    return ""


@dataclass(frozen=True, slots=True)
class RLE:
    width: int
    height: int
    counts: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise MaskError("RLE dimensions must be positive.")
        if not self.counts or sum(self.counts) != self.width * self.height:
            raise MaskError("RLE counts do not cover the raster.")


def mask_to_rle(mask: Mask) -> RLE:
    """Row-major run lengths starting with the background run."""
    counts: list[int] = []
    current = 0
    run = 0
    for bit in mask.data:
        if bit != current:
            counts.append(run)
            run = 0
            current = bit
        run += 1
    counts.append(run)
    return RLE(mask.width, mask.height, tuple(counts))


def rle_to_mask(rle: RLE) -> Mask:
    data = bytearray(rle.width * rle.height)
    position = 0
    value = 0
    for count in rle.counts:
        if value:
            data[position : position + count] = b"\x01" * count
        position += count
        value ^= 1
    return Mask(rle.width, rle.height, bytes(data))


def box_to_mask(box: Sequence[float], width: int, height: int) -> Mask:
    """Fill the normalised `[x0, y0, x1, y1]` box; the fallback when no mask arrives."""
    if len(box) != 4:
        raise MaskError("A box needs four coordinates.")
    left = max(0.0, min(1.0, float(box[0])))
    top = max(0.0, min(1.0, float(box[1])))
    right = max(0.0, min(1.0, float(box[2])))
    bottom = max(0.0, min(1.0, float(box[3])))
    data = bytearray(width * height)
    for y in range(height):
        centre_y = (y + 0.5) / height
        if not top <= centre_y < bottom:
            continue
        row = y * width
        for x in range(width):
            centre_x = (x + 0.5) / width
            if left <= centre_x < right:
                data[row + x] = 1
    return Mask(width, height, bytes(data))


def mask_or_box(mask: Mask | None, box: Sequence[float], width: int, height: int) -> Mask:
    if mask is not None:
        return mask
    return box_to_mask(box, width, height)


def mask_iou(left: Mask, right: Mask) -> float:
    if (left.width, left.height) != (right.width, right.height):
        raise MaskError("IoU needs masks with the same dimensions.")
    intersection = sum(1 for a, b in zip(left.data, right.data, strict=True) if a and b)
    union = sum(1 for a, b in zip(left.data, right.data, strict=True) if a or b)
    return intersection / union if union else 1.0


def mask_to_polygon(
    mask: Mask, *, tolerance: float = 1.0, max_points: int = _MAX_POLYGON_POINTS
) -> tuple[Point, ...]:
    """Largest boundary loop, Douglas-Peucker simplified and normalised to the frame."""
    loops = _trace_loops(mask)
    if not loops:
        return ()
    outer = max(loops, key=lambda loop: abs(_signed_area(loop)))
    outer = _open_loop(outer)
    simplified = _simplify(outer, tolerance)
    if len(simplified) > max_points:
        simplified = _resample(simplified, max_points)
    return tuple((x / mask.width, y / mask.height) for x, y in simplified)


def polygon_to_mask(
    polygon: Sequence[Point], width: int, height: int, *, normalised: bool = True
) -> Mask:
    if len(polygon) < 3:
        return Mask(width, height, bytes(width * height))
    points = [(x * width if normalised else x, y * height if normalised else y) for x, y in polygon]
    data = bytearray(width * height)
    for y in range(height):
        scan_y = y + 0.5
        crossings: list[float] = []
        previous = points[-1]
        for current in points:
            x1, y1 = previous
            x2, y2 = current
            if (y1 > scan_y) != (y2 > scan_y):
                crossings.append((x2 - x1) * (scan_y - y1) / (y2 - y1) + x1)
            previous = current
        crossings.sort()
        for index in range(0, len(crossings) - 1, 2):
            start = max(0, math.ceil(crossings[index] - 0.5))
            end = min(width - 1, math.floor(crossings[index + 1] - 0.5))
            for x in range(start, end + 1):
                data[y * width + x] = 1
    return Mask(width, height, bytes(data))


def _trace_loops(mask: Mask) -> list[list[Point]]:
    edges: dict[Point, list[Point]] = {}
    order: list[Point] = []

    def add(start: Point, end: Point) -> None:
        if start not in edges:
            edges[start] = []
            order.append(start)
        edges[start].append(end)

    width, height = mask.width, mask.height
    for y in range(height):
        for x in range(width):
            if not mask.pixel(x, y):
                continue
            if not mask.pixel(x, y - 1):
                add((float(x), float(y)), (x + 1.0, float(y)))
            if not mask.pixel(x + 1, y):
                add((x + 1.0, float(y)), (x + 1.0, y + 1.0))
            if not mask.pixel(x, y + 1):
                add((x + 1.0, y + 1.0), (float(x), y + 1.0))
            if not mask.pixel(x - 1, y):
                add((float(x), y + 1.0), (float(x), float(y)))

    loops: list[list[Point]] = []
    while order:
        start = order[0]
        if start not in edges or not edges[start]:
            order.pop(0)
            continue
        loop = [start]
        current = start
        while True:
            destinations = edges.get(current)
            if not destinations:
                break
            next_point = destinations.pop()
            loop.append(next_point)
            if next_point == start:
                break
            current = next_point
        if start in edges and not edges[start]:
            del edges[start]
        if len(loop) >= 4:
            loops.append(loop)
    return loops


def _open_loop(loop: Sequence[Point]) -> list[Point]:
    points = list(loop)
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()
    return points


def _signed_area(points: Sequence[Point]) -> float:
    total = 0.0
    previous = points[-1]
    for current in points:
        total += previous[0] * current[1] - current[0] * previous[1]
        previous = current
    return total / 2


def _simplify(points: Sequence[Point], tolerance: float) -> list[Point]:
    if len(points) < 3:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        if end <= start + 1:
            continue
        furthest = -1.0
        index = start
        for candidate in range(start + 1, end):
            distance = _point_line_distance(points[candidate], points[start], points[end])
            if distance > furthest:
                furthest = distance
                index = candidate
        if furthest > tolerance:
            keep[index] = True
            stack.append((start, index))
            stack.append((index, end))
    return [point for point, flag in zip(points, keep, strict=True) if flag]


def _point_line_distance(point: Point, start: Point, end: Point) -> float:
    x0, y0 = point
    x1, y1 = start
    x2, y2 = end
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x0 - x1, y0 - y1)
    return abs(dy * x0 - dx * y0 + x2 * y1 - y2 * x1) / math.hypot(dx, dy)


def _resample(points: Sequence[Point], limit: int) -> list[Point]:
    step = len(points) / limit
    return [points[int(index * step)] for index in range(limit)]


@dataclass(frozen=True, slots=True)
class MaskFrame:
    frame: int
    mask: Mask | None = None
    box: tuple[float, float, float, float] | None = None


def fill_short_gaps(frames: Sequence[MaskFrame], *, max_gap: int = 3) -> tuple[MaskFrame, ...]:
    """Copy the nearest mask into missing frames when the gap is <= `max_gap`."""
    ordered = sorted(frames, key=lambda item: item.frame)
    if len(ordered) < 2:
        return tuple(ordered)
    filled: list[MaskFrame] = [ordered[0]]
    for previous, current in itertools.pairwise(ordered):
        missing = current.frame - previous.frame - 1
        if 0 < missing <= max_gap:
            source = previous.mask or current.mask
            if source is not None:
                for index in range(previous.frame + 1, current.frame):
                    filled.append(
                        MaskFrame(index, source, previous.box if previous.mask else current.box)
                    )
        filled.append(current)
    return tuple(filled)


def smooth_masks(frames: Sequence[MaskFrame]) -> tuple[MaskFrame, ...]:
    """Pixel-wise majority over `previous, current, next` when the shapes agree."""
    ordered = sorted(frames, key=lambda item: item.frame)
    smoothed: list[MaskFrame] = []
    for index, frame in enumerate(ordered):
        mask = frame.mask
        if mask is None or index == 0 or index == len(ordered) - 1:
            smoothed.append(frame)
            continue
        before = ordered[index - 1].mask
        after = ordered[index + 1].mask
        if before is None or after is None:
            smoothed.append(frame)
            continue
        shape = (mask.width, mask.height)
        if (before.width, before.height) != shape or (after.width, after.height) != shape:
            smoothed.append(frame)
            continue
        data = bytes(
            1 if (a + b + c) >= 2 else 0
            for a, b, c in zip(before.data, mask.data, after.data, strict=True)
        )
        smoothed.append(MaskFrame(frame.frame, Mask(mask.width, mask.height, data), frame.box))
    return tuple(smoothed)


@dataclass(frozen=True, slots=True)
class CoverageReport:
    span_frames: int
    present_frames: int
    masked_frames: int
    coverage_ratio: float
    mean_area_ratio: float
    largest_gap: int


def coverage_report(frames: Sequence[MaskFrame]) -> CoverageReport:
    if not frames:
        return CoverageReport(0, 0, 0, 0.0, 0.0, 0)
    ordered = sorted(frames, key=lambda item: item.frame)
    span = ordered[-1].frame - ordered[0].frame + 1
    masked = [frame.mask for frame in ordered if frame.mask is not None]
    largest_gap = 0
    for previous, current in itertools.pairwise(ordered):
        largest_gap = max(largest_gap, current.frame - previous.frame - 1)
    return CoverageReport(
        span_frames=span,
        present_frames=len(ordered),
        masked_frames=len(masked),
        coverage_ratio=round(len(masked) / span, 4),
        mean_area_ratio=round(sum(mask.area_ratio for mask in masked) / len(masked), 4)
        if masked
        else 0.0,
        largest_gap=largest_gap,
    )


__all__ = [
    "RLE",
    "CoverageReport",
    "Mask",
    "MaskError",
    "MaskFrame",
    "MaskPayload",
    "box_to_mask",
    "coverage_report",
    "decode_mask",
    "encode_one_bit",
    "fill_short_gaps",
    "mask_iou",
    "mask_or_box",
    "mask_to_polygon",
    "mask_to_rle",
    "parse_mask_data",
    "polygon_to_mask",
    "rle_to_mask",
    "smooth_masks",
]

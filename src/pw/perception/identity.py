"""Track identity: label each non-hand tool/part track once (FR-05, TRD §6.5).

For every non-hand track the perception layer picks up to three crops (area x
sharpness x non-occlusion), sends them in **one** Wonder call with the SOP vocabulary
plus `other`, and turns the per-crop answers into a majority vote. Failures degrade to
`unknown`, never to a guess. Results are cached per track in `identities.json`, so a run
makes at most one call per track.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import math
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image, ImageFilter, ImageStat

from pw.clients.wonder import extract_text

if TYPE_CHECKING:
    from pw.pipeline.concurrency import ModelLimiter

SCHEMA_VERSION = "1.0.0"
PROMPT_VERSION = "identity-v1"
HAND_CONCEPT = "hand"
OTHER_LABEL = "other"
UNKNOWN_LABEL = "unknown"
MAX_CROPS = 3
PADDING_RATIO = 0.10
MIN_CROP_PX = 8

logger = logging.getLogger("pw.perception.identity")

Box = tuple[float, float, float, float]
FrameProvider = Callable[[int], Image.Image | None]
IdentityCaller = Callable[[Mapping[str, Any]], Mapping[str, Any]]


class IdentityError(ValueError):
    """An invalid identity request or response."""


@dataclass(frozen=True, slots=True)
class TrackFrame:
    frame: int
    box: Box
    score: float = 1.0


@dataclass(frozen=True, slots=True)
class TrackObservation:
    track_id: str
    concept: str
    frames: tuple[TrackFrame, ...]

    def __post_init__(self) -> None:
        if not self.frames:
            raise IdentityError(f"track {self.track_id!r} has no frames")


@dataclass(frozen=True, slots=True)
class Crop:
    frame: int
    image: Image.Image
    score: float


@dataclass(frozen=True, slots=True)
class Vote:
    label: str
    count: int

    def to_payload(self) -> dict[str, object]:
        return {"label": self.label, "count": self.count}


@dataclass(frozen=True, slots=True)
class IdentityResult:
    track_id: str
    label: str
    confidence: float
    votes: tuple[Vote, ...]
    crop_frames: tuple[int, ...] = ()

    def to_payload(self) -> dict[str, object]:
        return {
            "track_id": self.track_id,
            "label": self.label,
            "confidence": round(self.confidence, 4),
            "votes": [vote.to_payload() for vote in self.votes],
            "crop_frames": list(self.crop_frames),
        }


@dataclass(frozen=True, slots=True)
class IdentitiesFile:
    identities: tuple[IdentityResult, ...]
    run_id: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "identities": [identity.to_payload() for identity in self.identities],
        }
        if self.run_id is not None:
            payload["run_id"] = self.run_id
        return payload


def box_area(box: Box) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _intersection(left: Box, right: Box) -> float:
    width = max(0.0, min(left[2], right[2]) - max(left[0], right[0]))
    height = max(0.0, min(left[3], right[3]) - max(left[1], right[1]))
    return width * height


def crop_box(box: Box, image: Image.Image, *, padding: float = PADDING_RATIO) -> Image.Image:
    x0, y0, x1, y1 = box
    pad_x = (x1 - x0) * padding
    pad_y = (y1 - y0) * padding
    left = max(0, math.floor((x0 - pad_x) * image.width))
    top = max(0, math.floor((y0 - pad_y) * image.height))
    right = min(image.width, math.ceil((x1 + pad_x) * image.width))
    bottom = min(image.height, math.ceil((y1 + pad_y) * image.height))
    if right <= left or bottom <= top:
        raise IdentityError("track box is empty after padding")
    return image.crop((left, top, right, bottom))


def sharpness(image: Image.Image) -> float:
    """Variance of edge magnitude: flat crops score 0, textured crops score high."""
    edges = image.convert("L").filter(ImageFilter.FIND_EDGES)
    return float(ImageStat.Stat(edges).var[0])


def _occlusion(frame: TrackFrame, others: Sequence[TrackObservation]) -> float:
    own = box_area(frame.box)
    if own <= 0:
        return 0.0
    covered = 0.0
    for other in others:
        for candidate in other.frames:
            if candidate.frame == frame.frame:
                covered += _intersection(frame.box, candidate.box)
    return min(1.0, covered / own)


def select_crops(
    track: TrackObservation,
    *,
    others: Sequence[TrackObservation],
    frame_provider: FrameProvider,
    max_crops: int = MAX_CROPS,
) -> tuple[Crop, ...]:
    candidates: list[Crop] = []
    for frame in track.frames:
        image = frame_provider(frame.frame)
        if image is None:
            continue
        try:
            crop = crop_box(frame.box, image)
        except IdentityError:
            continue
        if crop.width < MIN_CROP_PX or crop.height < MIN_CROP_PX:
            continue
        score = box_area(frame.box) * sharpness(crop) * (1.0 - _occlusion(frame, others))
        candidates.append(Crop(frame=frame.frame, image=crop, score=round(score, 6)))
    candidates.sort(key=lambda crop: (-crop.score, crop.frame))
    return tuple(candidates[:max_crops])


def identity_schema(vocabulary: Sequence[str], count: int) -> dict[str, Any]:
    labels = [*dict.fromkeys(vocabulary), OTHER_LABEL]
    return {
        "type": "object",
        "properties": {
            "crops": {
                "type": "array",
                "minItems": count,
                "maxItems": count,
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string", "enum": labels},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": ["label", "confidence"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["crops"],
        "additionalProperties": False,
    }


def build_payload(
    crops: Sequence[Crop], vocabulary: Sequence[str], *, concept: str
) -> dict[str, Any]:
    if not crops:
        raise IdentityError("identity needs at least one crop")
    labels = ", ".join(dict.fromkeys(vocabulary))
    text = (
        f"These {len(crops)} numbered crops come from one tracked object in a procedure "
        f"video (the tracker called it {concept!r}). Identify the tool or part in each "
        f"crop independently. Choose exactly one label from: {labels}, {OTHER_LABEL}. "
        f"Use {OTHER_LABEL} when none fits. Return one prediction per crop, in image order, "
        "with a confidence from 0 to 1."
    )
    content: list[dict[str, Any]] = [{"type": "input_text", "text": text}]
    for crop in crops:
        buffer = io.BytesIO()
        crop.image.convert("RGB").save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        content.append({"type": "input_image", "image_url": "data:image/png;base64," + encoded})
    return {
        "model": "muse-wonder-1.0",
        "temperature": 0,
        "reasoning": {"effort": "low"},
        "text": {
            "format": {
                "type": "json_schema",
                "name": "track_identity",
                "schema": identity_schema(vocabulary, len(crops)),
                "strict": True,
            }
        },
        "input": [{"role": "user", "content": content}],
    }


def parse_predictions(
    body: Mapping[str, Any], *, vocabulary: Sequence[str], count: int
) -> tuple[tuple[str, float], ...]:
    text = extract_text(body)
    if text is None:
        raise IdentityError("identity response has no text")
    try:
        payload = json.loads(text)
    except ValueError as error:
        raise IdentityError("identity response is not valid JSON") from error
    crops = payload.get("crops") if isinstance(payload, Mapping) else None
    if not isinstance(crops, list) or len(crops) != count:
        raise IdentityError("identity response has the wrong number of predictions")
    allowed = set(vocabulary) | {OTHER_LABEL}
    predictions: list[tuple[str, float]] = []
    for item in crops:
        if not isinstance(item, Mapping):
            raise IdentityError("identity prediction is not an object")
        label = item.get("label")
        confidence = item.get("confidence")
        if not isinstance(label, str) or label not in allowed:
            raise IdentityError(f"identity label is not in the vocabulary: {label!r}")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            raise IdentityError("identity confidence is not a number")
        if not 0.0 <= float(confidence) <= 1.0:
            raise IdentityError("identity confidence is out of range")
        predictions.append((label, float(confidence)))
    return tuple(predictions)


def aggregate_votes(
    predictions: Sequence[tuple[str, float]],
) -> tuple[str, float, tuple[Vote, ...]]:
    if not predictions:
        raise IdentityError("identity needs at least one prediction")
    counts = Counter(label for label, _ in predictions)
    totals: dict[str, float] = {}
    for label, confidence in predictions:
        totals[label] = totals.get(label, 0.0) + confidence
    winner = max(counts, key=lambda label: (counts[label], totals[label]))
    winner_confidence = totals[winner] / counts[winner]
    confidence = (counts[winner] / len(predictions)) * winner_confidence
    votes = tuple(Vote(label=label, count=count) for label, count in counts.items())
    return winner, round(confidence, 4), votes


def unknown_result(track_id: str, crop_frames: Sequence[int] = ()) -> IdentityResult:
    return IdentityResult(
        track_id=track_id,
        label=UNKNOWN_LABEL,
        confidence=0.0,
        votes=(Vote(UNKNOWN_LABEL, 1),),
        crop_frames=tuple(crop_frames),
    )


def identify_track(
    track: TrackObservation,
    *,
    others: Sequence[TrackObservation],
    frame_provider: FrameProvider,
    vocabulary: Sequence[str],
    call: IdentityCaller,
    max_crops: int = MAX_CROPS,
) -> IdentityResult:
    if track.concept == HAND_CONCEPT:
        raise IdentityError("hand tracks are never identified")
    crops = select_crops(track, others=others, frame_provider=frame_provider, max_crops=max_crops)
    if not crops:
        logger.warning("no usable crops for %s; identity unknown", track.track_id)
        return unknown_result(track.track_id)
    try:
        body = call(build_payload(crops, vocabulary, concept=track.concept))
        predictions = parse_predictions(body, vocabulary=vocabulary, count=len(crops))
        label, confidence, votes = aggregate_votes(predictions)
    except Exception as error:  # transport, schema and parse failures degrade
        logger.warning("identity failed for %s: %s", track.track_id, error)
        return unknown_result(track.track_id, [crop.frame for crop in crops])
    return IdentityResult(
        track_id=track.track_id,
        label=label,
        confidence=confidence,
        votes=votes,
        crop_frames=tuple(crop.frame for crop in crops),
    )


def identify_tracks(
    tracks: Sequence[TrackObservation],
    *,
    frame_provider: FrameProvider,
    vocabulary: Sequence[str],
    call: IdentityCaller,
    existing: Mapping[str, IdentityResult] | None = None,
    max_crops: int = MAX_CROPS,
    limiter: ModelLimiter | None = None,
) -> IdentitiesFile:
    """Identify every non-hand track once; cached results are reused without a call."""
    cached = dict(existing or {})
    entries: list[IdentityResult | None] = []
    pending: list[tuple[int, TrackObservation]] = []
    for track in tracks:
        if track.concept == HAND_CONCEPT:
            continue
        previous = cached.get(track.track_id)
        if previous is not None and previous.label != UNKNOWN_LABEL:
            entries.append(previous)
            continue
        entries.append(None)
        pending.append((len(entries) - 1, track))

    def run(item: tuple[int, TrackObservation]) -> tuple[int, IdentityResult]:
        index, track = item
        return (
            index,
            identify_track(
                track,
                others=[other for other in tracks if other.track_id != track.track_id],
                frame_provider=frame_provider,
                vocabulary=vocabulary,
                call=call,
                max_crops=max_crops,
            ),
        )

    if limiter is None:
        completed = [run(item) for item in pending]
    else:
        completed = limiter.map("wonder", run, pending)
    for index, result in completed:
        entries[index] = result

    identities = tuple(entry for entry in entries if entry is not None)
    if len(identities) != len(entries):  # pragma: no cover - guarded by construction
        raise IdentityError("identity fan-out lost a track")
    return IdentitiesFile(identities=identities)


def read_identities(path: Path) -> dict[str, IdentityResult]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    results: dict[str, IdentityResult] = {}
    for item in payload.get("identities", []):
        try:
            votes = tuple(Vote(str(vote["label"]), int(vote["count"])) for vote in item["votes"])
            results[str(item["track_id"])] = IdentityResult(
                track_id=str(item["track_id"]),
                label=str(item["label"]),
                confidence=float(item["confidence"]),
                votes=votes,
                crop_frames=tuple(int(frame) for frame in item.get("crop_frames", ())),
            )
        except (KeyError, TypeError, ValueError):
            continue
    return results


def write_identities(path: Path, identities: IdentitiesFile) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(identities.to_payload(), indent=2), encoding="utf-8")
    return path


__all__ = [
    "HAND_CONCEPT",
    "MAX_CROPS",
    "OTHER_LABEL",
    "PADDING_RATIO",
    "PROMPT_VERSION",
    "SCHEMA_VERSION",
    "UNKNOWN_LABEL",
    "Crop",
    "IdentitiesFile",
    "IdentityCaller",
    "IdentityError",
    "IdentityResult",
    "TrackFrame",
    "TrackObservation",
    "Vote",
    "aggregate_votes",
    "box_area",
    "build_payload",
    "crop_box",
    "identify_track",
    "identify_tracks",
    "identity_schema",
    "parse_predictions",
    "read_identities",
    "select_crops",
    "sharpness",
    "unknown_result",
    "write_identities",
]

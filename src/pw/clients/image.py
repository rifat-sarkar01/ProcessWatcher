"""Muse Image client: text-to-image generation and reference edits (ADR-003)."""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pw.clients.base import ModelClient, Usage
from pw.clients.errors import MalformedResponseError
from pw.clients.pricing import IMAGE_MODEL
from pw.clients.transport import READ_TIMEOUT_S, FilePart

GENERATE_PATH = "/images/generations"
EDIT_PATH = "/images/edits"


@dataclass(frozen=True, slots=True)
class ImageInput:
    data: bytes
    filename: str = "image.png"
    content_type: str = "image/png"

    def to_file_part(self, *, field: str) -> FilePart:
        return FilePart(
            field=field,
            filename=self.filename,
            content=self.data,
            content_type=self.content_type,
        )


@dataclass(frozen=True, slots=True)
class ImageResult:
    images: tuple[bytes, ...]
    body: Mapping[str, Any]
    usage: Usage


class ImageClient(ModelClient):
    model = IMAGE_MODEL

    def generate(
        self,
        prompt: str,
        *,
        n: int = 1,
        timeout_s: float = READ_TIMEOUT_S,
    ) -> ImageResult:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "n": n,
            "response_format": "b64_json",
        }
        body = self._call_json(
            GENERATE_PATH, payload, operation="image.generate", timeout_s=timeout_s
        )
        return ImageResult(images=decode_images(body), body=body, usage=self._usage(body))

    def edit(
        self,
        prompt: str,
        images: Sequence[ImageInput],
        *,
        timeout_s: float = READ_TIMEOUT_S,
    ) -> ImageResult:
        if not images:
            raise ValueError("edit needs at least one reference image")
        fields = {"model": self.model, "prompt": prompt}
        # ADR-003: multipart edits use `image` once, then `image[0]`, `image[1]`, ...
        files = [
            image.to_file_part(field="image" if len(images) == 1 else f"image[{index}]")
            for index, image in enumerate(images)
        ]
        body = self._call_multipart(
            EDIT_PATH,
            fields,
            files,
            operation="image.edit",
            timeout_s=timeout_s,
        )
        return ImageResult(images=decode_images(body), body=body, usage=self._usage(body))

    def _usage(self, body: Mapping[str, Any]) -> Usage:
        data = body.get("data")
        return Usage(images=len(data) if isinstance(data, list) else 0)


def decode_images(body: Mapping[str, Any]) -> tuple[bytes, ...]:
    data = body.get("data")
    if not isinstance(data, list) or not data:
        raise MalformedResponseError("image response has no data items")
    images: list[bytes] = []
    for item in data:
        if not isinstance(item, Mapping) or not isinstance(item.get("b64_json"), str):
            raise MalformedResponseError("image response item has no b64_json")
        try:
            images.append(base64.b64decode(item["b64_json"], validate=True))
        except (binascii.Error, ValueError) as error:
            raise MalformedResponseError("image payload is not valid base64") from error
    return tuple(images)


__all__ = [
    "EDIT_PATH",
    "GENERATE_PATH",
    "ImageClient",
    "ImageInput",
    "ImageResult",
    "decode_images",
]

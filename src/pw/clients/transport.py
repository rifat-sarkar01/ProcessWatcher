"""HTTP transport seam for the model clients.

Clients never touch `httpx` directly: they call a `Transport`, which lets tests inject a
recording fake and keeps the API key inside one place. `HttpxTransport` is the only
object that holds the key; it never logs it and never lets it reach the cache.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from pw.clients.errors import (
    MalformedResponseError,
    MissingKeyError,
    TransportFailure,
    TransportTimeout,
)

DEFAULT_BASE_URL = "https://api.meta.ai/v1"
CONNECT_TIMEOUT_S = 5.0
READ_TIMEOUT_S = 120.0
VIDEO_TIMEOUT_S = 300.0


@dataclass(frozen=True, slots=True)
class RawResponse:
    status: int
    headers: Mapping[str, str]
    content: bytes

    def json(self, *, model: str | None = None) -> Any:
        try:
            return json.loads(self.content)
        except ValueError as error:
            raise MalformedResponseError(
                "response body is not valid JSON", model=model, status=self.status
            ) from error


@dataclass(frozen=True, slots=True)
class FilePart:
    field: str
    filename: str
    content: bytes
    content_type: str = "image/png"


class Transport(Protocol):
    def post_json(
        self, path: str, payload: Mapping[str, Any], *, timeout_s: float
    ) -> RawResponse: ...

    def post_multipart(
        self,
        path: str,
        fields: Mapping[str, str],
        files: Sequence[FilePart],
        *,
        timeout_s: float,
    ) -> RawResponse: ...


class HttpxTransport:
    """Synchronous `httpx` transport with the TRD's connect/read timeouts."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise MissingKeyError("META_API_KEY is not set")
        self._key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client()
        self._owns_client = client is None

    def __repr__(self) -> str:
        return f"HttpxTransport(base_url={self._base_url!r}, api_key='***')"

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> HttpxTransport:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def post_json(self, path: str, payload: Mapping[str, Any], *, timeout_s: float) -> RawResponse:
        return self._request("POST", path, timeout_s=timeout_s, json=dict(payload))

    def post_multipart(
        self,
        path: str,
        fields: Mapping[str, str],
        files: Sequence[FilePart],
        *,
        timeout_s: float,
    ) -> RawResponse:
        multipart = [
            (part.field, (part.filename, part.content, part.content_type)) for part in files
        ]
        return self._request("POST", path, timeout_s=timeout_s, data=dict(fields), files=multipart)

    def _request(self, method: str, path: str, *, timeout_s: float, **kwargs: Any) -> RawResponse:
        timeout = httpx.Timeout(
            timeout_s,
            connect=CONNECT_TIMEOUT_S,
            read=timeout_s,
            write=timeout_s,
            pool=CONNECT_TIMEOUT_S,
        )
        try:
            response = self._client.request(
                method,
                f"{self._base_url}{path}",
                headers={"Authorization": f"Bearer {self._key}"},
                timeout=timeout,
                **kwargs,
            )
        except httpx.TimeoutException as error:
            raise TransportTimeout("request timed out") from error
        except httpx.TransportError as error:
            raise TransportFailure(f"transport failed: {type(error).__name__}") from error
        return RawResponse(
            status=response.status_code,
            headers={key.lower(): value for key, value in response.headers.items()},
            content=response.content,
        )


__all__ = [
    "CONNECT_TIMEOUT_S",
    "DEFAULT_BASE_URL",
    "READ_TIMEOUT_S",
    "VIDEO_TIMEOUT_S",
    "FilePart",
    "HttpxTransport",
    "RawResponse",
    "Transport",
]

"""Typed model clients (live / replay / fake / demo) behind one cost ledger.

Nothing outside this package talks to the Meta Model API. Consumers import a typed
client, hand it a `RunLedger`, and pick a mode: `live` records responses to the cache,
`replay`/`demo` serve them without outbound calls and `fake` uses an injected responder.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pw.clients.base import MODES, FakeResponder, ModelClient, Usage, raise_for_status
from pw.clients.cache import ResponseCache, default_cache_dir
from pw.clients.errors import (
    AuthError,
    BadRequestError,
    CacheMissError,
    ClientError,
    MalformedResponseError,
    MissingKeyError,
    RateLimitError,
    ServerError,
    SpendCapExceeded,
    TransportFailure,
    TransportTimeout,
    UnsupportedModeError,
)
from pw.clients.image import ImageClient, ImageInput, ImageResult
from pw.clients.pricing import ESTIMATED_CALL_USD, IMAGE_MODEL, PRICES, SAM_MODEL, WONDER_MODEL
from pw.clients.retry import RetryPolicy
from pw.clients.sam import SamClient, SamResult
from pw.clients.transport import (
    CONNECT_TIMEOUT_S,
    DEFAULT_BASE_URL,
    READ_TIMEOUT_S,
    VIDEO_TIMEOUT_S,
    FilePart,
    HttpxTransport,
    RawResponse,
    Transport,
)
from pw.clients.wonder import WonderClient, WonderResult, extract_text
from pw.core.ledger import LedgerEntry, RunLedger


@dataclass(frozen=True, slots=True)
class Clients:
    wonder: WonderClient
    image: ImageClient
    sam: SamClient

    def close(self) -> None:
        for client in (self.wonder, self.image, self.sam):
            client.close()


def build_clients(
    *,
    mode: str,
    ledger: RunLedger,
    api_key: str = "",
    cache_dir: Path | None = None,
    transport: Transport | None = None,
    fake: FakeResponder | None = None,
    policy: RetryPolicy | None = None,
) -> Clients:
    if mode == "live" and transport is None:
        transport = HttpxTransport(api_key)
    cache = ResponseCache(cache_dir or default_cache_dir())
    return Clients(
        wonder=WonderClient(
            mode=mode, ledger=ledger, cache=cache, transport=transport, fake=fake, policy=policy
        ),
        image=ImageClient(
            mode=mode, ledger=ledger, cache=cache, transport=transport, fake=fake, policy=policy
        ),
        sam=SamClient(
            mode=mode, ledger=ledger, cache=cache, transport=transport, fake=fake, policy=policy
        ),
    )


__all__ = [
    "CONNECT_TIMEOUT_S",
    "DEFAULT_BASE_URL",
    "ESTIMATED_CALL_USD",
    "IMAGE_MODEL",
    "MODES",
    "PRICES",
    "READ_TIMEOUT_S",
    "SAM_MODEL",
    "VIDEO_TIMEOUT_S",
    "WONDER_MODEL",
    "AuthError",
    "BadRequestError",
    "CacheMissError",
    "ClientError",
    "Clients",
    "FakeResponder",
    "FilePart",
    "HttpxTransport",
    "ImageClient",
    "ImageInput",
    "ImageResult",
    "LedgerEntry",
    "MalformedResponseError",
    "MissingKeyError",
    "ModelClient",
    "RateLimitError",
    "RawResponse",
    "RetryPolicy",
    "RunLedger",
    "SamClient",
    "SamResult",
    "ServerError",
    "SpendCapExceeded",
    "Transport",
    "TransportFailure",
    "TransportTimeout",
    "UnsupportedModeError",
    "Usage",
    "WonderClient",
    "WonderResult",
    "build_clients",
    "extract_text",
    "raise_for_status",
]

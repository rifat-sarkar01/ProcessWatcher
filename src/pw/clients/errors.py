"""Typed errors raised by `pw.clients`; messages are safe to display and log."""

from __future__ import annotations


class ClientError(RuntimeError):
    """Base error for every model-client failure."""

    code = "client_error"

    def __init__(
        self,
        message: str,
        *,
        model: str | None = None,
        attempts: int = 0,
        status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.model = model
        self.attempts = attempts
        self.status = status


class MissingKeyError(ClientError):
    code = "missing_key"


class UnsupportedModeError(ClientError):
    code = "unsupported_mode"


class CacheMissError(ClientError):
    """`replay`/`demo` had no recorded response for the request hash."""

    code = "cache_miss"

    def __init__(self, key: str, *, model: str | None = None) -> None:
        super().__init__(f"no cached response for request {key}", model=model)
        self.key = key


class SpendCapExceeded(ClientError):
    code = "spend_cap"

    def __init__(self, total_usd: float, estimated_usd: float, cap_usd: float) -> None:
        super().__init__(
            f"spend cap {cap_usd:.4f} USD: {total_usd:.4f} spent + "
            f"{estimated_usd:.4f} requested would exceed it"
        )
        self.total_usd = total_usd
        self.estimated_usd = estimated_usd
        self.cap_usd = cap_usd


class TransportTimeout(ClientError):
    code = "timeout"


class TransportFailure(ClientError):
    code = "transport"


class RateLimitError(ClientError):
    code = "rate_limited"

    def __init__(
        self,
        message: str,
        *,
        retry_after_s: float | None = None,
        model: str | None = None,
        attempts: int = 0,
        status: int | None = None,
    ) -> None:
        super().__init__(message, model=model, attempts=attempts, status=status)
        self.retry_after_s = retry_after_s


class AuthError(ClientError):
    code = "auth"


class ServerError(ClientError):
    code = "server"


class BadRequestError(ClientError):
    code = "bad_request"


class MalformedResponseError(ClientError):
    code = "malformed_response"


__all__ = [
    "AuthError",
    "BadRequestError",
    "CacheMissError",
    "ClientError",
    "MalformedResponseError",
    "MissingKeyError",
    "RateLimitError",
    "ServerError",
    "SpendCapExceeded",
    "TransportFailure",
    "TransportTimeout",
    "UnsupportedModeError",
]

"""FastAPI app: public liveness plus the guarded runs API.

`/healthz` is public (TRD §5); every `/runs` route requires `X-Access-Code` and is
rate limited on creation. Uploads are validated by `pw.security` before a fake run
is started in the background. Responses carry the TRD §8 security headers.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from pw.api.errors import install_handlers
from pw.api.routes_events import router as events_router
from pw.api.routes_runs import ApiSettings
from pw.api.routes_runs import router as runs_router
from pw.pipeline.runstore import runs_root
from pw.security.ratelimit import RateLimiter
from pw.security.uploads import UploadCaps

# `04_TRD.md` §8. The API only returns JSON and self-contained artifacts, so no
# external origin and no inline script is ever needed.
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data: blob:; "
        "media-src 'self' blob:; style-src 'self' 'unsafe-inline'"
    ),
}


class SecurityHeadersMiddleware:
    """Pure ASGI so streamed SSE responses keep flowing (no buffering wrapper)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers[name] = value
            await send(message)

        await self.app(scope, receive, send_with_headers)


def create_app(
    *,
    runs_dir: Path | None = None,
    caps: UploadCaps | None = None,
    rate_limiter: RateLimiter | None = None,
) -> FastAPI:
    root = runs_dir if runs_dir is not None else runs_root()
    app = FastAPI(title="Process Watcher", version="0.0.0")
    app.state.settings = ApiSettings(
        runs_dir=root,
        caps=caps or UploadCaps(),
        limiter=rate_limiter or RateLimiter(),
    )
    install_handlers(app)
    app.include_router(runs_router)
    app.include_router(events_router)
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()


__all__ = ["SECURITY_HEADERS", "SecurityHeadersMiddleware", "app", "create_app"]

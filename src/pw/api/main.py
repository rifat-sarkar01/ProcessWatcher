"""FastAPI app: public liveness plus the guarded runs API.

`/healthz` is public (TRD §5); every `/runs` route requires `X-Access-Code` and is
rate limited on creation. Uploads are validated by `pw.security` before a fake run
is started in the background.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from pw.api.errors import install_handlers
from pw.api.routes_events import router as events_router
from pw.api.routes_runs import ApiSettings
from pw.api.routes_runs import router as runs_router
from pw.pipeline.runstore import runs_root
from pw.security.ratelimit import RateLimiter
from pw.security.uploads import UploadCaps


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

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()


__all__ = ["app", "create_app"]

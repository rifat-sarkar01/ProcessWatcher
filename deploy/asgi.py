"""ASGI entry point for the single-container deploy (ADR-004).

`pw.api.main` exposes the API only; the built SPA lives in `web/dist`. Mounting it on
the same FastAPI app keeps the deploy to one container (docs/04_TRD.md D-8). API routes
are registered first, so `/healthz` and `/runs/...` keep precedence over the static mount.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from pw.api.main import create_app

DEFAULT_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"


def web_dist() -> Path | None:
    """Return the built SPA directory, or None when the image has no web build."""
    configured = os.environ.get("PW_WEB_DIST", "").strip()
    candidates = [Path(configured)] if configured else []
    candidates.append(DEFAULT_DIST)
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    return None


def create_deploy_app() -> FastAPI:
    app = create_app()
    dist = web_dist()
    if dist is not None:
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")
    return app


app = create_deploy_app()

__all__ = ["app", "create_deploy_app", "web_dist"]

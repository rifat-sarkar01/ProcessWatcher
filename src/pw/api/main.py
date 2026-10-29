"""FastAPI app: liveness and run listing for the walking skeleton.

Route coverage is T-0.8 only: `/healthz` (public, per TRD §5) and `GET /runs`
listing filesystem runs. Guards, uploads and SSE arrive with T-5.1/T-5.2/T-5.4.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from pw.pipeline.runstore import list_runs, runs_root


def create_app(*, runs_dir: Path | None = None) -> FastAPI:
    root = runs_dir if runs_dir is not None else runs_root()
    app = FastAPI(title="Process Watcher", version="0.0.0")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/runs")
    def runs() -> list[dict[str, object]]:
        return [summary.to_artifact() for summary in list_runs(root)]

    return app


app = create_app()


__all__ = ["app", "create_app"]

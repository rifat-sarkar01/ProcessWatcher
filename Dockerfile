# syntax=docker/dockerfile:1.7
# Single-container deploy (docs/04_TRD.md D-8, ADR-004): API + built web, no model weights.
# The models are remote (ADR-001/002/003); the image needs ffmpeg and Chromium, not a GPU.

FROM node:24-bookworm-slim AS web

WORKDIR /app/web
# Playwright is a dev dependency; the browser bundle is not needed to build the SPA.
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 CI=1
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build


FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PW_CONTRACTS_DIR=/app/contracts \
    PW_RUNS_DIR=/data/runs \
    PW_CACHE_DIR=/data/cache \
    PW_CHROMIUM=/usr/bin/chromium \
    PW_WEB_DIST=/app/web/dist

# ffmpeg/ffprobe for ingest and rendering; Chromium for `pw export --format pdf`;
# util-linux provides setpriv, used by the entrypoint to drop privileges.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        chromium \
        ffmpeg \
        fonts-liberation \
        util-linux \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY contracts ./contracts
COPY config ./config
COPY demo ./demo
RUN uv sync --frozen --no-dev

COPY --from=web /app/web/dist ./web/dist
COPY deploy ./deploy

# The process runs as `pw`; the entrypoint starts as root only to chown the volume.
RUN useradd --create-home --uid 10001 pw \
    && mkdir -p /data/runs /data/cache \
    && chown -R pw:pw /data \
    && sed -i 's/\r$//' /app/deploy/entrypoint.sh \
    && chmod +x /app/deploy/entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"

ENTRYPOINT ["/app/deploy/entrypoint.sh"]
CMD ["uvicorn", "deploy.asgi:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]

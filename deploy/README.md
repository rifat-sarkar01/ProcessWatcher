# Deploying Process Watcher to Fly.io

Host decision and rationale: [`docs/adr/ADR-004-deploy.md`](../docs/adr/ADR-004-deploy.md).
This is the T-7.2 runbook; it is committed ahead of the card so deployment starts the
moment the demo cases and footage exist.

## Pre-deploy checklist

1. **Fix the run mode.** `_execute` in `src/pw/api/routes_runs.py` starts runs with
   `mode="fake"`. A public demo must run `live` (or `demo` for the frozen cases). This is
   a small O3 change; do not deploy a live demo until it lands.
2. **Demo pack.** `demo/cases/` must be populated by T-7.1 if `PW_MODE=demo` is used.
3. **Human approval.** G7 requires explicit approval before the public URL goes live.
4. **Unique app name.** `process-watcher` may already be taken; edit `app` in `fly.toml`.
5. **Secrets in hand.** `META_API_KEY` and `PW_ACCESS_CODE`; never commit them.

## First deploy

```sh
fly auth login
fly apps create process-watcher          # skip if the app already exists
fly volumes create pw_data --size 5 --region iad
fly secrets set META_API_KEY=... PW_ACCESS_CODE=...
fly deploy
curl https://process-watcher.fly.dev/healthz   # {"status":"ok"}
```

The image is built from the repo-root `Dockerfile`; `fly.toml` keeps the Machine always
on (`auto_stop_machines = false`) so judges never hit a cold start.

## Smoke

```sh
curl -fsS https://process-watcher.fly.dev/healthz
curl -fsS -H "X-Access-Code: $PW_ACCESS_CODE" https://process-watcher.fly.dev/runs
```

T-7.2's full smoke (`uv run pw smoke ...`) still has to be written; until then, use the
two requests above plus one end-to-end upload in the browser.

## Operating notes

- **One Machine only.** The run store is a local volume (`/data/runs`) and the app assumes
  a single writer; never scale this service horizontally.
- **Volume ownership.** The container starts as root only long enough to `chown /data`,
  then drops to `pw` via `setpriv` in `deploy/entrypoint.sh`.
- **PDF export** uses the Debian Chromium (`PW_CHROMIUM=/usr/bin/chromium`); the exporter
  already passes `--no-sandbox`.
- **Logs:** `fly logs`; **status:** `fly status`; **console:** `fly ssh console`.
- **Cost:** one 2 GB Machine plus a 5 GB volume, roughly $14/month at list price. Stop the
  Machine with `fly scale count 0` after judging; the volume keeps the runs.

## Known limitations

- Deep links into the SPA (for example a refresh on `/upload`) are not rewritten to
  `index.html`; navigate from `/`. API paths such as `/runs/<id>` are answered by the API.
- The API's SSE stream and 4-minute runs are fine on a normal Machine; this is exactly why
  Fly was chosen over request-scoped containers.

# ADR-004: Deploy host — Fly.io

- **Status:** Accepted (host choice); deployment itself still needs human approval at G7
- **Date:** 2026-11-02
- **Task:** T-7.2 (OPS, serves NFR-05, SUB-01); scaffold pulled forward at the human owner's request
- **Deciders:** O3 (platform), O4 (product)
- **Resolves:** the "Modal / Render / Fly" open item in `docs/04_TRD.md` §10

## Context

T-7.2 needs one non-root container that serves the API, the built web app, the filesystem
run store and a public `/healthz`, deployed before **Nov 4, 12:00 ET**. The plan left the
host open between Modal, Render and Fly, with the choice to be recorded here. No footage is
needed to make the decision, so the scaffold is committed ahead of T-7.2.

The runtime shape constrains the choice more than raw compute does:

- **No GPU is required.** SAM 3.1, Muse Wonder and Muse Image are called through the Meta
  Model API (`ADR-001` Q7, `ADR-002`, `ADR-003`). The host runs Python, ffmpeg and headless
  Chromium (PDF export, `src/pw/report/export.py`), not model weights. GPU support is a
  tie-breaker at most.
- **The run store is a local filesystem** (`runs/<id>/…`, `src/pw/pipeline/runstore.py`), so
  the host needs a persistent volume shared by every request of one instance.
- **Runs are long-lived request work.** A 2-minute clip has a 4-minute latency budget
  (NFR-01) and progress is streamed over SSE; the process must stay warm and accept
  connections for the whole run.
- **One instance is the design.** The store is not shared between machines, and the TRD
  caps concurrent runs at 2 (`04_TRD.md` §4). Horizontal scaling is neither needed nor safe.
- **Demo robustness (NFR-08) forbids cold starts.** The first judge request must not wait for
  a container to boot.
- **Cost is hackathon scale**: a few days of one always-on instance plus a small volume.

Sources read (accessed 2026-11-02):

1. Fly.io resource pricing — <https://docs.fly.io/about/pricing>, <https://fly.io/pricing/>
2. Render free-tier behaviour and pricing — <https://render.com/docs/free>, <https://render.com/pricing>
3. Modal pricing, volumes and cold starts — <https://modal.com/pricing>,
   <https://modal.com/docs/guide/volumes>, <https://modal.com/docs/guide/cold-start>

## Evaluation

| Criterion | Fly.io | Render | Modal |
|---|---|---|---|
| GPU inference | Machines with GPU sizes are offered; not needed here | Not advertised on the plans reviewed; not needed here | Best GPU story; not needed here |
| Cold start | None while a machine stays started (`auto_stop_machines = false`) | Free service sleeps after inactivity; first request takes about a minute | Containers are request-scoped; warm pools/cold-start tuning required |
| Persistent filesystem | Volumes, $0.15/GB-month, mounted into a Machine | Disks, $0.25/GB-month; free plan has no disk | Volumes are write-once/read-many optimised; needs commits and a different I/O discipline |
| Long-lived process + SSE | A normal Machine runs Uvicorn continuously | A normal web service runs continuously on paid plans | Web Functions are request-scoped; SSE and 4-minute runs need a custom wrapper |
| Deploy effort | `fly deploy` builds the committed Dockerfile; secrets via `fly secrets` | Docker deploy, but disk + always-on requires a paid service | Needs a `modal.App` wrapper, volume handling and a different entry point |
| Cost at hackathon scale | ≈$6.70/mo for shared-cpu-1x 1 GB; ≈$13–14/mo for shared-cpu-2x 2 GB, plus ≈$0.75 for a 5 GB volume | $7/mo for 512 MB always-on, plus $0.25/GB disk; 2 GB costs more | $30/mo of free compute, then per-second CPU; cheapest if truly idle |
| Rollback | Redeploy a previous release/image; the volume is untouched | Redeploy a previous deploy | Redeploy a previous app version |

Prices are list-price snapshots from the sources above; re-check before deploying.

## Decision

**Deploy to Fly.io** as a single always-on Machine:

- `shared-cpu-2x`, 2 GB RAM — headroom for ffmpeg cuts, Chromium PDF printing and the
  in-process run store; 1 GB is the floor, 2 GB avoids a demo-time OOM.
- 5 GB volume `pw_data` mounted at `/data`; `PW_RUNS_DIR=/data/runs`,
  `PW_CACHE_DIR=/data/cache`. Five GB holds several 500 MB uploads plus artifacts between
  purges.
- `auto_stop_machines = false`, `min_machines_running = 1` — no cold start during judging.
- One Machine only (no autoscaling): the filesystem store and the 2-run cap assume it.
- Secrets (`META_API_KEY`, `PW_ACCESS_CODE`) come from `fly secrets`, never the image.
- Public HTTPS only; `/healthz` is the Fly health check. No GPU.

**Why not Render:** the free tier's one-minute wake-up violates NFR-08, and the always-on
plan plus disk costs more than Fly at the same memory. **Why not Modal:** its request-scoped
containers and write-once/read-many volumes fight the app's local, long-lived run store;
the wrapper work is larger than the remaining schedule allows, and the GPU advantage buys
nothing because the models are remote.

## Scaffold (committed ahead of T-7.2)

| File | Purpose |
|---|---|
| `Dockerfile` | multi-stage: `npm ci` + `vite build`, then Python 3.12 + `uv sync --frozen --no-dev`, ffmpeg, Chromium, non-root runtime |
| `.dockerignore` | keeps `.git`, `.env`, `runs/`, caches, node_modules, tests, docs and the held-out/bench videos out of the image |
| `fly.toml` | app name, `iad`, 2 GB VM, volume mount, always-on HTTP service, `/healthz` check, non-secret env |
| `deploy/asgi.py` | serves the built SPA from `web/dist` on the same FastAPI app (the API has no static mount of its own) |
| `deploy/entrypoint.sh` | creates/chowns `/data`, then drops from root to the unprivileged `pw` user |
| `deploy/README.md` | the exact T-7.2 commands and the pre-deploy checklist |
| `deploy/ROLLBACK.md` | redeploy the previous release; the volume survives |

The image sets `PW_MODE=live` and `PW_CONTRACTS_DIR=/app/contracts`; `pw` is installed
editable from `/app/src`, which is what `contracts/` and `config/` path resolution expects.

## Open items (must close at T-7.2)

| # | Item | Owner | When |
|---|---|---|---|
| 1 | **The API starts runs with `mode="fake"`** (`src/pw/api/routes_runs.py` `_execute`); a public demo is therefore not a live run yet. Needs a small src change owned by O3 | O3 | T-7.2, before deploy |
| 2 | Deep links to `/runs/<id>` hit the API route instead of the SPA (the SPA mount is a fallback, API routes win). Demo flow starts at `/`, so this is acceptable for submission; fix by moving the SPA behind a prefix if time allows | O3 | T-7.2 |
| 3 | App name `process-watcher` must be globally unique; rename in `fly.toml` if taken | O3 | T-7.2 |
| 4 | Docker and flyctl are not installed on the current workstation; the scaffold is reviewed, not built. First real build happens on the deploy machine | O3 | T-7.2 |
| 5 | Human approves the public deploy before it goes live (G7 extra) | human (O4) | T-7.2 |
| 6 | Fly volume ownership: the entrypoint chowns `/data` at start; verify writes as `pw` on the first deploy | O3 | T-7.2 |

## Consequences

- T-7.2 can start with `fly deploy` as soon as footage/demo cases exist; no host decision
  remains.
- The single-Machine constraint is now explicit: never scale this app horizontally without
  moving the run store to shared storage.
- The public URL needs the access code in the submission text; `/healthz` stays public.

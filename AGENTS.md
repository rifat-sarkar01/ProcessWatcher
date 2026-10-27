# AGENTS.md: Process Watcher
> Read this file and `docs/PROGRESS.md` first. Then execute the current task for your owner row. Do not read other files unless the task's Context pack lists them.

## 1. What this project is
Process Watcher checks a recorded physical procedure against its written SOP and flags missed, out-of-order and wrong-tool steps with timestamps and SAM-annotated real-frame evidence. Models: SAM 3.1 (tracking), Muse Wonder (SOP compile, scoring, verification), Muse Image ("what correct looks like" diagrams). Built for the Meta Global AI Developer Hackathon (submission due Nov 4, 21:00 ET).

## 2. Spec docs (source of truth, in this order of authority)
`docs/01_PRD.md` requirements + acceptance criteria → `docs/05_Schema.md` artifacts, IDs, access rules → `docs/04_TRD.md` stack, APIs, algorithms → `docs/02_AppFlow.md` screens, states, errors → `docs/03_UI_Spec.md` tokens, components → `docs/06_Plan.md` tasks. Never invent requirements, libraries, endpoints, colours or fields that these docs do not define; if something is missing, log it under Discoveries in `docs/PROGRESS.md` and stop.

## 3. Task protocol
1. **Branch isolation:** Before writing any code, create a new branch from `main`: `git checkout -b task/T-x.y-<slug>`. **NEVER work on or commit to `main`**.
2. Take only the task named in your PROGRESS.md row. Read its Context pack, nothing else.
3. Write the named tests first (red), then implement (green). One task = one commit: `T-x.y: <title>`.
4. Touch only the paths in the task's `Touch` list. Never touch another owner's paths or frozen files (`contracts/*` after C1, `config/thresholds.json` after G3, `bench/HELDOUT.lock`, anything under `bench/heldout/*`).
5. Tick the box in `docs/06_Plan.md` only after the "Done when" command passes; add one evidence line to PROGRESS.md (command → result).
6. **Submit Pull Request:** Push your branch and open a Pull Request targeting `main`. Merging to `main` happens strictly via PR review after CI passes.
7. Failed twice? Stop and write the blocker in PROGRESS.md. Three failed attempts in a row = health RED: escalate, do not thrash.
8. Anything out of scope (`docs/01_PRD.md` §4) or on the Parking Lot is never built without human approval.

## 3.1 Git, Branching & Pull Request Protocol
- **Protected `main` branch:** The `main` branch is strictly read-only for agents. Direct commits, direct pushes, or direct merges to `main` are strictly forbidden.
- **One branch per card:** Every task/card (`T-x.y`) must have its own isolated branch created from up-to-date `main`:
  ```bash
  git checkout main
  git pull origin main
  git checkout -b task/T-x.y-<short-slug>
  ```
- **Commit format:** Exactly one commit per task: `T-x.y: <imperative title>` (e.g. `T-0.2: configure uv workspace and linters`).
- **Pull Request creation:** Once "Done when" passes and verification is documented:
  ```bash
  git push -u origin task/T-x.y-<short-slug>
  gh pr create --title "T-x.y: <title>" --body "### Task\nT-x.y\n\n### Touch List Compliance\n...\n\n### Done When Evidence\n...\n"
  ```
- **Never bypass CI / Gate checks:** PR must pass linting, typechecking, tests, and gitleaks before merging.

## 4. Non-negotiable rules
- **Never touch main:** No agent ever commits or pushes directly to `main`. Every card gets a new branch and PR.
- **Evidence is real frames only.** Illustrations carry `kind: illustration` and a burned-in watermark and never appear in evidence lists.
- **Every model call goes through `pw.clients`** (live / replay / fake). No direct HTTP to the Meta API elsewhere. Default to `replay` while developing.
- **Never run any model on `bench/heldout/*`** before T-6.2. Tune on dev only.
- **No secrets** in code, logs, cache files, fixtures or the browser bundle. Run `uv run pre-commit run gitleaks --all-files` before committing.
- **The VLM is not the judge:** compliance decisions come from the deterministic aligner (TRD §6.7), not from model prose.
- Time is seconds (float); frame indices only inside `tracks`; IDs per `docs/05_Schema.md` §2.
- Python: full type hints, ruff + mypy clean. Web: TypeScript strict, tokens from `03_UI_Spec.md`, no raw hex in components.
- No new dependency without a note in PROGRESS.md; never install a release younger than 14 days.

## 5. Owners and paths
O1 perception + evaluation (`src/pw/perception`, `timeline`, `bench`) · O2 reasoning + evidence (`src/pw/sop`, `align`, `illustrate`, `evidence`, `report/build.py`) · O3 platform (`api`, `clients`, `core`, `ingest`, `pipeline`, `security`, `report/export.py`, `.github`, `Dockerfile`, `deploy`, `tests/robustness`, `web/e2e`) · O4 product (`web/src`, `contracts`, `src/pw/data`, `bench` data, docs, `scripts`). One in-progress task per owner.

## 15. Project Commands (Process Watcher)
> Windows-first (PowerShell-safe); every command also works on macOS/Linux. No TRD exists: versions below are pinned by the lockfiles created in T-0.2 / T-0.3. Unknowns are marked `TODO(Q-n)` or "decided by ADR-00x".

### Runtime and tooling
| Item | Value |
|---|---|
| Python | 3.12, managed with `uv` (pin in `pyproject.toml`; lock in `uv.lock`) |
| Node | current LTS (pin in `web/.nvmrc` at T-0.3), npm |
| ffmpeg / ffprobe | on PATH (`winget install Gyan.FFmpeg`); invoked WITHOUT a shell |
| Meta Model API | base URL `https://api.meta.ai/v1`; models `muse-wonder-1.0`, `muse-image-1.0`, SAM 3.1 via the Responses API (request shape and limits: ADR-001) |
| Env vars | `META_API_KEY`, `PW_MODE=live\|replay\|fake\|demo`, `PW_ACCESS_CODE`, `PW_SPEND_CAP_USD` (default 3), `PW_RUNS_DIR`, `PW_DISABLE_ILLUSTRATIONS`, `PW_DISABLE_VERIFIER` |

### Commands
| Purpose | Command |
|---|---|
| Install backend | `uv sync` |
| Install web | `npm --prefix web ci` |
| Dev API | `uv run uvicorn pw.api.main:app --reload --port 8000` |
| Dev web | `npm --prefix web run dev` |
| Run pipeline | `uv run pw run --mode replay --video <file> --sop <file>` (modes: live, replay, fake) |
| Lint / format check | `uv run ruff check .` · `uv run ruff format --check .` · `npm --prefix web run lint` |
| Typecheck | `uv run mypy src` · `npm --prefix web run typecheck` |
| Unit tests | `uv run pytest -m "not integration and not live" -q` · `npm --prefix web run test -- --run` |
| Single test | `uv run pytest tests/<dir>/<file>.py::<test> -x` |
| Integration (replay, free) | `uv run pytest -m integration -q` |
| Live smoke (spends money, manual) | `uv run pytest -m live -q` · `uv run python -m pw.clients.selftest --mode live --models all` |
| E2E | `npm --prefix web exec playwright test` |
| Build | `npm --prefix web run build` · `docker build -t process-watcher .` |
| Migrate up/down | N/A: no database (filesystem run store) |
| Contracts | `uv run pw-data validate-contracts` · `uv run pw-data validate-artifact <file>` · `npm --prefix web run gen:types` |
| Bench data | `uv run pw-data validate --split dev\|heldout` · `uv run pw-data verify-lock` |
| Bench | `uv run pw-bench run --split dev --predictor full\|baseline_a\|baseline_b\|oracle\|empty` · `uv run pw-bench ablate --split dev` · `uv run pw-bench tune --split dev` · `uv run pw-bench sop-eval` · `uv run pw-bench perception-check --split dev` |
| Evidence | `uv run pw verify-evidence runs/<id>/report.json --video <file>` · `uv run pw overlay runs/<id> --out overlay.mp4` |
| Demo | `uv run pw demo-build` · `uv run pw demo-verify` · `PW_MODE=demo uv run pw serve` |
| Secret scan | `uv run pre-commit run gitleaks --all-files` |
| Dependency audit | `uv run pip-audit` · `npm --prefix web audit --audit-level=high` |
| OpenAPI check | `uv run pw openapi --check` |

### Coverage thresholds
`src/pw/align/*`, `src/pw/timeline/*`, `src/pw/bench/metrics.py` ≥ 90% lines · rest of `src/pw/*` ≥ 70% · web: component tests for every UI state; e2e covers journeys. Gates compute coverage on `replay`/`fake` only (never `live`).

### Folder structure
```
contracts/            JSON Schemas (source of truth, DATA) + examples
src/pw/{api,clients,core,ingest,pipeline,security,perception,timeline,sop,align,illustrate,evidence,report,bench,data,demo}/
tests/<module>/       tests mirror src modules; tests/robustness/, tests/fixtures/
web/src/{app,api,ui,features/*,types/generated}/   web/e2e/
bench/{sops,golden,dev,heldout}/   HELDOUT.lock (never edit)
config/thresholds.json  (frozen after G3)
runs/  demo/cases/      (runs/ is git-ignored; demo/cases is committed, checksummed)
docs/{adr,results,security,submission,finals,demo,bench}/  06_Plan.md  PROGRESS.md
```

### Naming and conventions
- Python `snake_case`, 4-space indent, full type hints; React components `PascalCase`, files `kebab-case`.
- Time is always **seconds (float, ms precision)**; frame indices only inside `tracks`. IDs: `stp_01`, `trk_001`, `evt_001`, `dev_001`, `evd_001`.
- Every model call goes through `pw.clients` (live/replay/fake). Never call the Meta API directly from other modules.
- Evidence = real frames only. Illustrations carry `kind: illustration` and a burned-in watermark; never put them in evidence lists.
- One task = one commit: `T-x.y: <imperative title>`. Tick a box only after "Done when" passes and evidence is in PROGRESS.md.

### Stack-specific pitfalls
- **Variable frame rate:** phone video is VFR. Normalise to constant frame rate at ingest and use the PTS-based time map; never compute time as `frame / nominal_fps`.
- **SAM limits:** duration, file size, max objects (some hosts cap at 16) and the mask encoding are decided by ADR-001 (T-0.4). Group concepts to stay under the object cap; keep `hand` in every group.
- **Models:** `muse-wonder-1.0` is in preview and priced per token; `muse-image-1.0` is per image. Always set temperature 0 for judging calls, validate JSON against a schema, and cache by request hash.
- **Cost:** every call writes to the ledger; `PW_SPEND_CAP_USD` aborts a run with a partial valid report. Prefer `replay` for development.
- **Windows:** keep paths short, no shell string-building for ffmpeg, `runs/` and `bench/**/videos/` stay out of git, large clips live in shared storage with sha256 in the manifest.
- **Held-out data:** never run models on `bench/heldout/*` before T-6.2; `verify-lock` must be OK before any tuning.
- **Licence:** SAM 3.1 weights/materials fall under the SAM License; acknowledge in README. Deployment host, access-code handling and licence choice: `TODO(Q-5)` (decided by T-0.1 and ADR-004).

### Verify command per track
| Track | Verify |
|---|---|
| BE | `uv run pytest tests/<module> -q` + `uv run mypy src` |
| ML | `uv run pytest tests/<module> -q` + `uv run pw-bench <check>` named in the task |
| FE | `npm --prefix web run test -- --run <path>` + typecheck + lint |
| DATA | `uv run pw-data validate-contracts` / `validate --split <s>` / `verify-lock` |
| OPS | CI green from a clean clone; `curl <url>/healthz` |
| SEC | `uv run pytest tests/security -q` + audits + gitleaks |
| QA | `uv run pytest tests/robustness -q` · `npm --prefix web exec playwright test -- --repeat-each 3` |
| DOC | `uv run python scripts/readme_check.py` + the file-content check in the task |

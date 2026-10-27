# 04_TRD.md: Process Watcher · Technical Requirements Document
> Layer 02 · v1.0 · 2026-10-25 · Locks the stack, APIs, algorithms and engineering rules so the coding agent never guesses. Requirement IDs: `01_PRD.md`. Schemas: `05_Schema.md`. Anything marked **ADR-00x** is decided by a spike task and recorded there; until then the stated default holds.

## 1. Decisions (locked unless an ADR amends them)
| # | Decision | Why |
|---|---|---|
| D-1 | **VLM supplies likelihoods; a deterministic aligner decides.** | Explainable, unit-testable, calibrated abstention (FR-06/07) |
| D-2 | **Evidence is real frames only**; illustrations carry `kind: illustration` and a burned-in watermark. | Integrity story (FR-09/10, OOS-8) |
| D-3 | **No database.** Filesystem run store with JSON artifacts. | 10-day build, single container, nothing to migrate; schema in `05_Schema.md` |
| D-4 | **Stage artifacts are content-hash cached;** every model call goes through one client with `live / replay / fake` modes. | Cost control, deterministic tests, offline demo (NFR-02/06/08) |
| D-5 | **SSE, not WebSocket,** for progress. | One-way, simple, proxy-friendly |
| D-6 | **Tool identity is classified once per SAM track,** not per frame. | Persistent IDs → ~10–50× fewer model calls |
| D-7 | **Time is seconds (float, ms precision);** frames appear only inside `tracks`. | Avoids VFR bugs |
| D-8 | **Single container** serves API + built web; deploy host chosen in ADR-004. | Simplicity, rollback = previous image |
| D-9 | **Soft ordering constraints** in alignment (penalties, not hard rules). | Lets strong evidence reveal out-of-order/missed steps |
| D-10 | **No vendor SDK:** plain `httpx` against OpenAI-compatible JSON. | Full control of retries, caching, redaction |

## 2. Stack and version policy
Exact pins live in the lockfiles (`uv.lock`, `web/package-lock.json`) created by T-0.2 / T-0.3; the lockfile is the source of truth. **Rules:** never install a release published in the last 14 days; no deprecated APIs (listed per row); record the resolved version of each row in `AGENTS.md` §15 after install.

| Layer | Choice | Constraint at install | No-deprecated rule |
|---|---|---|---|
| Language | Python | 3.12.x | Type hints everywhere; `from __future__ import annotations` not required |
| Package mgr | uv | current stable | lockfile committed |
| API | FastAPI + Uvicorn | current stable, < 1.0 | `lifespan` context, not `on_event` |
| Models/validation | Pydantic | v2 | `model_validate`, `model_dump` (no v1 API) |
| HTTP client | httpx | current stable | async client, explicit timeouts |
| SSE | sse-starlette | current stable | |
| Numerics | NumPy, SciPy (`linear_sum_assignment`) | current stable | |
| Vision | opencv-python-headless, Pillow, imagehash | current stable | encode video with ffmpeg, not OpenCV writers |
| PDF | PyMuPDF | current stable | |
| Schema | jsonschema (2020-12) | current stable | |
| Media | ffmpeg / ffprobe | on PATH, ≥ 6 | invoked without a shell |
| Python QA | ruff, mypy, pytest, pytest-cov, hypothesis, pip-audit, pre-commit (gitleaks) | current stable | |
| Frontend | React | 19.x | function components + hooks only |
| | TypeScript | 5.x, `strict: true` | |
| | Vite | current stable | |
| | Tailwind CSS | current major at install | tokens from `03_UI_Spec.md` |
| | Vitest + Testing Library, Playwright, axe-core | current stable | |
| | lucide-react, json-schema-to-typescript | current stable | |
| Fonts | Inter, JetBrains Mono (OFL) bundled locally | | no external font requests |
| CI | GitHub Actions | | |
| Container | python slim base + ffmpeg, non-root | | |

## 3. System architecture
```
Browser (React) ──HTTPS──► FastAPI app ──► Pipeline orchestrator ──► stages (pure modules)
        ▲  SSE progress        │                   │                       │
        └──────────────────────┘                   ▼                       ▼
                                          Run store (filesystem)     pw.clients ──► Meta Model API
                                          runs/<run_id>/…            (live | replay | fake)
```
- **Process model:** one Uvicorn process; runs execute as `asyncio` tasks (max `PW_MAX_CONCURRENT_RUNS`, default 2; others queue). CPU/IO-heavy work (ffmpeg, mask decode, rendering) runs in a bounded `ProcessPoolExecutor` (default 2 workers).
- **Stage DAG (12 stages):** `ingest → sop_compile → perceive → timeline → identify → score → align → verify → evidence → illustrate → report → done`. `sop_compile` and `ingest` run in parallel; `evidence` and `illustrate` run in parallel after `verify`.
- **Caching:** each stage output is stored under `runs/<id>/stages/<stage>.json` with a key `sha256(stage_version ‖ input hashes ‖ config hash)`. A rerun with the same key is a no-op. Model-call responses are additionally cached by request hash in `PW_CACHE_DIR` (record in `live`, serve in `replay`).
- **Modes (`PW_MODE`):** `live` real API · `replay` cached real responses (error on cache miss) · `fake` hand-made fixtures for unit tests · `demo` frozen cases served read-only, zero outbound calls.
- **Failure policy:** a failing stage retries per client policy; on exhaustion it is marked `failed`, downstream stages that cannot run are `skipped`, and `report` still assembles a valid degraded report (`status: partial`). Spend cap or invalid media → `failed` before `align`.

## 4. Meta Model API integration (`pw.clients`)
Base URL `https://api.meta.ai/v1` (OpenAI-compatible request formats). Key from `META_API_KEY` (env only).

| Model | ID | Interface | Use | Notes |
|---|---|---|---|---|
| Muse Wonder | `muse-wonder-1.0` | chat/completions-style, text + image + video input, JSON/tool output | SOP compile, segment scoring, identity, verifier, explanations, illustration QA | In preview; ~1M-token context; priced per token ($4 in / $20 out per 1M at last check). Set temperature 0 for judging calls |
| Muse Image | `muse-image-1.0` | `/v1/images/generations`, `/v1/images/edits` (edit supports multi-image composition) | Illustrations | $0.01 per image at last check; best mode (edit-with-reference vs generate) decided by ADR-003 |
| SAM 3.1 | via the Responses API on the same base URL | video + text prompt(s) → detections, masks, tracks with persistent IDs | Perception | **Request/response shape, mask encoding, max duration/size/objects: ADR-001.** Open weights exist; self-hosting is the fallback |

**Client rules (all in `pw.clients`):** connect timeout 5 s; read timeout 120 s (video calls 300 s); ≤ 3 retries with exponential backoff + jitter (base 1 s, cap 20 s) on timeout/5xx/429, honouring `Retry-After`; JSON responses validated against Pydantic models, with a single repair re-ask on schema failure; every call records `{model, tokens_in, tokens_out | images | sam_units, usd, latency_ms, cache_hit}` to the run ledger; `Authorization` is redacted from logs and never written to cache files; global concurrency limits per model (default SAM 4, Wonder 4, Image 2; ADR-001/002 may lower them).

## 5. REST API (locked; OpenAPI exported to `openapi.json`)
All routes except `/healthz` and `/demo/*` require header `X-Access-Code`. Error shape: `{"error":{"code":"E-xx","message":"…"}}`.

| Method · Path | Purpose | Success | Errors |
|---|---|---|---|
| `GET /healthz` | Liveness | 200 `{"status":"ok"}` | n/a |
| `POST /sop/compile` | Compile preview. Body: `{sop_text}` or multipart `sop` file | 200 `{step_graph, vocabulary, warnings[]}` | 401, 413, 415, 422 (E-04) |
| `POST /runs` | Start a run. Multipart: `video`, `sop` (file) or `sop_text`, optional `step_graph` (JSON override) | 202 `{run_id, status}` | 401, 413 (E-03), 415 (E-01), 422 (E-02/E-04), 429 (E-05/E-06) |
| `GET /runs` | List recent runs | 200 `[{run_id,status,created_at,cost_usd}]` | 401 |
| `GET /runs/{id}` | Status, stage table, cost, manifest summary | 200 | 401, 404 (E-13) |
| `POST /runs/{id}/cancel` | Cancel | 202 | 401, 404, 409 |
| `GET /runs/{id}/events` | SSE progress | 200 `text/event-stream` | 401, 404 |
| `GET /runs/{id}/report` | `report.json` | 200 | 401, 404, 409 while running |
| `GET /runs/{id}/report.html` · `.pdf` | Export | 200 | 401, 404, 409, 500 (E-11) |
| `GET /runs/{id}/artifacts/{path}` | Frames, clips, tracks, video (HTTP Range) | 200/206 | 401, 404, 416 |
| `PATCH /runs/{id}/review` | `{deviation_id, decision: accepted\|dismissed, note?}` | 200 `review.json` | 401, 404, 422 |
| `GET /demo/cases` · `GET /demo/cases/{id}/…` | Frozen offline cases (no code needed) | 200 | 404 |

**SSE events:** `stage` `{stage,status:pending|running|done|failed|skipped,pct,elapsed_s,cost_usd}` · `warning` `{stage,message}` · `done` `{status}` · `error` `{code,message}` · `heartbeat` every 15 s. Late joiners receive the full event history first.

## 6. Pipeline stage specifications
Each stage is a pure module: `run(inputs, config, client) → artifact`. Inputs/outputs are contract-validated (`05_Schema.md`).

### 6.1 `ingest` (FR-01)
ffprobe → reject if no video stream, duration > 180 s, size > 500 MB, dims > 3840×2160. Normalise with ffmpeg to **constant frame rate** (`analysis_fps`, default 15), height ≤ 720, yuv420p, H.264, rotation applied; compute `sha256(source)`, build the frame↔time map from PTS (never `frame/fps`). Output `ingest.json` + `analysis.mp4`.

### 6.2 `sop_compile` (FR-02)
Wonder, strict JSON → `step_graph` (`05_Schema.md` §3). Rules: every tool/part string must occur in the SOP text (case/plural-normalised) or the item is dropped with a warning; `critical` set only on explicit cues (must, never, warning, caution, critical, ensure); ordering `strict` by default, `unordered_group` only when the SOP says "in any order"/"either"; `vocabulary.sam_concepts` = unique generic noun phrases (tools, parts, zones) ≤ 24, always including `hand`. ≤ 2 repair re-asks.

### 6.3 `perceive` (FR-03)
1. **Chunk plan** from ADR-001 limits: default 20 s chunks, 2 s overlap.
2. **Concept groups:** split `sam_concepts` into groups ≤ the object cap; `hand` is in every group.
3. **Call** SAM per chunk × group → per-chunk raw tracks (`stages/tracks_raw/chunk_k.json`), resumable.
4. **Stitch:** per concept, match tracks across the overlap with the Hungarian algorithm on mask IoU (cost = 1 − IoU, accept if IoU ≥ 0.3 and centroid displacement plausible); re-associate after gaps ≤ 3 s using HSV colour-histogram similarity ≥ 0.6; never merge different concepts.
5. **Mask utilities:** decode per ADR-001; RLE ↔ polygon; Douglas–Peucker simplification (1.5 px at 720p); median smoothing over 3 frames; gap-fill ≤ 3 frames; box fallback when masks are unavailable.
Output `tracks.json`. Quality check: fragmentation ratio (global tracks ÷ GT instances) ≤ 1.5; hand coverage ≥ 90% of frames.

### 6.4 `timeline` (FR-04)
Per frame features: **contact** = overlap of the hand mask dilated by `d = 0.02·diag` with the object mask (area ratio over the object), fallback box IoU; **proximity** = min mask distance ÷ hand-box diagonal; **velocity** = centroid speed ÷ frame diagonal.
Hysteresis: enter hold when contact ≥ 0.30 for ≥ 3 frames; exit when < 0.10 for ≥ 5 frames; ignore holds < 0.4 s.
Events: `hold_start/end` (hand, object), `contact_start/end` (tool, part, while held), `move` (object displacement ≥ 0.06·diag within 0.5 s), `enter/exit` (object centroid enters a tracked zone concept mask). Debounce: merge same-type events closer than 0.3 s. Each event carries `tracks[]`, `t_start`, `t_end`, `confidence = mean(score) × coverage`.
**Segmentation:** change-points at hold/contact boundaries and idle gaps > 2 s; min 1 s (merge), max 20 s (split); each segment lists `salient_tracks` and `event_ids`.

### 6.5 `identify` (FR-05)
For each non-hand track: choose the top-3 frames by `area × sharpness × (1 − occlusion)` → crop (padded 10%) → Wonder with the SOP vocabulary list + `other` → strict JSON `{label, confidence}`; majority vote over crops; track-level `identity = {label, confidence, votes}`; `unknown` on failure. One call per track, cached.

### 6.6 `score` (FR-06)
Per segment, Wonder receives: up to 4 **set-of-mark keyframes** (SAM masks with numbered labels, rendered by `evidence/render.py`), the segment's events as text (`t, type, track labels`), and the step list (`id, text, tools, parts`). Strict JSON out:
```json
{"segment_id":"seg_012","step_probs":{"stp_01":0.02,"stp_05":0.88,"none":0.10},
 "observed_tools":[{"track":"trk_007","label":"Phillips screwdriver","confidence":0.9}],
 "rationale_short":"Hand holds screwdriver at the lower-left screw."}
```
Probabilities are renormalised (sum 1 ± 0.02 tolerated). Batch ≤ 6 segments per call when prompts fit the token budget (default 24k input tokens). Failure → uniform distribution + `scorer_unavailable` flag on the segment.

### 6.7 `align` (FR-06) — constrained decoding
Let segments `i = 1…N`, steps `j = 1…K` plus `0 = none`, likelihood matrix `P[i][j]` from §6.6. Each step has an order rank `o(j)` (steps in the same `unordered_group` share a rank) and a critical flag `c_j`.
Decode `a_1…a_N` minimising
```
J = Σ_i −log(P[i][a_i] + ε)  +  Σ_i T(ℓ_{i-1}, a_i)
```
where `ℓ` is the last non-`none` step before `i` (DP state `(i, a_i, ℓ)`; N ≤ 300, K ≤ 20 → ≤ 2M states).
Transition cost `T(ℓ, k)` for `k ≠ 0`: `0` if `o(k) = o(ℓ)` or `o(k) = o(ℓ)+1`; **skip** `λ_skip(c)·(Σ criticality weight of ranks jumped)` for forward jumps; **back** `λ_back + 0.5·(o(ℓ) − o(k))` for backward jumps; `none` transitions are free. Defaults: `ε = 1e-3`, `λ_skip = 1.5` (3.0 when a skipped step is critical), `λ_back = 2.0`.
Post-processing: merge consecutive segments with the same step into a `step_interval`; steps with no interval are *missed candidates*.
**Counterfactual margin** for a candidate finding: re-decode with the finding forbidden (missed → force step `j` into its best location; out-of-order → infinite cost on backward jumps among the involved steps) and set `Δ = J_forced − J_best`. `confidence = σ(Δ / τ_T)`, `τ_T = 2.0`. This is the "second-best path" margin and what turns weak evidence into `needs_review`.
Domain guard: `coverage = (# steps with interval and mean P ≥ 0.4) / K`; if `coverage < 0.3` or `J_best/N > τ_domain` → `procedure_not_recognized`.

### 6.8 `deviations` (inside `align`) (FR-07)
- **missed(j):** no interval for `j` **and** `max_i P[i][j] < τ_miss (0.25)`.
- **out_of_order:** take first-interval start times of assigned steps, order by time, compute the **longest increasing subsequence** of ranks (non-decreasing within unordered groups); steps outside the LIS are out of place; each yields a deviation with its own interval and `relates_to` = the step it should follow.
- **wrong_tool(j):** during `j`'s interval, held tools (from `hold` events + track identity) exclude every required tool of `j` for ≥ 50% of contact time **and** the held tool's identity ∈ vocabulary with confidence ≥ 0.6 (identity `unknown` never flags).
- Severity: `high` if the step is critical, else `medium`; `low` is unused in the MVP.
- Every deviation must carry `step_id`, `t_start`, `t_end`, ≥ 1 `track_ids` (missed: the hands/tracks active in the gap window), and `margin`/`confidence`. Duplicate steps are not a deviation type (A-9).
Status rule: `flagged` if `confidence ≥ τ_flag (0.7)` and verifier agrees; `needs_review` if `τ_review (0.4) ≤ confidence < τ_flag` or the verifier disagrees; below `τ_review` → `dropped` (counted in the manifest).

### 6.9 `verify` (FR-08)
- **missed:** Wonder receives the **video clip of the gap window** (plus 2 s margins) and the step text: "Did step X occur? Cite times." (`occurred: bool`, `times`). `occurred=true` → drop; `false` → raise confidence; unsure → `needs_review`.
- **wrong_tool / out_of_order:** independent second look with different framing (2 set-of-mark frames at interval start/mid + question phrased about the *required* tool/order). Disagreement → `needs_review`.
- `PW_DISABLE_VERIFIER=1` skips and marks `verifier_unavailable`.
**Explanation:** Wonder fills a constrained template; validator accepts only if length ≤ 40 words, ≤ 2 sentences, every `mm:ss` within ±0.5 s of data, every tool name ∈ vocabulary; ≤ 2 retries, then the template text.

### 6.10 `evidence` (FR-09)
For each deviation choose 2–4 frames: score `= 0.4·area_norm + 0.3·sharpness_norm + 0.3·(1 − occlusion)`, frames ≥ 0.5 s apart. Strategies — missed: frames bracketing the gap + the busiest frame inside it; out-of-order: one frame of each swapped step; wrong_tool: frames with the wrong tool in hand. Render with masks, labels, timestamp burn-in from the **source-resolution** frame when available (else analysis video). Clip: 3–5 s mp4 with overlay.
**Provenance:** `evidence_manifest.json` entry per item `{evidence_id, source_sha256, frame_index, t, render_version, params_hash, output_sha256, phash}`. `pw verify-evidence` re-renders from the source and passes when `Hamming(phash) ≤ 4`.

### 6.11 `illustrate` (FR-10)
One diagram per flagged step (dedupe by `step_id`; skip `needs_review` unless `PW_ILLUSTRATE_REVIEW=1`).
Prompt template:
```
Technical schematic, flat vector style, white background, thin dark lines, no people, no faces.
Show the CORRECT execution of: "{step_text}". Required tool: {tool}. Highlight: {part}.
Use text labels only from this list: {allowed_labels}.
```
Mode per ADR-003 (default: edit with the annotated real frame as layout reference). Burn in the watermark `AI ILLUSTRATION · NOT EVIDENCE` (not configurable). **QA loop:** Wonder reviews → `{matches_step, correct_tool_shown, text_legible, hallucinated_labels[], people_visible, verdict, reason}`; pass requires all good; ≤ 2 regenerations; then fallback `illustration_unavailable` with the reason. `PW_DISABLE_ILLUSTRATIONS=1` skips.

### 6.12 `report`
Join everything into `report.json` (`05_Schema.md` §8): status, SOP, alignment lanes, deviations with evidence and illustrations, manifest (model IDs, versions, thresholds hash, input hashes, costs, mode, degraded stages). Builder enforces contract invariants (`05_Schema.md` §11) and rejects illustrations in `evidence[]`. HTML export is self-contained (inline CSS, base64 images, no `src="http`); PDF via headless Chromium print.

## 7. Configuration (`config/thresholds.json`, frozen after G3)
```json
{"schema_version":"1.0.0",
 "analysis_fps":15,
 "chunk":{"seconds":20,"overlap_seconds":2},
 "timeline":{"contact_enter":0.30,"contact_exit":0.10,"enter_frames":3,"exit_frames":5,"min_hold_s":0.4,"move_disp":0.06,"idle_gap_s":2.0,"seg_min_s":1.0,"seg_max_s":20.0},
 "align":{"eps":0.001,"lambda_skip":1.5,"lambda_skip_critical":3.0,"lambda_back":2.0,"tau_T":2.0,"domain_coverage_min":0.3,"domain_cost_max":null},
 "deviation":{"tau_miss":0.25,"tau_flag":0.7,"tau_review":0.4,"wrong_tool_conf":0.6},
 "limits":{"max_duration_s":180,"max_mb":500,"spend_cap_usd":3.0,"max_concurrent_runs":2}}
```
`T-3.10` tunes `deviation.*` and `align.lambda_*` on **dev only**; the file's sha256 is recorded in every manifest. Defaults above are starting points.

## 8. Security (NFR-05)
- Secrets only via env; `.env` git-ignored; gitleaks in pre-commit and CI; `Authorization` redacted in logs; keys never reach the browser.
- Access: constant-time compare of `X-Access-Code`; per-IP token bucket (default 30 req/min, burst 10); demo routes are read-only.
- Uploads: magic-byte sniffing, extension allowlist, size/duration/resolution caps, sanitised filenames, stored under `runs/<id>/input/` with random names, ffprobe/ffmpeg via argument lists (no shell), processing in a temp dir with a wall-clock timeout.
- Serving: artifact paths resolved against an allowlist under the run directory; traversal tests; `Content-Type` fixed by extension; `X-Content-Type-Options: nosniff`; `Referrer-Policy: no-referrer`; CSP `default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; style-src 'self' 'unsafe-inline'` (tightened if Tailwind allows).
- Privacy: videos retained 24 h then purged (demo cases exempt); no identification or scoring of people; operator names exist only in bench metadata, never in reports; evidence may show hands/tools only by design (no face prompts; face blur is a Parking Lot item).
- Model output is data: never executed, never used to build paths or shell strings.

## 9. Observability, cost, performance
- **Logs:** structured JSON with `request_id`, `run_id`, `stage`, `duration_ms`, `cost_usd`; levels INFO default; no media bytes.
- **Ledger:** `runs/<id>/ledger.json` (per call) rolled up in the manifest; spend cap checked before each call (concurrency-safe).
- **Budgets (targets, re-baselined by ADRs):** per video-minute ≤ $1.00 → SAM ≤ $0.30, Wonder ≤ $0.60, Image ≤ $0.05, slack $0.05.
- **Latency budget for a 2-min clip:** ingest 15 s · SAM 90 s (≤ 4 parallel chunks) · timeline 5 s · identify 20 s · score 45 s · align 1 s · verify 30 s · evidence ∥ illustrate 30 s · report 5 s → ≤ 4 min wall with overlaps.

## 10. Evaluation spec (FR-13, NFR-07)
- **Ground truth (`bench/**/gt/*.yaml`):** per clip `compliant`, `steps[{id,t_start,t_end}]`, `deviations[{type,step_id,t_start,t_end}]`, `instances{concept:count}`, `operator`, `camera`.
- **Matching:** one-to-one greedy by temporal overlap; a prediction matches a GT deviation when `type` and `step_id` are equal and intervals overlap or lie within ±2.0 s. Only `flagged` predictions count as positives; `needs_review` are reported separately.
- **Metrics:** per-type and overall P/R/F1 · false flags per compliant clip · timestamp MAE on matched · step frame-accuracy · cost and latency per video-minute · `needs_review` rate · 95% bootstrap CIs (1000 resamples over clips).
- **Predictors:** `oracle`, `empty`, `full`, `baseline_a` (Wonder with raw video + SOP), `baseline_b` (Wonder with uniformly sampled keyframes, no SAM), plus ablation switches (`no_aligner` greedy argmax, `no_verifier`, `no_identity_vote`).
- **Protocol:** thresholds tuned on **dev only**; `bench/HELDOUT.lock` committed before tuning; held-out run once on the release candidate (`rc1`); a second run needs a logged reason.
- **Perception check:** hand coverage ≥ 90%, fragmentation ≤ 1.5, pick-up events inside GT step windows ±2 s ≥ 80%.

## 11. Testing strategy
| Level | Tool | Notes |
|---|---|---|
| Unit | pytest + hypothesis | Pure modules (`timeline`, `align`, `bench.metrics`) ≥ 90% coverage; property tests: aligner output ordered, ids unique, determinism |
| Contract | jsonschema | Examples valid, negatives rejected; illustration in `evidence[]` rejected |
| Client | pytest with fake transport | Retry/backoff/timeout/redaction |
| Integration | pytest `-m integration` in `replay` | Real responses recorded once; free and deterministic |
| Golden image | imagehash | pHash distance ≤ 4 for renders |
| Component | Vitest + Testing Library | Every UI state in `02_AppFlow.md` §7 |
| a11y | axe | 0 serious/critical on 4 routes |
| E2E | Playwright (`replay` backend) | `--repeat-each 3` |
| Robustness / failure injection | pytest | VFR, shake, low light, occlusion, long clip, mismatched SOP; 429/5xx/timeouts/malformed JSON |
| Live smoke | `pytest -m live` | Manual, spends money |
Markers: `unit`, `integration`, `live`. CI runs everything except `live`.

## 12. Repo structure, conventions, CI/CD
Structure and commands: `AGENTS.md` §15. Conventions: one task = one commit (`T-x.y: title`); modules import models only via `pw.clients`; no module reads env directly except `pw.core.config`; every public function typed; no `print` (use logger); IDs and time formats per `05_Schema.md`.
**CI (GitHub Actions):** backend lint/type/unit/integration(replay) · web lint/type/test/build · gitleaks · skeleton `pw run --mode fake` · `verify-lock` if the lock exists · audits (non-blocking until G6, blocking after). **Release:** tag `v0.<n>.0` at each gate, `rc1` at D8 start, `v1.0.0` at submission; deploy = build image → push → host deploy (ADR-004); rollback = redeploy previous tag.

## 13. ADR register
| ADR | Decided by | Question |
|---|---|---|
| ADR-000 | T-0.1 | Official-rules constraints (deliverables, video limit, licence, pre-existing work, deadlines in UTC) |
| ADR-001 | T-0.4 | SAM call shape, mask encoding, limits, ID persistence, $/min, API vs self-hosted |
| ADR-002 | T-0.5 | Wonder video/image limits, JSON validity, variance, latency/cost, parallelism |
| ADR-003 | T-0.6 | Muse Image best mode, label legibility, consistency, cost |
| ADR-004 | T-7.2 | Deploy host (Modal / Render / Fly) |

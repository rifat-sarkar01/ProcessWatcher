# PROGRESS.md: agent handoff ledger (keep under 60 lines; prune at every gate)
> Read AGENTS.md and this file, then execute the current task for YOUR owner row. Read only that task's Context pack from docs/06_Plan.md.
> Clock: kickoff Mon Oct 26 · hard internal deadline Nov 4 12:00 ET · official deadline Nov 4 21:00 ET (= Nov 5 02:00 UTC)

## Now (one row per owner; one task in progress per owner)
| Owner | Track | Current task | Status | Branch / last green commit |
|---|---|---|---|---|
| O3 | BE | T-5.4 · SSE progress stream | done | task/T-5.4-sse-progress |
| O4 | FE | T-6.7 · State, accessibility and projector polish | done | 18b072a (merged) |
| O1 | ML | T-2.8 · Candidate action segmentation | done | task/T-2.8-segments |
| O2 | ML | T-3.8 · Grounded explanation writer | done | task/T-3.8-explanation-writer |
Current phase: P0/P1 + early P2/P3/P5/P6 · C1 frozen (`contracts-v1`) · **CI gates every push and PR** · 33/74 cards [x]
Micro-plan (M tasks only, 3–6 lines):
- T-3.8's validator/retry/fallback are done behind a `Writer` callable; T-3.9 must pass a `pw.clients` writer and feed the result into `build_report(explanations=...)`.
- T-2.6 events and T-2.8 segments now emit the full contract-valid `timeline.json` (events + non-overlapping 1–20 s activity segments); T-3.4 scoring is the next consumer once `META_API_KEY` lands.
- Still blocked: T-2.2/T-2.4/T-2.7/T-3.4 on ADR-001/002 + `pw.clients`; T-3.7/T-3.8 on Wonder; T-4.3/T-4.4 on Muse Image/Wonder; T-3.12 on T-0.5/T-1.7.
- Pull-forwards are logged in `06_Plan.md` §7; latest is T-0.8 before T-0.7 (human-approved 2026-10-29: build every key-free card now).

## Last 5 completed (newest first)
| Task | Commit | Evidence (command → result) | Date |
|---|---|---|---|
| T-5.4 SSE progress: guarded `GET /runs/{id}/events` streaming `stage` done/running events in DAG order, late-joiner replay from stage artifacts, 15 s heartbeat, stream timeout; observes the run store only (no pipeline import) so the T-3.9 swap keeps the wire contract | `task/T-5.4-sse-progress` (stacked on #30) | `uv run pytest tests/api/test_sse.py -q` → 6 passed · `curl -N` on a fake run → 12 `stage` events then `done` · full API suite → 23 passed · ordering/replay/heartbeat/disconnect/404/401 cases | 2026-10-29 |
| T-5.2 runs API: guarded `POST /runs` (multipart video + SOP or `sop_text`, streaming cap, security validation, background fake run), `GET /runs`, `GET /runs/{id}` stage table, report 409-while-running, Range-capable artifact serving through the traversal guard, `{error:{code,message}}` envelope, `pw openapi --check` | `task/T-5.2-runs-api` (stacked on #29) | `uv run pytest tests/api -q` → 17 passed · `uv run pw openapi --check` → exit 0 · full suite → 401 passed · 401/404/409/413/415/422/429/206 cases | 2026-10-29 |
| T-5.1 security guards: upload validator (extension allowlist + ftyp/Matroska magic, zip-bomb rejection, 500 MB / 180 s / 3840x2160 caps, UTF-8 SOP, filename sanitation), constant-time fail-closed access-code dependency, thread-safe per-IP token bucket (30/min, burst 10), traversal-safe artifact resolver with dir allowlist, 24 h purge with exemptions, secret redaction | `task/T-5.1-security-guards` (stacked on #28) | `uv run pytest tests/security -q` → 42 passed · full suite → 384 passed · caps from TRD §5 (ADR-001 absent) · magic, bomb, cap-boundary, traversal (`../`, `%2f`, backslash, drive), auth, concurrent-burst and purge cases | 2026-10-29 |
| T-0.8 walking skeleton: 12-stage fake DAG with per-stage content-hash cache and `.key` files, run store (`input/stages/media/evidence/illustrations` + root `report.json`), `pw run --mode fake`, FastAPI `/healthz` + `GET /runs`, `pw` entry point now `pw.cli:main` delegating `overlay`/`verify-evidence` | `task/T-0.8-walking-skeleton` | `uv run pytest tests/pipeline -q` → 16 passed · `uv run pw run --mode fake …` → exit 0, 12 json files · `curl /healthz` → `{"status":"ok"}` · full suite → 342 passed | 2026-10-29 |
| T-2.8 candidate segments: change-point cuts at event times, start events open the following interval and end events close the preceding one so tails stay idle, idle gaps < 2 s absorbed, activity < 1 s merged, activity > 20 s split, contiguous `seg_NNN` coverage with salient tracks and event ids, contract-valid segmented `timeline.json` | `task/T-2.8-segments` · PR #27 | `uv run pytest tests/timeline/test_segments.py -q` → 9 passed · timeline coverage → 96.56% (segments.py 95%) · full suite → 351 passed · boundaries/short-merge/idle-gap/split/coverage/artifact/write cases | 2026-10-28 |

## Blockers / Decisions needed from human
- **META_API_KEY missing** → T-0.4/0.5/0.6 cannot start; T-0.7/0.8, all of P2 beyond ingest, T-3.2 and the API cards behind them wait on those ADRs. Every remaining card except gated polish work needs this.
- **Filming:** T-1.4 (15 dev clips) and T-1.5 (9 held-out clips) need a camera, props and a second operator; T-1.7/T-1.8 wait on them. `docs/bench/shot_list.md` is ready, and T-2.1's CLI smoke is ready to run on the first real clip.
- Q-1 track (Indie vs Startup), Q-3 procedures (defaults A-8 used), Q-4 OS mix; Q-5 closed by ADR-000. Human items: portal field list (login-gated), name the Representative, sign waiver/tax form.
- Decision log (fill at G0): SAM backend (API | self-hosted) · chunk length/overlap · mask decode path · deploy host candidate

## Health
Scope violations: 0 · Tasks reopened: 0 · Tasks added: 0 · Failed-attempt streak: 0 · Health: GREEN

## Discoveries (found, not yet planned)
- **ffmpeg 9 can no longer write rotation metadata** (`-metadata:s:v rotate=90` is silently dropped), so a rotated fixture cannot be generated locally. Rotation handling is therefore covered by unit tests on the ffprobe payload (side-data and tag paths) and must be re-checked against a real phone clip once T-1.4 films one.
- Time is always PTS-derived (`frames / nominal_fps` never appears); `TimeMap.is_variable` flags phone VFR input, and normalisation is what makes analysis frames unambiguous.
- **Ruff reads every text file under the repo root, including `docs/*.md`**; a ledger saved in a non-UTF-8 encoding fails `ruff format --check` (happened once in T-0.9 — the ledger is now always written as UTF-8).
- **Abstention is a real DP outcome, not a threshold after the fact:** with weak step probabilities the `none` state can be cheaper than a skip or back transition, so the aligner naturally drops a step instead of forcing it (calibrated abstention, §1A item 4). Tests use strong likelihoods when they intend to exercise skip/back costs.
- The domain guard reuses the aligner's `coverage` (steps with interval and mean P ≥ 0.4 ÷ K) and leaves `domain_cost_max` null until T-3.10 calibrates it, matching `contracts/examples/thresholds.example.json`; with `null` the cost rule is inactive.
- Stitching matches on shared analysis frame indices (polygon IoU at 64x64, box fallback); features rasterise masks the same way with a 2-cell dilation, score contact as `overlap / object area` and bridge hold gaps up to `bridge_s`. Mask-encoding IoU stays with T-2.4/ADR-001.
- Explanations use `mm:ss.cc` timestamps so the ±0.5 s check is exact; the report builder still formats its template as `mm:ss`. Tool detection is a narrow phrase pattern around with/using/used/needs/requires, and the caller passes the procedure vocabulary (tools and parts), so parts such as `bolt` are not misread as unknown tools.
- Evidence items and illustration blocks are optional inputs to the report builder: a deviation with no evidence gets `evidence_unavailable: true` and a deviation with no illustration gets a reason string, so T-3.9 can assemble partial reports before T-4.3/T-4.4 land.
- The illustration watermark is drawn with Pillow's default font (no font files are vendored); the guard lives in `pw.evidence.labeling` and the report builder calls `assert_evidence_kinds` before schema validation.
- Evidence provenance compares a 64-bit dHash with an 8-bit budget rather than bytes: ffmpeg/font builds differ across hosts, so re-renders are never byte-identical. The item still carries exact `output_sha256` for tamper detection of the stored PNG, and verification re-renders from `stages/tracks.json` + `media/analysis.mp4` next to the report.
- The evidence selector takes a `FrameProvider` callable, not a video path: T-4.2/T-3.9 can pass a decoder, tests pass synthetic PIL frames. Missed deviations seed the gap brackets and out-of-order seeds one frame per swapped window before score-filling, so the strategy survives noisy scores; zero usable frames or unreadable frames return `evidence_unavailable` reasons instead of placeholders.
- New npm dependencies (AGENTS.md §4): `react-router-dom`, `axe-core` (dev). New Python deps: `jsonschema`, `types-jsonschema`, `pymupdf`, `pillow 12.3.0` (T-2.9), `fastapi` + `uvicorn` (T-0.8 runtime), `httpx` (dev, TestClient) — all mature releases inside the 14-day rule.
- Upload caps come from `04_TRD` §5 (500 MB, 180 s, 3840x2160), not ADR-001 (absent); a "zip bomb" is rejected on container magic and never decompressed, and every cap check runs before ffprobe. Security failures carry `status_code`/`code`/`to_payload()` so T-5.2 can render the `{error:{code,message}}` envelope.
- The `pw` entry point is now `pw.cli:main` (T-0.8) and delegates `overlay` and `verify-evidence`; `pw run` only supports `--mode fake` until T-0.7/T-3.9 wire the real stages. The 12-stage fake DAG writes `stages/<stage>.key` = sha256(stage_version ‖ video/sop hashes ‖ dependency artifact hashes ‖ mode), so reruns are no-ops.
- Host toolchain: `uv 0.13.6`, `ffmpeg 9.0.2`, `gitleaks 8.30.1` (winget; the 14-day rule is enforced for project deps).
- Timeline events derive contacts as held-tool ↔ contacted-part (the hand's contact window with the part while the same hand holds the tool), deduped by unordered pair with the earliest sorted hold winning; zones arrive as `Track`s passed via `zones=`, so no SOP import is needed. Debounce merges same-type/same-tracks events, keeping the earliest start, latest end and max confidence.
- DSH sandbox: ACL/label repair needed once; `pre-commit` cannot bootstrap upstream hooks (gitleaks is a local hook; CI installs the CLI); the web toolchain cannot be sandboxed locally; pytest `tmp_path` and `tempfile` temp dirs are unusable (tests use `.uv/tests-tmp`).

## Next up
**Key-free queue (approved 2026-10-29):** T-5.5 is open PR #32; T-5.8 progress view is next. T-2.6/T-2.8 are merged. Everything else needs `META_API_KEY` (T-0.4–0.7, T-2.2/T-2.4/T-2.7, T-3.2–T-3.4/T-3.7/T-3.9, T-4.3/T-4.4), filmed clips (T-1.4/T-1.5/T-1.7/T-1.8/T-2.10/T-3.12/T-6.1/T-6.2) or ADR-001/002/003.

# PROGRESS.md: agent handoff ledger (keep under 60 lines; prune at every gate)
> Read AGENTS.md and this file, then execute the current task for YOUR owner row. Read only that task's Context pack from docs/06_Plan.md.
> Clock: kickoff Mon Oct 26 · hard internal deadline Nov 4 12:00 ET · official deadline Nov 4 21:00 ET (= Nov 5 02:00 UTC)

## Now (one row per owner; one task in progress per owner)
| Owner | Track | Current task | Status | Branch / last green commit |
|---|---|---|---|---|
| O4 | FE | T-5.9 · Review core: player and dual-lane timeline | done | task/T-5.9-review-core |
| O2 | ML | T-3.1 · SOP ingest (md, txt, pdf) | done | 28e831f (merged) |
| O1 | ML | T-1.6 · Metrics module | done | 82360e8 (merged) |
| O3 | OPS | T-0.2 · Python scaffold and tooling | done | 44b9ed9 (merged) |
Current phase: P1 + early P3 + early P5 · C1 frozen (`contracts-v1`); T-0.1–T-0.3, T-1.1–T-1.3, T-1.6, T-3.1, T-5.6, T-5.9 are [x]
Micro-plan (M tasks only, 3–6 lines):
- T-5.12 (demo gallery) is the last FE card startable without an API or footage; then FE needs T-5.2 and T-2.4.
- T-1.4/T-1.5 filming blocks T-1.7/T-1.8; `META_API_KEY` blocks T-0.4–T-0.6, T-3.2 and the rest of P2.

## Last 5 completed (newest first)
| Task | Commit | Evidence (command → result) | Date |
|---|---|---|---|
| T-5.9 review core: time↔pixel scale, dual-lane timeline (expected vs observed), type-coloured deviation markers, playhead, keyboard transport (J/K/L, ←/→ frame, shift ±1 s, N/P) | `task/T-5.9-review-core` · PR #10 | `npm --prefix web run test -- --run web/src/features/review/timeline` → 24 passed · full suite → 88 passed · `typecheck`/`lint`/`build` → 0 | 2026-10-27 |
| T-5.6 app shell + design tokens + routes + typed API client + access gate + state components | `task/T-5.6-app-shell` · PR #9 · merged | `npm --prefix web run test -- --run` → 41 passed · `typecheck` → 0 · `lint` → 0 · `build` → 0 | 2026-10-27 |
| T-3.1 SOP ingest: md/txt/pdf → `SopSource` (sha256, page count, numbering normalisation), scanned PDFs rendered to PNG + `needs_vision`, 50-page and 20 MB caps | `task/T-3.1-sop-ingest` · PR #8 · merged | `pytest tests/sop -q` → 20 passed · `pytest -q` → 116 passed · coverage `pw.sop.ingest` → 93% · ruff/mypy clean | 2026-10-27 |
| T-1.6 pure metrics: type-aware matching (±2 s), P/R/F1 per type + overall, false flags/compliant clip, timestamp MAE, needs-review rate, cost/latency per video-minute | `task/T-1.6-metrics` · PR #7 · merged | `pytest tests/bench/test_metrics.py -q` → 30 passed · coverage 100% · `pytest -q` → 96 passed | 2026-10-27 |
| T-1.3 3 SOPs, 3 golden step graphs, `bench/gt.schema.json`, shot list covering every variant, `pw-data validate-sops` / `validate-gt` | `task/T-1.3-sops-golden-gt` · PR #6 · merged | `pw-data validate-sops` → `3 SOPs, 3 golden graphs valid; steps 8–12; critical ≥ 1; tools ≥ 3` · `pytest tests/data -q` → 18 passed | 2026-10-27 |

## Blockers / Decisions needed from human
- **Filming is the critical path:** T-1.4 (15 dev clips) and T-1.5 (9 held-out clips) need a camera, props and a second operator; T-1.7/T-1.8 wait on them. `docs/bench/shot_list.md` is ready.
- **META_API_KEY missing** → T-0.4/0.5/0.6 cannot start; T-0.7/0.8/0.9, all of P2, T-3.2 and the API cards behind them wait on those ADRs.
- Q-1 track (Indie vs Startup), Q-3 procedures (defaults A-8 used), Q-4 OS mix; Q-5 closed by ADR-000. Human items: portal field list (login-gated), name the Representative, sign waiver/tax form.
- Decision log (fill at G0): SAM backend (API | self-hosted) · chunk length/overlap · mask decode path · deploy host candidate

## Health
Scope violations: 0 · Tasks reopened: 0 · Tasks added: 0 · Failed-attempt streak: 0 · Health: GREEN

## Discoveries (found, not yet planned)
- **Vitest now runs with the repository as its root** (`web/vite.config.ts` → `test.root: ".."`, `include: web/src/**`), so the repo-relative `--run <path>` filters written in `06_Plan.md` work verbatim; before this, `--run web/src/...` matched nothing because npm --prefix sets the web folder as cwd.
- `ReviewSurface` owns the review clock: player scrubbing, marker clicks and keyboard shortcuts all call one `seek`, which is why the playhead, timecode and markers cannot drift apart. It is not mounted in the run route yet — that wiring belongs to T-5.13.
- Deviation markers are labelled with type + step + timecode (`"Wrong tool step stp_04 at 01:12.4"`) and `needs_review` gets a dashed border plus a spoken "(needs review)", so colour is never the only signal (03_UI_Spec §2).
- Design tokens live in `web/src/ui/tokens.css` and Tailwind maps them; the only raw colours in the repo are in that file and in `tokens.css`'s overlay palette, by design.
- `web/src/api/client.ts` turns every HTTP failure into a typed `ApiError` code; route shapes stay provisional until `openapi.json` (T-5.2).
- New npm dependency (AGENTS.md §4): `react-router-dom` (resolved with `--before=2026-10-13`). New Python deps: `jsonschema`, `types-jsonschema`, `pymupdf`.
- Host toolchain: `uv 0.13.6`, `ffmpeg 9.0.2`, `gitleaks 8.30.1` (winget; machine tooling at latest patch — the 14-day rule is enforced for project deps).
- DSH sandbox: ACL/label repair was needed once; `pre-commit` cannot bootstrap upstream hooks (gitleaks is a local hook; CI installs the CLI); the web toolchain cannot run sandboxed (Node `spawn EPERM`); pytest `tmp_path` is unusable (tests use `.uv/tests-tmp`).
- `pw-data` reconfigures stdio to UTF-8 so the en-dash / greater-or-equal summary line works on a cp1252 console.

## Next up
T-5.12 (demo gallery — last FE card that needs neither API nor footage) · T-1.7/T-1.8 need filming · T-0.4/0.5/0.6 need `META_API_KEY`.

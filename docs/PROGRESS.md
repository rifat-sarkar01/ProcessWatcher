# PROGRESS.md: agent handoff ledger (keep under 60 lines; prune at every gate)
> Read AGENTS.md and this file, then execute the current task for YOUR owner row. Read only that task's Context pack from docs/06_Plan.md.
> Clock: kickoff Mon Oct 26 · hard internal deadline Nov 4 12:00 ET · official deadline Nov 4 21:00 ET (= Nov 5 02:00 UTC)

## Now (one row per owner; one task in progress per owner)
| Owner | Track | Current task | Status | Branch / last green commit |
|---|---|---|---|---|
| O3 | OPS | T-0.9 · CI and skeleton check | done | task/T-0.9-ci |
| O4 | FE | T-5.12 · Demo gallery | done | c778742 (merged) |
| O2 | ML | T-3.1 · SOP ingest (md, txt, pdf) | done | 28e831f (merged) |
| O1 | ML | T-1.6 · Metrics module | done | 82360e8 (merged) |
Current phase: P0/P1 + early P3/P5 · C1 frozen (`contracts-v1`) · **CI gates every push and PR** · 13/74 cards [x]
Micro-plan (M tasks only, 3–6 lines):
- Agent queue is empty again: every other ready card needs `META_API_KEY` or filmed clips.
- CI skeleton step is conditional and activates by itself when T-0.8 adds `src/pw/cli.py` + `tests/fixtures/tiny.mp4`.

## Last 5 completed (newest first)
| Task | Commit | Evidence (command → result) | Date |
|---|---|---|---|
| T-0.9 CI: backend (ruff, mypy, pytest, pw-data checks), web (lint/types/tests/build, generated-types freshness), gitleaks history; conditional skeleton + held-out lock; non-blocking audits | `task/T-0.9-ci` · PR #12 | `gh run list --limit 1 --json conclusion -q ".[0].conclusion"` → `success` | 2026-10-27 |
| T-5.12 demo gallery: 3 frozen cases (IT/lab/mechanical), offline badge, one-click load into the review core | `task/T-5.12-demo-gallery` · PR #11 · merged | `--run web/src/features/demo` → 10 passed · suite → 98 passed · `typecheck`/`lint`/`build` → 0 | 2026-10-27 |
| T-5.9 review core: time↔pixel scale, dual-lane timeline, type-coloured markers, playhead, keyboard transport (J/K/L, ←/→ frame, shift ±1 s, N/P) | `task/T-5.9-review-core` · PR #10 · merged | `--run web/src/features/review/timeline` → 24 passed · suite → 88 passed · `typecheck`/`lint`/`build` → 0 | 2026-10-27 |
| T-5.6 app shell + design tokens + routes + typed API client + access gate + state components | `task/T-5.6-app-shell` · PR #9 · merged | `--run` → 41 passed · `typecheck` → 0 · `lint` → 0 · `build` → 0 | 2026-10-27 |
| T-3.1 SOP ingest: md/txt/pdf → `SopSource` (sha256, page count, numbering normalisation), scanned PDFs → PNG + `needs_vision`, 50-page/20 MB caps | `task/T-3.1-sop-ingest` · PR #8 · merged | `pytest tests/sop -q` → 20 passed · `pytest -q` → 116 passed · coverage 93% | 2026-10-27 |

## Blockers / Decisions needed from human
- **META_API_KEY missing** → T-0.4/0.5/0.6 cannot start; T-0.7/0.8 (and the CI skeleton step), all of P2, T-3.2 and the API cards behind them wait on those ADRs. Top blocker: the agent queue is otherwise empty.
- **Filming:** T-1.4 (15 dev clips) and T-1.5 (9 held-out clips) need a camera, props and a second operator; T-1.7/T-1.8 wait on them. `docs/bench/shot_list.md` is ready.
- Q-1 track (Indie vs Startup), Q-3 procedures (defaults A-8 used), Q-4 OS mix; Q-5 closed by ADR-000. Human items: portal field list (login-gated), name the Representative, sign waiver/tax form.
- Decision log (fill at G0): SAM backend (API | self-hosted) · chunk length/overlap · mask decode path · deploy host candidate

## Health
Scope violations: 0 · Tasks reopened: 0 · Tasks added: 0 · Failed-attempt streak: 0 · Health: GREEN

## Discoveries (found, not yet planned)
- **Ruff reads every text file under the repo root, including `docs/*.md`.** A ledger file saved in a non-UTF-8 encoding therefore fails `ruff format --check` with "stream did not contain valid UTF-8". Keep docs UTF-8; if this recurs, add `docs` to `[tool.ruff] extend-exclude`.
- **T-0.9 was executed before T-0.8** (human-approved pull-forward; recorded in `06_Plan.md` §7). The skeleton step is `if:`-guarded on `src/pw/cli.py` + `tests/fixtures/tiny.mp4` so it enables itself when T-0.8 lands; the held-out lock step guards on `bench/HELDOUT.lock`; audits stay non-blocking until G6.
- CI runs on Linux (ubuntu-latest), which sidesteps this host's sandbox limits: commands that need wider access locally (`vitest`, ESLint, `uv sync`) run unmodified there, so local Windows quirks never reach the gate.
- The web job regenerates contract types and fails on a diff, so `web/src/types/generated/*` can never drift from `contracts/*` (05_Schema §15).
- **Demo data is inline and deterministic** (`web/src/features/demo/cases.ts`); T-7.1 `pw demo-build` replaces it with checksummed `demo/cases/` files of the same shape. `/demo/:caseId` mounts the real `ReviewSurface`.
- Vitest runs with the repository as its root (`web/vite.config.ts`), so repo-relative `--run <path>` filters from `06_Plan.md` work verbatim.
- `ReviewSurface` owns the review clock: player, markers and shortcuts share one `seek`. Real runs still need T-5.13 to mount it on `/runs/:id`.
- Design tokens live in `web/src/ui/tokens.css`; components carry no raw hex. `web/src/api/client.ts` maps every HTTP failure to a typed `ApiError` code.
- New npm dependency (AGENTS.md §4): `react-router-dom`. New Python deps: `jsonschema`, `types-jsonschema`, `pymupdf`.
- Host toolchain: `uv 0.13.6`, `ffmpeg 9.0.2`, `gitleaks 8.30.1` (winget; the 14-day rule is enforced for project deps).
- DSH sandbox: ACL/label repair needed once; `pre-commit` cannot bootstrap upstream hooks (gitleaks is a local hook; CI installs the CLI); the web toolchain cannot run sandboxed locally; pytest `tmp_path` is unusable (tests use `.uv/tests-tmp`).
- `pw-data` reconfigures stdio to UTF-8 so the en-dash / greater-or-equal summary line works on a cp1252 console.

## Next up
**Nothing is startable without a human decision:** supply `META_API_KEY` (unblocks T-0.4 → T-0.7 → T-0.8 → all of P2/P3), film T-1.4/T-1.5 (unblocks T-1.7/T-1.8), or explicitly approve another dependency pull-forward (candidates: T-6.5 security audit, which cannot be finished without model code, or T-6.7 a11y polish on the three shipped routes).

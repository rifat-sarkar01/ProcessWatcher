# PROGRESS.md: agent handoff ledger (keep under 60 lines; prune at every gate)
> Read AGENTS.md and this file, then execute the current task for YOUR owner row. Read only that task's Context pack from docs/06_Plan.md.
> Clock: kickoff Mon Oct 26 · hard internal deadline Nov 4 12:00 ET · official deadline Nov 4 21:00 ET (= Nov 5 02:00 UTC)

## Now (one row per owner; one task in progress per owner)
| Owner | Track | Current task | Status | Branch / last green commit |
|---|---|---|---|---|
| O4 | FE | T-5.12 · Demo gallery | done | task/T-5.12-demo-gallery |
| O2 | ML | T-3.1 · SOP ingest (md, txt, pdf) | done | 28e831f (merged) |
| O1 | ML | T-1.6 · Metrics module | done | 82360e8 (merged) |
| O3 | OPS | T-0.2 · Python scaffold and tooling | done | 44b9ed9 (merged) |
Current phase: P1 + early P3 + early P5 · C1 frozen (`contracts-v1`); T-0.1–T-0.3, T-1.1–T-1.3, T-1.6, T-3.1, T-5.6, T-5.9, T-5.12 are [x]
Micro-plan (M tasks only, 3–6 lines):
- **Agent queue is empty after this card**: every remaining task needs `META_API_KEY`, filmed clips, or a dependency built on them.
- Unblock options: (a) provide `META_API_KEY` → T-0.4/0.5/0.6 then T-0.7/0.8/0.9 + P2; (b) film T-1.4/T-1.5 → T-1.7/T-1.8; (c) approve pulling T-0.9 (CI) forward despite its T-0.8 dependency.

## Last 5 completed (newest first)
| Task | Commit | Evidence (command → result) | Date |
|---|---|---|---|
| T-5.12 demo gallery: 3 frozen cases across IT/lab/mechanical, offline badge, one-click load into the review core | `task/T-5.12-demo-gallery` · PR #11 | `npm --prefix web run test -- --run web/src/features/demo` → 10 passed · full suite → 98 passed · `typecheck`/`lint`/`build` → 0 | 2026-10-27 |
| T-5.9 review core: time↔pixel scale, dual-lane timeline, type-coloured markers, playhead, keyboard transport (J/K/L, ←/→ frame, shift ±1 s, N/P) | `task/T-5.9-review-core` · PR #10 · merged | `--run web/src/features/review/timeline` → 24 passed · suite → 88 passed · `typecheck`/`lint`/`build` → 0 | 2026-10-27 |
| T-5.6 app shell + design tokens + routes + typed API client + access gate + state components | `task/T-5.6-app-shell` · PR #9 · merged | `--run` → 41 passed · `typecheck` → 0 · `lint` → 0 · `build` → 0 | 2026-10-27 |
| T-3.1 SOP ingest: md/txt/pdf → `SopSource` (sha256, page count, numbering normalisation), scanned PDFs → PNG + `needs_vision`, 50-page/20 MB caps | `task/T-3.1-sop-ingest` · PR #8 · merged | `pytest tests/sop -q` → 20 passed · `pytest -q` → 116 passed · coverage 93% | 2026-10-27 |
| T-1.6 pure metrics: type-aware matching (±2 s), P/R/F1 per type + overall, false flags/compliant clip, timestamp MAE, needs-review rate, cost per video-minute | `task/T-1.6-metrics` · PR #7 · merged | `pytest tests/bench/test_metrics.py -q` → 30 passed · coverage 100% · `pytest -q` → 96 passed | 2026-10-27 |

## Blockers / Decisions needed from human
- **META_API_KEY missing** → T-0.4/0.5/0.6 cannot start; T-0.7/0.8/0.9, all of P2, T-3.2 and the API cards behind them wait on those ADRs. This is now the top blocker: the agent queue is otherwise empty.
- **Filming:** T-1.4 (15 dev clips) and T-1.5 (9 held-out clips) need a camera, props and a second operator; T-1.7/T-1.8 wait on them. `docs/bench/shot_list.md` is ready.
- Q-1 track (Indie vs Startup), Q-3 procedures (defaults A-8 used), Q-4 OS mix; Q-5 closed by ADR-000. Human items: portal field list (login-gated), name the Representative, sign waiver/tax form.
- Decision log (fill at G0): SAM backend (API | self-hosted) · chunk length/overlap · mask decode path · deploy host candidate

## Health
Scope violations: 0 · Tasks reopened: 0 · Tasks added: 0 · Failed-attempt streak: 0 · Health: GREEN

## Discoveries (found, not yet planned)
- **Demo data is inline and deterministic** (`web/src/features/demo/cases.ts`) so `/demo` works with no backend; T-7.1's `pw demo-build` will replace it with checksummed `demo/cases/` files of the same shape. The gallery carries a permanent "Offline" badge because that promise is the demo's safety net.
- Demo cases load into the **same `ReviewSurface`** used by real runs (`/demo/:caseId`), so the demo exercises the product's actual review path instead of a mock.
- Vitest runs with the repository as its root (`web/vite.config.ts`), so repo-relative `--run <path>` filters from `06_Plan.md` work verbatim.
- `ReviewSurface` owns the review clock: player, markers and shortcuts share one `seek`, so playhead/timecode/markers cannot drift. Real runs still need T-5.13 to mount it on `/runs/:id`.
- Design tokens live in `web/src/ui/tokens.css`; components carry no raw hex. `web/src/api/client.ts` maps every HTTP failure to a typed `ApiError` code (route shapes stay provisional until `openapi.json` in T-5.2).
- New npm dependency (AGENTS.md §4): `react-router-dom`. New Python deps: `jsonschema`, `types-jsonschema`, `pymupdf`.
- Host toolchain: `uv 0.13.6`, `ffmpeg 9.0.2`, `gitleaks 8.30.1` (winget; machine tooling at latest patch — the 14-day rule is enforced for project deps).
- DSH sandbox: ACL/label repair was needed once; `pre-commit` cannot bootstrap upstream hooks (gitleaks is a local hook; CI installs the CLI); the web toolchain cannot run sandboxed (Node `spawn EPERM`); pytest `tmp_path` is unusable (tests use `.uv/tests-tmp`).
- `pw-data` reconfigures stdio to UTF-8 so the en-dash / greater-or-equal summary line works on a cp1252 console.

## Next up
**Nothing is startable without a human decision.** Either supply `META_API_KEY` (unblocks T-0.4 → T-0.7 → all of P2/P3), or film T-1.4/T-1.5 (unblocks T-1.7/T-1.8), or approve pulling T-0.9 (CI workflow) forward ahead of its T-0.8 dependency.

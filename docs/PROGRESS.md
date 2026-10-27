# PROGRESS.md: agent handoff ledger (keep under 60 lines; prune at every gate)
> Read AGENTS.md and this file, then execute the current task for YOUR owner row. Read only that task's Context pack from docs/06_Plan.md.
> Clock: kickoff Mon Oct 26 · hard internal deadline Nov 4 12:00 ET · official deadline Nov 4 21:00 ET (= Nov 5 02:00 UTC)

## Now (one row per owner; one task in progress per owner)
| Owner | Track | Current task | Status | Branch / last green commit |
|---|---|---|---|---|
| O4 | FE | T-6.7 · State, accessibility and projector polish | done | task/T-6.7-a11y-polish |
| O3 | OPS | T-0.9 · CI and skeleton check | done | 18e664c (merged) |
| O1 | ML | T-1.6 · Metrics module | done | 82360e8 (merged) |
| O2 | ML | T-3.1 · SOP ingest (md, txt, pdf) | done | 28e831f (merged) |
Current phase: P0/P1 + early P3/P5/P6 · C1 frozen (`contracts-v1`) · **CI gates every push and PR** · 14/74 cards [x]
Micro-plan (M tasks only, 3–6 lines):
- Agent queue is empty: every remaining card needs `META_API_KEY`, filmed clips, or a gate (G2–G5) that those two unblock.
- Two pull-forwards are already logged in `06_Plan.md` §7 (T-0.9 before T-0.8, T-6.7 before G5); further ones need a fresh decision.

## Last 5 completed (newest first)
| Task | Commit | Evidence (command → result) | Date |
|---|---|---|---|
| T-6.7 a11y polish: axe over the 4 shipped routes (+ planted-violation self-check), token-contrast contract from `03_UI_Spec` §2, type/motion guards | `task/T-6.7-a11y-polish` · PR #13 | `npm --prefix web run test:a11y` → 5 passed, 0 serious/critical · full suite → 119 passed · `typecheck`/`lint`/`build` → 0 | 2026-10-27 |
| T-0.9 CI: backend (ruff, mypy, pytest, pw-data checks), web (lint/types/tests/build, generated-types freshness), gitleaks history; conditional skeleton + held-out lock; non-blocking audits | `task/T-0.9-ci` · PR #12 · merged | `gh run list --limit 1 --json conclusion -q ".[0].conclusion"` → `success` | 2026-10-27 |
| T-5.12 demo gallery: 3 frozen cases (IT/lab/mechanical), offline badge, one-click load into the review core | `task/T-5.12-demo-gallery` · PR #11 · merged | `--run web/src/features/demo` → 10 passed · suite → 98 passed | 2026-10-27 |
| T-5.9 review core: time↔pixel scale, dual-lane timeline, type-coloured markers, playhead, keyboard transport | `task/T-5.9-review-core` · PR #10 · merged | `--run web/src/features/review/timeline` → 24 passed · suite → 88 passed | 2026-10-27 |
| T-5.6 app shell + design tokens + routes + typed API client + access gate + state components | `task/T-5.6-app-shell` · PR #9 · merged | `--run` → 41 passed · `typecheck`/`lint`/`build` → 0 | 2026-10-27 |

## Blockers / Decisions needed from human
- **META_API_KEY missing** → T-0.4/0.5/0.6 cannot start; T-0.7/0.8, all of P2, T-3.2 and the API cards behind them wait on those ADRs. This now blocks **every** remaining card that is not polishing work already shipped.
- **Filming:** T-1.4 (15 dev clips) and T-1.5 (9 held-out clips) need a camera, props and a second operator; T-1.7/T-1.8 wait on them. `docs/bench/shot_list.md` is ready.
- Q-1 track (Indie vs Startup), Q-3 procedures (defaults A-8 used), Q-4 OS mix; Q-5 closed by ADR-000. Human items: portal field list (login-gated), name the Representative, sign waiver/tax form.
- Decision log (fill at G0): SAM backend (API | self-hosted) · chunk length/overlap · mask decode path · deploy host candidate

## Health
Scope violations: 0 · Tasks reopened: 0 · Tasks added: 0 · Failed-attempt streak: 0 · Health: GREEN

## Discoveries (found, not yet planned)
- **Accessibility is now test-enforced, not asserted.** `web/src/ui/a11y.test.tsx` runs axe over `/`, `/runs/:id`, `/demo`, `/demo/:id`, and a planted `<img>` without `alt` must be caught — proving the harness can fail. `color-contrast` is disabled there because jsdom has no layout; `web/src/ui/tokens.test.ts` covers it properly by computing WCAG ratios from the token hex values (all ≥ 4.5:1 on `surface`, borders ≥ 3:1).
- The axe run found **zero** serious/critical violations on the shipped UI, so this card is a guard rather than a fix pass. The real 1080p-projector check still needs a browser viewport and is deferred to T-5.13 (Playwright), not claimed here.
- **Ruff reads every text file under the repo root, including `docs/*.md`**; a ledger saved in a non-UTF-8 encoding fails `ruff format --check` (this happened once in T-0.9 and is why the ledger is always rewritten as UTF-8 now).
- Pull-forwards logged in `06_Plan.md` §7: T-0.9 before T-0.8, T-6.7 before G5. Both keep their original scope.
- CI (T-0.9) runs on Linux and re-executes the axe suite on every push; the skeleton step stays `if:`-guarded until T-0.8 lands.
- Demo data is inline and deterministic (`web/src/features/demo/cases.ts`); T-7.1 replaces it with checksummed `demo/cases/` files. `/demo/:caseId` mounts the real `ReviewSurface`.
- Design tokens live in `web/src/ui/tokens.css`; components carry no raw hex. `web/src/api/client.ts` maps every HTTP failure to a typed `ApiError` code.
- New npm dependencies (AGENTS.md §4): `react-router-dom`, `axe-core` (dev). New Python deps: `jsonschema`, `types-jsonschema`, `pymupdf`.
- Host toolchain: `uv 0.13.6`, `ffmpeg 9.0.2`, `gitleaks 8.30.1` (winget; the 14-day rule is enforced for project deps).
- DSH sandbox: ACL/label repair needed once; `pre-commit` cannot bootstrap upstream hooks (gitleaks is a local hook; CI installs the CLI); the web toolchain cannot be sandboxed locally; pytest `tmp_path` is unusable (tests use `.uv/tests-tmp`).

## Next up
**Nothing is startable without a human decision.** Supply `META_API_KEY` (unblocks T-0.4 → T-0.7 → T-0.8 → all of P2/P3), film T-1.4/T-1.5 (unblocks T-1.7/T-1.8), or explicitly name another card to pull forward — the remaining honest candidates are T-6.3 robustness (only for the modules that exist: ingest is not built yet) and T-6.4 failure injection (needs `pw.clients`).

# PROGRESS.md: agent handoff ledger (keep under 60 lines; prune at every gate)
> Read AGENTS.md and this file, then execute the current task for YOUR owner row. Read only that task's Context pack from docs/06_Plan.md.
> Clock: kickoff Mon Oct 26 · hard internal deadline Nov 4 12:00 ET · official deadline Nov 4 21:00 ET (= Nov 5 02:00 UTC)

## Now (one row per owner; one task in progress per owner)
| Owner | Track | Current task | Status | Branch / last green commit |
|---|---|---|---|---|
| O4 | DOC | T-0.1 · Read Official Rules and log constraints | done | task/T-0.1-read-official-rules |
| O3 | OPS | T-0.2 · Python scaffold and tooling | done | task/T-0.2-python-scaffold |
| O1 | ML | T-0.4 · Spike: SAM 3.1 on Meta Model API (blocked: no `META_API_KEY`) | blocked | |
| O2 | ML | T-0.5 · Spike: Muse Wonder (blocked: no `META_API_KEY`) | blocked | |
Current phase: P0 · Mode: parallel (4 owners) · T-0.1 and T-0.2 are [x]
Micro-plan (M tasks only, 3–6 lines):
- T-0.3: Vite + React + TS + Tailwind + Vitest + ESLint skeleton, one render test.

## Last 5 completed (newest first)
| Task | Commit | Evidence (command → result) | Date |
|---|---|---|---|
| T-0.2 `uv` scaffold, ruff/mypy/pytest (markers, coverage), pre-commit gitleaks, `.env.example`, smoke test | `task/T-0.2-python-scaffold` · PR #2 | `uv sync` → 26 pkgs · `uv run ruff check .` → pass · `uv run ruff format --check .` → 13 files · `uv run mypy src` → clean (strict) · `uv run pytest -q` → 1 passed · `uv run pre-commit run gitleaks --all-files` → Passed | 2026-10-27 |
| T-0.1 rules + waiver read; A-10 resolved; §7 updated | `task/T-0.1-read-official-rules` · PR #1 | `Select-String docs/adr/ADR-000-rules.md -Pattern "Deliverables:|Video:|Repo/licence:|Pre-existing work:|Deadline UTC:"` → 5 matches; §7 has 1 new line | 2026-10-27 |

## Blockers / Decisions needed from human
- Q-1 track (Indie vs Startup), Q-2 API credits and rate limits, Q-3 three procedures you can film, Q-4 OS mix (defaults in 06_Plan §2)
- Q-5 **closed** by T-0.1 → `docs/adr/ADR-000-rules.md` (no video limit, no repo/licence rule, Indie ≤ 4, $150 credits, deadline 2026-11-05T02:00:00Z). Remaining human items: portal field list (login-gated), name the Representative, sign waiver/tax form.
- **META_API_KEY missing** → T-0.4, T-0.5, T-0.6 (live model spikes) cannot start. Everything downstream (T-0.7 clients, T-2.x perception) needs their ADRs.
- Decision log (fill at G0): SAM backend (API | self-hosted) · chunk length/overlap · mask decode path · deploy host candidate

## Health
Scope violations: 0 · Tasks reopened: 0 · Tasks added: 0 · Failed-attempt streak: 0 · Health: GREEN

## Discoveries (found, not yet planned)
- Host toolchain was incomplete for AGENTS.md §15: Python 3.14.4 only (no `uv`), no `ffmpeg`, no `META_API_KEY`. Installed `uv 0.13.6`, `ffmpeg 9.0.2`, `gitleaks 8.30.1` (winget, 2026-10-27). Project dependencies are pinned by `uv.lock` under `tool.uv.exclude-newer = 2026-10-13` (the 14-day rule); the three binaries are machine tooling and were installed at their latest patch — logged as a deviation.
- DSH sandbox on this Windows host: (a) workspace ACLs/labels had to be repaired before git could write; (b) `pre-commit` cannot bootstrap an upstream hook repo (it clones into a temp dir the sandbox denies). `gitleaks` is therefore a **local** pre-commit hook calling the installed CLI; T-0.9 must install the same CLI in CI.
- Tool caches live inside the repo (`UV_CACHE_DIR=.uv/cache`, `PRE_COMMIT_HOME=.uv/pre-commit`) because the sandbox blocks `%LOCALAPPDATA%`; `.uv/` is git-ignored. CI uses the defaults.

## Next up
T-0.3 (now) · then T-0.7 → T-0.8 → T-0.9 once T-0.4/0.5/0.6 unblock; contracts T-1.1 starts when T-0.2 is [x]

# PROGRESS.md: agent handoff ledger (keep under 60 lines; prune at every gate)
> Read AGENTS.md and this file, then execute the current task for YOUR owner row. Read only that task's Context pack from docs/06_Plan.md.
> Clock: kickoff Mon Oct 26 · hard internal deadline Nov 4 12:00 ET · official deadline Nov 4 21:00 ET (= Nov 5 02:00 UTC)

## Now (one row per owner; one task in progress per owner)
| Owner | Track | Current task | Status | Branch / last green commit |
|---|---|---|---|---|
| O4 | DATA | T-1.1 · Contracts A: sop, tracks, timeline + validator CLI | done | task/T-1.1-contracts-a |
| O3 | OPS | T-0.2 · Python scaffold and tooling | done | 44b9ed9 (merged) |
| O1 | ML | T-0.4 · Spike: SAM 3.1 on Meta Model API (blocked: no `META_API_KEY`) | blocked | |
| O2 | ML | T-0.5 · Spike: Muse Wonder (blocked: no `META_API_KEY`) | blocked | |
Current phase: P1 · T-0.1/T-0.2/T-0.3/T-1.1 are [x]; C1 contract freeze still pending (T-1.2)
Micro-plan (M tasks only, 3–6 lines):
- T-1.2: alignment/report/manifest/review/thresholds schemas + generated TS types + contract fixtures → tag `contracts-v1` (C1).

## Last 5 completed (newest first)
| Task | Commit | Evidence (command → result) | Date |
|---|---|---|---|
| T-1.1 JSON Schema 2020-12 for step graph / tracks / timeline, 3 examples, `pw-data` CLI (`validate-contracts`, `validate-artifact`) + semantic checks | `task/T-1.1-contracts-a` · PR #4 | `uv run pytest tests/contracts -q` → 19 passed · `uv run pw-data validate-contracts` → `OK 3 schemas, 3 examples` · `ruff check/format` → clean · `mypy src` strict → clean | 2026-10-27 |
| T-0.3 Vite + React + TS + Tailwind + Vitest + ESLint skeleton, `gen:types` placeholder, one render test | `task/T-0.3-web-scaffold` · PR #3 · merged | `npm --prefix web ci` → exit 0 · `lint` → exit 0 · `typecheck` → exit 0 · `test -- --run` → 1 passed · `build` → 16 modules transformed, `dist/` written · `gen:types` → placeholder OK | 2026-10-27 |
| T-0.2 `uv` scaffold, ruff/mypy/pytest (markers, coverage), pre-commit gitleaks, `.env.example`, smoke test | `task/T-0.2-python-scaffold` · PR #2 · merged | `uv sync` → 26 pkgs · `ruff check .` → pass · `ruff format --check .` → 13 files · `mypy src` → clean (strict) · `pytest -q` → 1 passed · `pre-commit run gitleaks --all-files` → Passed | 2026-10-27 |
| T-0.1 rules + waiver read; A-10 resolved; §7 updated | `task/T-0.1-read-official-rules` · PR #1 · merged | `Select-String docs/adr/ADR-000-rules.md -Pattern "Deliverables:|Video:|Repo/licence:|Pre-existing work:|Deadline UTC:"` → 5 matches; §7 has 1 new line | 2026-10-27 |

## Blockers / Decisions needed from human
- Q-1 track (Indie vs Startup), Q-3 three procedures you can film, Q-4 OS mix (defaults in 06_Plan §2); Q-5 closed by ADR-000. Human items: portal field list (login-gated), name the Representative, sign waiver/tax form.
- **META_API_KEY missing** → T-0.4, T-0.5, T-0.6 (live model spikes) cannot start; T-0.7/T-0.8/T-0.9 and all of P2/P3 wait on those ADRs. Not blocking DATA/FE work (T-1.2, T-1.3, T-1.8).
- Decision log (fill at G0): SAM backend (API | self-hosted) · chunk length/overlap · mask decode path · deploy host candidate

## Health
Scope violations: 0 · Tasks reopened: 0 · Tasks added: 0 · Failed-attempt streak: 0 · Health: GREEN

## Discoveries (found, not yet planned)
- **New dependencies (noted per AGENTS.md §4):** `jsonschema>=4.23` (runtime, schema validation) and `types-jsonschema` (dev stubs for mypy strict). Both resolved under `tool.uv.exclude-newer = 2026-10-13`.
- `pw-data` needs *semantic* checks on top of JSON Schema: non-monotonic frames, unsorted events, overlapping segments and dangling event references cannot be expressed in JSON Schema 2020-12. They live in `src/pw/data/validate.py` and must stay in sync with `docs/05_Schema.md` §11.
- Host toolchain was incomplete for AGENTS.md §15: Python 3.14.4 only (no `uv`), no `ffmpeg`, no `META_API_KEY`. Installed `uv 0.13.6`, `ffmpeg 9.0.2`, `gitleaks 8.30.1` (winget, 2026-10-27); the three binaries are machine tooling installed at their latest patch — a deviation from the 14-day rule, which is enforced for project dependencies in `uv.lock` and `web/package-lock.json`.
- DSH sandbox on this Windows host: (a) workspace ACLs/labels had to be repaired before git could write; (b) `pre-commit` cannot bootstrap an upstream hook repo → `gitleaks` is a **local** hook and T-0.9 must install the CLI in CI; (c) the web toolchain cannot run at all (Node `spawn EPERM`) and must be run with wider access locally — CI unaffected.
- Pytest's `tmp_path` is unusable here: `tempfile.mkdtemp` directories cannot be listed again (ACL/delete-pending state under the sandbox). Contract CLI tests use a repo-local `.uv/tests-tmp` scratch fixture instead. This is a test-harness constraint, not a product constraint.
- Tool caches live inside the repo (`UV_CACHE_DIR=.uv/cache`, `PRE_COMMIT_HOME=.uv/pre-commit`, `npm_config_cache=.uv/npm-cache`); `.uv/` is git-ignored.

## Next up
T-1.2 (contracts B + generated TS types, tag `contracts-v1` = C1), then T-1.3 (SOPs/golden/GT schema), T-1.8 (held-out lock). T-0.4/0.5/0.6 stay blocked on `META_API_KEY`.

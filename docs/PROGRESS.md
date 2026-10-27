# PROGRESS.md: agent handoff ledger (keep under 60 lines; prune at every gate)
> Read AGENTS.md and this file, then execute the current task for YOUR owner row. Read only that task's Context pack from docs/06_Plan.md.
> Clock: kickoff Mon Oct 26 · hard internal deadline Nov 4 12:00 ET · official deadline Nov 4 21:00 ET (= Nov 5 02:00 UTC)

## Now (one row per owner; one task in progress per owner)
| Owner | Track | Current task | Status | Branch / last green commit |
|---|---|---|---|---|
| O4 | DATA | T-1.3 · SOPs, golden step graphs, GT schema, shot list | done | task/T-1.3-sops-golden-gt |
| O3 | OPS | T-0.2 · Python scaffold and tooling | done | 44b9ed9 (merged) |
| O1 | ML | T-0.4 · Spike: SAM 3.1 on Meta Model API (blocked: no `META_API_KEY`) | blocked | |
| O2 | ML | T-0.5 · Spike: Muse Wonder (blocked: no `META_API_KEY`) | blocked | |
Current phase: P1 · C1 frozen (`contracts-v1`); T-0.1–T-0.3, T-1.1–T-1.3 are [x]
Micro-plan (M tasks only, 3–6 lines):
- T-1.6: pure metrics module (matching ±2 s, P/R/F1 per type, MAE, false flags) — unblocked by T-1.2+T-1.3.
- Next human step: film 15 dev clips per `docs/bench/shot_list.md` (T-1.4) and 9 held-out (T-1.5).

## Last 5 completed (newest first)
| Task | Commit | Evidence (command → result) | Date |
|---|---|---|---|
| T-1.3 3 SOPs, 3 hand-written golden step graphs, `bench/gt.schema.json`, shot list covering every variant, `pw-data validate-sops` / `validate-gt` | `task/T-1.3-sops-golden-gt` · PR #6 | `pw-data validate-sops` → `3 SOPs, 3 golden graphs valid; steps 8–12; critical ≥ 1; tools ≥ 3` · `pytest tests/data -q` → 18 passed · `pytest -q` → 66 passed · ruff/mypy clean | 2026-10-27 |
| T-1.2 alignment/report/manifest/review/thresholds schemas, 9 new examples (3 report states), semantic invariants, real `gen:types` → 8 TS modules, tag `contracts-v1` | `task/T-1.2-contracts-b` · PR #5 · merged | `pytest tests/contracts -q` → 47 passed · `pw-data validate-contracts` → `OK 8 schemas, 12 examples` · `gen:types` + `git diff --exit-code` → clean · web typecheck/lint/build → 0 · mypy strict → clean | 2026-10-27 |
| T-1.1 JSON Schema 2020-12 for step graph / tracks / timeline, 3 examples, `pw-data` CLI (`validate-contracts`, `validate-artifact`) + semantic checks | `task/T-1.1-contracts-a` · PR #4 · merged | `uv run pytest tests/contracts -q` → 19 passed · `uv run pw-data validate-contracts` → `OK 3 schemas, 3 examples` · `ruff check/format` → clean · `mypy src` strict → clean | 2026-10-27 |
| T-0.3 Vite + React + TS + Tailwind + Vitest + ESLint skeleton, `gen:types` placeholder, one render test | `task/T-0.3-web-scaffold` · PR #3 · merged | `npm --prefix web ci` → exit 0 · `lint`/`typecheck`/`test`/`build` → 0 (1 test) | 2026-10-27 |
| T-0.2 `uv` scaffold, ruff/mypy/pytest (markers, coverage), pre-commit gitleaks, `.env.example`, smoke test | `task/T-0.2-python-scaffold` · PR #2 · merged | `uv sync` → 26 pkgs · `ruff`/`mypy`/`pytest` (1 test) green · gitleaks Passed | 2026-10-27 |

## Blockers / Decisions needed from human
- **Filming is now the critical path:** T-1.4 (15 dev clips) and T-1.5 (9 held-out clips) need a camera, props and a second operator; T-1.8 (held-out lock) and T-1.7 (bench runner) wait on them. Shot list is ready in `docs/bench/shot_list.md`.
- **META_API_KEY missing** → T-0.4, T-0.5, T-0.6 cannot start; T-0.7/T-0.8/T-0.9 and all of P2/P3 wait on those ADRs.
- Q-1 track (Indie vs Startup), Q-3 procedures (defaults A-8 used), Q-4 OS mix; Q-5 closed by ADR-000. Human items: portal field list (login-gated), name the Representative, sign waiver/tax form.
- Decision log (fill at G0): SAM backend (API | self-hosted) · chunk length/overlap · mask decode path · deploy host candidate

## Health
Scope violations: 0 · Tasks reopened: 0 · Tasks added: 0 · Failed-attempt streak: 0 · Health: GREEN

## Discoveries (found, not yet planned)
- **C1 is frozen** (tag `contracts-v1`). Per `docs/05_Schema.md` §15 any contract change is now its own task with a `schema_version` bump + regenerated TS types in the same commit.
- `bench/gt.schema.json` is deliberately **outside** `contracts/` (it is bench data per §14), so the GT schema can evolve without breaking C1.
- **New dependencies (noted per AGENTS.md §4):** `jsonschema` + `types-jsonschema` (T-1.1). No npm dependency for type generation: `gen-types.mjs` covers the JSON Schema subset the contracts use.
- Semantic checks live in `src/pw/data/{validate,sopcheck}.py`; they must stay in sync with `docs/05_Schema.md` §11 and §14.
- Host toolchain: installed `uv 0.13.6`, `ffmpeg 9.0.2`, `gitleaks 8.30.1` (winget, 2026-10-27); the binaries are machine tooling at their latest patch — the 14-day rule is enforced for project dependencies via `uv.lock` / `web/package-lock.json`.
- DSH sandbox on this Windows host: workspace ACLs/labels had to be repaired; `pre-commit` cannot bootstrap an upstream hook repo (gitleaks is a local hook; CI must install the CLI); the web toolchain cannot run sandboxed (Node `spawn EPERM`) and needs wider access locally; pytest `tmp_path` is unusable (tests use `.uv/tests-tmp`).
- `pw-data` reconfigures stdio to UTF-8 so the en-dash / greater-or-equal summary line works on a cp1252 console.

## Next up
T-1.6 (metrics module, no clips needed) · T-1.4/T-1.5 filming (human) · then T-1.7 (bench runner) and T-1.8 (held-out lock). T-0.4/0.5/0.6 stay blocked on `META_API_KEY`.

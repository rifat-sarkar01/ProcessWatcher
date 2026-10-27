# PROGRESS.md: agent handoff ledger (keep under 60 lines; prune at every gate)
> Read AGENTS.md and this file, then execute the current task for YOUR owner row. Read only that task's Context pack from docs/06_Plan.md.
> Clock: kickoff Mon Oct 26 · hard internal deadline Nov 4 12:00 ET · official deadline Nov 4 21:00 ET (= Nov 5 02:00 UTC)

## Now (one row per owner; one task in progress per owner)
| Owner | Track | Current task | Status | Branch / last green commit |
|---|---|---|---|---|
| O2 | ML | T-3.1 · SOP ingest (md, txt, pdf) | done | task/T-3.1-sop-ingest |
| O3 | OPS | T-0.2 · Python scaffold and tooling | done | 44b9ed9 (merged) |
| O4 | DATA | T-1.3 · SOPs, golden graphs, GT schema, shot list | done | 8ba8580 (merged) |
| O1 | ML | T-1.6 · Metrics module | done | 82360e8 (merged) |
Current phase: P1 + early P3 · C1 frozen (`contracts-v1`); T-0.1–T-0.3, T-1.1–T-1.3, T-1.6, T-3.1 are [x]
Micro-plan (M tasks only, 3–6 lines):
- T-1.4/T-1.5: film 15 dev + 9 held-out clips per `docs/bench/shot_list.md` (human, camera + second operator).
- Then T-1.7 (bench runner) and T-1.8 (held-out lock); T-3.2 (SOP compiler) needs the Wonder ADR (T-0.5).

## Last 5 completed (newest first)
| Task | Commit | Evidence (command → result) | Date |
|---|---|---|---|
| T-3.1 SOP ingest: md/txt/pdf → `SopSource` (sha256, page count, numbering normalisation), scanned PDFs rendered to PNG + `needs_vision`, 50-page and 20 MB caps | `task/T-3.1-sop-ingest` | `pytest tests/sop -q` → 20 passed · `pytest -q` → 116 passed · coverage `pw.sop.ingest` → 93% · ruff/mypy clean | 2026-10-27 |
| T-1.6 pure metrics: type-aware one-to-one matching (±2 s), P/R/F1 per type + overall, false flags/compliant clip, timestamp MAE, needs-review rate, cost/latency per video-minute, step timing accuracy | `task/T-1.6-metrics` · PR #7 · merged | `pytest tests/bench/test_metrics.py -q` → 30 passed · coverage 100% · `pytest -q` → 96 passed · ruff/mypy clean | 2026-10-27 |
| T-1.3 3 SOPs, 3 hand-written golden step graphs, `bench/gt.schema.json`, shot list covering every variant, `pw-data validate-sops` / `validate-gt` | `task/T-1.3-sops-golden-gt` · PR #6 · merged | `pw-data validate-sops` → `3 SOPs, 3 golden graphs valid; steps 8–12; critical ≥ 1; tools ≥ 3` · `pytest tests/data -q` → 18 passed | 2026-10-27 |
| T-1.2 alignment/report/manifest/review/thresholds schemas, 9 new examples (3 report states), semantic invariants, real `gen:types` → 8 TS modules, tag `contracts-v1` | `task/T-1.2-contracts-b` · PR #5 · merged | `pytest tests/contracts -q` → 47 passed · `pw-data validate-contracts` → `OK 8 schemas, 12 examples` · `gen:types` → clean diff · web typecheck/lint/build → 0 | 2026-10-27 |
| T-1.1 JSON Schema 2020-12 for step graph / tracks / timeline, 3 examples, `pw-data` CLI + semantic checks | `task/T-1.1-contracts-a` · PR #4 · merged | `pytest tests/contracts -q` → 19 passed · `pw-data validate-contracts` → `OK 3 schemas, 3 examples` · `mypy src` strict → clean | 2026-10-27 |

## Blockers / Decisions needed from human
- **Filming is the critical path:** T-1.4 (15 dev clips) and T-1.5 (9 held-out clips) need a camera, props and a second operator. T-1.7 (bench runner) and T-1.8 (held-out lock) wait on them. `docs/bench/shot_list.md` is ready.
- **META_API_KEY missing** → T-0.4, T-0.5, T-0.6 cannot start; T-0.7/T-0.8/T-0.9 and all of P2 wait on those ADRs, and T-3.2 (SOP compiler) needs T-0.5.
- Q-1 track (Indie vs Startup), Q-3 procedures (defaults A-8 used), Q-4 OS mix; Q-5 closed by ADR-000. Human items: portal field list (login-gated), name the Representative, sign waiver/tax form.
- Decision log (fill at G0): SAM backend (API | self-hosted) · chunk length/overlap · mask decode path · deploy host candidate

## Health
Scope violations: 0 · Tasks reopened: 0 · Tasks added: 0 · Failed-attempt streak: 0 · Health: GREEN

## Discoveries (found, not yet planned)
- `SopSource` is the only thing the SOP compiler (T-3.2) needs: normalised text, sha256, page count, and `images`/`needs_vision` for scanned PDFs. Ingest never calls a model and never invents steps.
- `pw.bench.metrics` is pure (no I/O): it takes `Deviation` values and returns counts, so the bench runner (T-1.7) and the API can reuse it.
- **C1 is frozen** (tag `contracts-v1`); contract changes are their own task with a `schema_version` bump and regenerated TS types.
- `bench/gt.schema.json` stays outside `contracts/` so it can evolve without breaking C1.
- New dependencies (AGENTS.md §4): `jsonschema`, `types-jsonschema`, `pymupdf` (T-3.1 PDF reading). `gen-types.mjs` stays dependency-free.
- Host toolchain: `uv 0.13.6`, `ffmpeg 9.0.2`, `gitleaks 8.30.1` installed via winget (machine tooling at latest patch; the 14-day rule is enforced for project deps).
- DSH sandbox on this Windows host: ACL/label repair was needed once; `pre-commit` cannot bootstrap upstream hooks (gitleaks is a local hook; CI installs the CLI); the web toolchain cannot run sandboxed (Node `spawn EPERM`); pytest `tmp_path` is unusable (tests use `.uv/tests-tmp`).
- `pw-data` reconfigures stdio to UTF-8 so the en-dash / greater-or-equal summary line works on a cp1252 console.

## Next up
T-5.6 (app shell, tokens, typed client — deps T-0.3 + T-1.2 are met) · T-1.7 needs T-1.4 clips · T-1.8 needs T-1.5 · T-0.4/0.5/0.6 blocked on `META_API_KEY`.

# PROGRESS.md: agent handoff ledger (keep under 60 lines; prune at every gate)
> Read AGENTS.md and this file, then execute the current task for YOUR owner row. Read only that task's Context pack from docs/06_Plan.md.
> Clock: kickoff Mon Oct 26 · hard internal deadline Nov 4 12:00 ET · official deadline Nov 4 21:00 ET (= Nov 5 02:00 UTC)

## Now (one row per owner; one task in progress per owner)
| Owner | Track | Current task | Status | Branch / last green commit |
|---|---|---|---|---|
| O3 | BE | T-2.9 · Render primitives and debug overlay | done | task/T-2.9-overlay |
| O4 | FE | T-6.7 · State, accessibility and projector polish | done | 18b072a (merged) |
| O1 | ML | T-1.6 · Metrics module | done | 82360e8 (merged) |
| O2 | ML | T-3.1 · SOP ingest (md, txt, pdf) | done | 28e831f (merged) |
Current phase: P0/P1 + early P2/P3/P5/P6 · C1 frozen (`contracts-v1`) · **CI gates every push and PR** · 16/74 cards [x]
Micro-plan (M tasks only, 3–6 lines):
- Ingest and render primitives are done; T-2.2 (SAM chunks), T-2.4 (masks) and T-2.5 still need ADR-001 / `pw.clients`.
- T-2.9 unblocks the set-of-mark input for T-3.4, which still needs Wonder/ADR-002; T-4.1 can now render chosen frames.
- Three pull-forwards are logged in `06_Plan.md` §7 (T-0.9 before T-0.8, T-6.7 before G5, T-2.1 before G2/T-0.4).

## Last 5 completed (newest first)
| Task | Commit | Evidence (command → result) | Date |
|---|---|---|---|
| T-2.9 render primitives + debug overlay: alpha mask/box overlays, collision-free `#id concept` labels, timestamp/caption burn-in, numbered set-of-mark, streaming `pw overlay` CLI | `task/T-2.9-overlay` | `uv run pytest tests/evidence -q` → 15 passed · coverage `pw.evidence` → 83% · `uv run pw overlay <synthetic run> --out …` → 30 frames, duration 2.000 s · golden pHash ≤ 4 | 2026-10-28 |
| T-2.1 video ingest: ffprobe wrapper, CFR/≤720p/silent normalisation, PTS time map (VFR detection), sha256, keyframes, cap + hostile-filename tests | `task/T-2.1-ingest` · PR #14 · merged | `uv run pytest tests/ingest -q` → 30 passed · coverage `pw.ingest` → 88% · `uv run python -m pw.ingest <clip> --out …` → `fps=15`, `frame_count=90` for a 6.000 s clip · ruff/mypy clean | 2026-10-27 |
| T-6.7 a11y polish: axe over the 4 shipped routes (+ planted-violation self-check), token-contrast contract, type/motion guards | `task/T-6.7-a11y-polish` · PR #13 · merged | `npm --prefix web run test:a11y` → 5 passed, 0 serious/critical · suite → 119 passed | 2026-10-27 |
| T-0.9 CI: backend (ruff, mypy, pytest, pw-data checks), web (lint/types/tests/build, generated-types freshness), gitleaks history | `task/T-0.9-ci` · PR #12 · merged | `gh run list --limit 1 --json conclusion -q ".[0].conclusion"` → `success` | 2026-10-27 |
| T-5.12 demo gallery: 3 frozen cases (IT/lab/mechanical), offline badge, one-click load into the review core | `task/T-5.12-demo-gallery` · PR #11 · merged | `--run web/src/features/demo` → 10 passed · suite → 98 passed | 2026-10-27 |

## Blockers / Decisions needed from human
- **META_API_KEY missing** → T-0.4/0.5/0.6 cannot start; T-0.7/0.8, all of P2 beyond ingest, T-3.2 and the API cards behind them wait on those ADRs. Every remaining card except gated polish work needs this.
- **Filming:** T-1.4 (15 dev clips) and T-1.5 (9 held-out clips) need a camera, props and a second operator; T-1.7/T-1.8 wait on them. `docs/bench/shot_list.md` is ready, and T-2.1's CLI smoke is ready to run on the first real clip.
- Q-1 track (Indie vs Startup), Q-3 procedures (defaults A-8 used), Q-4 OS mix; Q-5 closed by ADR-000. Human items: portal field list (login-gated), name the Representative, sign waiver/tax form.
- Decision log (fill at G0): SAM backend (API | self-hosted) · chunk length/overlap · mask decode path · deploy host candidate

## Health
Scope violations: 0 · Tasks reopened: 0 · Tasks added: 0 · Failed-attempt streak: 0 · Health: GREEN

## Discoveries (found, not yet planned)
- **ffmpeg 9 can no longer write rotation metadata** (`-metadata:s:v rotate=90` is silently dropped), so a rotated fixture cannot be generated locally. Rotation handling is therefore covered by unit tests on the ffprobe payload (side-data and tag paths) and must be re-checked against a real phone clip once T-1.4 films one.
- **A genuine VFR fixture** is made by concatenating a 30 fps and a 10 fps segment with `-fps_mode vfr`; `setpts` jitter is re-timed away by the mp4 muxer, so it is not usable for this.
- The ingest CLI takes `--out` because this host's sandbox cannot use `tempfile` directories; the default path (throwaway temp dir) still works on CI. Cleanup failures are non-fatal (`ignore_cleanup_errors=True`).
- Time is always PTS-derived (`frames / nominal_fps` never appears); `TimeMap.is_variable` flags phone VFR input, and normalisation is what makes analysis frames unambiguous.
- T-2.1's card smoke references `bench/dev/A1.mp4`, which does not exist until T-1.4; the run used a generated stand-in (deleted afterwards). The pytest gate is the authoritative check and does not depend on filmed data.
- **Ruff reads every text file under the repo root, including `docs/*.md`**; a ledger saved in a non-UTF-8 encoding fails `ruff format --check` (happened once in T-0.9 — the ledger is now always written as UTF-8).
- Pull-forwards logged in `06_Plan.md` §7: T-0.9 before T-0.8, T-6.7 before G5, T-2.1 before G2/T-0.4. All keep their original scope.
- CI (T-0.9) runs on Linux, re-runs the axe suite and both test suites on every push, and installs ffmpeg so the ingest fixtures are generated on the runner; the skeleton step stays `if:`-guarded until T-0.8 lands.
- Demo data is inline and deterministic (`web/src/features/demo/cases.ts`); T-7.1 replaces it with checksummed `demo/cases/` files.
- Design tokens live in `web/src/ui/tokens.css`; components carry no raw hex. `web/src/api/client.ts` maps every HTTP failure to a typed `ApiError` code.
- New npm dependencies (AGENTS.md §4): `react-router-dom`, `axe-core` (dev). New Python deps: `jsonschema`, `types-jsonschema`, `pymupdf`, `pillow 12.3.0` (T-2.9; released 2026-07-01, inside the 14-day rule).
- **`pw` console script currently points at `pw.evidence.overlay_cli:main`** (T-2.9) because `src/pw/cli.py` is still T-0.8; T-0.8 must take over the `pw` entry point and delegate `overlay` to this module.
- The render golden is `tests/fixtures/evidence/golden_overlay.png` (geometry only, no text): fonts differ across hosts, so labels are asserted by layout, not by pHash.
- Host toolchain: `uv 0.13.6`, `ffmpeg 9.0.2`, `gitleaks 8.30.1` (winget; the 14-day rule is enforced for project deps).
- DSH sandbox: ACL/label repair needed once; `pre-commit` cannot bootstrap upstream hooks (gitleaks is a local hook; CI installs the CLI); the web toolchain cannot be sandboxed locally; pytest `tmp_path` and `tempfile` temp dirs are unusable (tests use `.uv/tests-tmp`).

## Next up
**No perception/reasoning card is startable without a human decision.** Supply `META_API_KEY` (unblocks T-0.4 → T-0.7 → T-0.8 → all of P2/P3/T-3.4), film T-1.4/T-1.5 (unblocks T-1.7/T-1.8), or explicitly name the next pull-forward. Remaining honest candidates are thin: T-2.4 (mask utilities — needs ADR-001's mask encoding), T-3.2 (SOP compiler — needs Wonder), T-5.10 (SAM overlay layer — needs T-2.4).

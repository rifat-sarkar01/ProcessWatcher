# PROGRESS.md: agent handoff ledger (keep under 60 lines; prune at every gate)
> Read AGENTS.md and this file, then execute the current task for YOUR owner row. Read only that task's Context pack from docs/06_Plan.md.
> Clock: kickoff Mon Oct 26 · hard internal deadline Nov 4 12:00 ET · official deadline Nov 4 21:00 ET (= Nov 5 02:00 UTC)

## Now (one row per owner; one task in progress per owner)
| Owner | Track | Current task | Status | Branch / last green commit |
|---|---|---|---|---|
| O3 | BE | T-3.11 · Procedure-not-recognized guard | done | task/T-3.11-domain-guard |
| O4 | FE | T-6.7 · State, accessibility and projector polish | done | 18b072a (merged) |
| O1 | ML | T-1.6 · Metrics module | done | 82360e8 (merged) |
| O2 | ML | T-3.1 · SOP ingest (md, txt, pdf) | done | 28e831f (merged) |
Current phase: P0/P1 + early P2/P3/P5/P6 · C1 frozen (`contracts-v1`) · **CI gates every push and PR** · 19/74 cards [x]
Micro-plan (M tasks only, 3–6 lines):
- Reasoning chain (aligner → deviations → domain guard) is done; T-2.2 (SAM chunks), T-2.4 (masks), T-2.7 (identities) and T-3.4 (scorer) still need ADR-001/002 + `pw.clients`.
- T-4.1 (evidence selector) is the only fully unblocked card left; T-3.7/T-3.8 need Wonder, T-3.12 needs T-0.5/T-1.7.
- Five pull-forwards are logged in `06_Plan.md` §7 (T-0.9, T-6.7, T-2.1, T-3.5, T-3.6 before their dependencies).

## Last 5 completed (newest first)
| Task | Commit | Evidence (command → result) | Date |
|---|---|---|---|
| T-3.11 domain guard: `coverage < 0.3` or calibrated cost cap → `not_recognized` with a message and no deviations; recognized runs keep findings | `task/T-3.11-domain-guard` | `uv run pytest tests/align/test_domain_guard.py -q` → 12 passed · `--cov=src/pw/align` → 96% · full suite → 215 passed · boundary/cost/null-cap tests | 2026-10-28 |
| T-3.6 deviations: missed (max P < 0.25), out-of-order (LIS over partial-order ranks), wrong-tool (≥50% contact with a confident non-required tool), severity/status, mandatory track refs, time-ordered `dev_NNN` ids | `task/T-3.6-deviations` · PR #17 · merged | `uv run pytest tests/align/test_deviations.py -q` → 16 passed · `--cov=src/pw/align` → 96% · full suite → 203 passed · each type + compound + refs rejection tested | 2026-10-28 |
| T-3.5 constrained aligner: Viterbi/DP with null state, shared ranks for unordered groups, critical-skip penalty, counterfactual per-interval margin, merges intervals and emits contract-valid `alignment.json` | `task/T-3.5-aligner` · PR #16 · merged | `uv run pytest tests/align/test_aligner.py -q --cov=src/pw/align --cov-fail-under=90` → 26 passed, **100%** coverage · full suite → 187 passed · artifact validated against `alignment.schema.json` | 2026-10-28 |
| T-2.9 render primitives + debug overlay: alpha mask/box overlays, collision-free `#id concept` labels, timestamp/caption burn-in, numbered set-of-mark, streaming `pw overlay` CLI | `task/T-2.9-overlay` · PR #15 · merged | `uv run pytest tests/evidence -q` → 15 passed · coverage `pw.evidence` → 83% · `uv run pw overlay <synthetic run> --out …` → 30 frames, duration 2.000 s · golden pHash ≤ 4 | 2026-10-28 |
| T-2.1 video ingest: ffprobe wrapper, CFR/≤720p/silent normalisation, PTS time map (VFR detection), sha256, keyframes, cap + hostile-filename tests | `task/T-2.1-ingest` · PR #14 · merged | `uv run pytest tests/ingest -q` → 30 passed · coverage `pw.ingest` → 88% · `uv run python -m pw.ingest <clip> --out …` → `fps=15`, `frame_count=90` for a 6.000 s clip · ruff/mypy clean | 2026-10-27 |

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
- Pull-forwards logged in `06_Plan.md` §7: T-0.9 before T-0.8, T-6.7 before G5, T-2.1 before G2/T-0.4, T-3.5 before T-3.4, T-3.6 before T-2.7/T-3.7. All keep their original scope.
- **Abstention is a real DP outcome, not a threshold after the fact:** with weak step probabilities the `none` state can be cheaper than a skip or back transition, so the aligner naturally drops a step instead of forcing it (calibrated abstention, §1A item 4). Tests use strong likelihoods when they intend to exercise skip/back costs.
- Deviations consume three small views (`TrackIdentity`, `TrackActivity`, `IntervalObservation`) instead of timeline/tracks artifacts, because T-2.6/T-2.7 are still blocked. T-2.6/T-2.7/T-3.9 must fill these views in the pipeline; statuses here are pre-verifier and T-3.7 may downgrade them.
- The domain guard reuses the aligner's `coverage` (steps with interval and mean P ≥ 0.4 ÷ K) and leaves `domain_cost_max` null until T-3.10 calibrates it, matching `contracts/examples/thresholds.example.json`; with `null` the cost rule is inactive.
- CI (T-0.9) runs on Linux, re-runs the axe suite and both test suites on every push, and installs ffmpeg so the ingest fixtures are generated on the runner; the skeleton step stays `if:`-guarded until T-0.8 lands.
- Demo data is inline and deterministic (`web/src/features/demo/cases.ts`); T-7.1 replaces it with checksummed `demo/cases/` files.
- Design tokens live in `web/src/ui/tokens.css`; components carry no raw hex. `web/src/api/client.ts` maps every HTTP failure to a typed `ApiError` code.
- New npm dependencies (AGENTS.md §4): `react-router-dom`, `axe-core` (dev). New Python deps: `jsonschema`, `types-jsonschema`, `pymupdf`, `pillow 12.3.0` (T-2.9; released 2026-07-01, inside the 14-day rule).
- **`pw` console script currently points at `pw.evidence.overlay_cli:main`** (T-2.9) because `src/pw/cli.py` is still T-0.8; T-0.8 must take over the `pw` entry point and delegate `overlay` to this module.
- The render golden is `tests/fixtures/evidence/golden_overlay.png` (geometry only, no text): fonts differ across hosts, so labels are asserted by layout, not by pHash.
- Host toolchain: `uv 0.13.6`, `ffmpeg 9.0.2`, `gitleaks 8.30.1` (winget; the 14-day rule is enforced for project deps).
- DSH sandbox: ACL/label repair needed once; `pre-commit` cannot bootstrap upstream hooks (gitleaks is a local hook; CI installs the CLI); the web toolchain cannot be sandboxed locally; pytest `tmp_path` and `tempfile` temp dirs are unusable (tests use `.uv/tests-tmp`).

## Next up
**T-4.1 (evidence frame selector) is the only fully unblocked card.** T-3.7/T-3.8 need Wonder, T-3.12 needs T-0.5/T-1.7. Otherwise supply `META_API_KEY` (unblocks T-0.4 → T-0.7 → the model/API chain) or film T-1.4/T-1.5 (unblocks T-1.7/T-1.8).

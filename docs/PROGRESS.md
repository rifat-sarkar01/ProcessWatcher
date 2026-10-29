# PROGRESS.md: agent handoff ledger (keep under 60 lines; prune at every gate)
> Read AGENTS.md and this file, then execute the current task for YOUR owner row. Read only that task's Context pack from docs/06_Plan.md.
> Clock: kickoff Mon Oct 26 · hard internal deadline Nov 4 12:00 ET · official deadline Nov 4 21:00 ET (= Nov 5 02:00 UTC)

## Now (one row per owner; one task in progress per owner)
| Owner | Track | Current task | Status | Branch / last green commit |
|---|---|---|---|---|
| O3 | BE | T-4.6 · Report assembly | done | task/T-4.6-report-assembly |
| O4 | FE | T-6.7 · State, accessibility and projector polish | done | 18b072a (merged) |
| O1 | ML | T-2.6 · Event extraction → timeline.json | done | task/T-2.6-events |
| O2 | ML | T-3.8 · Grounded explanation writer | done | task/T-3.8-explanation-writer |
Current phase: P0/P1 + early P2/P3/P5/P6 · C1 frozen (`contracts-v1`) · **CI gates every push and PR** · 26/74 cards [x]
Micro-plan (M tasks only, 3–6 lines):
- T-3.8's validator/retry/fallback are done behind a `Writer` callable; T-3.9 must pass a `pw.clients` writer and feed the result into `build_report(explanations=...)`.
- T-2.6 emits contract-valid `timeline.json` events (holds, contacts, moves, zone enter/exit, debounced); T-2.8 (segments) is the last buildable card and consumes `pw.timeline.events`.
- Still blocked: T-2.2/T-2.4/T-2.7/T-3.4 on ADR-001/002 + `pw.clients`; T-3.7/T-3.8 on Wonder; T-4.3/T-4.4 on Muse Image/Wonder; T-3.12 on T-0.5/T-1.7.
- Five pull-forwards are logged in `06_Plan.md` §7 (T-0.9, T-6.7, T-2.1, T-3.5, T-3.6 before their dependencies).

## Last 5 completed (newest first)
| Task | Commit | Evidence (command → result) | Date |
|---|---|---|---|
| T-2.6 event extraction: hold/contact start-end (tool↔part while held), moves from normalised velocity, zone enter/exit via centroid-in-mask, 0.3 s debounce merge, confidence = mean score × coverage, deterministic `evt_NNN` ids, contract-valid `timeline.json` | `task/T-2.6-events` | `uv run pytest tests/timeline -q --cov=src/pw/timeline --cov-fail-under=90` → 29 passed, 97% · events.py → 99% · full suite → 342 passed · `gitleaks detect` → no leaks · pick-up/put-down, tool swap, drop, zone, debounce, idempotent/reversed-input cases | 2026-10-28 |
| T-2.5 interaction features: dilated hand-mask contact over object area (polygon, box fallback), hold hysteresis with gap bridging, proximity in hand diagonals, velocity normalised by frame diagonal | `task/T-2.5-interaction-features` · PR #24 | `uv run pytest tests/timeline/test_features.py -q` → 13 passed · `pw.timeline` coverage → 95% · full suite → 327 passed (with T-2.3 merged) · static/brief-touch/flicker/two-hands cases | 2026-10-28 |
| T-2.3 cross-chunk stitching: Hungarian IoU matching in overlaps, appearance re-association over gaps, concept barrier, deterministic `trk_NNN` ids, contract-valid `tracks.json` with `source_chunks` + fragmentation stats | `task/T-2.3-stitching` | `uv run pytest tests/perception/test_stitch.py -q` → 15 passed · `pw.perception` coverage → 94% · full suite → 314 passed · artifact validated against `tracks.schema.json` | 2026-10-28 |
| T-3.8 grounded explanations: constrained prompt, validator (≤ 2 sentences / ≤ 40 words / step cited / ±0.5 s timestamps / procedure-vocabulary tools), ≤ 2 retries, deterministic template fallback behind an injected `Writer` | `task/T-3.8-explanation-writer` | `uv run pytest tests/align/test_explain.py -q` → 20 passed · explain.py coverage → 100% · full suite → 299 passed · retry/fallback/invented-time/unknown-tool cases | 2026-10-28 |
| T-4.6 report assembly: joins lanes/deviation/evidence/illustration, deterministic ordering, summary counts, `procedure_not_recognized` shape, kind guard, report + manifest validated against the contracts, `write_report` writes both | `task/T-4.6-report-assembly` | `uv run pytest tests/report/test_build.py -q` → 16 passed · `pw.report` coverage → 92% · full suite → 279 passed · `uv run pw-data validate-artifact <run>/report.json` → `OK (report)` and `manifest.json` → `OK (manifest)` | 2026-10-28 |

## Blockers / Decisions needed from human
- **META_API_KEY missing** → T-0.4/0.5/0.6 cannot start; T-0.7/0.8, all of P2 beyond ingest, T-3.2 and the API cards behind them wait on those ADRs. Every remaining card except gated polish work needs this.
- **Filming:** T-1.4 (15 dev clips) and T-1.5 (9 held-out clips) need a camera, props and a second operator; T-1.7/T-1.8 wait on them. `docs/bench/shot_list.md` is ready, and T-2.1's CLI smoke is ready to run on the first real clip.
- Q-1 track (Indie vs Startup), Q-3 procedures (defaults A-8 used), Q-4 OS mix; Q-5 closed by ADR-000. Human items: portal field list (login-gated), name the Representative, sign waiver/tax form.
- Decision log (fill at G0): SAM backend (API | self-hosted) · chunk length/overlap · mask decode path · deploy host candidate

## Health
Scope violations: 0 · Tasks reopened: 0 · Tasks added: 0 · Failed-attempt streak: 0 · Health: GREEN

## Discoveries (found, not yet planned)
- **ffmpeg 9 can no longer write rotation metadata** (`-metadata:s:v rotate=90` is silently dropped), so a rotated fixture cannot be generated locally. Rotation handling is therefore covered by unit tests on the ffprobe payload (side-data and tag paths) and must be re-checked against a real phone clip once T-1.4 films one.
- Time is always PTS-derived (`frames / nominal_fps` never appears); `TimeMap.is_variable` flags phone VFR input, and normalisation is what makes analysis frames unambiguous.
- **Ruff reads every text file under the repo root, including `docs/*.md`**; a ledger saved in a non-UTF-8 encoding fails `ruff format --check` (happened once in T-0.9 — the ledger is now always written as UTF-8).
- **Abstention is a real DP outcome, not a threshold after the fact:** with weak step probabilities the `none` state can be cheaper than a skip or back transition, so the aligner naturally drops a step instead of forcing it (calibrated abstention, §1A item 4). Tests use strong likelihoods when they intend to exercise skip/back costs.
- Deviations consume three small views (`TrackIdentity`, `TrackActivity`, `IntervalObservation`) instead of timeline/tracks artifacts, because T-2.6/T-2.7 are still blocked. T-2.6/T-2.7/T-3.9 must fill these views in the pipeline; statuses here are pre-verifier and T-3.7 may downgrade them.
- The domain guard reuses the aligner's `coverage` (steps with interval and mean P ≥ 0.4 ÷ K) and leaves `domain_cost_max` null until T-3.10 calibrates it, matching `contracts/examples/thresholds.example.json`; with `null` the cost rule is inactive.
- Stitching matches on shared analysis frame indices (polygon IoU at 64x64, box fallback); features rasterise masks the same way with a 2-cell dilation, score contact as `overlap / object area` and bridge hold gaps up to `bridge_s`. Mask-encoding IoU stays with T-2.4/ADR-001.
- Explanations use `mm:ss.cc` timestamps so the ±0.5 s check is exact; the report builder still formats its template as `mm:ss`. Tool detection is a narrow phrase pattern around with/using/used/needs/requires, and the caller passes the procedure vocabulary (tools and parts), so parts such as `bolt` are not misread as unknown tools.
- Evidence items and illustration blocks are optional inputs to the report builder: a deviation with no evidence gets `evidence_unavailable: true` and a deviation with no illustration gets a reason string, so T-3.9 can assemble partial reports before T-4.3/T-4.4 land.
- The illustration watermark is drawn with Pillow's default font (no font files are vendored); the guard lives in `pw.evidence.labeling` and the report builder calls `assert_evidence_kinds` before schema validation.
- Evidence provenance compares a 64-bit dHash with an 8-bit budget rather than bytes: ffmpeg/font builds differ across hosts, so re-renders are never byte-identical. The item still carries exact `output_sha256` for tamper detection of the stored PNG, and verification re-renders from `stages/tracks.json` + `media/analysis.mp4` next to the report.
- The evidence selector takes a `FrameProvider` callable, not a video path: T-4.2/T-3.9 can pass a decoder, tests pass synthetic PIL frames. Missed deviations seed the gap brackets and out-of-order seeds one frame per swapped window before score-filling, so the strategy survives noisy scores; zero usable frames or unreadable frames return `evidence_unavailable` reasons instead of placeholders.
- CI (T-0.9) runs on Linux, re-runs the axe suite and both test suites on every push, and installs ffmpeg so the ingest fixtures are generated on the runner; the skeleton step stays `if:`-guarded until T-0.8 lands.
- New npm dependencies (AGENTS.md §4): `react-router-dom`, `axe-core` (dev). New Python deps: `jsonschema`, `types-jsonschema`, `pymupdf`, `pillow 12.3.0` (T-2.9; released 2026-07-01, inside the 14-day rule).
- **`pw` console script currently points at `pw.evidence.overlay_cli:main`** (T-2.9) because `src/pw/cli.py` is still T-0.8; T-0.8 must take over the `pw` entry point and delegate `overlay` and `verify-evidence` (dispatched in `overlay_cli.main` to `provenance.verify_cli`).
- The render golden is `tests/fixtures/evidence/golden_overlay.png` (geometry only, no text): fonts differ across hosts, so labels are asserted by layout, not by pHash.
- Host toolchain: `uv 0.13.6`, `ffmpeg 9.0.2`, `gitleaks 8.30.1` (winget; the 14-day rule is enforced for project deps).
- Timeline events derive contacts as held-tool ↔ contacted-part (the hand's contact window with the part while the same hand holds the tool), deduped by unordered pair with the earliest sorted hold winning; zones arrive as `Track`s passed via `zones=`, so no SOP import is needed. Debounce merges same-type/same-tracks events, keeping the earliest start, latest end and max confidence.
- DSH sandbox: ACL/label repair needed once; `pre-commit` cannot bootstrap upstream hooks (gitleaks is a local hook; CI installs the CLI); the web toolchain cannot be sandboxed locally; pytest `tmp_path` and `tempfile` temp dirs are unusable (tests use `.uv/tests-tmp`).

## Next up
**T-2.8 (segments) is the only buildable card left** (needs T-2.6 merged). Everything else needs `META_API_KEY` (T-0.4–0.8, T-2.2/T-2.4/T-2.7, T-3.2–T-3.4/T-3.7/T-3.9, T-4.3/T-4.4, all P5), filmed clips (T-1.4/T-1.5/T-1.7/T-1.8/T-3.12/T-6.x/T-7.x) or ADR-001/002/003. Next real input needed: `META_API_KEY`, filmed T-1.4/T-1.5, or a new pull-forward approval.

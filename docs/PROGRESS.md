# PROGRESS.md: agent handoff ledger (keep under 60 lines; prune at every gate)
> Read AGENTS.md and this file, then execute the current task for YOUR owner row. Read only that task's Context pack from docs/06_Plan.md.
> Clock: kickoff Mon Oct 26 · hard internal deadline Nov 4 12:00 ET · official deadline Nov 4 21:00 ET (= Nov 5 02:00 UTC)

## Now (one row per owner; one task in progress per owner)
| Owner | Track | Current task | Status | Branch / last green commit |
|---|---|---|---|---|
| O1 | ML | T-2.10 · Perception check on dev | tool merged; **2/15 PASS** (fragmentation), card open | PR #70 |
| O2 | ML | T-4.4 · Illustration QA loop | done | task/T-4.4-illustration-qa |
| O3 | OPS | T-7.2 · Container and deploy | blocked: no Docker/flyctl on this machine | scaffold merged |
| O4 | DOC | T-7.5 · Submission package | done | fix/T-3.6-parts-neutral |
Current phase: P0–P3/P4/P5 closed; P6 measured; P7 docs done · **67/74 cards [x]** · spend $135.57 / $150 credit

Micro-plan (M tasks only, 3–6 lines):
- **Evaluation is measured, not projected.** Dev (15 clips, in-sample): P 0.054 · R 0.222 · F1 0.087 · 1.67 false flags/compliant · MAE 0.52 s. Held-out (9 clips, single pass, frozen thresholds): P 0.182 · R 0.333 · F1 0.235 [0–0.533] · 0.67 false flags/compliant · MAE 0.08 s · $27.33. `missed` recall is 1.00; out-of-order/wrong-tool land in the review lane or are typed `missed`.
- **Quality fix that mattered:** `SegmentParams.max_s` 20 s → 4 s (one action per scoring window) took A2 from 4 false findings to 1 and rescued stp_03/07/08; split parts now inherit `activity`. The tool-neutral fix also applies to identity labels.
- **T-3.10 constraint is unmet and documented:** the tuner falls back to best F1 and writes `NOT met` in `docs/results/tune_dev.md`; `config/thresholds.json` is frozen at tau_review 0.20 / tau_flag 0.90 (`sha256 1963006…d69a21`).
- **Demo pack is real:** 3 checksummed cases (`keyboard-compliant`, `keyboard-missed-tilt`, `keyboard-heldout-missed-blower`); `/demo/cases` + media routes serve with `PW_MODE=demo`; `pw demo-verify` → 3/3.
- **Remaining cards are human/tool-gated:** T-7.2 needs Docker + flyctl + approval for the public URL; T-7.4 needs a recorded walkthrough; T-7.6 needs a clean machine; T-2.10's branch needs a PR/merge.

## Last 5 completed (newest first)
| Task | Commit | Evidence (command → result) | Date |
|---|---|---|---|
| T-7.5 submission draft | branch | `Select-String … 'Theme:\|Track:\|Models:\|Repo:\|Demo:\|Video:\|Results:'`.Count → 7 | 2026-11-03 |
| T-7.3 README + architecture + checker | branch | `uv run python scripts/readme_check.py` → 15 commands OK · mermaid figure · measured tables · SAM licence noted | 2026-11-03 |
| T-7.1 demo pack + routes | branch | `pw demo-build --spec demo/spec.json` → 3 cases · `pw demo-verify` → 3/3 cases OK · `curl :8010/demo/cases` → 3 · media 200 | 2026-11-03 |
| T-6.2 held-out single pass | branch | `pw-bench run --split heldout --config config/thresholds.json --mode live` → F1 0.235 · `docs/results/heldout.md` has `lock: OK` · `pw-data verify-lock` → LOCK OK | 2026-11-03 |
| T-6.1 + T-3.10 dev numbers | branch | `pw-bench run --split dev --predictor full` → F1 0.087 · `pw-bench ablate --split dev` → 8 rows (5 not run, declared) · `pw-bench tune --split dev` → 0.20/0.90, constraint NOT met | 2026-11-03 |

## Blockers / Decisions needed from human
- **Deploy (T-7.2):** this machine has no `docker`/`flyctl`, so the public-URL done-when cannot run here. Scaffold is committed (`Dockerfile`, `fly.toml`, `deploy/*`); a human with those tools must `docker build`, `fly deploy`, set `META_API_KEY` + `PW_ACCESS_CODE`, then run `pw smoke --url`. **Public deploy needs explicit approval.**
- **Video (T-7.4):** needs a recorded 3-minute walkthrough + 60 s teaser from the demo pack; not producible by an agent.
- **Clean room (T-7.6):** needs a machine that has never seen the repo; README quickstart is the script.
- **T-2.10 branch:** `task/T-2.10-perception-check` holds the perception check + results; open a PR and merge it (it was not part of this branch's touch list).
- **T-2.10 branch merged; the gate fails honestly.** `pw-bench perception-check --split dev --mode live` → 2/15 (required 12). Hand coverage is 94.9–100% and pick-up hit rate 94.1–100% on every clip; the failures are all SAM fragmentation (1.29–2.71 tracks per concept against a 1.5 bar). The table is `docs/results/perception_dev.md`; the card stays `[ ]` until stitching improves.
- Spend: **$135.57 of $150**; no further live runs planned. Q-1 track (Indie), Q-3 procedure (P-A keyboard), Q-4 OS mix, Q-5 rules are settled; portal entry needs the Representative/waiver items from ADR-000.

## Health
Scope violations: 0 · Tasks reopened: 0 · Tasks added: 0 · Failed-attempt streak: 0 · Health: GREEN

## Discoveries (found, not yet planned)
- **Segment resolution dominates precision.** With 20 s windows the scorer merges "wipe keycaps" and "wipe frame" into one label, so every compliant clip gets a high-confidence `missed` for stp_06/07. 4 s windows fix the merging but not the semantic near-duplicate; the remaining fix is a sub-window or per-step spot-check prompt.
- **Replay cannot reuse a live run's stage cache** because `mode` is in the stage key; a same-`run_id` replay re-executes every stage and some scoring requests miss the cache, so live artifacts must never be "re-derived" this way (one A1 run was overwritten and re-run live to restore it).
- **`wrong_tool` is reported as `missed` when the substituted object is not tracked**: without the expected tool the step never aligns. Type-level attribution needs the aligner to treat a tool mismatch as partial evidence.
- **Tuning reclassifies raw `stages/deviations.json` while the bench scores `report.json`**, where the verifier can change status, so tune's false-flag rate (1.00) and the report's (1.67 on dev) differ; both are documented.
- **`.gitignore` had `results/`** (matches `docs/results/` too); changed to `/results/` so the measured results docs are tracked, and `pytest-of-*/` is ignored.
- **The held-out lock hashed checkout bytes, not content.** Windows checked the JSON out as CRLF while CI got LF, so `verify-lock` passed locally and failed in CI. The lock now hashes with `\r\n` normalised to `\n`; the content is unchanged and the lock was regenerated.
- **SAM fragmentation is the perception bottleneck, not hand tracking.** Hand coverage and tool pick-up alignment are ~100%, but one concept becomes 1.7–2.7 tracks. The 4 s scoring windows absorb this today; better stitching is the next quality lever.

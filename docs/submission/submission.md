# Process Watcher — submission

**One-liner:** Process Watcher checks a recorded physical procedure against its SOP and
shows exactly where it went wrong, backed by real-frame evidence.

**Theme:** Push the Frontier — applying frontier multimodal models to a problem that has
never had a machine-checked answer: the physical SOP audit.
**Track:** Indie (solo builder, open-source, MIT).

## Problem

Every regulated physical procedure — IT hardware servicing, lab work, mechanical assembly —
ends with a human signing that the SOP was followed. The video exists, but reviewing hours
of footage is slow, subjective and rarely done. Missed steps, swapped steps and wrong tools
are exactly the errors that cause failures, and they are invisible in the paperwork.

## Solution

Process Watcher watches the video and reports:

- **missed steps**, **out-of-order steps** and **wrong tools**, each with a timestamp;
- a plain-language explanation and the SOP step it belongs to;
- **real-frame evidence** (never generated images) with the hand/tool polygons drawn on it;
- a watermarked "what correct looks like" diagram for each flagged step;
- a JSON report (schema-validated) plus HTML/PDF export, and a review UI to accept or
  overturn each finding.

The decision is deterministic: models supply perception (tracking, labels, likelihoods) and
a constrained dynamic-programming aligner decides compliance. The same artifacts always
produce the same verdict.

## How each model is used

**Models:** SAM 3.1 (tracking), Muse Wonder (SOP compile, scoring, verification,
explanations, illustration QA), Muse Image (reference diagrams).

- **SAM 3.1** segments hands, tools and parts frame-by-frame; its one-bit masks become the
  polygons on the evidence frames and the debug overlay.
- **Muse Wonder** compiles the SOP into a step graph, labels tracks, scores each timeline
  segment against each step (median of three repeats, because temperature 0 is not
  deterministic), verifies findings and writes explanations.
- **Muse Image** draws one diagram per flagged step from a clean reference frame; the
  diagram is watermarked and never appears in the evidence list.

The measured contribution of each component is in the dev ablation table
(`docs/results/ablation_dev.md`). The verifier/writer add explanation quality but do not
change the verdicts; the baselines and two component ablations were not run in this
submission timebox and are marked "not run" rather than invented.

## Results

**Results:** frozen-threshold evaluation, dev (calibration) and held-out (single pass):

<!-- RESULTS -->
| Split | P | R | F1 | F1 95% CI | False flags / compliant clip | Timestamp MAE |
|---|---|---|---|---|---|---|
| dev (15 clips, in-sample) | 0.054 | 0.222 | 0.087 | 0.000–0.186 | 1.67 | 0.52 s |
| held-out (9 clips, single pass) | 0.182 | 0.333 | 0.235 | 0.000–0.533 | 0.67 | 0.08 s |

`missed` recall on the held-out split is **1.00** (both planted missing steps flagged with
confidence 1.0). `out_of_order` and `wrong_tool` are detected but classified into the
review lane or typed as missing steps, so their flag-level recall is 0. Full tables:
`docs/results/heldout.md`, `docs/results/ablation_dev.md`, `docs/results/tune_dev.md`;
ranked failure analysis: `docs/results/failures.md`.

## Demo

**Repo:** https://github.com/rifat-sarkar01/ProcessWatcher
**Demo:** `PW_MODE=demo uv run uvicorn pw.api.main:app --port 8000` → `GET /demo/cases`
returns three frozen, checksummed cases that run with no network and no API key.
**Video:** `docs/demo/demo.mp4` — three-minute walkthrough (teaser `docs/demo/teaser.mp4`).

## What is original

- A deterministic compliance engine over model perception, with abstention built into the
  aligner rather than bolted on as a threshold.
- Evidence provenance: every evidence image is re-derivable from stored tracks and the
  analysis video, verified by a perceptual hash (`pw verify-evidence`).
- An offline, checksummed demo pack so the submission can be judged without spending money.

## Honest limitations

Perception is the bottleneck: very short actions that look like their neighbour ("wipe the
keycaps" vs "wipe the frame") are under-detected, so compliant clips can carry a
high-confidence `missed` finding. Threshold calibration on dev could not reach the planned
false-flag budget; the result is reported, not hidden. The verifier layer improves
explanations more than accuracy. See `docs/results/failures.md` for the ranked failure
analysis and the fix direction for each one.

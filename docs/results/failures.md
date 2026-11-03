# Failure analysis — dev and held-out

Ranked by frequency × impact on the headline numbers. Evidence frames are in each run's
`evidence/` directory (real frames with SAM contours); no illustrations are used here.

### F-01 Compliant clips carry a high-confidence `missed` finding for the late short steps
- **Frequency:** 5 of 6 compliant dev clips after the 4 s segmentation fix (stp_06 flagged),
  and most of the planted clips as an extra finding on top of their true deviation.
- **Symptom:** `missed stp_06` at confidence 0.9–1.0 while the operator performed it.
- **Root cause:** the scorer sees one 3–4 s window that contains the tail of wiping and the
  start of inspection; stp_05 and stp_06 share the same tool (`lint-free cloth`) and look
  nearly identical. The step never wins a segment, so the aligner has to skip it and the
  deviation rule sees a long low-probability window.
- **Fix direction:** ask the scorer for sub-window evidence ("keycaps vs frame") or add a
  per-step spot-check call near the segment end; both cost roughly one Wonder call per step.

### F-02 A short step between two long ones is absorbed by its neighbour
- **Frequency:** stp_07 (inspect, ~1.5 s) in most clips; stp_03 (brush lower half) whenever
  the two brush strokes merge into one continuous contact.
- **Symptom:** the step is either aligned inside the neighbour's interval or reported missed.
- **Root cause:** segments are cut at timeline event changes; a continuous contact window
  has no change point, so a shorter action inside it is invisible to the segmenter.
- **Fix direction:** score at fixed 2 s hops inside long contact windows, or add a
  motion-change detector that cuts on direction reversals even without a hold change.

### F-03 `procedure_not_recognized` on three dev clips
- **Frequency:** 3/15 dev runs in the first live pass.
- **Symptom:** no report; status `not_recognized`, zero deviations.
- **Root cause:** the deterministic coverage guard (`coverage_prob` 0.4 with K steps) is not
  met when SAM loses the hand for a long stretch or the scorer assigns most probability to
  `none`.
- **Fix direction:** keep the guard (it prevents false acceptance), but emit the coverage
  table in the report so an operator can see which step failed; retry track stitching with a
  lower IoU threshold before declaring non-recognition.

### F-04 Near-synonym labels leak into wrong-tool evidence
- **Frequency:** first live pass only; fixed in the parts-neutral change.
- **Symptom:** `wrong_tool` for stp_01/02/04/05 on compliant clips, expected `hand` or
  `cleaning brush`, observed `keyboard` / `hand`.
- **Root cause:** the hold detector attributes every held track to the interval, including
  script parts (keyboard, keycaps) and the hand; Muse Wonder labels a brush as
  "cleaning brush" while the compiled SOP says "brush".
- **Fix:** parts and the hand are neutral, and a step whose only tool is `hand` has no tool
  requirement. Verified by `tests/pipeline/test_observation_filter.py`.

### F-05 Duplicate wrong-tool findings for one step
- **Frequency:** A1 first pass (stp_02 twice), A1 replay (stp_01 once, stp_05 once).
- **Symptom:** two deviations with the same step id and overlapping windows.
- **Root cause:** the alignment can contain two intervals for the same step (a stack/repeat),
  and each interval is classified independently.
- **Fix direction:** merge wrong-tool findings per step per contiguous window before the
  report; deduplication belongs in `pw.align.deviations`.

### F-06 Out-of-order findings sit at the review boundary
- **Frequency:** planted swap clips A10–A12; confidences 0.30–0.31.
- **Symptom:** `out_of_order` with `needs_review`, so it does not count as a flag.
- **Root cause:** the out-of-order confidence is derived from the back-jump margin, which is
  small when the swapped steps have similar likelihoods.
- **Fix direction:** calibrate `lambda_back`/margin on dev swap clips; the current grid only
  tunes the flag and review thresholds.

### F-07 The verifier and writer add cost but rarely change a verdict
- **Frequency:** all runs; 6 verifier + 6 writer calls per run.
- **Symptom:** `no_verifier` and `full` produce the same deviations in the ablation.
- **Root cause:** the verifier is asked to agree, and mostly does; explanations are prose and
  do not feed the decision.
- **Fix direction:** keep the verifier as an explanation layer (as designed), stop counting
  it as an accuracy component in the ablation, or make it veto high-confidence findings.

### F-08 Identity is the slowest stage
- **Frequency:** every run; 4–9 minutes for 9–12 tracks.
- **Symptom:** `identify` dominates wall time (about half of a 20-minute run).
- **Root cause:** three Wonder calls per track, each with three crops, run sequentially under
  the `ModelLimiter` (cap 4).
- **Fix direction:** batch tracks per call (the Wonder payload accepts multiple images) or
  raise the limiter to 8 for identity only; quality risk is low because it is a vote.

### F-09 Windows ledger lock contention
- **Frequency:** once in the first live pass (`Access is denied` renaming `ledger.json.tmp`).
- **Symptom:** one scoring repeat logged a retry message; the run continued.
- **Root cause:** two processes in the same run tried to rename the ledger temp file on
  Windows. The retry handling is correct but noisy.
- **Fix direction:** serialise ledger writes with a per-run lock file on Windows.

### F-10 Illustrations are skipped when the report has no flagged step
- **Frequency:** the $2-cap run and any `not_recognized` run.
- **Symptom:** empty `illustrations/`, `illustrate` stage status `disabled`/`skipped`.
- **Root cause:** the stage only draws diagrams for flagged deviations; a run with none (or
  a cap hit before the stage) has nothing to draw.
- **Fix direction:** none needed for compliance, but the demo pack must use runs that have at
  least one flagged step so the illustration lane is populated.

## Limitations (plain language, for README and video)

Process Watcher sees what the camera sees. It is good at long, distinctive actions and
weak at very short ones that look like their neighbours: separating "wipe the keycaps" from
"wipe the frame" is a few seconds of nearly identical motion. When it is unsure it still
reports the finding, marked for human review, rather than hiding it. The compliance decision
is deterministic and auditable, but the perception underneath it is not perfect, so the
product is a reviewer accelerator, not an autopilot. It also depends on a clear, mostly
top-down view and on the SOP naming the tools the way the operator actually uses them.
# Held-out results — single pass

lock: OK (`pw-data verify-lock`, `bench/HELDOUT.lock` unchanged)

- Config frozen before the run: `config/thresholds.json`
  `sha256 1963006bebcda523639fa025433ec7b475029d4fdb473d1c185d686379d69a21`
  (`tau_review 0.20`, `tau_flag 0.90`)
- 9 clips, one live pass each, no tuning afterwards.
- Mode: live · predictor: `full` · result dir `results/run_01M6GNRH5EWFHY31GZDWJD5P1P`

| Metric | Value |
|---|---|
| Overall P / R / F1 | 0.182 / 0.333 / 0.235 |
| F1 95% CI (1000 clip resamples) | 0.000 – 0.533 |
| `missed` P / R / F1 | 0.182 / 1.000 / 0.308 |
| `out_of_order` P / R / F1 | — / 0.000 / 0.000 |
| `wrong_tool` P / R / F1 | — / 0.000 / 0.000 |
| False flags per compliant clip | 0.67 (compliant clips: A16–A18) |
| Timestamp MAE | 0.08 s |
| Cost | $27.33 total · $5.48 per video-minute |
| Needs-review rate | 65.6% of findings |

## Per clip

| Clip | TP | FP | FN | Flagged | Needs review |
|---|---|---|---|---|---|
| A16 | 0 | 1 | 0 | 1 | 1 |
| A17 | 0 | 1 | 0 | 1 | 3 |
| A18 | 0 | 0 | 0 | 0 | 3 |
| A19 | 1 | 0 | 0 | 1 | 3 |
| A20 | 1 | 1 | 0 | 2 | 1 |
| A21 | 0 | 2 | 1 | 2 | 2 |
| A22 | 0 | 1 | 1 | 1 | 2 |
| A23 | 0 | 2 | 1 | 2 | 3 |
| A24 | 0 | 1 | 1 | 1 | 3 |

## Reading

- **Missed steps are found but not separated from short neighbours.** Both planted
  `missed` deviations (A19 blower, A20 tilt) are flagged with confidence 1.0; every
  compliant clip also carries a `missed stp_06` (wipe frame) finding, because the
  segment scorer cannot separate it from `stp_05` wiping.
- **Out-of-order is detected but sits in review, not flagged** (confidence 0.30), so the
  benchmark counts it as a miss. The classification is right; the calibrated confidence is
  too low.
- **Wrong-tool is reported as `missed`** for the planted wrong-tool clips: without the
  expected tool the step never aligns, and the deviation rule sees a missing step rather
  than a tool substitution.
- Every finding carries a timestamp within 0.1 s of the ground-truth window when it matches.
- Cost is dominated by SAM frames and the three Wonder scoring repeats; it is within the
  $150 credit budget together with all dev runs ($135.57 spent in total).

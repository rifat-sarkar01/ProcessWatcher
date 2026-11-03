# Dev ablation — dev

| Row | P | R | F1 | False flags / compliant clip | Note |
|---|---|---|---|---|---|
| full | 0.054 | 0.222 | 0.087 | 1.67 |
| no_verifier | 0.044 | 0.222 | 0.074 | 2.17 |
| no_aligner (greedy argmax) | — | — | — | — | not run: needs a re-decode |
| no_identity_vote | — | — | — | — | not run: needs per-call identity votes |
| baseline_a (raw video, Wonder) | — | — | — | — | not run: T-3.12 not implemented |
| baseline_b (keyframes, Wonder) | — | — | — | — | not run: T-3.12 not implemented |
| oracle | 1.000 | 1.000 | 1.000 | 0.00 |
| empty | 0.000 | 0.000 | 0.000 | 0.00 |

Full F1 95% CI: 0.000-0.192 (1000 clip resamples).

Cost: $5.24/video-minute · mean wall time: 32.6 min/clip.

## Analysis

Full ≥ baseline B F1 + 0.10 cannot be claimed: the two Wonder baselines and the component recomputations (greedy aligner, identity vote) were not run in this submission. The full pipeline's false flags on compliant clips remain high because SAM tracks parts (keyboard, keycaps) next to tools; parts are now excluded from wrong-tool evidence, but identity noise still leaks through.

# PW-Bench shot list (T-1.3, revised for the delivered dataset)

The delivered footage is a single procedure — cleaning a mechanical keyboard —
filmed as 15 dev clips and 9 held-out clips. The original A/B/C shot list was never
filmed; the keyboard procedure replaces P-A and the clips are labelled `A1`…`A15`
(dev) and `A16`…`A24` (held-out). P-B and P-C remain authored SOPs for SOP-eval only.

**Waiver (2026-11-03, human-approved):** clips are 23.7–54.3 s, so the T-1.4/T-1.5
45 s floor is waived to 20 s; the upper bound stays 180 s. No model runs on
`bench/heldout/*` before T-6.2.

## Setup

| Item | Rule |
|---|---|
| Camera | Phone on a stand, fixed, hands and tools fully in frame |
| Source | 1920×1080, 30 fps |
| Lighting | Dev: overhead room light · Held-out: side light and closer framing |
| Operator | Dev: operator 1 · Held-out: operator 2 |
| Audio | Not used by the pipeline |
| Storage | Clips live outside git (`bench/**/videos/`); `sha256` goes in the split manifest |

**Labeling:** ground truth is written with `bench/gt.schema.json`, then validated with
`uv run pw-data validate-gt <gt> --golden bench/golden/P-A.json` and
`uv run pw-data validate --split dev|heldout`.

## Procedure P-A · Clean a mechanical keyboard (`bench/sops/P-A-keyboard-clean.md`)

Steps: `stp_01` tilt/tap · `stp_02` brush upper · `stp_03` brush lower (2↔3 any order) ·
`stp_04` blower · `stp_05` wipe keycaps · `stp_06` wipe frame · `stp_07` inspect ·
`stp_08` reconnect USB (critical).

| Clip | File | Split | Variant | Deviation (GT) |
|---|---|---|---|---|
| A1 | `dev_01_correct.mp4` | dev | compliant | — |
| A2 | `dev_02_correct.mp4` | dev | compliant | — |
| A3 | `dev_03_correct.mp4` | dev | compliant | — |
| A4 | `dev_04_correct.mp4` | dev | compliant | — |
| A5 | `dev_05_correct.mp4` | dev | compliant | — |
| A6 | `dev_06_correct.mp4` | dev | compliant | — |
| A7 | `dev_07_skipstep_tilttap.mp4` | dev | missed | `missed` stp_01 |
| A8 | `dev_08_skipstep_brush.mp4` | dev | missed | `missed` stp_02 |
| A9 | `dev_09_skipstep_blower.mp4` | dev | missed | `missed` stp_04 |
| A10 | `dev_10_swaporder_blowerbeforebrush.mp4` | dev | out_of_order | `out_of_order` stp_04 |
| A11 | `dev_11_swaporder_pluginbeforewipe.mp4` | dev | out_of_order | `out_of_order` stp_08 |
| A12 | `dev_12_swaporder_wipebeforeblower.mp4` | dev | out_of_order | `out_of_order` stp_05 |
| A13 | `dev_13_wrongtool_card.mp4` | dev | wrong_tool | `wrong_tool` stp_02 (card) |
| A14 | `dev_14_wrongtool_finger.mp4` | dev | wrong_tool | `wrong_tool` stp_02 (finger) |
| A15 | `dev_15_wrongtool_Screwdriver .mp4` | dev | wrong_tool | `wrong_tool` stp_02 (screwdriver) |
| A16 | `held_01_correct.mp4` | held-out | compliant | — |
| A17 | `held_02_correct.mp4` | held-out | compliant | — |
| A18 | `held_03_correct.mp4` | held-out | compliant | — |
| A19 | `held_04_skipstep_blower.mp4` | held-out | single | `missed` stp_04 |
| A20 | `held_05_skipstep_tilttap.mp4` | held-out | single | `missed` stp_01 |
| A21 | `held_06_swaporder_blowerbeforebrush.mp4` | held-out | single | `out_of_order` stp_04 |
| A22 | `held_07_swaporder_pluginbeforewipe.mp4` | held-out | single | `out_of_order` stp_08 |
| A23 | `held_08_wrongtool_screwdriver.mp4` | held-out | single | `wrong_tool` stp_02 (screwdriver) |
| A24 | `held_09_wrongtool_card.mp4` | held-out | single | `wrong_tool` stp_02 (card) |

## Coverage check

| Slice | Clips | Compliant | missed | out_of_order | wrong_tool |
|---|---|---|---|---|---|
| dev | 15 | 6 | 3 | 3 | 3 |
| held-out | 9 | 3 | 2 | 2 | 2 |

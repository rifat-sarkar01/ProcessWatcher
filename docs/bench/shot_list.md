# PW-Bench shot list (T-1.3)

Every clip below is filmed for PW-Bench. The list exists so the dev set (T-1.4, 15 clips)
and the held-out set (T-1.5, 9 clips) cover every deviation variant exactly once per
procedure, with a different operator/camera/lighting for held-out.

**Clip IDs:** `<procedure letter><number>` — `A1`…`A5`, `B1`…`B5`, `C1`…`C5` are dev;
`A6`…`A8`, `B6`…`B8`, `C6`…`C8` are held-out. The number ranges are fixed: never reuse an ID.

## Setup (same for every clip)

| Item | Rule |
|---|---|
| Camera | Phone on a tripod, fixed, hands and tools fully in frame |
| Source | 1080p, ≥ 30 fps, 45–180 s of usable footage |
| Lighting | Dev: overhead room light · Held-out: window side light (different from dev) |
| Operator | Dev: operator 1 · Held-out: operator 2 |
| Angle | Dev: front-left 35° · Held-out: right 45°, higher |
| Audio | Not used by the pipeline; keep it quiet anyway |
| Consent | Each operator signs the filming consent note kept in `docs/bench/` |
| Privacy | Hands and tools only. No faces in frame, no name badges, no documents with personal data |
| Storage | Clips live outside git (`bench/**/videos/`); `sha256` goes in the split manifest |

**Labeling:** ground truth is written the same day as filming with `bench/gt.schema.json`,
to ±0.5 s, then validated with `uv run pw-data validate-gt <gt> --golden bench/golden/P-<X>.json`.
A second person spot-checks 5 labels per split.

## Deviation recipes (how to perform each variant)

| Variant | Recipe |
|---|---|
| `compliant` | Follow `bench/sops/P-<X>-*.md` exactly, including the any-order groups, and show every `visual_check` |
| `missed` | Skip one step completely (the one named in the GT) and continue as if it never existed |
| `out_of_order` | Perform a strict step before the step it must follow (e.g. torque bolt 4 before bolt 3) |
| `wrong_tool` | Use a visually different tool for one step (e.g. adjustable wrench instead of the torque wrench) |
| `mixed` (dev) | One `missed` **and** one `wrong_tool` in the same clip, at least 20 s apart |
| `single` (held-out) | Exactly one deviation, of the type named in the GT |
| `mixed` (held-out) | One `out_of_order` **and** one `missed`, at least 20 s apart |

## P-A · SSD swap in a desktop PC (`bench/sops/P-A-ssd-swap.md`)

| Clip | Split | Variant | Deviation to capture (GT) | Notes |
|---|---|---|---|---|
| A1 | dev | compliant | — | Baseline; both unordered groups (3↔4, 7↔8) executed in the written order |
| A2 | dev | missed | `missed` stp_04 (power cable still plugged) | Keep the mistake visible for ≥ 10 s |
| A3 | dev | out_of_order | `out_of_order` stp_09 before stp_07 | Close the panel before the data cable is reconnected |
| A4 | dev | wrong_tool | `wrong_tool` stp_05 (torque screwdriver instead of Phillips) | Both tools must be visually distinct |
| A5 | dev | mixed | `missed` stp_09 + `wrong_tool` stp_06 | ≥ 20 s between the two deviations |
| A6 | held-out | compliant | — | Operator 2, right 45°, window light |
| A7 | held-out | single | `wrong_tool` stp_08 (SATA power not connected) | Only one deviation in the clip |
| A8 | held-out | mixed | `out_of_order` stp_06 before stp_05 + `missed` stp_10 | ≥ 20 s apart |

## P-B · Prepare 100 ml standard solution (`bench/sops/P-B-standard-solution.md`)

| Clip | Split | Variant | Deviation to capture (GT) | Notes |
|---|---|---|---|---|
| B1 | dev | compliant | — | Swap steps 1↔2 (any-order group) to prove the group is honoured |
| B2 | dev | missed | `missed` stp_06 (no top-up to the mark) | Meniscus visibly below the mark |
| B3 | dev | out_of_order | `out_of_order` stp_09 before stp_06 | Labelling before the flask is topped up |
| B4 | dev | wrong_tool | `wrong_tool` stp_02 (kitchen scale instead of analytical balance) | Different scale body and display |
| B5 | dev | mixed | `missed` stp_05 + `wrong_tool` stp_09 (no marker, uses a pen) | ≥ 20 s apart |
| B6 | held-out | compliant | — | Operator 2, right 45°, window light |
| B7 | held-out | single | `missed` stp_08 (no second meniscus check) | Only one deviation |
| B8 | held-out | mixed | `out_of_order` stp_04 before stp_03 + `missed` stp_07 | ≥ 20 s apart |

## P-C · 4-bolt cross-pattern torque (`bench/sops/P-C-cross-pattern-torque.md`)

| Clip | Split | Variant | Deviation to capture (GT) | Notes |
|---|---|---|---|---|
| C1 | dev | compliant | — | Full 1-3-2-4 cross pattern, stripe and job card |
| C2 | dev | missed | `missed` stp_05 (bolt 2 never torqued) | Wrench must move bolt 3 → bolt 4 |
| C3 | dev | out_of_order | `out_of_order` stp_06 before stp_05 | Bolt 4 before bolt 2 |
| C4 | dev | wrong_tool | `wrong_tool` stp_03 (adjustable wrench instead of torque wrench) | No click cue with the wrong tool |
| C5 | dev | mixed | `missed` stp_07 (no stripe) + `wrong_tool` stp_02 (power driver instead of hand) | ≥ 20 s apart |
| C6 | held-out | compliant | — | Operator 2, right 45°, window light |
| C7 | held-out | single | `out_of_order` stp_04 before stp_03 | Only one deviation |
| C8 | held-out | mixed | `missed` stp_08 + `wrong_tool` stp_06 (short socket) | ≥ 20 s apart |

## Coverage check (must stay true)

| Slice | Clips | Compliant | missed | out_of_order | wrong_tool | mixed |
|---|---|---|---|---|---|---|
| dev | 15 (A1–A5, B1–B5, C1–C5) | 3 | 3 | 3 | 3 | 3 |
| held-out | 9 (A6–A8, B6–B8, C6–C8) | 3 | 2 | 2 | 2 | 3 |

Each procedure therefore has 5 dev variants (compliant, missed, out-of-order, wrong-tool,
mixed) and 3 held-out variants (compliant, single, mixed) — matching `06_Plan.md` T-1.3.

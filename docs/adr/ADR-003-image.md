# ADR-003: Muse Image 1.0 — generate vs edit-with-reference, labels, QA and cost

- **Status:** Accepted
- **Date:** 2026-11-02
- **Task:** T-0.6 (ML, serves FR-10)
- **Deciders:** O1 (perception), O2 (reasoning), O4 (product)
- **Resolves:** the card's questions Q1–Q5 (best mode, label legibility, faces/people avoidance, consistency, latency/$)

## Context

FR-10 needs one clean "what correct looks like" illustration per flagged step: labeled, watermarked,
never mistaken for evidence. TRD §7 defaults to *edit with the annotated real frame as layout
reference* but nothing was verified outside the model name. This spike measured the two image
endpoints live on 2026-11-02 with the project key (spend ≈ $0.25: 9 scored images + probes), on a
synthetic reference frame because **no real hand/tool footage exists yet**. Shape, validity, latency,
variance and cost are settled; visual fidelity on real frames is re-checked at T-1.4/T-4.3.

Sources read: `dev.meta.ai/docs/models`, `dev.meta.ai/docs/pricing-rate-limits`, the live API.
Fixtures in `tests/fixtures/spikes/image/`: raw generate request/response (WebP base64), one raw
Wonder-QA request/response, the reference frame, one PNG per mode, and `summary.json` with all runs.

## Answers

Q1: Best mode — **edit-with-reference** is the default (single multipart `image`), because it keeps the real frame's camera angle, hand position and part layout, which is exactly what the reviewer is comparing against; **text-only generation** is the fallback when no usable annotated frame exists (it produced the most readable, uncluttered schematics); **compose (two inputs)** is reserved for style consistency, since a style reference anchors it tightly (dHash 6–22 vs 77–86 for edit and 92–123 for text). Edit is also faithful to artifacts: the red annotation box became dashed circles, and the synthetic blue rectangles were kept as picture frames — so the reference must be a clean annotated real frame, never a QA mock.
Q2: Label legibility — **9/9 outputs were legible** with a quoted, short, all-caps caption (`'REMOVE 2 SCREWS'`) in the prompt; Wonder QA returned `text_legible: true` and zero hallucinated labels on every run. Long labels and non-English text were not tested; keep captions ≤ 3 words and derive them from the step action.
Q3: Faces/people avoidance — **9/9 outputs showed no people or faces** with the explicit instruction "no faces or people; at most a single gloved hand". A glove is not a guarantee: arms/wrists can enter the frame, so the Wonder QA gate (`people_visible`) must stay mandatory before an illustration is stored.
Q4: Consistency across 3 runs — **text-only is not reproducible**: the composition changes substantially between runs (pairwise dHash 92–123 of 256 bits). Edit narrows it (77–86) and compose with a fixed style image narrows it most (6–22). Same-step illustrations across a report therefore need a fixed style reference (compose) or a deterministic retry loop; a seed parameter is not documented and was not tested.
Q5: Latency and cost — generation median **13.2 s** (9.5–17.3) at 1920×1280, edit **11.8 s** (8.5–21.1) at 1792×1344, compose **15.2 s** (12.4–18.2) at 1920×1280; Wonder QA adds **6.2 s** median (5.0–14.4) and ≈**$0.016** per check (616–718 input / 557–1321 output tokens, 458–1215 of them reasoning). The image call is ≈$0.01 each (TRD §2), so **the QA loop roughly doubles the cost per illustration** — budget ≈$0.03 per accepted diagram, ≤ 2 regenerations as TRD §7 requires.

## Wire shape (verified)

- **Generate:** `POST /v1/images/generations` with JSON `{model:"muse-image-1.0", prompt, n:1,
  response_format:"b64_json"}` → `{created, data:[{b64_json}]}`. The payload is **WebP**, not PNG,
  and the response carries no `usage`, cost or `revised_prompt` field.
- **Edit:** `POST /v1/images/edits` as multipart (`model`, `prompt`, `image`). Multi-image composition
  uses indexed keys `image[0]`, `image[1]`, …; `image[]` is rejected with
  `"use image[N] with indices numbered consecutively from 0, in order"`. The runner accepts two
  inputs in order (reference first, style second in this spike).
- `size` is accepted but **not honored** in probes (512×512 and 1024×1024 both returned 1600×1600;
  omitting it returned 1920×1280). Omit it and accept server-chosen dimensions; the report layout
  letterboxes to its own aspect ratio.
- Output has no watermark: the `AI ILLUSTRATION · NOT EVIDENCE` banner is burned in after
  generation with Pillow, as already implemented by `pw.evidence.labeling` (T-4.4 owns wiring it).

## Decision

- **T-4.3** calls the edit endpoint with the selected evidence frame (annotated, no face crops) and a
  step-derived caption; falls back to text-only when the frame is unusable; records mode and prompt
  version on the illustration.
- **T-4.4** burns in the watermark and sets `kind: "illustration"`; never enters `evidence[]`.
- **T-4.5** QA is a Wonder call with this strict schema:
  `{matches_step bool, correct_tool_shown bool, text_legible bool, hallucinated_labels [str],
  people_visible bool, verdict "pass"|"fail", reason str}`, `temperature 0`, `effort low`; pass
  requires all checks good, ≤ 2 regenerations, then `illustration_unavailable`.
- **T-0.7** `ImageClient` returns decoded image bytes plus `{mode, seconds, usd}`; the ledger prices
  $0.01 per image and ≈$0.016 per QA call, since the API exposes no usage field.
- **T-3.9** may pass a `Writer` that is either endpoint; the ledger line is the same.

## Consequences and open items

- Edit mode is only as good as its reference: annotation overlays can be redrawn as illustration
  elements. Use clean evidence frames (post-overlay) or text-only when the overlay dominates.
- `n > 1` was not tested (one image per call is the planned path); max reference images and per-image
  size caps are unknown.
- Determinism: no seed parameter surfaced; consistency needs the compose/style-reference trick.
- Real-footage quality (hands with tools, clutter, faces in background) must be re-checked at T-1.4.

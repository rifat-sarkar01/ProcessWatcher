# ADR-001: SAM 3.1 on the Meta Model API

- **Status:** Accepted
- **Date:** 2026-11-02
- **Task:** T-0.4 (ML, serves FR-03, NFR-01, NFR-02)
- **Deciders:** O1 (perception), O3 (clients) — reviewed by O2 for evidence use
- **Resolves:** the card's questions Q1–Q7 (call shape, mask encoding, limits, objects, ID persistence, cost, API vs self-hosted)

## Context

T-0.4 is a time-boxed spike to fix SAM 3.1's request/response shape, mask decoding, limits and cost
before T-2.x builds perception on top of it. Nothing about the wire format was verified in the repo:
`docs/06_Plan.md` only named the model. This ADR records what was measured against the live API on
2026-11-02 with the project key (spend: 9 billed calls — 197 video frames and 7 images, ≈$0.06 at
list price — plus one rejected 17-object probe) and what remains open.

Sources read (accessed 2026-11-02):

1. SAM 3 protocol — <https://github.com/meta-models/meta-sam/blob/main/protocol/sam3.md>
2. `@meta-sam/parser` 0.1.0 README + the official Python parser source (`meta_sam_parser`) —
   <https://github.com/meta-models/meta-sam/tree/main/python>
3. SAM 3.1 docs and pricing — <https://dev.meta.ai/docs/sam/overview>,
   <https://dev.meta.ai/docs/pricing-rate-limits>

Fixtures for every measurement live in `tests/fixtures/spikes/sam/` (one synthetic clip, two request
bodies, two raw responses, four decoded masks). Decoding used the official Python parser **from a
scratch directory**; it is not a project dependency.

## Decision

Use **SAM 3.1 through the Responses API** (`POST /v1/responses`) for tracking, with:

- a **noun-phrase** `input_text` for concept tracking (e.g. `"hand"`, `"screwdriver"`), and
  object prompts (box/point token text) when the SOP already knows the tool or part;
- `metadata.mask_encoding = "one_bit"` on every request (26× smaller than the default);
- masks decoded by a **port of the official range coder** inside `pw.perception` (T-2.4), with the
  box always present as a fallback;
- at most **16 objects per request**, chunking long clips by frames.

## Answers

Q1: **Call shape.** `POST https://api.meta.ai/v1/responses` with `{"model":"sam-3.1","input":[{"role":"user","content":[{"type":"input_text","text":"red circle"},{"type":"input_video","video_url":"data:video/mp4;base64,…"}]}]}`; images use `input_image` with `image_url` (data URL). The result is `output[0].content[0].text`, one line per frame: `<Nf>id<|box;x1=..;y1=..;x2=..;y2=..;w=W;h=H;c=..|><|mask;x=0;y=0;data=H,W,payload|>`, records comma-separated, ids stable per object. `/v1/chat/completions` rejects `sam-3.1` with "not available on this endpoint. Use /v1/responses". `metadata` also accepts `include_confidence:"true"` and `propagation_direction` (`both` default, `forward`, `backward`).

Q2: **Mask encoding.** The mask is a **box-local raster** (`data=H,W,payload`), not frame-sized: the
256×256 probe returned 97×97 = 9409 bytes at box (80,80)–(176,176), decoded to 7339 set pixels.
Payload is **base85** over the 85 printable characters minus `" \ , ; < > |`, prefixed by a
5-character length, then an adaptive range coder; `~` = `lossless` (byte coverage, threshold ≥129,
the API default), `!` = `one_bit` (binary, canonical round-trip). Measured payload for the same mask:
**2454 chars lossless vs 93 chars one_bit**, so requests set `mask_encoding:"one_bit"`; a 75-frame
video response shrank from 64.5 KB of text (lossless) to 16.1 KB for 122 frames (one_bit).
Box corners are inclusive source pixels (`x2`,`y2`); normalized boxes are half-open (`right = x2 + 1`).

Q3: **Duration/size limits.** 5 s / 75 frames (320×240, 15 fps) and **61 s / 122 frames** (160×120,
2 fps) were both accepted and fully segmented. The vendor docs state no duration or file-size limit,
and the published claim is **15,000 input frames** (8 m 20 s at 30 fps); that ceiling was **not
reached** — a 15,001-frame probe would cost ≈$3.00, above the $2.00 per-run cap. File-size limit is
also unmeasured. Both stay open below; chunking is frame-based, never duration-based.

Q4: **Max objects.** **16 per request**, measured: 17 object prompts → `400 "invalid prompt: 17
objects exceed this model's limit of 16"`; 16 prompts → `200` with 16 box records. This matches the
plan's "group concepts, keep `hand` in every group" pitfall.

Q5: **ID persistence after occlusion.** On a 5 s clip where a black square covers the moving red
circle for frames 30–50 (2.0–3.4 s), **all 75 frames returned a record under the same id `0`** — the
id survives occlusion. But the mask **leaks onto the occluder** (frame 40: box 160,80–241,161,
81×81 mask with 6549/6561 pixels set) and returns to the circle when uncovered (frame 0: 53×53,
2207/2809). Confidence was constant at 0.9416 on every frame of this clip, which suggests a
per-object score; do not treat it as a per-frame probability. Perception must not trust masks or
boxes during occlusion (T-2.3/T-2.4), and evidence selection must fall back to pre/post windows.

Q6: **Cost and latency.** Pricing (dev.meta.ai, 2026-11-02): **$2.50 / 1k images** ($0.0025 each)
and **$0.20 / 1k frames** ($0.0002 each) → **$0.18 per 15 fps video-minute**, $0.36 at 30 fps, well
under NFR-02's $1.00/min. Measured latency: image 1.32–1.65 s (256×256); 5 s / 75-frame video
**5.81 s**; 61 s / 122-frame video **7.25 s** (upload included). Rate limit observed: 60 requests
and 2.1 M tokens per minute. The API returns `usage.video_frames_processed` but **no cost field**;
the ledger (T-0.7) must price frames itself.

Q7: **API vs self-hosted.** **API.** It meets the latency and cost targets, returns decodable masks,
needs no GPU or model hosting during the hackathon, and avoids weight-download latency; self-hosting
would add SAM-licence packaging and GPU ops for no measurable gain. SAM 3.1 materials fall under the
SAM License and stay acknowledged in the README.

## Consequences

- T-2.2 sends analysis frames/chunks as `input_video` data URLs (or `file_id` if the upload API is
  used later) with `mask_encoding:"one_bit"` and noun-phrase prompts from the compiled step graph.
- T-2.4 ports the range coder (or vendors a decoder) and always emits the box alongside the mask;
  tests use the fixtures here, including the occlusion leak.
- Concept groups are capped at 16 objects/request, and `hand` stays in every group.
- Long clips are chunked by frames, not seconds; plan for the unverified 15,000-frame ceiling.
- Every call goes through `pw.clients` (T-0.7), which owns retries, the replay cache and the ledger;
  this ADR fixes the shapes that layer must speak.

## Open items

| # | Item | Owner | When |
|---|---|---|---|
| 1 | Hard frame/file-size ceiling (public claim: 15,000 frames; not probed to avoid a $3 call) | O1 | T-2.2 chunk sizing, re-check with the first real clip |
| 2 | ID persistence and mask quality on **real** hand/tool footage (only synthetic shapes probed) | O1 | T-1.4/T-2.2 |
| 3 | Whether `c` is per-object or per-frame (constant 0.9416 on the synthetic clip) | O1 | T-2.3 |
| 4 | Upload path (`file_id`) for clips above the inline base64 size the API accepts | O3 | T-0.7 |

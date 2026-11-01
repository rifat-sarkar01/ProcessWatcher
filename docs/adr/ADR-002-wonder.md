# ADR-002: Muse Wonder 1.0 — prompts, strict JSON, variance and budget

- **Status:** Accepted
- **Date:** 2026-11-02
- **Task:** T-0.5 (ML, serves FR-02, FR-06, NFR-02)
- **Deciders:** O1 (perception), O2 (reasoning), O3 (clients)
- **Resolves:** the card's questions Q1–Q7 (video limits, images per call, JSON validity, variance at T=0, latency/cost, parallelism, quirks)

## Context

T-0.5 fixes how Process Watcher talks to `muse-wonder-1.0` for the four reasoning jobs: SOP compile,
segment scoring, identity and verification. Nothing was verified before: the repo only knew the model
name and an OpenAI-compatible Responses API. Everything below was measured live on 2026-11-02 with the
project key (spend ≈ $0.70 of the $150 pool: 10 compile + 10 scoring runs, plus image/video limit
probes). **No real hand/tool footage exists yet**, so both prompt types ran on synthetic clips
(`tests/fixtures/spikes/wonder/clip-20s.mp4`); accuracy on real footage is an open item, while the
shape, validity, variance, latency and cost measurements are not affected by that limitation.

Sources read: `dev.meta.ai/docs/models`, `dev.meta.ai/docs/pricing-rate-limits`, the live API.

Fixtures in `tests/fixtures/spikes/wonder/`: the 20 s clip, four numbered keyframes (one intentionally
has no detection), the ~1.5k-token `timeline.json`, both request bodies, one raw response per prompt
type, and `summary.json` with the 10-run statistics.

## Decision

- **One wire shape for all four jobs:** `POST /v1/responses` with `input_text` (+ `input_video` or
  `input_image` parts), `temperature: 0`, `reasoning: {"effort": "low"}`, and a strict
  `text.format = {type:"json_schema", name, schema, strict:true}`.
- **Compile (T-3.2):** SOP text + clip → `{"steps":[{"idx":int,"action":str,"tools":[str]}]}`. The
  parser/repair loop already in `pw.sop.compiler` is the right place for schema rejection.
- **Scoring (T-3.4):** ~1.5k-token timeline JSON + 4 numbered-mask keyframes + the step list →
  `{"steps":[{"id":str,"prob":0..1}]}`. Run the same request **k = 3 times and take the median** per
  step, because probabilities are NOT stable at temperature 0.
- **Identity/verification (T-3.7/T-3.9):** same pattern, one strict schema per job, temperature 0.
- **Never trust the VLM as a judge and never use it for the domain guard:** on mismatched footage it
  still returned SOP steps (see Q7); the deterministic coverage check stays in the aligner.
- **Budget:** ≈$0.02 per compile call and ≈$0.03 per scoring call; a 2-minute procedure with 6–10
  scoring windows × 3 repeats stays well under NFR-02's $1.00/minute.

## Answers

Q1: **Video limits.** 20 s / 200 frames (320×240, 10 fps) and **61 s / 122 frames** were both accepted
and described. The docs state no duration limit; context is 1,048,576 tokens. Input cost does not grow
with duration the way frames do: the 20 s clip + SOP used **711 input tokens**, the 61 s clip **857**,
so video is sampled rather than tokenised per frame. Output tokens dominate every call.

Q2: **Images per call.** 8 and **24 images** were both accepted in one request (no limit hit); each
32×32 image contributed ≈4–5 input tokens (24 images → 94 tokens). The scoring prompt sends 4
full-resolution keyframes with numbered mask overlays and is accepted. The docs state no image-count
cap, so the product should keep 4–6 keyframes per call and treat a larger number as untested.

Q3: **JSON validity.** **10/10** compile runs and **10/10** scoring runs parsed and validated against
their strict schemas. A rejected schema would have returned a 400; none occurred. Validity is not the
risk — semantic quality and variance are.

Q4: **Variance at temperature 0.** Outputs are **not deterministic**. Compile: 9 of 10 runs were
byte-identical and 1 differed (90% agreement), all extracting exactly one SOP step from footage that
does not show the procedure. Scoring probabilities: `stp_02` ranged **0.08–0.85** (mean 0.405, σ 0.336),
`stp_03` 0.85–0.97 (σ 0.032), `stp_01` 0.01–0.08, `stp_04` 0.01–0.06. A single call can therefore move a
step across an alignment threshold; T-3.4 must aggregate repeated calls (median of k=3) or widen the
calibration.

Q5: **Latency and cost per call type.** Compile: 7.1–17.8 s (median 9.2 s), 711 input + 830 output
tokens ≈ **$0.019/call**. Scoring: 6.5–15.0 s, 3,217 input + 1,023 output tokens ≈ **$0.033/call**
(prompt caching returned 3,174/3,217 input tokens as cached on repeat). Reasoning tokens were 94% and
93% of output respectively, so `reasoning.effort` is the main cost lever; `low` is what was measured.
Images alone: 8 small images 2.6 s, 24 images 15.2 s.

Q6: **Parallelism and rate limits.** Four concurrent requests worked with **no 429s**: ten compile
calls finished in 27.1 s wall time vs 103.0 s summed latency (≈3.8×), ten scoring calls in 28.6 s vs
99.0 s. Observed headers: **3,000 requests/min** and **4,000,000 tokens/min**. Backoff was therefore
not exercised; T-0.7 still needs 429 handling for safety, but 4-way parallelism is within budget.

Q7: **Quirks.** (1) On footage that does not show the SOP, the model did **not** refuse or say
"not recognized" — it returned one SOP step anyway, so a model-based domain check would be unsafe.
(2) Strict schemas were honoured everywhere, including `minimum`/`maximum` on probabilities. (3) The
24-image probe answered "25" — small miscounts happen and must not be used as evidence. (4) Reasoning
tokens dominate cost and latency. (5) One compile run at T=0 disagreed with the other nine, confirming
Q4. (6) Real hand/tool footage, refusals on graphic or unsafe content, and the effect of rotation
metadata are untested.

## Consequences

- T-3.2 keeps its `Compiler` seam: the prompt, schema and repair loop become the live path; the
  measured shape replaces the stub.
- T-3.4 consumes probabilities as **distributions** (median of k=3) and keeps the deterministic domain
  guard; tests must cover a 0.08 vs 0.85 swing for the same clip.
- T-3.7's verifier reuses the same strict-schema pattern at ≈$0.02–0.03 per call.
- T-0.7's client layer must set `temperature`, `reasoning.effort` and `text.format` from one place,
  cache by request hash (prompt caching is upstream, replay is ours) and price input/output separately.
- Budget planning uses ≈$0.02 (compile) and ≈$0.03 (score) per call; reasoning effort is the knob.

## Open items

| # | Item | Owner | When |
|---|---|---|---|
| 1 | Real hand/tool footage: refusal quirks, accuracy, rotation handling | O1 | T-1.4 → T-3.4 |
| 2 | k for scoring: 3 was assumed, not tuned; pick k from the T-3.10 calibration | O1 | T-3.10 |
| 3 | Maximum images per call not found (24 accepted) | O3 | T-0.7 |
| 4 | Cached-input pricing per the vendor docs vs the observed cache hits | O3 | T-0.7 ledger |

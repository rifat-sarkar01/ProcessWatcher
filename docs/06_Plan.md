# 06_Plan.md: Process Watcher Implementation Plan
> Plan v1.0 · Built from docs 01–05 (`01_PRD`, `02_AppFlow`, `03_UI_Spec`, `04_TRD`, `05_Schema`) + the Meta Global AI Developer Hackathon page · 2026-10-25
> Rule: tick a box ONLY after its "Done when" passes and evidence is in docs/PROGRESS.md.
> Clock: kickoff **Mon Oct 26** · submission due **Wed Nov 4, 21:00 ET (= Nov 5, 02:00 UTC)** · internal hard deadline **Nov 4, 12:00 ET** · judging Nov 4–8 · finals Mon Nov 9. US clocks go back on Sun Nov 1 (EDT → EST); always reason in UTC.

> **Spec docs (read order for every agent):** `01_PRD.md` (requirements + acceptance criteria) → `02_AppFlow.md` (screens, states, errors) → `03_UI_Spec.md` (design tokens, components) → `04_TRD.md` (stack, APIs, algorithms) → `05_Schema.md` (artifacts, IDs, access rules) → this plan.
> **Citation map used in Context packs:** `§1A` strategy (this file) · `§1B` = `04_TRD §3` + `05_Schema §2` · `§3 FR-xx/NFR-xx` = `01_PRD §5–6` · `UI states` = `02_AppFlow §7` · `contracts/*` = `05_Schema §3–10`. On any conflict the order of authority is PRD > Schema > TRD > AppFlow > UI Spec > this plan; fix the plan via §7.

## 0. Dashboard (update at gates only)
| Phase | Tasks | Done | Blocked | Gate |
|---|---|---|---|---|
| P0 Foundation, spikes, walking skeleton (D1) | 9 | 0 | 0 | G0 [ ] |
| P1 Data, contracts, eval harness (D1–D3) | 8 | 0 | 0 | G1 [ ] |
| P2 Perception and interaction timeline (D2–D4) | 10 | 0 | 0 | G2 [ ] |
| P3 Reasoning: SOP compile, alignment, deviations (D3–D5) | 12 | 0 | 0 | G3 [ ] |
| P4 Evidence and illustration (D5–D6) | 6 | 0 | 0 | G4 [ ] |
| P5 API, UI, report (D3–D7) | 13 | 0 | 0 | G5 [ ] |
| P6 Evaluation and hardening (D8) | 8 | 0 | 0 | G6 [ ] |
| P7 Release and submission (D9–D10, finals D11–D14) | 8 | 0 | 0 | G7 [ ] |

**Track Board** (tasks done/total)
| Phase | BE | FE | DATA | OPS | SEC | QA | DOC | ML |
|---|---|---|---|---|---|---|---|---|
| P0 | 0/2 | 0/1 | 0/0 | 0/2 | 0/0 | 0/0 | 0/1 | 0/3 |
| P1 | 0/0 | 0/0 | 0/6 | 0/0 | 0/0 | 0/0 | 0/0 | 0/2 |
| P2 | 0/2 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/8 |
| P3 | 0/1 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/11 |
| P4 | 0/4 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/2 |
| P5 | 0/4 | 0/7 | 0/0 | 0/0 | 0/1 | 0/1 | 0/0 | 0/0 |
| P6 | 0/1 | 0/1 | 0/0 | 0/0 | 0/1 | 0/2 | 0/0 | 0/3 |
| P7 | 0/1 | 0/0 | 0/0 | 0/1 | 0/0 | 0/1 | 0/5 | 0/0 |

Overall: 0/74 (0%) · Current: T-0.1 · Plan health: GREEN · Mode: parallel (4 owners)

## 1. Legend
- **Status:** `[ ]` todo · `[~]` in progress (max ONE per owner) · `[x]` done and verified · `[!]` blocked · `[-]` dropped (reason).
- **Size:** S ≤ ~50 LOC, ≤ 3 files · M ≤ ~150 LOC, ≤ 5 file groups (a glob of schemas, goldens or fixtures counts as one group).
- **Tier:** `light` mechanical/docs/config · `standard` ordinary feature + tests · `deep` architecture, concurrency, security, hard debugging.
- **Run modes** (`PW_MODE`): `live` real Meta Model API · `replay` cached real responses (deterministic, free) · `fake` hand-made fixtures (unit tests) · `demo` frozen demo cases served offline.
- **Parallel mode (adapted):** 4 owners, one in-progress task per OWNER; an owner may hold tasks in several tracks. Concurrently active tasks must have disjoint `Touch` paths. Merge only at sync points: **C1** contract freeze (end D2), **G-gates**, **FF** feature freeze (end D7), **RC** release candidate (D8 start).
- **Default Never-touch:** any path owned by another track/owner; `contracts/*` unless the task is DATA; frozen files after their freeze (`config/thresholds.json` after G3, `bench/HELDOUT.lock` always, `contracts/*` after C1 except via a dedicated contract-change task).
- **Owners (suggested; tracks, not people, are the contract):**

| Owner | Role | Owns paths |
|---|---|---|
| O1 | Perception + evaluation lead | `src/pw/perception/*`, `src/pw/timeline/*`, `src/pw/bench/*` |
| O2 | Reasoning + evidence lead | `src/pw/sop/*`, `src/pw/align/*`, `src/pw/illustrate/*`, `src/pw/evidence/*`, `src/pw/report/build.py` |
| O3 | Platform lead (BE, OPS, SEC, QA) | `src/pw/api/*`, `src/pw/clients/*`, `src/pw/core/*`, `src/pw/ingest/*`, `src/pw/pipeline/*`, `src/pw/security/*`, `src/pw/report/export.py`, `.github/*`, `Dockerfile`, `deploy/*`, `tests/robustness/*`, `web/e2e/*` |
| O4 | Product lead (FE, DATA, DOC) | `web/src/*`, `contracts/*`, `src/pw/data/*`, `bench/*` (except lock logic owned by DATA tasks), `README.md`, `docs/adr/*` (index), `docs/submission/*`, `docs/finals/*`, `docs/demo/*`, `scripts/*` |

  Generated TS types in `web/src/types/generated/*` are owned by DATA tasks only. ADR files belong to the task that writes them. Load-balance review at G2.
- **Standard gate checks (apply to every gate):**
  - S1 every phase task is `[x]` or `[-]` with a reason
  - S2 full suite green: lint, typecheck, unit, integration in `replay` mode (+ e2e from G5)
  - S3 coverage meets AGENTS.md §15 thresholds
  - S4 security: gitleaks clean, dependency audit has no high/critical, guard tests exist for every new endpoint
  - S5 zero scope violations (§3 Out of Scope) and Parking Lot untouched
  - S6 phase-specific extras below pass
  - S7 track board reviewed, no owner blocked > 1 session, contracts (`contracts/*`, `openapi.json`, generated types) in sync
  - S8 docs updated (README, ADRs, `.env.example`)
  - S9 plan-health review done (planned vs actual, reopened, discoveries triaged) and tag `v0.<n>.0` pushed

## 1A. Win Strategy (read once, then ignore)
**What the event rewards.** Indie track: creativity, technical ambition, and whether it works. Startup track: technical execution and holding up in production. Theme "Push the Frontier" (manufacturing and physical systems): verify what is actually happening, not what the paperwork says. We optimise for both tracks: ambition AND proof AND reliability. (Track choice is A-1.)

**Seven things most teams will not do (our edge):**
1. **Ground-truth benchmark with a held-out split locked before tuning** (PW-Bench: 3 procedures, 24 filmed clips, injected deviations). Headline numbers: F1 per deviation type, false flags per compliant clip, timestamp error, $ per video-minute.
2. **Ablation that proves each model earns its place:** raw-video Wonder (A) vs keyframes-only Wonder (B) vs full SAM-timeline pipeline; plus no-aligner, no-verifier, no-identity-voting. Report honestly with bootstrap CIs.
3. **The VLM is never the judge.** Muse Wonder supplies perception likelihoods; a deterministic constrained aligner (partial-order aware, margin-based confidence) decides. Deviations fall out of the alignment, so every flag is explainable and unit-tested.
4. **Calibrated abstention:** low-margin findings become `needs_review`, a mismatched SOP/video becomes `procedure_not_recognized`. Low false alarms is what makes a QA tool believable.
5. **Evidence integrity:** evidence is always real frames with SAM masks, hashed and re-derivable (`pw verify-evidence`); Muse Image output is watermarked "AI illustration, not evidence" and the report builder refuses to mix them.
6. **Persistent IDs as an efficiency story:** tool identity is classified once per SAM track (not per frame), cutting model calls by an order of magnitude; show cost per video-minute.
7. **Demo that cannot fail:** a frozen offline `demo` mode, a backup video, and a clean-room rehearsal. One held-out clip with a planted mistake a human viewer would miss.

**3-minute demo arc.** 0:00 hook: the SOP says star-pattern torque; the video looks fine; what really happened? · 0:20 upload SOP+video, pipeline stages tick, SOP-vs-observed lanes fill, flags appear with SAM masks · 1:30 click a deviation: evidence frame, explanation, "what correct looks like" diagram · 2:15 the numbers: held-out F1, ablation bar, $/min · 2:45 second domain loads in seconds; roadmap one-liner.

**Never cut:** eval harness, held-out numbers, aligner, evidence integrity, demo video, offline demo mode.
**Cut list if behind (in this order):** (1) PDF export (keep HTML) · (2) enter/exit zone events · (3) evidence clips (keep frames) · (4) illustration QA loop → single regeneration · (5) SOP editor → read-only preview · (6) public deploy → local demo + video.
**Anti-patterns:** generating anything that looks like evidence · claiming accuracy without held-out · demoing only the happy path · raw JSON on screen · tuning on held-out.

## 1B. Architecture and contracts digest (the shared mental model)
```
SOP (.md/.txt/.pdf) -> [W] SOP compiler -> step_graph.json --+--> SAM concept vocabulary
Video -> ingest (CFR, <=720p, sha256) -> [S] SAM 3.1 tracks (chunked, stitched) -> tracks.json
tracks -> interaction features -> timeline.json (events) -> candidate segments
segments + set-of-mark keyframes -> [W] step likelihoods -> constrained DP aligner -> alignment.json
alignment + track identities ([W] once per track) -> deviations (missed / out_of_order / wrong_tool)
deviations -> [W] verifier -> [W] grounded explanation (validated against data)
deviations -> evidence (SAM-annotated REAL frames + clip, hashed) -> report.json
flagged steps -> [I] Muse Image "what correct looks like" -> [W] QA -> illustration (watermarked)
report.json -> API + SSE -> Review UI + self-contained HTML/PDF audit report
[S]=SAM 3.1  [W]=Muse Wonder  [I]=Muse Image    Base URL: api.meta.ai/v1 (OpenAI-compatible)
```
**Contracts (JSON Schema, DATA owns, frozen at C1):** `sop`, `tracks`, `timeline`, `alignment`, `report`, `manifest`. Time unit is seconds (float, ms precision); frame indices appear only inside `tracks`. IDs: `stp_01`, `trk_001`, `evt_001`, `dev_001`, `evd_001`.
**Run store:** filesystem, `runs/<run_id>/{input,stages,evidence,illustrations,report.json,manifest.json}`; no database. Stage outputs are content-hash cached.
**UI states to implement (G5 check):** access gate · upload · SOP review · processing · stage failed/partial · review (flagged, needs_review) · procedure_not_recognized · evidence_unavailable · illustration_unavailable · demo gallery.

## 2. Assumptions (A-n) and Open Questions (Q-n)
- **A-1** Track = Indie (individuals/students; team of 4). If the application was for Startup, framing in T-7.5 changes; build plan does not.
- **A-2** Team = you + 3 teammates, all able to code with agents; owners O1–O4 as in §1.
- **A-3** Docs 01–05 are in `docs/` (added with this plan). No relational database: `05_Schema.md` specifies JSON artifacts, IDs and access rules instead of tables/RLS (TRD D-3).
- **A-4** Meta Model API (`api.meta.ai/v1`, key from dev.meta.ai) is the primary access path for all three models (`muse-wonder-1.0`, `muse-image-1.0`, SAM 3.1 via the Responses API). **SAM request/response shape, mask encoding, duration/size/object limits are NOT verified: T-0.4 decides.** Credits and rate limits for accepted participants unknown (Q-2).
- **A-5** SAM 3.1 has open weights (SAM License; acknowledge in README). Fallback to self-hosting on Modal/Baseten GPUs only if ADR-001 says the API blocks us.
- **A-6** Stack: Python 3.12 + uv + FastAPI + Pydantic v2 + ffmpeg/OpenCV; React + Vite + TypeScript + Tailwind; Playwright; filesystem run store. Exact versions pinned in T-0.2/T-0.3 lockfiles (no TRD exists).
- **A-7** Video: single fixed camera (phone on stand), 1080p source, normalised to ≤720p constant-frame-rate for analysis; clips 45–180 s; English SOPs.
- **A-8** Procedures (swappable): P-A "SSD swap in a desktop PC", P-B "prepare 100 ml of a standard solution", P-C "4-bolt cross-pattern torque". Each 8–12 steps, ≥3 tools, ≥1 critical step, ≥1 order-sensitive pair, ≥1 any-order group.
- **A-9** Exactly three deviation types (missed, out_of_order, wrong_tool) plus a status `needs_review`; nothing else is a type.
- **A-10** ~~Official Rules are unseen (published Oct 26). T-0.1 may force plan edits (IP, open-source, video length, pre-existing work); log in §7. **No product code before the rules are read.**~~ **Resolved by T-0.1 / ADR-000 (2026-10-27):** rules read, no plan conflict. No video-length limit; no repo-visibility or licence requirement (MIT kept); submission must be original, solely owned work; Indie teams ≤ 4; $150 API credits for the 10-day window; deadline 2026-11-05T02:00:00Z. Product code unblocked.
- **A-11** Muse Wonder is in preview; Muse Spark is NOT used unless an ADR approves it for cost/rate reasons.
- **A-12** Public demo is gated by an access code (protects API spend); judges receive the code in the submission.
- **A-13** Latency, cost and quality figures in §3 are targets, re-baselined from ADR-001/002 and logged in §7.
- **Q-1** (non-blocking) Which track did the application choose? Default Indie.
- **Q-2** (non-blocking) Do accepted participants get Model API credits and what rate limits? Default: pay-as-you-go, `PW_SPEND_CAP_USD=3` per run, budget agreed by the team.
- **Q-3** (non-blocking) Which three procedures can you physically film with props you own? Default A-8.
- **Q-4** (non-blocking) Is everyone on Windows? Default: Windows-first, PowerShell-safe commands via `uv`/`npm --prefix`.
- **Q-5** (resolved by T-0.1) Official-rules constraints: repo public? licence? video length? team size? pre-existing code?

## 3. Requirement Coverage Matrix (mirrors `01_PRD.md` §5–7; the PRD wins on conflict)
**Out of Scope (no task may implement these):** live/streaming camera inference · training or fine-tuning any model · user accounts, RBAC, multi-tenant · MES/ERP/QMS integrations · multi-camera fusion · identifying, scoring or ranking individual workers · safety-certification or regulatory-compliance claims · synthetic images presented as evidence · mobile app · automatic SOP authoring.

| Req ID | Summary | Tasks |
|---|---|---|
| FR-01 | Ingest a procedure video + SOP (md/txt/pdf) with caps and validation | T-0.8, T-2.1, T-3.1, T-5.1, T-5.2 |
| FR-02 | Compile SOP into a validated step graph (steps, tools, parts, ordering, critical flags, SAM vocabulary); user can edit it | T-0.5, T-3.1, T-3.2, T-3.3, T-5.3, T-5.7 |
| FR-03 | SAM 3.1 tracks hands, tools, parts with persistent IDs across chunks | T-0.4, T-2.2, T-2.3, T-2.4 |
| FR-04 | Deterministic interaction timeline (hold, contact, move, enter/exit) and candidate segments | T-2.5, T-2.6, T-2.8, T-2.10 |
| FR-05 | Per-track tool/part identity vs the SOP vocabulary, with confidence | T-2.7 |
| FR-06 | Step alignment by global constrained DP honouring ordering constraints; mismatch guard | T-0.5, T-3.4, T-3.5, T-3.11 |
| FR-07 | Flag missed, out-of-order, wrong-tool steps with severity, timestamps, track IDs | T-3.6 |
| FR-08 | Verification pass, calibrated `flagged`/`needs_review`, grounded short explanation | T-3.7, T-3.8, T-3.10 |
| FR-09 | Evidence = SAM-annotated real frames + clip, hashed and re-derivable | T-2.9, T-4.1, T-4.2, T-4.5 |
| FR-10 | Muse Image "what correct looks like" diagram per flagged step, labeled, QA-checked | T-0.6, T-4.3, T-4.4, T-4.5, T-5.11 |
| FR-11 | Review UI: video + dual-lane timeline + SAM overlay + deviation panel + decisions | T-0.3, T-5.3, T-5.6, T-5.7, T-5.9, T-5.10, T-5.11 |
| FR-12 | Self-contained HTML/PDF audit report | T-1.2, T-4.6, T-5.5 |
| FR-13 | PW-Bench: ground truth, metrics, baselines, ablation, held-out protocol | T-1.1, T-1.3, T-1.4, T-1.5, T-1.6, T-1.7, T-1.8, T-2.10, T-3.3, T-3.12, T-6.1, T-6.8 |
| FR-14 | Offline demo mode with frozen cases | T-5.12, T-7.1 |
| FR-15 | Live progress (SSE) with cost and elapsed counters | T-0.8, T-3.9, T-5.4, T-5.8 |
| NFR-01 | Latency target: 2-min clip → report ≤ 4 min p50 (live); demo case loads ≤ 3 s | T-0.4, T-6.6 |
| NFR-02 | Cost target ≤ $1.00 per video-minute; hard per-run cap; full ledger | T-0.4, T-0.5, T-0.7, T-3.9, T-6.6 |
| NFR-03 | Reliability: timeouts, ≤3 retries, schema validation, partial-failure degrade, resumable stages | T-0.7, T-3.9, T-6.3, T-6.4 |
| NFR-04 | Traceability: every deviation links step id + track ids + timestamps + evidence | T-1.1, T-1.2, T-3.6, T-4.6 |
| NFR-05 | Security/privacy: no keys in repo/logs/client, upload validation, access code, rate limit, 24 h retention, no worker identification | T-0.2, T-0.7, T-5.1, T-6.5, T-7.2 |
| NFR-06 | Reproducibility: pinned deps, deterministic `replay`, manifest, re-derivable evidence, CI from clean clone | T-0.2, T-0.9, T-4.2, T-7.6 |
| NFR-07 | Quality targets on held-out: overall F1 ≥ 0.70 (each type ≥ 0.60), ≤ 0.3 false flags per compliant clip, timestamp MAE ≤ 1.5 s, Full ≥ baseline B + 0.10 F1 on dev | T-1.6, T-1.8, T-3.10, T-6.1, T-6.2 |
| NFR-08 | Demo robustness: offline demo, backup video, clean-room quickstart ≤ 10 min | T-5.13, T-7.1, T-7.4, T-7.6, T-7.8 |
| NFR-09 | Usability: every UI state handled, keyboard-operable timeline, readable on a 1080p projector, WCAG AA contrast | T-5.6, T-6.7 |
| SUB-01 | Submission: everything the Official Rules require by Nov 4 21:00 ET (repo/licence, demo video, write-up, demo link, track + theme statement) | T-0.1, T-7.2, T-7.3, T-7.4, T-7.5, T-7.7, T-7.8 |

## 4. Phases
### Phase 0: Foundation, Spikes, Walking Skeleton (Day 1 · Mon Oct 26)
**Goal:** repo, CI, the three model APIs proven with real calls, and the thinnest end-to-end path. **Exit:** Gate G0

**Phase Profile**
- Purpose: kill the biggest unknowns (SAM video limits and mask encoding, Wonder video/JSON behaviour, Muse Image editing) before any feature code.
- Entry: Official Rules read first; Meta Model API keys in `.env` for every owner.
- Workflow: config-first; spikes are time-boxed (≤3 h) and output decisions (ADRs + raw response fixtures), not features; then client layer; then skeleton.
- Test focus: smoke (build, start, health), client retry/timeout/replay behaviour.
- Security focus: secret scanning from commit 1, keys only via env, log redaction, `.gitignore` for `runs/`, `bench/**/videos/`, `.env`.
- Default tier: light (spikes deep).
- Gate extras: CI green from a clean clone · `pw run --mode fake` produces all stage artifacts · ADR-000..003 present · live selftest OK for all 3 models · decision log filled (SAM backend, chunk length, mask decode path, deploy host candidate).
- Exit evidence: CI run URL, three selftest outputs, ADR list in PROGRESS.md.

### T-0.1 · Read Official Rules and log constraints                                   [x]
- **Track:** DOC | **Serves:** SUB-01 | **Size:** S | **Tier:** light | **Depends:** (none) | **Blocks:** all (plan edits)
- **Context pack (read only these):** Official Rules + waiver (published Oct 26) · event page
- **Goal:** know the deliverables, video length, repo/licence/IP rules, team and pre-existing-work rules, then amend the plan.
- **Touch:** `docs/adr/ADR-000-rules.md` | **Never touch:** `src/*`, `web/*`
- **Steps:** 1. Read rules and waiver. 2. Record deliverables, video limit, repo/licence, pre-existing code, AI-tool rules, team size, judging detail. 3. Convert deadlines to UTC. 4. List plan edits. 5. Add an entry to §7 (even "no changes").
- **Tests first:** n/a (reading task).
- **Done when:** `Select-String docs/adr/ADR-000-rules.md -Pattern "Deliverables:|Video:|Repo/licence:|Pre-existing work:|Deadline UTC:"` → 5 matches; §7 has a new line.

### T-0.2 · Python scaffold and tooling                                              [x]
- **Track:** OPS | **Serves:** NFR-05, NFR-06 | **Size:** M | **Tier:** light | **Depends:** T-0.1 | **Blocks:** T-0.3, T-0.7, T-1.1
- **Context pack (read only these):** §1B · AGENTS.md §15
- **Goal:** `uv` project with src layout, lint/type/test, secret scan, env template, AGENTS.md.
- **Touch:** `pyproject.toml`, `uv.lock`, `.pre-commit-config.yaml`, `.gitignore`, `.env.example`, `AGENTS.md`, `src/pw/__init__.py`, `tests/test_smoke.py` | **Never touch:** `web/*`
- **Steps:** 1. `uv init` (Python 3.12), add ruff, mypy, pytest (markers unit/integration/live), pytest-cov, pre-commit. 2. Add gitleaks hook. 3. `.env.example`: `META_API_KEY`, `PW_MODE`, `PW_ACCESS_CODE`, `PW_SPEND_CAP_USD`, `PW_RUNS_DIR`. 4. Paste §15 block into AGENTS.md. 5. One smoke test.
- **Tests first:** smoke: `import pw`.
- **Done when:** `uv sync; uv run ruff check .; uv run mypy src; uv run pytest -q; uv run pre-commit run gitleaks --all-files` → all exit 0, 1 test passed.
- **Rollback:** delete branch; no state.

### T-0.3 · Web scaffold                                                              [x]
- **Track:** FE | **Serves:** FR-11 | **Size:** S | **Tier:** light | **Depends:** T-0.2 | **Blocks:** T-1.2, T-5.6
- **Context pack (read only these):** AGENTS.md §15
- **Goal:** Vite + React + TypeScript + Tailwind + Vitest + ESLint skeleton with placeholder `gen:types` script.
- **Touch:** `web/package.json`, `web/vite.config.ts`, `web/src/main.tsx`, `web/src/App.test.tsx`, `web/scripts/gen-types.mjs` (placeholder) | **Never touch:** `src/*`
- **Steps:** 1. Scaffold. 2. Add scripts: `lint`, `typecheck`, `test`, `build`, `gen:types`. 3. One render test.
- **Tests first:** App renders heading.
- **Done when:** `npm --prefix web ci; npm --prefix web run lint; npm --prefix web run typecheck; npm --prefix web run test -- --run; npm --prefix web run build` → exit 0, 1 test passed.

### T-0.4 · Spike: SAM 3.1 on Meta Model API (video, concepts, masks, limits)        [ ]
- **Track:** ML | **Serves:** FR-03, NFR-01, NFR-02 | **Size:** M | **Tier:** deep | **Depends:** T-0.1 | **Blocks:** T-0.7, T-2.1, T-2.2
- **Context pack (read only these):** Meta Model API docs for SAM 3.1 (dev.meta.ai) · SAM 3.1 model card · §1B
- **Goal:** ADR-001 decides call shape, mask decoding path, chunk length, object cap, ID persistence, price per minute, and API vs open-weights.
- **Touch:** `docs/adr/ADR-001-sam.md`, `tests/fixtures/spikes/sam/*` | **Never touch:** `src/*`
- **Steps:** 1. One text-prompted video call on a 20 s clip (`hand`, `screwdriver`, `screw`); save raw JSON. 2. Decode a mask in Python (or via the `@meta-sam/parser` Node package); record the method and a box fallback. 3. Probe limits: duration, file size, max objects, latency, price. 4. Occlusion test: hide an object ≥3 s; does its ID persist? 5. Decide API vs self-hosted (Modal) and chunk length/overlap.
- **Tests first:** n/a (spike). Questions Q1–Q7: call shape · mask encoding · max duration/size · max objects · ID persistence after occlusion · $/min and latency · API-vs-open-weights decision.
- **Done when:** `Select-String docs/adr/ADR-001-sam.md -Pattern "^Q[1-7]:"` → 7 matches each with a measured value; `(Get-ChildItem tests/fixtures/spikes/sam).Count` ≥ 2.
- **Risk or security notes:** time-box 3 h; if the API cannot meet needs, switch to self-hosted weights immediately and log in §7.

### T-0.5 · Spike: Muse Wonder (video + image input, strict JSON, latency, cost)    [ ]
- **Track:** ML | **Serves:** FR-02, FR-06, NFR-02 | **Size:** M | **Tier:** deep | **Depends:** T-0.1 | **Blocks:** T-0.7, T-2.7, T-3.2, T-3.12
- **Context pack (read only these):** Meta Model API docs for `muse-wonder-1.0` · §1B
- **Goal:** ADR-002 decides prompt/response shapes and budgets for SOP compile, segment scoring, identity, verification.
- **Touch:** `docs/adr/ADR-002-wonder.md`, `tests/fixtures/spikes/wonder/*` | **Never touch:** `src/*`
- **Steps:** 1. Send a 20 s clip + SOP and ask for steps in strict JSON. 2. Send 4 keyframes with numbered masks + a 1.5k-token timeline and ask for step probabilities. 3. Run each 10× at temperature 0: measure schema-valid rate and variance. 4. Measure latency, tokens, $; test 4 parallel calls and the rate limit. 5. Note refusal quirks on hands/tools footage.
- **Tests first:** n/a (spike). Questions Q1–Q7: video limits · images per call · JSON validity rate (target ≥ 9/10) · variance at T=0 · latency/cost per call type · parallelism/rate limits · quirks.
- **Done when:** `Select-String docs/adr/ADR-002-wonder.md -Pattern "^Q[1-7]:"` → 7 matches; fixtures ≥ 2.

### T-0.6 · Spike: Muse Image (generate vs edit-with-reference, labels, cost)       [ ]
- **Track:** ML | **Serves:** FR-10 | **Size:** S | **Tier:** standard | **Depends:** T-0.1 | **Blocks:** T-0.7, T-4.3
- **Context pack (read only these):** Meta Model API docs for `muse-image-1.0`
- **Goal:** ADR-003 decides how to produce a clean, labeled "what correct looks like" schematic.
- **Touch:** `docs/adr/ADR-003-image.md`, `tests/fixtures/spikes/image/*` | **Never touch:** `src/*`
- **Steps:** 1. Generate from text only. 2. Edit with a real annotated frame as reference. 3. Compose two inputs. 4. Check label legibility, face avoidance, style consistency, latency, cost.
- **Tests first:** n/a (spike). Questions Q1–Q5: best mode · label legibility · faces/people avoidance · consistency across 3 runs · latency and $.
- **Done when:** `Select-String docs/adr/ADR-003-image.md -Pattern "^Q[1-5]:"` → 5 matches; fixtures ≥ 3 images.

### T-0.7 · Model client layer (live / replay / fake, retries, cost ledger)          [ ]
- **Track:** BE | **Serves:** NFR-02, NFR-03, NFR-05 | **Size:** M | **Tier:** standard | **Depends:** T-0.2, T-0.4, T-0.5, T-0.6 | **Blocks:** T-0.8, T-2.2, T-2.7, T-3.4
- **Context pack (read only these):** ADR-001, ADR-002, ADR-003 · §1B
- **Goal:** one `ModelClient` abstraction with typed `SamClient`, `WonderClient`, `ImageClient`; record/replay cache; per-run cost ledger.
- **Touch:** `src/pw/clients/*`, `src/pw/core/ledger.py`, `tests/clients/*` | **Never touch:** `src/pw/pipeline/*`
- **Steps:** 1. Define protocol + modes. 2. httpx with timeouts, ≤3 retries with jitter, 429 backoff. 3. Request-hash cache (record in live, serve in replay). 4. Ledger (tokens, images, SAM units, USD). 5. `python -m pw.clients.selftest`.
- **Tests first:** happy (replay returns cached) · edge (cache key stable across dict order) · failure (timeout → 3 retries → typed error; 429 backoff; malformed JSON → typed error) · security (API key never in logs or cache files).
- **Done when:** `uv run pytest tests/clients -q` → pass (≥ 12 tests); `uv run python -m pw.clients.selftest --mode live --models all` → 3× OK, total < $0.10 (manual live smoke).
- **Risk or security notes:** redact `Authorization` everywhere; cache files contain no headers.

### T-0.8 · Walking-skeleton pipeline, CLI and API health                             [ ]
- **Track:** BE | **Serves:** FR-01, FR-15 | **Size:** M | **Tier:** standard | **Depends:** T-0.2, T-0.7 | **Blocks:** T-0.9, T-3.9, T-5.1
- **Context pack (read only these):** §1B
- **Goal:** a stage DAG of fake stages writing stub artifacts; `pw run`; FastAPI `/healthz` and `GET /runs`; filesystem run store.
- **Touch:** `src/pw/pipeline/*`, `src/pw/api/main.py`, `src/pw/cli.py`, `tests/pipeline/*` | **Never touch:** `src/pw/clients/*`
- **Steps:** 1. Stage interface + 12 fake stages. 2. Run store layout. 3. `pw run` CLI. 4. `/healthz`, `/runs`. 5. Test fixture builds a 2 s mp4 via ffmpeg.
- **Tests first:** happy (all 12 stub artifacts written) · edge (rerun is a no-op via cache) · failure (missing video → typed error exit 2).
- **Done when:** `uv run pw run --mode fake --video tests/fixtures/tiny.mp4 --sop tests/fixtures/tiny_sop.md` → exit 0 and `runs/<id>/stages` has 12 json files; `curl http://localhost:8000/healthz` → `{"status":"ok"}`.

### T-0.9 · CI and skeleton check                                                     [ ]
- **Track:** OPS | **Serves:** NFR-06 | **Size:** S | **Tier:** light | **Depends:** T-0.3, T-0.8 | **Blocks:** G0
- **Context pack (read only these):** AGENTS.md §15
- **Goal:** GitHub Actions on every push: backend lint/type/unit, web lint/type/test/build, gitleaks, fake-mode skeleton run, `verify-lock` once it exists.
- **Touch:** `.github/workflows/ci.yml` | **Never touch:** `src/*`, `web/*`
- **Steps:** 1. Backend job. 2. Web job. 3. gitleaks job. 4. Skeleton step (`pw run --mode fake`). 5. Conditional `pw-data verify-lock` if `bench/HELDOUT.lock` exists. 6. Audits non-blocking until G6.
- **Tests first:** n/a (config).
- **Done when:** `gh run list --limit 1 --json conclusion -q ".[0].conclusion"` on a fresh clone's push → `success`.
- **Rollback:** revert the workflow file.

#### Gate G0: Foundation   [ ]
Standard checks S1–S9 plus the G0 extras in the Phase Profile. Evidence in PROGRESS.md.

---
### Phase 1: Data, Contracts, Eval Harness (Days 1–3 · contract freeze C1 at end of D2)
**Goal:** frozen contracts, three SOPs with golden step graphs, a filmed and labeled benchmark, and metrics that run before any model exists. **Exit:** Gate G1

**Phase Profile**
- Purpose: define the interfaces and the yardstick first, so every later task is measured.
- Entry: G0 passed (contracts can start after T-0.2).
- Workflow: schema → examples → validator → fixtures; filming follows a written shot list; ground truth labeled the same day.
- Test focus: negative schema cases; metric edge cases (shifted, duplicate, wrong type); oracle/empty sanity.
- Security focus: no real PII in clips beyond consenting teammates; clips stay out of git; manifests carry sha256.
- Default tier: standard (filming: light).
- Gate extras: tag `contracts-v1` · 15 dev + 9 held-out clips validated · oracle F1 = 1.00, empty recall = 0 · held-out lock committed BEFORE any tuning.
- Exit evidence: `pw-data validate` outputs, lock hash, oracle/empty bench outputs.

### T-1.1 · Contracts A: sop, tracks, timeline + validator CLI                         [x]
- **Track:** DATA | **Serves:** NFR-04, FR-13 | **Size:** M | **Tier:** standard | **Depends:** T-0.2 | **Blocks:** T-1.3, T-2.2, T-3.2
- **Context pack (read only these):** §1B · ADR-001 (track shape)
- **Goal:** JSON Schema 2020-12 for step graph, tracks and timeline, with examples and a `pw-data` CLI.
- **Touch:** `contracts/{sop,tracks,timeline}.schema.json`, `contracts/examples/*`, `src/pw/data/*`, `tests/contracts/*` | **Never touch:** `src/pw/perception/*`
- **Steps:** 1. Write the three schemas. 2. One realistic example each. 3. `pw-data validate-contracts` and `validate-artifact <file>`. 4. Negative tests.
- **Tests first:** happy (examples valid) · edge (empty tracks list ok) · failure (missing field, bad enum, negative time, non-monotonic frames rejected).
- **Done when:** `uv run pytest tests/contracts -q` → pass; `uv run pw-data validate-contracts` → "OK 3 schemas, 3 examples".

### T-1.2 · Contracts B: alignment, report, manifest + generated TS types (C1)       [x]
- **Track:** DATA | **Serves:** NFR-04, FR-12 | **Size:** M | **Tier:** standard | **Depends:** T-1.1, T-0.3 | **Blocks:** T-1.6, T-3.5, T-5.6
- **Context pack (read only these):** 05_Schema §6–11, §14 · 01_PRD FR-12 · T-1.1 schemas
- **Goal:** contracts per `05_Schema.md` §6–10 and §14 (alignment incl. identities/likelihoods, report with evidence/illustration `kind`, manifest, review, thresholds); TS types generated; three hand-authored realistic fixture reports for FE.
- **Touch:** `contracts/{alignment,report,manifest,review,thresholds}.schema.json`, `contracts/examples/*`, `web/src/types/generated/*`, `web/scripts/gen-types.mjs` | **Never touch:** `web/src/app/*`
- **Steps:** 1. Schemas. 2. Fixtures with SAM-like polygons. 3. Implement `gen-types.mjs`. 4. Negative tests (illustration inside `evidence[]` must fail). 5. Tag `contracts-v1` (**C1 freeze**).
- **Tests first:** happy · evidence/illustration kind mixing rejected · deviation without track/time refs rejected.
- **Done when:** `uv run pytest tests/contracts -q` → pass; `npm --prefix web run gen:types; git diff --exit-code web/src/types/generated` → exit 0; `git tag -l contracts-v1` → `contracts-v1`.

### T-1.3 · Author 3 SOPs, golden step graphs, GT schema, shot list                   [x]
- **Track:** DATA | **Serves:** FR-13 | **Size:** M | **Tier:** light | **Depends:** T-1.1 | **Blocks:** T-1.4, T-1.5, T-1.6, T-3.3
- **Context pack (read only these):** A-8 · `contracts/sop.schema.json`
- **Goal:** SOP text for P-A/P-B/P-C, hand-written golden step graphs, GT YAML schema, and a shot list covering every deviation variant.
- **Touch:** `bench/sops/*.md`, `bench/golden/*.json`, `bench/gt.schema.json`, `docs/bench/shot_list.md` | **Never touch:** `src/*`
- **Steps:** 1. Write SOPs (8–12 steps, ≥3 tools, ≥1 critical, ≥1 order-sensitive pair, ≥1 any-order group). 2. Hand-write golden graphs. 3. GT schema: per clip `compliant`, `steps[{id,t_start,t_end}]`, `deviations[{type,step_id,t_start,t_end}]`, `instances{concept:count}`, `operator`, `camera`. 4. Shot list: per procedure 1 compliant, 1 missed, 1 out-of-order, 1 wrong-tool, 1 mixed (dev) + 1 compliant, 1 single, 1 mixed (held-out).
- **Tests first:** golden graphs validate; GT schema accepts a sample and rejects a deviation with unknown step id.
- **Done when:** `uv run pw-data validate-sops` → "3 SOPs, 3 golden graphs valid; steps 8–12; critical ≥ 1; tools ≥ 3".

### T-1.4 · Film and label the dev set (15 clips)                                      [ ]
- **Track:** DATA | **Serves:** FR-13 | **Size:** M | **Tier:** light | **Depends:** T-1.3 | **Blocks:** T-1.7, T-2.10
- **Context pack (read only these):** `docs/bench/shot_list.md` · `bench/gt.schema.json`
- **Goal:** 15 dev clips (3 procedures × 5 variants), 45–180 s, fixed phone on a stand, 1080p ≥ 30 fps, hands and tools visible, ground truth labeled the same day.
- **Touch:** `bench/dev/manifest.json`, `bench/dev/gt/*.yaml` (video files live outside git) | **Never touch:** `bench/heldout/*`
- **Steps:** 1. Film per shot list. 2. Label steps and deviations to ±0.5 s. 3. Hash clips; upload to shared storage; write manifest. 4. Second person spot-checks 5 labels.
- **Tests first:** validator rejects missing clip, wrong sha256, GT step outside clip duration.
- **Done when:** `uv run pw-data validate --split dev` → "15 clips OK · 15 GT OK · durations 45–180 s · sha256 match".

### T-1.5 · Film and label the held-out set (9 clips)                                  [ ]
- **Track:** DATA | **Serves:** FR-13 | **Size:** M | **Tier:** light | **Depends:** T-1.3 | **Blocks:** T-1.8
- **Context pack (read only these):** `docs/bench/shot_list.md`
- **Goal:** 9 clips (3 procedures × [compliant, single deviation, mixed]) with a different operator, lighting and camera angle than dev. Never used for tuning.
- **Touch:** `bench/heldout/manifest.json`, `bench/heldout/gt/*.yaml` | **Never touch:** `bench/dev/*`
- **Steps:** 1. Film with a different operator/angle/lighting. 2. Label and hash. 3. Manifest. 4. Do NOT run any model on these.
- **Tests first:** same validator cases as T-1.4.
- **Done when:** `uv run pw-data validate --split heldout` → "9 clips OK · 9 GT OK".

### T-1.6 · Metrics module                                                              [x]
- **Track:** ML | **Serves:** FR-13, NFR-07 | **Size:** S | **Tier:** standard | **Depends:** T-1.2, T-1.3 | **Blocks:** T-1.7
- **Context pack (read only these):** NFR-07 · `contracts/report.schema.json` · `bench/gt.schema.json`
- **Goal:** pure functions: type-aware matching (±2.0 s, same step id), P/R/F1 per type and overall, false flags per compliant clip, timestamp MAE, step frame accuracy, cost/latency aggregation.
- **Touch:** `src/pw/bench/metrics.py`, `tests/bench/test_metrics.py` | **Never touch:** `src/pw/bench/runner.py`
- **Steps:** 1. Matching (greedy by overlap, one-to-one). 2. Metrics. 3. Aggregation. 4. Tests.
- **Tests first:** perfect · empty · shifted within tolerance · shifted outside · wrong type · duplicate predictions · compliant clip with a false flag · `needs_review` excluded from "flagged" counts.
- **Done when:** `uv run pytest tests/bench/test_metrics.py -q` → pass (≥ 15 tests).

### T-1.7 · Bench runner with oracle and empty predictors                              [ ]
- **Track:** ML | **Serves:** FR-13 | **Size:** M | **Tier:** standard | **Depends:** T-1.4, T-1.6 | **Blocks:** T-3.10, T-3.12
- **Context pack (read only these):** T-1.6 API · manifests
- **Goal:** `pw-bench run --split --predictor oracle|empty|full|baseline_a|baseline_b --config` writes `results/<run>/{summary.json,table.md,per_clip.json,manifest.json}`.
- **Touch:** `src/pw/bench/runner.py`, `src/pw/bench/cli.py`, `tests/bench/test_runner.py` | **Never touch:** `src/pw/bench/metrics.py`
- **Steps:** 1. Predictor protocol. 2. Oracle and empty predictors. 3. Results writers. 4. CLI.
- **Tests first:** oracle → F1 1.00 · empty → recall 0 and zero false flags · unknown predictor → exit 2.
- **Done when:** `uv run pw-bench run --split dev --predictor oracle` → overall F1 1.00; `uv run pw-bench run --split dev --predictor empty` → recall 0.00.

### T-1.8 · Held-out lock                                                                [ ]
- **Track:** DATA | **Serves:** FR-13, NFR-07 | **Size:** S | **Tier:** light | **Depends:** T-1.5 | **Blocks:** T-3.10, T-6.2
- **Context pack (read only these):** `bench/heldout/manifest.json`
- **Goal:** `bench/HELDOUT.lock` (sha256 of all held-out clips and GT) and `pw-data verify-lock`; committed BEFORE any tuning (T-3.10).
- **Touch:** `bench/HELDOUT.lock`, `src/pw/data/lock.py`, `tests/contracts/test_lock.py` | **Never touch:** `bench/heldout/gt/*`
- **Steps:** 1. Hash everything. 2. Write lock + verifier. 3. Record the commit hash in PROGRESS.md. 4. Tamper test.
- **Tests first:** unchanged → OK; edited GT → violation; added/removed clip → violation.
- **Done when:** `uv run pw-data verify-lock` → `LOCK OK`; after editing any held-out GT file → exit 1 `LOCK VIOLATION` (then revert).

#### Gate G1: Data and contracts   [ ]
Standard checks S1–S9 plus the G1 extras in the Phase Profile. Evidence in PROGRESS.md.

---
### Phase 2: Perception and Interaction Timeline (Days 2–4)
**Goal:** from a video, produce stitched SAM tracks with persistent IDs, a deterministic interaction timeline, per-track tool identities and candidate segments. **Exit:** Gate G2

**Phase Profile**
- Purpose: turn pixels into a structured, testable "what was touched, moved, and when".
- Entry: G0 passed; contracts-v1 frozen (C1); dev clips available for live smokes.
- Workflow: pure-function modules over synthetic tracks first (red → green), then live smoke on one clip, then replay on all dev clips.
- Test focus: synthetic scenes (pick-up, tool swap, occlusion, ID switch), VFR video, chunk boundaries; coverage ≥ 90% on `timeline/`.
- Security focus: ffmpeg/ffprobe invoked without a shell; filename sanitisation; no model output executed.
- Default tier: standard (stitching, events: deep).
- Gate extras: `pw-bench perception-check` PASS on ≥ 12/15 dev clips · stitched tracks validate vs contract · a human reviews debug overlays for one clip per procedure and signs in PROGRESS.md · SAM cost/latency per clip within NFR budgets (or an ADR amends them).
- Exit evidence: perception-check table, overlay review note, ledger totals.

### T-2.1 · Video ingest and normalisation                                              [ ]
- **Track:** BE | **Serves:** FR-01 | **Size:** S | **Tier:** standard | **Depends:** T-0.2, T-0.4 | **Blocks:** T-2.2, T-2.9
- **Context pack (read only these):** ADR-001 (limits) · §1B
- **Goal:** probe, normalise to constant frame rate (default 15 fps) and ≤720p, compute sha256, build frame↔time map from PTS, enforce caps, extract keyframes on demand.
- **Touch:** `src/pw/ingest/*`, `tests/ingest/*` | **Never touch:** `src/pw/perception/*`
- **Steps:** 1. ffprobe wrapper (no shell). 2. ffmpeg normalise (handle rotation). 3. PTS-based time map. 4. Caps (≤180 s, ≤500 MB). 5. Keyframe util.
- **Tests first:** happy (CFR in → out) · edge (variable-frame-rate phone video; rotation metadata) · failure (corrupt file, no video stream, too long) · security (malicious filename never reaches a shell).
- **Done when:** `uv run pytest tests/ingest -q` → pass; `uv run python -m pw.ingest bench/dev/A1.mp4` → prints fps=15 and frame count within ±1 of duration×15.

### T-2.2 · SAM chunk runner                                                            [ ]
- **Track:** ML | **Serves:** FR-03 | **Size:** M | **Tier:** deep | **Depends:** T-0.4, T-0.7, T-1.1, T-2.1 | **Blocks:** T-2.3, T-2.4
- **Context pack (read only these):** ADR-001 · `contracts/tracks.schema.json` · `src/pw/clients/sam.py`
- **Goal:** split video into overlapping chunks, call SAM per chunk × concept group (respecting the object cap), parse to per-chunk raw tracks, resumable.
- **Touch:** `src/pw/perception/chunking.py`, `src/pw/perception/sam_runner.py`, `tests/perception/test_chunk_runner.py` | **Never touch:** `src/pw/clients/*`
- **Steps:** 1. Chunk planner from ADR-001 limits. 2. Concept grouping (`hand` always present). 3. Per-chunk call + parse. 4. Persist `stages/tracks_raw/chunk_k.json`. 5. Resume skips completed chunks.
- **Tests first:** happy (3 chunks, fake SAM) · edge (clip shorter than a chunk) · failure (chunk 2 times out → retried → marked partial) · ledger counts calls.
- **Done when:** `uv run pytest tests/perception/test_chunk_runner.py -q` → pass; live smoke `uv run pw perceive bench/dev/A1.mp4 --mode live --max-seconds 30` → ≥ 1 chunk file and `uv run pw-data validate-artifact` OK.

### T-2.3 · Track stitching across chunks                                                [ ]
- **Track:** ML | **Serves:** FR-03 | **Size:** M | **Tier:** deep | **Depends:** T-2.2 | **Blocks:** T-2.5, T-2.7
- **Context pack (read only these):** `src/pw/perception/sam_runner.py` outputs · ADR-001 (ID persistence)
- **Goal:** global track IDs by Hungarian matching on mask IoU in chunk overlaps (same concept, motion-consistent), plus re-association after occlusion via colour-histogram similarity.
- **Touch:** `src/pw/perception/stitch.py`, `tests/perception/test_stitch.py` | **Never touch:** `src/pw/perception/sam_runner.py`
- **Steps:** 1. Overlap matching. 2. Gap re-association. 3. Fragmentation report. 4. Tests.
- **Tests first:** two objects crossing in an overlap · occlusion gap · injected ID switch · different concepts never merged.
- **Done when:** `uv run pytest tests/perception/test_stitch.py -q` → pass; on a dev clip (replay) `uv run pw perceive --stitch-report` → fragmentation ratio (global tracks ÷ GT `instances`) ≤ 1.5.

### T-2.4 · Mask utilities                                                                [ ]
- **Track:** ML | **Serves:** FR-03 | **Size:** S | **Tier:** standard | **Depends:** T-2.2 | **Blocks:** T-2.5, T-5.10
- **Context pack (read only these):** ADR-001 (mask encoding)
- **Goal:** decode per ADR-001, RLE↔polygon, simplify polygons for the UI, box fallback, temporal smoothing and ≤3-frame gap fill, coverage report.
- **Touch:** `src/pw/perception/masks.py`, `tests/perception/test_masks.py` | **Never touch:** `src/pw/perception/stitch.py`
- **Steps:** 1. Decode. 2. Polygon simplify (Douglas–Peucker). 3. Smooth/gap-fill. 4. Coverage stats.
- **Tests first:** round-trip RLE ↔ polygon IoU ≥ 0.95 · empty mask · single-frame gap filled · gap > 3 frames kept as gap.
- **Done when:** `uv run pytest tests/perception/test_masks.py -q` → pass.

### T-2.5 · Hand–object interaction features                                            [ ]
- **Track:** ML | **Serves:** FR-04 | **Size:** M | **Tier:** standard | **Depends:** T-2.3, T-2.4 | **Blocks:** T-2.6
- **Context pack (read only these):** `contracts/tracks.schema.json` · `contracts/timeline.schema.json`
- **Goal:** per-frame contact (dilated-mask overlap, fallback box IoU), proximity normalised by hand size, hold state with hysteresis, object velocity normalised by frame diagonal.
- **Touch:** `src/pw/timeline/features.py`, `tests/timeline/test_features.py` | **Never touch:** `src/pw/perception/*`
- **Steps:** 1. Contact. 2. Hysteresis thresholds in config. 3. Velocity. 4. Tests on synthetic tracks.
- **Tests first:** static object · brief touch (< 0.3 s ignored) · sustained hold · occlusion flicker bridged · two hands.
- **Done when:** `uv run pytest tests/timeline/test_features.py -q` → pass.

### T-2.6 · Event extraction → timeline.json                                             [ ]
- **Track:** ML | **Serves:** FR-04 | **Size:** M | **Tier:** deep | **Depends:** T-2.5 | **Blocks:** T-2.8, T-2.10, T-3.4
- **Context pack (read only these):** `contracts/timeline.schema.json` · `src/pw/timeline/features.py`
- **Goal:** events `hold_start/hold_end`, `contact_start/contact_end` (tool↔part), `move`, `enter/exit` (object ↔ tracked zone concept), debounced, each citing track IDs and times with a confidence.
- **Touch:** `src/pw/timeline/events.py`, `tests/timeline/test_events.py` | **Never touch:** `src/pw/timeline/features.py`
- **Steps:** 1. Event rules. 2. Debounce/merge. 3. Confidence from mean score × coverage. 4. Emit contract-valid JSON. 5. Property test: events ordered, ids unique.
- **Tests first:** pick-up/put-down · tool swap · drop · part placed into a zone · idempotent re-run.
- **Done when:** `uv run pytest tests/timeline -q --cov=src/pw/timeline --cov-fail-under=90` → pass.

### T-2.7 · Track identity classification                                                [ ]
- **Track:** ML | **Serves:** FR-05 | **Size:** M | **Tier:** standard | **Depends:** T-0.5, T-0.7, T-2.3 | **Blocks:** T-3.6
- **Context pack (read only these):** ADR-002 · golden step graph vocabulary · `src/pw/clients/wonder.py`
- **Goal:** classify each tool/part track once: choose top-3 crops (area × sharpness × non-occlusion), ask Wonder to pick from the SOP vocabulary or `other`, majority vote, confidence; cache per track.
- **Touch:** `src/pw/perception/identity.py`, `tests/perception/test_identity.py` | **Never touch:** `src/pw/clients/*`
- **Steps:** 1. Crop selection. 2. Prompt + strict JSON. 3. Vote and confidence. 4. Per-track cache. 5. `identities.json` (≤ 1 call per track).
- **Tests first:** consistent label · split vote → low confidence · `other` · API failure → `unknown`.
- **Done when:** `uv run pytest tests/perception/test_identity.py -q` → pass; `uv run pw identify runs/<id> --mode replay` → ≥ 80% of tool tracks labeled with confidence ≥ 0.6.

### T-2.8 · Candidate action segmentation                                                [ ]
- **Track:** ML | **Serves:** FR-04 | **Size:** S | **Tier:** standard | **Depends:** T-2.6 | **Blocks:** T-3.4
- **Context pack (read only these):** `contracts/timeline.schema.json`
- **Goal:** segments from change-points (hold start/stop, contact start/stop, idle > 2 s); min 1 s, max 20 s (split); each lists salient tracks and event IDs.
- **Touch:** `src/pw/timeline/segments.py`, `tests/timeline/test_segments.py` | **Never touch:** `src/pw/timeline/events.py`
- **Steps:** 1. Change-points. 2. Merge short. 3. Split long. 4. Emit.
- **Tests first:** boundaries at events · short segments merged · long segment split · no events → one idle segment.
- **Done when:** `uv run pytest tests/timeline/test_segments.py -q` → pass.

### T-2.9 · Render primitives and debug overlay                                           [ ]
- **Track:** BE | **Serves:** FR-09 | **Size:** M | **Tier:** standard | **Depends:** T-2.1, T-1.1 | **Blocks:** T-3.4, T-4.1
- **Context pack (read only these):** `contracts/tracks.schema.json` · §1A (evidence rule)
- **Goal:** pure functions to draw mask overlays (alpha, colour by track ID), `#id concept` labels, timestamp burn-in, set-of-mark numbered keyframes, caption bar; `pw overlay` writes a debug mp4.
- **Touch:** `src/pw/evidence/render.py`, `src/pw/evidence/overlay_cli.py`, `tests/evidence/test_render.py` | **Never touch:** `src/pw/perception/*`
- **Steps:** 1. Overlay + labels. 2. Timestamp + caption. 3. Set-of-mark renderer. 4. Overlay CLI. 5. Golden perceptual-hash tests.
- **Tests first:** golden image within pHash distance ≤ 4 · label collision keeps both readable · empty track list renders the plain frame.
- **Done when:** `uv run pytest tests/evidence/test_render.py -q` → pass; `uv run pw overlay runs/<id> --out overlay.mp4` → file exists and `ffprobe` duration within 0.2 s of source.

### T-2.10 · Perception check on dev                                                       [ ]
- **Track:** ML | **Serves:** FR-04, FR-13 | **Size:** S | **Tier:** standard | **Depends:** T-1.4, T-2.6, T-2.7 | **Blocks:** G2
- **Context pack (read only these):** `bench/dev/gt/*.yaml` · NFR-07
- **Goal:** automated sanity gate: hand coverage ≥ 90% of frames, fragmentation ratio ≤ 1.5, tool pick-up events fall inside GT step windows ±2 s for ≥ 80%.
- **Touch:** `src/pw/bench/perception_check.py`, `docs/results/perception_dev.md` | **Never touch:** `src/pw/bench/metrics.py`
- **Steps:** 1. Compute the three checks. 2. Table output. 3. Write results file.
- **Tests first:** synthetic pass case and each failing case.
- **Done when:** `uv run pw-bench perception-check --split dev --mode replay` → PASS on ≥ 12/15 clips; exceptions listed in the results file.

#### Gate G2: Perception   [ ]
Standard checks S1–S9 plus the G2 extras in the Phase Profile. Evidence in PROGRESS.md.

---
### Phase 3: Reasoning: SOP Compile, Alignment, Deviations (Days 3–5)
**Goal:** SOP → step graph; segments → step likelihoods → constrained global alignment → verified, explained deviations; first end-to-end dev numbers vs baselines. **Exit:** Gate G3

**Phase Profile**
- Purpose: make the decision logic deterministic and testable; let Muse Wonder supply perception, not verdicts.
- Entry: G2 passed (or perception-check ≥ 12/15); C1 frozen.
- Workflow: contract-first → pure module with synthetic tests (red → green) → model prompt behind a fake → replay on dev → live on one clip.
- Test focus: aligner on synthetic likelihood matrices (perfect, swapped, missing, duplicate, any-order group, noisy); each deviation type; compliant → zero flags; coverage ≥ 90% on `align/`.
- Security focus: model output is data, never executed; explanations validated against structured data (no invented timestamps or tools).
- Default tier: deep.
- Gate extras: `pw-bench run --split dev --predictor full` completes on 15/15 clips · first dev numbers recorded for Full vs A vs B · `pw-bench sop-eval` PASS 3/3 · every deviation has step id + track ids + times · **RED trigger:** if Full F1 < baseline B F1, stop and re-plan (identity/set-of-mark/segmentation) before G4.
- Exit evidence: dev results table (Full, A, B), sop-eval output, coverage report.

### T-3.1 · SOP ingest (md, txt, pdf)                                                     [x]
- **Track:** ML | **Serves:** FR-01, FR-02 | **Size:** S | **Tier:** light | **Depends:** T-0.2 | **Blocks:** T-3.2
- **Context pack (read only these):** `bench/sops/*.md`
- **Goal:** normalise `.md`/`.txt`/text-PDF (pymupdf) into a `SopSource`; scanned PDFs yield page images flagged for Wonder vision.
- **Touch:** `src/pw/sop/ingest.py`, `tests/sop/test_ingest.py` | **Never touch:** `src/pw/sop/compiler.py`
- **Steps:** 1. Readers per type. 2. Step-number normalisation. 3. Size caps (≤ 50 pages). 4. Tests.
- **Tests first:** md · txt · text PDF · scanned PDF fixture · empty file · oversize.
- **Done when:** `uv run pytest tests/sop/test_ingest.py -q` → pass.

### T-3.2 · SOP compiler → step graph + SAM vocabulary                                    [ ]
- **Track:** ML | **Serves:** FR-02 | **Size:** M | **Tier:** deep | **Depends:** T-0.5, T-1.1, T-3.1 | **Blocks:** T-3.3, T-3.4, T-5.3
- **Context pack (read only these):** ADR-002 · `contracts/sop.schema.json` · `bench/golden/*.json`
- **Goal:** strict-JSON compile into steps (id, text, action, tools, parts, ordering `strict|unordered_group`, `critical`, `visual_check`) and a generic-noun-phrase SAM vocabulary that always includes `hand`.
- **Touch:** `src/pw/sop/compiler.py`, `src/pw/sop/prompts.py`, `tests/sop/test_compiler.py` | **Never touch:** `contracts/*`
- **Steps:** 1. Prompt + schema. 2. Validator + repair loop (≤ 2). 3. Grounding rule: every tool/part string must occur in the SOP text (normalised). 4. Critical cues (must, warning, caution). 5. Cache at T=0.
- **Tests first:** golden SOP → expected structure · invalid JSON → repair · hallucinated tool rejected · unordered group detected.
- **Done when:** `uv run pytest tests/sop/test_compiler.py -m "not live" -q` → pass.

### T-3.3 · SOP compiler golden evaluation                                                [ ]
- **Track:** ML | **Serves:** FR-02, FR-13 | **Size:** S | **Tier:** standard | **Depends:** T-3.2, T-1.3 | **Blocks:** G3
- **Context pack (read only these):** `bench/golden/*.json`
- **Goal:** measure compiler vs golden: exact step count, tool P/R ≥ 0.9, ordering-constraint F1 ≥ 0.9, critical recall 1.0.
- **Touch:** `src/pw/sop/eval.py`, `tests/sop/test_eval.py` | **Never touch:** `src/pw/sop/compiler.py`
- **Steps:** 1. Compare graphs. 2. Metrics. 3. CLI `pw-bench sop-eval`.
- **Tests first:** identical → 1.0 · dropped step → fails · extra tool → precision drop.
- **Done when:** `uv run pw-bench sop-eval --mode replay` → `PASS 3/3`.

### T-3.4 · Segment → step likelihood scorer                                               [ ]
- **Track:** ML | **Serves:** FR-06 | **Size:** M | **Tier:** deep | **Depends:** T-0.7, T-2.6, T-2.8, T-2.9, T-3.2 | **Blocks:** T-3.5
- **Context pack (read only these):** ADR-002 · `src/pw/evidence/render.py` (set-of-mark) · `contracts/timeline.schema.json`
- **Goal:** per segment, send ≤ 4 set-of-mark keyframes + a timeline excerpt + the step list; receive `{step_probs, observed_tools, rationale_short}` (with a `none` option) in strict JSON; batch and cache.
- **Touch:** `src/pw/align/scorer.py`, `src/pw/align/prompts.py`, `tests/align/test_scorer.py` | **Never touch:** `src/pw/evidence/*`
- **Steps:** 1. Prompt builder with token budget. 2. Parse/normalise probabilities. 3. Batching. 4. Failure → uniform + flag. 5. Likelihood matrix writer.
- **Tests first:** parse · missing steps default 0 · normalisation · overlong prompt truncated deterministically · failure path flagged.
- **Done when:** `uv run pytest tests/align/test_scorer.py -q` → pass; `uv run pw score runs/<id> --mode replay` → matrix rows sum to 1 ± 0.01.

### T-3.5 · Constrained global aligner (DP)                                                [ ]
- **Track:** ML | **Serves:** FR-06 | **Size:** M | **Tier:** deep | **Depends:** T-1.2, T-3.4 | **Blocks:** T-3.6, T-3.11
- **Context pack (read only these):** `contracts/alignment.schema.json` · §1A item 3
- **Goal:** pure module: Viterbi/DTW-style alignment of segments to steps with a null state, partial-order constraints, higher skip penalty for critical steps, and margin (best vs second-best path) as confidence.
- **Touch:** `src/pw/align/aligner.py`, `tests/align/test_aligner.py` | **Never touch:** `src/pw/align/scorer.py`
- **Steps:** 1. Cost model. 2. DP with constraints. 3. Margin by constrained second-best. 4. Emit alignment.json. 5. Performance test.
- **Tests first:** perfect · adjacent swap · missing step · repeated step · any-order group · two critical skipped · noisy likelihoods · 200 segments < 1 s.
- **Done when:** `uv run pytest tests/align/test_aligner.py -q --cov=src/pw/align --cov-fail-under=90` → pass.

### T-3.6 · Deviation derivation (missed, out-of-order, wrong-tool)                        [ ]
- **Track:** ML | **Serves:** FR-07, NFR-04 | **Size:** M | **Tier:** deep | **Depends:** T-2.7, T-3.5 | **Blocks:** T-3.7, T-3.8, T-3.11
- **Context pack (read only these):** `contracts/report.schema.json` (deviation) · A-9
- **Goal:** derive deviations from alignment + identities: missed (gap with no segment ≥ τ), out-of-order (minimal violating set via longest-increasing-subsequence over the partial order), wrong-tool (identity ≠ required with confidence ≥ τ while holding on the target part); severity from `critical`; status by thresholds; every deviation cites step id, track ids, times.
- **Touch:** `src/pw/align/deviations.py`, `tests/align/test_deviations.py` | **Never touch:** `src/pw/align/aligner.py`
- **Steps:** 1. Missed. 2. Out-of-order minimal set. 3. Wrong-tool. 4. Severity/status. 5. Reference check.
- **Tests first:** each type · compound · compliant → 0 · any-order group not flagged · critical → high severity · deviation without refs rejected.
- **Done when:** `uv run pytest tests/align/test_deviations.py -q` → pass.

### T-3.7 · Verifier pass                                                                   [ ]
- **Track:** ML | **Serves:** FR-08 | **Size:** M | **Tier:** deep | **Depends:** T-0.7, T-3.6 | **Blocks:** T-3.9
- **Context pack (read only these):** ADR-002 · `src/pw/align/deviations.py`
- **Goal:** for each `missed`, ask Wonder (video clip of the gap window) "did step X occur? cite times" (negative-evidence check); for `wrong_tool`/`out_of_order`, an independent second look with different framing; disagreement → `needs_review`.
- **Touch:** `src/pw/align/verifier.py`, `tests/align/test_verifier.py` | **Never touch:** `src/pw/align/deviations.py`
- **Steps:** 1. Prompts. 2. Agreement logic. 3. Confidence update. 4. `PW_DISABLE_VERIFIER` switch. 5. Failure keeps original with `verifier_unavailable`.
- **Tests first:** confirm raises confidence · reject drops to `needs_review` or removes · disagreement → `needs_review` · API failure path.
- **Done when:** `uv run pytest tests/align/test_verifier.py -q` → pass.

### T-3.8 · Grounded explanation writer                                                     [ ]
- **Track:** ML | **Serves:** FR-08 | **Size:** S | **Tier:** standard | **Depends:** T-3.6 | **Blocks:** T-3.9
- **Context pack (read only these):** `src/pw/align/deviations.py`
- **Goal:** ≤ 2 sentences, ≤ 40 words, citing step, observed vs expected, mm:ss; validator rejects any time not within ±0.5 s of data or any tool not in the vocabulary; template fallback.
- **Touch:** `src/pw/align/explain.py`, `tests/align/test_explain.py` | **Never touch:** `src/pw/align/verifier.py`
- **Steps:** 1. Constrained prompt. 2. Validator. 3. ≤ 2 retries. 4. Template fallback.
- **Tests first:** valid text accepted · invented timestamp rejected · unknown tool rejected · fallback used.
- **Done when:** `uv run pytest tests/align/test_explain.py -q` → pass.

### T-3.9 · Orchestrator: real stages, caching, spend cap, partial failure                [ ]
- **Track:** BE | **Serves:** FR-15, NFR-02, NFR-03 | **Size:** M | **Tier:** standard | **Depends:** T-0.8, T-2.3, T-2.6, T-2.7, T-3.2, T-3.7, T-3.8 | **Blocks:** T-3.10, T-5.2
- **Context pack (read only these):** `src/pw/pipeline/*` · §1B
- **Goal:** replace fake stages with real ones; content-hash cache per stage; resume; progress events; `PW_SPEND_CAP_USD` abort with a partial report; a failed stage degrades the report instead of crashing.
- **Touch:** `src/pw/pipeline/*`, `tests/pipeline/*` | **Never touch:** `src/pw/align/*`, `src/pw/perception/*`
- **Steps:** 1. Wire stages. 2. Cache keys. 3. Events. 4. Cap + degrade policy. 5. Manifest (models, versions, thresholds hash, costs).
- **Tests first:** resume skips cached stages · cap aborts with a partial valid report · stage failure isolated and bannered.
- **Done when:** `uv run pytest tests/pipeline -q` → pass; `uv run pw run --mode replay --video bench/dev/A2.mp4 --sop bench/sops/A.md` → exit 0 and `uv run pw-data validate-artifact runs/<id>/report.json` OK.

### T-3.10 · Threshold calibration on dev                                                  [ ]
- **Track:** ML | **Serves:** NFR-07, FR-08 | **Size:** M | **Tier:** standard | **Depends:** T-1.7, T-1.8, T-3.9 | **Blocks:** T-6.1
- **Context pack (read only these):** NFR-07 · `src/pw/bench/runner.py`
- **Goal:** grid-search flag threshold, verifier-agreement rule and margin cutoff on DEV only to maximise F1 subject to ≤ 0.3 false flags per compliant clip; write `config/thresholds.json` and freeze it.
- **Touch:** `src/pw/bench/tune.py`, `config/thresholds.json`, `docs/results/tune_dev.md` | **Never touch:** `bench/heldout/*`
- **Steps:** 1. Grid. 2. Constraint filter. 3. Write config + results. 4. Assert `verify-lock` OK before and after. 5. Record the config hash.
- **Tests first:** synthetic predictions pick the expected optimum · constraint violated → rejected.
- **Done when:** `uv run pw-bench tune --split dev` → prints chosen thresholds with dev F1 ≥ baseline B; `uv run pw-data verify-lock` → `LOCK OK`.

### T-3.11 · Procedure-not-recognized guard                                                [ ]
- **Track:** ML | **Serves:** FR-06 | **Size:** S | **Tier:** standard | **Depends:** T-3.5, T-3.6 | **Blocks:** T-4.6
- **Context pack (read only these):** `contracts/report.schema.json` (status)
- **Goal:** if matched-step coverage < 0.3 or alignment cost > τ, return `procedure_not_recognized` with a message and no deviations.
- **Touch:** `src/pw/align/domain_guard.py`, `tests/align/test_domain_guard.py` | **Never touch:** `src/pw/align/aligner.py`
- **Steps:** 1. Coverage/cost rule. 2. Report status. 3. Tests.
- **Tests first:** SOP A with video of procedure B → not recognized · blank video → not recognized · matching pair → recognized.
- **Done when:** `uv run pytest tests/align/test_domain_guard.py -q` → pass.

### T-3.12 · Baselines A and B for the ablation                                             [ ]
- **Track:** ML | **Serves:** FR-13 | **Size:** M | **Tier:** standard | **Depends:** T-0.5, T-1.7 | **Blocks:** T-6.1
- **Context pack (read only these):** ADR-002 · `src/pw/bench/runner.py`
- **Goal:** `baseline_a` = Wonder with the full raw video + SOP → deviations; `baseline_b` = Wonder with uniformly sampled keyframes (no SAM) + SOP → deviations; same schema and spend cap; fairness note.
- **Touch:** `src/pw/bench/baselines.py`, `docs/results/baselines.md` | **Never touch:** `src/pw/bench/metrics.py`
- **Steps:** 1. Prompts. 2. Schema parse. 3. Budget parity. 4. Register predictors.
- **Tests first:** parse valid/invalid · over-budget aborts.
- **Done when:** `uv run pw-bench run --split dev --predictor baseline_b --mode replay` → summary.json with F1 and per-clip cost (any value).

#### Gate G3: Reasoning   [ ]
Standard checks S1–S9 plus the G3 extras in the Phase Profile. `config/thresholds.json` frozen after this gate. Evidence in PROGRESS.md.

---
### Phase 4: Evidence and Illustration (Days 5–6)
**Goal:** every deviation carries tamper-evident real-frame evidence; every flagged step gets a labeled, QA-checked "what correct looks like" diagram; a contract-valid report. **Exit:** Gate G4

**Phase Profile**
- Purpose: make findings trustworthy and understandable at a glance.
- Entry: G3 passed.
- Workflow: pure selection/render logic first, then provenance, then Muse Image behind a fake, then QA loop.
- Test focus: golden-image tests, provenance tamper tests, `kind` mixing rejected, fallbacks when frames or diagrams are unavailable.
- Security focus: no generated pixels in evidence, ever; watermarks cannot be disabled by config; no faces/identities in prompts.
- Default tier: standard (QA loop deep).
- Gate extras: for all flagged dev deviations `pw verify-evidence` → VERIFIED · illustrations present or explicit fallback · human reviews 10 illustrations (≥ 8 acceptable) · test proves an illustration cannot enter an evidence list.
- Exit evidence: verify-evidence output, illustration review note.

### T-4.1 · Evidence frame selector                                                        [ ]
- **Track:** BE | **Serves:** FR-09 | **Size:** M | **Tier:** standard | **Depends:** T-2.9, T-3.6 | **Blocks:** T-4.2, T-4.6
- **Context pack (read only these):** `src/pw/evidence/render.py` · `contracts/report.schema.json` (evidence)
- **Goal:** choose 2–4 frames per deviation by type (missed: bracket before/after the gap; out-of-order: the two swapped steps; wrong-tool: wrong tool in hand), scored by mask area, Laplacian sharpness, low occlusion; render with SAM masks via the render primitives.
- **Touch:** `src/pw/evidence/selector.py`, `tests/evidence/test_selector.py` | **Never touch:** `src/pw/evidence/render.py`
- **Steps:** 1. Frame scoring. 2. Type strategies. 3. Render. 4. `evidence_unavailable` fallback.
- **Tests first:** each type on synthetic tracks · deterministic output · no usable frame → graceful fallback.
- **Done when:** `uv run pytest tests/evidence/test_selector.py -q` → pass.

### T-4.2 · Evidence clip and provenance                                                    [ ]
- **Track:** BE | **Serves:** FR-09, NFR-06 | **Size:** M | **Tier:** standard | **Depends:** T-4.1 | **Blocks:** T-4.6
- **Context pack (read only these):** `src/pw/evidence/selector.py`
- **Goal:** 3–5 s overlay clip per deviation; `evidence_manifest.json` with source sha256, frame index, render-params version, output sha256; `pw verify-evidence` re-renders and compares perceptual hashes.
- **Touch:** `src/pw/evidence/clip.py`, `src/pw/evidence/provenance.py`, `tests/evidence/test_provenance.py` | **Never touch:** `src/pw/evidence/selector.py`
- **Steps:** 1. ffmpeg clip (no shell). 2. Manifest. 3. Verify command. 4. Tamper tests.
- **Tests first:** untouched → VERIFIED · tampered source → fails · changed render params → fails.
- **Done when:** `uv run pytest tests/evidence/test_provenance.py -q` → pass; `uv run pw verify-evidence runs/<id>/report.json --video bench/dev/A2.mp4` → `VERIFIED n/n`.

### T-4.3 · Muse Image illustration generator                                               [ ]
- **Track:** ML | **Serves:** FR-10 | **Size:** M | **Tier:** standard | **Depends:** T-0.6, T-0.7, T-3.6 | **Blocks:** T-4.4, T-4.5
- **Context pack (read only these):** ADR-003 · `src/pw/clients/image.py`
- **Goal:** per flagged step (deduped), build a prompt from step text, expected tool/part and the deviation; pass the annotated real frame as reference (edit mode per ADR-003); flat technical-schematic style, labeled, no people; cache by hash; ledger entry.
- **Touch:** `src/pw/illustrate/generator.py`, `src/pw/illustrate/prompts.py`, `tests/illustrate/test_generator.py` | **Never touch:** `src/pw/clients/*`
- **Steps:** 1. Prompt builder. 2. Reference handling. 3. Dedupe by step. 4. Cache. 5. `PW_DISABLE_ILLUSTRATIONS`.
- **Tests first:** dedupe by step · cache hit · disabled switch · API failure → `illustration_unavailable`.
- **Done when:** `uv run pytest tests/illustrate/test_generator.py -q` → pass; live smoke `uv run pw illustrate runs/<id> --mode live --limit 1` → 1 image, cost ≈ $0.01.

### T-4.4 · Illustration QA loop                                                             [ ]
- **Track:** ML | **Serves:** FR-10 | **Size:** M | **Tier:** deep | **Depends:** T-4.3 | **Blocks:** T-4.6
- **Context pack (read only these):** ADR-002, ADR-003 · `src/pw/illustrate/generator.py`
- **Goal:** Wonder reviews the diagram against the SOP step (right tool, right action, legible text, no hallucinated labels); ≤ 2 regenerations; else fall back to "no illustration" with a reason.
- **Touch:** `src/pw/illustrate/qa.py`, `tests/illustrate/test_qa.py` | **Never touch:** `src/pw/illustrate/generator.py`
- **Steps:** 1. Review prompt (strict JSON). 2. Retry policy. 3. Fallback. 4. Record QA verdict in the report.
- **Tests first:** pass first time · fail then pass · fail ×3 → fallback · reviewer error → fallback.
- **Done when:** `uv run pytest tests/illustrate/test_qa.py -q` → pass.

### T-4.5 · Provenance labeling and kind enforcement                                         [ ]
- **Track:** BE | **Serves:** FR-09, FR-10 | **Size:** S | **Tier:** standard | **Depends:** T-4.3 | **Blocks:** T-4.6
- **Context pack (read only these):** `contracts/report.schema.json` (`kind`)
- **Goal:** burn "AI ILLUSTRATION · NOT EVIDENCE" into every diagram; the report builder rejects an illustration in `evidence[]`.
- **Touch:** `src/pw/evidence/labeling.py`, `tests/evidence/test_kinds.py` | **Never touch:** `contracts/*`
- **Steps:** 1. Watermark. 2. Kind guard. 3. Tests.
- **Tests first:** watermark present (pixel check) · illustration in evidence → ValidationError · evidence in illustration slot → ValidationError · watermark not configurable off.
- **Done when:** `uv run pytest tests/evidence/test_kinds.py -q` → pass (≥ 4 tests).

### T-4.6 · Report assembly                                                                  [ ]
- **Track:** BE | **Serves:** FR-12, NFR-04 | **Size:** S | **Tier:** standard | **Depends:** T-3.11, T-4.1, T-4.2, T-4.4, T-4.5 | **Blocks:** T-5.2, T-5.5
- **Context pack (read only these):** `contracts/report.schema.json` · `contracts/manifest.schema.json`
- **Goal:** `report.json` builder joining deviations, evidence, illustrations, alignment lanes, manifest (model ids/versions, thresholds hash, costs, input hashes, mode); deterministic ordering; handles `procedure_not_recognized`.
- **Touch:** `src/pw/report/build.py`, `tests/report/test_build.py` | **Never touch:** `src/pw/report/export.py`
- **Steps:** 1. Join. 2. Order. 3. Manifest. 4. Validate.
- **Tests first:** full report valid · not-recognized valid · missing evidence → `evidence_unavailable` valid.
- **Done when:** `uv run pytest tests/report/test_build.py -q` → pass; `uv run pw-data validate-artifact runs/<id>/report.json` → OK.

#### Gate G4: Evidence and illustration   [ ]
Standard checks S1–S9 plus the G4 extras in the Phase Profile. Evidence in PROGRESS.md.

---
### Phase 5: API, UI, Report (Days 3–7; FE starts D3 against frozen fixtures)
**Goal:** a secure API and a review experience a judge understands in ten seconds, plus a self-contained audit report. **Exit:** Gate G5 and **FF** (feature freeze, end of D7)

**Phase Profile**
- Purpose: turn the pipeline into the product people see.
- Entry: C1 frozen; FE may start before the BE gate only against contract-tested fixtures (`contracts/examples`) and may not merge until the endpoints it consumes pass their tests.
- Workflow: tokens → isolated component → all states from §1B → wire to the OpenAPI contract → e2e.
- Test focus: component states, time↔pixel mapping, keyboard, overlay frame budget, e2e journey ×3.
- Security focus: upload validation, access code, rate limit, traversal-safe artifact serving, CSP, no secrets in the client, report HTML has no external references.
- Default tier: standard (guards, review core, overlay: deep).
- Gate extras: every state in §1B implemented · e2e green ×3 · Range seeking works in Chrome and Edge · overlay p95 draw ≤ 8 ms · `openapi.json` and generated types in sync · a human walks the full journey on a held-out-like clip.
- Exit evidence: e2e output, perf output, walkthrough note.

### T-5.1 · Security guards                                                                  [ ]
- **Track:** SEC | **Serves:** FR-01, NFR-05 | **Size:** M | **Tier:** deep | **Depends:** T-0.8 | **Blocks:** T-5.2
- **Context pack (read only these):** NFR-05 · ADR-001 (caps)
- **Goal:** upload validation (magic bytes, extension allowlist, ≤500 MB, ≤180 s via ffprobe in a no-shell subprocess, max resolution), filename sanitation; constant-time access-code dependency; per-IP token-bucket rate limit; traversal-safe artifact resolver; 24 h retention purge (demo cases exempt); log redaction.
- **Touch:** `src/pw/security/*`, `tests/security/*` | **Never touch:** `src/pw/api/*`
- **Steps:** 1. Upload validator. 2. Access dependency. 3. Rate limiter. 4. Safe path resolver. 5. Purge job.
- **Tests first:** happy · edge (exactly at caps) · failure (wrong magic, zip-bomb ratio, `..%2f` traversal) · authz (missing/invalid code → 401).
- **Done when:** `uv run pytest tests/security -q` → pass (≥ 20 tests).
- **Risk or security notes:** this is the only task guarding API spend; the cap must hold under concurrent requests.

### T-5.2 · Runs API and artifact serving                                                    [ ]
- **Track:** BE | **Serves:** FR-01 | **Size:** M | **Tier:** standard | **Depends:** T-3.9, T-4.6, T-5.1 | **Blocks:** T-5.3, T-5.4, T-5.5, T-5.13
- **Context pack (read only these):** `contracts/report.schema.json` · `src/pw/security/*`
- **Goal:** `POST /runs` (multipart video + SOP), `GET /runs`, `GET /runs/{id}`, `GET /runs/{id}/report`, `GET /runs/{id}/artifacts/{path}` with HTTP Range; consistent error shape `{error:{code,message}}`; all routes behind guards; OpenAPI exported.
- **Touch:** `src/pw/api/routes_runs.py`, `src/pw/api/errors.py`, `openapi.json`, `tests/api/test_runs.py` | **Never touch:** `src/pw/security/*`
- **Steps:** 1. Routes. 2. Background run start. 3. Range. 4. Error shape. 5. `pw openapi` export.
- **Tests first:** happy · 404 · 413 · 401 · Range 206 · report 409 while running · concurrent runs queued.
- **Done when:** `uv run pytest tests/api/test_runs.py -q` → pass; `uv run pw openapi --check` → no diff.

### T-5.3 · SOP compile preview and review-decision endpoints                                [ ]
- **Track:** BE | **Serves:** FR-02, FR-11 | **Size:** S | **Tier:** standard | **Depends:** T-3.2, T-5.2 | **Blocks:** T-5.7, T-5.11
- **Context pack (read only these):** `contracts/sop.schema.json`
- **Goal:** `POST /sop/compile` (preview before a run), `PATCH /runs/{id}/review` (accept/dismiss/note per deviation, stored in `review.json`), `POST /runs` accepts an edited step-graph override.
- **Touch:** `src/pw/api/routes_sop.py`, `src/pw/api/routes_review.py`, `tests/api/test_sop_review.py` | **Never touch:** `src/pw/api/routes_runs.py`
- **Steps:** 1. Compile preview. 2. Review PATCH + validation. 3. Override. 4. OpenAPI refresh.
- **Tests first:** happy · invalid graph → 422 · unknown deviation id → 404 · missing code → 401.
- **Done when:** `uv run pytest tests/api/test_sop_review.py -q` → pass.

### T-5.4 · SSE progress stream                                                               [ ]
- **Track:** BE | **Serves:** FR-15 | **Size:** S | **Tier:** standard | **Depends:** T-3.9, T-5.2 | **Blocks:** T-5.8
- **Context pack (read only these):** `src/pw/pipeline/events.py`
- **Goal:** `GET /runs/{id}/events`: stage start/finish, % within stage, running cost, elapsed; late joiners get a replay; 15 s heartbeat.
- **Touch:** `src/pw/api/routes_events.py`, `tests/api/test_sse.py` | **Never touch:** `src/pw/pipeline/*`
- **Steps:** 1. Event stream. 2. Replay for finished runs. 3. Heartbeat. 4. Disconnect handling.
- **Tests first:** ordering · replay · disconnect cleanup · unknown run → 404.
- **Done when:** `uv run pytest tests/api/test_sse.py -q` → pass; `curl -N http://localhost:8000/runs/<id>/events` on a fake run → ≥ 12 `stage` events then `done`.

### T-5.5 · Self-contained report export (HTML, PDF)                                           [ ]
- **Track:** BE | **Serves:** FR-12 | **Size:** M | **Tier:** standard | **Depends:** T-4.6, T-5.2 | **Blocks:** T-5.11, T-5.13
- **Context pack (read only these):** `contracts/report.schema.json` · §1A (evidence rule)
- **Goal:** one HTML file with embedded images, deviations, evidence hashes, model versions, thresholds, and the illustration disclaimer; PDF via headless Chromium print.
- **Touch:** `src/pw/report/export.py`, `src/pw/report/templates/*`, `tests/report/test_export.py` | **Never touch:** `src/pw/report/build.py`
- **Steps:** 1. Template. 2. Inline assets. 3. PDF. 4. Routes `report.html|pdf`.
- **Tests first:** every deviation id present · no `src="http` · size < 15 MB on a dev run · PDF page count ≥ 1.
- **Done when:** `uv run pytest tests/report/test_export.py -q` → pass; `uv run pw export runs/<id> --format html` then `(Select-String -Path runs/<id>/report.html -Pattern 'src="http').Count` → 0.

### T-5.6 · App shell, tokens, typed API client                                               [ ]
- **Track:** FE | **Serves:** FR-11, NFR-09 | **Size:** M | **Tier:** standard | **Depends:** T-0.3, T-1.2 | **Blocks:** T-5.7, T-5.8, T-5.9, T-5.12
- **Context pack (read only these):** `contracts/examples/*` (stub client until `openapi.json` lands in T-5.2) · `web/src/types/generated/*` · §1B (UI states)
- **Goal:** Tailwind tokens (dark, high contrast, 18 px base for projectors), layout, routes (`/`, `/runs/:id`, `/demo`), typed client, loading/empty/error components, access-code gate.
- **Touch:** `web/src/app/*`, `web/src/api/*`, `web/src/ui/*` | **Never touch:** `web/src/types/generated/*`
- **Steps:** 1. Tokens. 2. Routes. 3. Client with error mapping. 4. State components. 5. Code gate.
- **Tests first:** state components render · client maps 401/404/413 to typed errors.
- **Done when:** `npm --prefix web run test -- --run; npm --prefix web run typecheck; npm --prefix web run lint` → exit 0.

### T-5.7 · Upload and SOP editor                                                             [ ]
- **Track:** FE | **Serves:** FR-02, FR-11 | **Size:** M | **Tier:** standard | **Depends:** T-5.3, T-5.6 | **Blocks:** T-5.13
- **Context pack (read only these):** `contracts/sop.schema.json` · `web/src/api/*`
- **Goal:** drag-and-drop video + SOP; compile preview; editable step list (reorder, edit text, tool chips, toggle critical, ordering mode); validation; start run.
- **Touch:** `web/src/features/upload/*` | **Never touch:** `web/src/api/*`
- **Steps:** 1. Dropzone. 2. Step editor. 3. Validation. 4. Start run.
- **Tests first:** invalid graph blocked · reorder preserved · labels and focus order correct.
- **Done when:** `npm --prefix web run test -- --run web/src/features/upload` → pass.

### T-5.8 · Run progress view                                                                  [ ]
- **Track:** FE | **Serves:** FR-15 | **Size:** S | **Tier:** standard | **Depends:** T-5.4, T-5.6 | **Blocks:** T-5.13
- **Context pack (read only these):** SSE event shape in `openapi.json`
- **Goal:** 12-stage stepper from SSE with live $ and elapsed, partial results, per-stage failure banner, "continue with partial".
- **Touch:** `web/src/features/progress/*` | **Never touch:** `web/src/api/*`
- **Steps:** 1. EventSource hook. 2. Stepper. 3. Failure banner. 4. Tests with a mocked stream.
- **Tests first:** ordered events · failed stage · reconnect replay.
- **Done when:** `npm --prefix web run test -- --run web/src/features/progress` → pass.

### T-5.9 · Review core: player and dual-lane timeline                                         [ ]
- **Track:** FE | **Serves:** FR-11 | **Size:** M | **Tier:** deep | **Depends:** T-5.6 | **Blocks:** T-5.10, T-5.11, T-5.13
- **Context pack (read only these):** `contracts/report.schema.json` · fixture reports
- **Goal:** custom video controls (frame-step, speed), two lanes (SOP expected vs observed from alignment), deviation markers coloured by type, scrub↔lane sync, keyboard (J/K/L, ←/→ frame, N/P next/previous deviation).
- **Touch:** `web/src/features/review/player/*`, `web/src/features/review/timeline/*` | **Never touch:** `web/src/features/review/overlay/*`
- **Steps:** 1. Player. 2. Time↔pixel mapping. 3. Lanes + markers. 4. Keyboard. 5. Snapshot test with fixtures.
- **Tests first:** mapping unit tests · marker click seeks · keyboard actions · 3 deviations at expected x positions.
- **Done when:** `npm --prefix web run test -- --run web/src/features/review/timeline` → pass.

### T-5.10 · SAM overlay layer and track inspector                                              [ ]
- **Track:** FE | **Serves:** FR-11 | **Size:** M | **Tier:** deep | **Depends:** T-2.4, T-5.9 | **Blocks:** T-5.13
- **Context pack (read only these):** `contracts/tracks.schema.json` · `web/src/features/review/player/*`
- **Goal:** canvas synced via `requestVideoFrameCallback`; draws simplified polygons; toggles per concept/track; hover `#id concept`; inspector listing a track's holds over time.
- **Touch:** `web/src/features/review/overlay/*` | **Never touch:** `web/src/features/review/player/*`
- **Steps:** 1. Frame sync. 2. Draw. 3. Toggles/hover. 4. Inspector. 5. Perf test.
- **Tests first:** correct frame selection at time t · toggle hides track · empty tracks no-op.
- **Done when:** `npm --prefix web run test:perf -- --run` → p95 draw ≤ 8 ms with 12 tracks at 720p; unit tests pass.

### T-5.11 · Deviation panel                                                                    [ ]
- **Track:** FE | **Serves:** FR-11, FR-10 | **Size:** M | **Tier:** standard | **Depends:** T-5.3, T-5.5, T-5.9 | **Blocks:** T-5.13
- **Context pack (read only these):** `contracts/report.schema.json` · fixture reports
- **Goal:** cards sorted by time/severity; type badge; confidence; `needs_review` styling; explanation; evidence carousel (frames + clip); illustration with a permanent "AI illustration, not evidence" badge; accept/dismiss/note (PATCH); filter chips; export button.
- **Touch:** `web/src/features/review/panel/*` | **Never touch:** `web/src/features/review/timeline/*`
- **Steps:** 1. Card. 2. Carousel. 3. Illustration block. 4. Decisions. 5. State variants.
- **Tests first:** states: flagged · needs_review · procedure_not_recognized · evidence_unavailable · illustration_unavailable.
- **Done when:** `npm --prefix web run test -- --run web/src/features/review/panel` → pass.

### T-5.12 · Demo gallery                                                                        [ ]
- **Track:** FE | **Serves:** FR-14 | **Size:** S | **Tier:** light | **Depends:** T-1.2, T-5.6 | **Blocks:** T-5.13, T-7.1
- **Context pack (read only these):** fixture reports
- **Goal:** `/demo` lists frozen cases across the three domains with one-click load and an "offline" badge.
- **Touch:** `web/src/features/demo/*` | **Never touch:** `web/src/api/*`
- **Steps:** 1. List. 2. Load. 3. Badge. 4. Tests with fixtures.
- **Tests first:** list renders 3 cases · load opens review · empty list state.
- **Done when:** `npm --prefix web run test -- --run web/src/features/demo` → pass.

### T-5.13 · End-to-end journey tests                                                            [ ]
- **Track:** QA | **Serves:** NFR-08 | **Size:** M | **Tier:** standard | **Depends:** T-5.2, T-5.5, T-5.7, T-5.8, T-5.9, T-5.10, T-5.11, T-5.12 | **Blocks:** G5
- **Context pack (read only these):** §1A demo arc · `web/e2e/*`
- **Goal:** Playwright journey in `replay` mode: access code → upload → edit SOP → progress → review → open deviation → evidence + diagram visible → accept → export HTML; plus demo gallery.
- **Touch:** `web/e2e/*` | **Never touch:** `web/src/*`
- **Steps:** 1. Fixtures/replay server. 2. Journey. 3. Gallery path. 4. Deterministic data, no sleeps.
- **Tests first:** the journey itself is the test.
- **Done when:** `npm --prefix web exec playwright test -- --repeat-each 3` → 3 consecutive passes.

#### Gate G5: API, UI, report   [ ]
Standard checks S1–S9 (with e2e) plus the G5 extras in the Phase Profile. **Feature freeze (FF) at end of D7.** Evidence in PROGRESS.md.

---
### Phase 6: Evaluation and Hardening (Day 8) — NO NEW FEATURES
**Goal:** honest numbers, proof each model earns its place, and a system that survives bad inputs, flaky APIs and judges. **Exit:** Gate G6 · tag `rc1` at the start of D8

**Phase Profile**
- Purpose: audit → fix → verify; produce the evidence for the submission.
- Entry: G5 passed; feature freeze in force; `rc1` tagged.
- Workflow: run the ablation on DEV, fix bugs found, freeze config, run HELD-OUT exactly once on the release candidate, write the failure analysis.
- Test focus: ablation with bootstrap CIs, robustness suite, failure injection, a11y, cost reconciliation.
- Security focus: ASVS-lite checklist, upload fuzz, traversal, CORS/headers, dependency audit blocking from this gate, retention purge, privacy statement (no identification or scoring of individuals).
- Default tier: deep.
- Gate extras: held-out numbers recorded with `lock: OK` · ablation table present · zero high/critical audit findings · failure-injection suite green · perf and cost targets met or amended by ADR · limitations written. A second held-out run requires a logged reason.
- Exit evidence: `docs/results/{ablation_dev,heldout,failures}.md`, audit outputs.

### T-6.1 · Dev full run and ablations                                                          [ ]
- **Track:** ML | **Serves:** FR-13, NFR-07 | **Size:** M | **Tier:** standard | **Depends:** T-3.10, T-3.12, T-4.6 | **Blocks:** T-6.2
- **Context pack (read only these):** NFR-07 · `src/pw/bench/runner.py`
- **Goal:** `pw-bench ablate --split dev` over {full, raw_video(A), no_sam(B), no_aligner (greedy argmax), no_verifier, no_identity_vote}; per-type P/R/F1, false flags per compliant clip, MAE, $/min, latency; bootstrap 95% CIs (1000 resamples over clips).
- **Touch:** `src/pw/bench/ablate.py`, `docs/results/ablation_dev.md` | **Never touch:** `bench/heldout/*`
- **Steps:** 1. Config switches. 2. Run in replay then live where missing. 3. Bootstrap. 4. Table + analysis.
- **Tests first:** bootstrap on toy data matches a hand calculation · config switch actually disables the component.
- **Done when:** `uv run pw-bench ablate --split dev` → table with 6 rows; Full ≥ baseline B F1 + 0.10, or the `#analysis` section explains why not (honest reporting).

### T-6.2 · Held-out single-shot run                                                            [ ]
- **Track:** ML | **Serves:** NFR-07 | **Size:** S | **Tier:** deep | **Depends:** T-6.1, T-6.3, T-6.4, T-6.6, T-1.8 | **Blocks:** G6
- **Context pack (read only these):** `config/thresholds.json` · `bench/HELDOUT.lock`
- **Goal:** run the frozen pipeline once on the 9 held-out clips and record the headline numbers; no tuning afterwards.
- **Touch:** `docs/results/heldout.md` | **Never touch:** `config/thresholds.json`, `bench/heldout/*`
- **Steps:** 1. `verify-lock` OK. 2. Record thresholds hash and commit. 3. Run live. 4. Write results with CIs and cost.
- **Tests first:** n/a (measurement). Pre-check: lock verifies.
- **Done when:** `uv run pw-bench run --split heldout --config config/thresholds.json --mode live` → summary (F1, false flags per compliant clip, MAE, $/min); `Select-String docs/results/heldout.md -Pattern "lock: OK"` → 1 match.

### T-6.3 · Robustness suite                                                                      [ ]
- **Track:** QA | **Serves:** NFR-03 | **Size:** M | **Tier:** standard | **Depends:** G5 | **Blocks:** T-6.2
- **Context pack (read only these):** `tests/robustness/*` · fixtures
- **Goal:** cases: variable-frame-rate phone video, camera shake, low light, heavy occlusion, 3-minute clip, no-hands clip, mismatched SOP (expect `procedure_not_recognized`), repeated step; each asserts graceful behaviour and records expected degradation.
- **Touch:** `tests/robustness/*` | **Never touch:** `src/*`
- **Steps:** 1. Build fixtures (ffmpeg transforms of dev clips). 2. Assertions. 3. Replay where possible. 4. File bugs as discoveries.
- **Tests first:** the suite is the test.
- **Done when:** `uv run pytest tests/robustness -q` → pass.

### T-6.4 · Failure-injection suite and kill switches                                              [ ]
- **Track:** QA | **Serves:** NFR-03 | **Size:** M | **Tier:** deep | **Depends:** G5 | **Blocks:** T-6.2
- **Context pack (read only these):** `src/pw/clients/*` (read only) · NFR-03
- **Goal:** inject timeouts, 5xx, 429, malformed JSON and partial SAM output; assert retries, backoff, degraded-but-valid reports; verify `PW_DISABLE_ILLUSTRATIONS`, `PW_DISABLE_VERIFIER` and spend-cap abort.
- **Touch:** `tests/robustness/failure/*` | **Never touch:** `src/*`
- **Steps:** 1. Fault-injecting fake transport. 2. Scenarios. 3. Switch tests. 4. Spend-cap test under concurrency.
- **Tests first:** the suite is the test.
- **Done when:** `uv run pytest tests/robustness/failure -q` → pass.

### T-6.5 · Security audit (ASVS-lite) and fixes                                                   [ ]
- **Track:** SEC | **Serves:** NFR-05 | **Size:** M | **Tier:** deep | **Depends:** G5 | **Blocks:** G6
- **Context pack (read only these):** NFR-05 · `src/pw/security/*` · `openapi.json`
- **Goal:** upload fuzz (zip bomb, giant dimensions, wrong extension), traversal, CORS and security headers, CSP, secret scan, dependency audits (now blocking), key redaction in logs, retention purge test, written privacy statement (no identification or scoring of individuals).
- **Touch:** `docs/security/audit.md`, `tests/security/audit/*` | **Never touch:** `src/pw/api/*`
- **Steps:** 1. Checklist. 2. Fuzz tests. 3. Findings by severity; fixes go through discovery tasks owned by the relevant track. 4. Re-run.
- **Tests first:** each finding gets a failing test before its fix.
- **Done when:** `uv run pip-audit; npm --prefix web audit --audit-level=high; uv run pre-commit run gitleaks --all-files; uv run pytest tests/security -q` → no high/critical, gitleaks clean, tests pass; `Select-String docs/security/audit.md -Pattern "High: 0|Critical: 0"` → 2 matches.

### T-6.6 · Performance and cost reconciliation                                                    [ ]
- **Track:** BE | **Serves:** NFR-01, NFR-02 | **Size:** M | **Tier:** standard | **Depends:** G5 | **Blocks:** T-6.2
- **Context pack (read only these):** NFR-01, NFR-02 · ADR-001, ADR-002 (rate limits)
- **Goal:** bounded concurrency (SAM chunks ≤ 4, Wonder ≤ 4 or per ADR), warm cache paths, profile hot spots, reconcile ledger vs provider usage within 5%.
- **Touch:** `src/pw/pipeline/concurrency.py`, `tests/pipeline/test_concurrency.py` | **Never touch:** `src/pw/align/*`
- **Steps:** 1. Semaphores. 2. Profile. 3. Fix top 2 hot spots. 4. Reconcile.
- **Tests first:** concurrency never exceeds limit · results identical to sequential run.
- **Done when:** `uv run pw run --mode live --video bench/dev/A2.mp4 --sop bench/sops/A.md --profile` → wall time ≤ NFR-01 target; ledger total within 5% of provider dashboard (note in PROGRESS.md).

### T-6.7 · State, accessibility and projector polish                                               [ ]
- **Track:** FE | **Serves:** NFR-09 | **Size:** S | **Tier:** light | **Depends:** G5 | **Blocks:** G6
- **Context pack (read only these):** §1B UI states
- **Goal:** no new features: verify every UI state, contrast ≥ 4.5:1, keyboard traversal, 1080p projector layout, reduced motion.
- **Touch:** `web/src/features/*/styles/*`, `web/src/ui/*` | **Never touch:** `web/src/api/*`
- **Steps:** 1. axe checks. 2. Fix contrast/focus. 3. Projector pass. 4. Reduced motion.
- **Tests first:** axe on the 4 routes.
- **Done when:** `npm --prefix web run test:a11y` → 0 serious/critical violations on 4 routes.

### T-6.8 · Failure analysis and limitations                                                         [ ]
- **Track:** ML | **Serves:** FR-13 | **Size:** S | **Tier:** standard | **Depends:** T-6.2 | **Blocks:** G6
- **Context pack (read only these):** `docs/results/*.md`
- **Goal:** top-10 failures (dev + held-out) with evidence frames, root cause, and what would fix them; a plain-language "Limitations" section for README and video.
- **Touch:** `docs/results/failures.md` | **Never touch:** `src/*`
- **Steps:** 1. Rank errors. 2. Root cause each. 3. Fix-or-document. 4. Limitations text.
- **Tests first:** n/a (analysis).
- **Done when:** `(Select-String docs/results/failures.md -Pattern '^### F-\d+').Count` → 10.

#### Gate G6: Evaluation and hardening   [ ]
Standard checks S1–S9 (audits blocking) plus the G6 extras in the Phase Profile. Evidence in PROGRESS.md.

---
### Phase 7: Release and Submission (Days 9–10; finals kit Nov 5–8)
**Goal:** a deployed, rehearsed, submitted project with a demo that cannot fail. **Exit:** Gate G7

**Phase Profile**
- Purpose: ship and present.
- Entry: G6 passed; thresholds and code frozen except fixes with a logged reason.
- Workflow: demo pack → deploy → docs → video → submission draft → clean-room rehearsal → submit at 12:00 ET with a 9-hour buffer.
- Test focus: smoke on the public URL, offline demo mode, clean-room quickstart ×3.
- Security focus: production secrets set out-of-band; access code distributed only in the submission; least privilege on the host.
- Default tier: light / standard.
- Gate extras: submission receipt saved · tag `v1.0.0` · rollback rehearsed (redeploy previous image) · **human approves the public deploy** · finals kit ready.
- Exit evidence: receipt screenshot, public smoke output, clean-room log.

### T-7.1 · Demo pack (frozen offline cases)                                                         [ ]
- **Track:** BE | **Serves:** FR-14, NFR-08 | **Size:** S | **Tier:** standard | **Depends:** T-5.12, T-6.2 | **Blocks:** T-7.4
- **Context pack (read only these):** §1A demo arc · `src/pw/pipeline/*`
- **Goal:** `pw demo-build` runs 3 cases live once (one per procedure; include one held-out with a planted mistake and one compliant clip), freezes artifacts in `demo/cases/<id>/` (report, evidence, illustrations, polygons, 720p source), with checksums; `PW_MODE=demo` serves them with no network.
- **Touch:** `src/pw/demo/*`, `demo/cases/*`, `tests/demo/*` | **Never touch:** `src/pw/pipeline/*`
- **Steps:** 1. Build command. 2. Checksums. 3. Demo mode server path. 4. Verify command.
- **Tests first:** checksum mismatch detected · demo mode makes zero outbound calls.
- **Done when:** `uv run pw demo-verify` → `3/3 cases OK`; with `PW_MODE=demo`, `curl http://localhost:8000/demo/cases` → 3 cases.

### T-7.2 · Container and deploy                                                                      [ ]
- **Track:** OPS | **Serves:** NFR-05, SUB-01 | **Size:** M | **Tier:** standard | **Depends:** T-6.5, T-7.1 | **Blocks:** T-7.5, T-7.6
- **Context pack (read only these):** ADR-000 (rules) · AGENTS.md §15
- **Goal:** single non-root image (python slim + ffmpeg + built web) with a health check; deploy to the chosen host (decide Modal / Render / Fly in `ADR-004-deploy.md`); secrets via the host store; smoke on the public URL.
- **Touch:** `Dockerfile`, `deploy/*`, `docs/adr/ADR-004-deploy.md` | **Never touch:** `src/*`
- **Steps:** 1. Dockerfile. 2. Host config. 3. Secrets (`META_API_KEY`, `PW_ACCESS_CODE`). 4. Deploy. 5. Smoke.
- **Tests first:** container health check passes locally.
- **Done when:** `curl https://<host>/healthz` → `{"status":"ok"}`; `uv run pw smoke --url https://<host> --code $env:PW_ACCESS_CODE` → demo case loads and one live 20 s run completes.
- **Rollback:** redeploy the previous image tag; documented in `deploy/ROLLBACK.md`; rehearsed once.

### T-7.3 · README and docs                                                                           [ ]
- **Track:** DOC | **Serves:** SUB-01 | **Size:** M | **Tier:** light | **Depends:** T-6.2, T-6.8 | **Blocks:** T-7.5
- **Context pack (read only these):** `docs/results/*.md` · §1B · ADR-000 (licence rules)
- **Goal:** what/why, 60-second quickstart (Windows/macOS/Linux), architecture figure, how each Meta model is used with its measured contribution (ablation), held-out results, cost/latency, limitations, security/privacy, SAM License acknowledgement, LICENSE per rules, contributors.
- **Touch:** `README.md`, `docs/architecture.md`, `scripts/readme_check.py` | **Never touch:** `src/*`
- **Steps:** 1. Draft. 2. Figure (mermaid). 3. Results table from `docs/results`. 4. Command checker. 5. Trim.
- **Tests first:** the checker parses fenced commands and dry-runs them.
- **Done when:** `uv run python scripts/readme_check.py` → "N commands OK".

### T-7.4 · Demo video                                                                                   [ ]
- **Track:** DOC | **Serves:** SUB-01, NFR-08 | **Size:** M | **Tier:** standard | **Depends:** T-7.1 | **Blocks:** T-7.5
- **Context pack (read only these):** §1A demo arc · ADR-000 (video limit)
- **Goal:** ≤ limit (default 3 min) video recorded from the demo pack with narration and captions, plus a 60 s teaser.
- **Touch:** `docs/demo/*` | **Never touch:** `src/*`
- **Steps:** 1. Script. 2. Record. 3. Edit/captions. 4. Teaser. 5. Upload.
- **Tests first:** n/a (media).
- **Done when:** `ffprobe -v error -show_entries format=duration -of csv=p=0 docs/demo/demo.mp4` → ≤ 180.0 (or the limit in ADR-000).

### T-7.5 · Submission package and dry run                                                              [ ]
- **Track:** DOC | **Serves:** SUB-01 | **Size:** S | **Tier:** light | **Depends:** T-7.2, T-7.3, T-7.4 | **Blocks:** T-7.7
- **Context pack (read only these):** ADR-000 · README
- **Goal:** title, one-liner, problem, solution, theme fit (Push the Frontier), track statement, how each model is used with evidence, results, links, team; draft entered in the portal if allowed (Nov 3).
- **Touch:** `docs/submission/submission.md` | **Never touch:** `src/*`
- **Steps:** 1. Write. 2. Screenshots. 3. Links check. 4. Dry-run entry.
- **Tests first:** n/a.
- **Done when:** `(Select-String docs/submission/submission.md -Pattern 'Theme:|Track:|Models:|Repo:|Demo:|Video:|Results:').Count` → 7.

### T-7.6 · Clean-room rehearsal                                                                          [ ]
- **Track:** QA | **Serves:** NFR-06, NFR-08 | **Size:** S | **Tier:** standard | **Depends:** T-7.2 | **Blocks:** T-7.7
- **Context pack (read only these):** README quickstart
- **Goal:** on a machine that has never seen the repo: clone → quickstart ≤ 10 min → demo mode offline → one live run; three consecutive passes.
- **Touch:** `docs/results/cleanroom.md` | **Never touch:** `src/*`
- **Steps:** 1. Fresh machine/VM. 2. Follow README literally. 3. Time it. 4. Fix doc gaps via DOC.
- **Tests first:** n/a.
- **Done when:** `(Select-String docs/results/cleanroom.md -Pattern 'PASS').Count` → 3.

### T-7.7 · Submit                                                                                         [ ]
- **Track:** DOC | **Serves:** SUB-01 | **Size:** S | **Tier:** light | **Depends:** T-7.5, T-7.6 | **Blocks:** G7
- **Context pack (read only these):** ADR-000 · submission.md
- **Goal:** submit by **Nov 4, 12:00 ET** (9 h buffer before the 21:00 ET deadline); tag `v1.0.0`; save the receipt.
- **Touch:** `docs/submission/receipt.png` | **Never touch:** `src/*`
- **Steps:** 1. Final link check. 2. Tag. 3. Submit. 4. Screenshot receipt.
- **Tests first:** n/a.
- **Done when:** `git tag -l v1.0.0` → `v1.0.0`; `Test-Path docs/submission/receipt.png` → `True`.

### T-7.8 · Finals kit (Nov 5–8)                                                                          [ ]
- **Track:** DOC | **Serves:** NFR-08, SUB-01 | **Size:** M | **Tier:** standard | **Depends:** T-7.7 | **Blocks:** G7
- **Context pack (read only these):** §1A · `docs/results/*.md`
- **Goal:** 3-minute live script with fallbacks (A live, B demo mode, C video), ≥ 20 hard Q&A (cost, accuracy, failures, privacy, why three models, production path, novelty, small-N honesty), one-page module explainer per owner, hotspot rehearsal.
- **Touch:** `docs/finals/*` | **Never touch:** `src/*`
- **Steps:** 1. Script. 2. Q&A. 3. Explainers (each owner can defend their module). 4. Two timed dry runs.
- **Tests first:** n/a.
- **Done when:** `(Get-ChildItem docs/finals).Count` ≥ 7; `(Select-String docs/finals/qa.md -Pattern '^### Q').Count` ≥ 20.

#### Gate G7: Release   [ ]
Standard checks S1–S9 plus the G7 extras in the Phase Profile. **Human approves production.** Evidence in PROGRESS.md.

---

## 5. Parking Lot (never build without human approval; ordered by value if approved after G5)
- **P-1** External-validity run on a public procedural-mistake dataset subset (verify availability and licence first).
- **P-2** Privacy mode: SAM prompt `face` → blur in evidence frames (no identification).
- **P-3** Five-person mini study: time-to-understand a flagged step with vs without the Muse Image diagram.
- **P-4** Near-real-time rolling-window mode.
- **P-5** Multilingual SOPs.
- **P-6** SOP-quality feedback: many operators deviating at the same step → suggest clarifying the SOP.
- **P-7** Multi-camera fusion.
- **P-8** Muse Spark for cheap bulk calls (needs an ADR on cost/rate limits).

## 6. Risk Register
| # | Risk | Mitigation | Owning task |
|---|---|---|---|
| R1 | SAM API limits (duration, objects) or ID drift on long clips | Chunk + stitch; ≤ 3 min clips; self-hosted fallback decided on D1 | T-0.4, T-2.3 |
| R2 | Mask encoding unknown or hard to decode in Python | Spike answers it; Node parser or box fallback | T-0.4, T-2.4 |
| R3 | Occlusion breaks tool identity | Per-track voting over best crops; `unknown` state; needs_review | T-2.7 |
| R4 | Wonder preview instability, rate limits, JSON drift | Strict schemas, repair loop, retries, replay cache; Spark only via ADR | T-0.5, T-0.7 |
| R5 | False alarms destroy trust | Verifier, margin-based abstention, thresholds tuned on dev with an FP constraint | T-3.7, T-3.10 |
| R6 | Muse Image diagram wrong or off-spec | QA loop, fallback to none, watermark, never in evidence | T-4.4, T-4.5 |
| R7 | Overfitting to our own filming | Held-out split by different operator/angle, locked before tuning, single run | T-1.5, T-1.8, T-6.2 |
| R8 | Rules forbid something we planned (IP, open source, pre-existing work) | Read rules first; no product code before | T-0.1 |
| R9 | Demo-day failure (network, API outage) | Offline demo mode, backup video, clean-room rehearsal | T-7.1, T-7.4, T-7.6 |
| R10 | API spend overrun or abuse of the public demo | Per-run cap, rate limit, access code, cache | T-3.9, T-5.1 |
| R11 | Schedule slip | Feature freeze end D7; cut list in §1A; contracts frozen at C1 | all |
| R12 | Ownership gaps (nobody can explain a module in Q&A) | Per-owner explainers, owners defend their code in dry runs | T-7.8 |
| R13 | Filming takes longer than expected | Shot list on D1, film D1–D3 in parallel with contracts; cut P-C if needed | T-1.3, T-1.4 |

## 7. Plan Change Log
| Date | Change | Reason |
|---|---|---|
| 2026-10-25 | v1.0 initial plan | Created from the project brief, hackathon page and the master-plan method |
| 2026-10-25 | Docs 01–05 added; citation map and authority order added to the header; T-1.2 extended with review + thresholds contracts; A-3 updated | User asked for the full spec-driven 6-doc set |
| 2026-10-27 | T-0.1 complete → `docs/adr/ADR-000-rules.md`. A-10 resolved. No task added/removed/re-scoped: rules conflict with nothing in the plan; only administrative items (Representative, waiver, W-9/W-8BEN, $150 credit budget) recorded. Portal field list stays open (login-gated) for T-7.2. | Official Rules + waiver read (sources in ADR-000) |

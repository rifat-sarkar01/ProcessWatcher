# 01_PRD.md: Process Watcher · Product Requirements Document
> Layer 01 · Scope and User Journey · v1.0 · 2026-10-25 · Source of truth for requirement IDs (FR / NFR / SUB). `06_Plan.md` §3 mirrors these IDs.
> Event: Meta Global AI Developer Hackathon (Cerebral Valley) · kickoff Oct 26 · submission due **Nov 4, 21:00 ET (Nov 5, 02:00 UTC)** · theme **Push the Frontier** (manufacturing and physical systems).

## 1. Problem and vision
Written SOPs describe what *should* happen on a line, in a lab, or at a repair bench. What *actually* happens is rarely checked: a skipped step, a swapped order or a wrong tool is found only after a defect, an audit finding or an injury.

**Process Watcher** watches a recorded physical procedure and checks it against the written SOP. It flags **missed**, **out-of-order** and **wrong-tool** steps, each with a timestamp, a short explanation and **visual evidence made of real, SAM-annotated video frames**. For every flagged step it also shows a clearly labeled illustration of what the correct step looks like.

**One-liner:** *"Not what the paperwork says: what actually happened."*

### Three Meta models, three distinct jobs
| Model | Job in the product | Never used for |
|---|---|---|
| **SAM 3.1** | Open-vocabulary detection, masks and tracking of hands, tools and parts with persistent object IDs → structured "what was touched, moved, and when" timeline | Judging compliance |
| **Muse Wonder** | Compiles the SOP into a step graph; supplies step likelihoods per video segment; classifies each tool track once; verifies findings; writes grounded explanations | Making the final compliance decision (a deterministic aligner decides) |
| **Muse Image** | "What correct looks like" schematic for each flagged step | Evidence (illustrations are watermarked and can never enter an evidence list) |

## 2. Users and jobs to be done
| Persona | Job to be done | Success looks like |
|---|---|---|
| **Quality / process engineer** (primary) | Verify a recorded run of a procedure against its SOP without watching hours of video | Reviews only flagged moments; trusts the evidence; exports an audit report |
| **Line supervisor / lab lead** | See where operators deviate from the SOP and why it matters | Clear deviation list with severity (critical steps first) |
| **Trainer** | Show a trainee the difference between what they did and the correct step | Evidence frame next to the "what correct looks like" diagram |
| **Hackathon judge** (demo persona) | Understand the product and judge whether it works in under 3 minutes | Live or frozen run; held-out numbers; no failed demo |

The product evaluates **procedures**, never people: it does not identify, rank or score individual workers (OOS-6).

## 3. MVP goals
| ID | Goal | Measure |
|---|---|---|
| G1 | Given a video + SOP, produce a reviewed deviation report end to end | `pw run` → valid `report.json` on 15/15 dev clips |
| G2 | Findings are right | Held-out overall F1 ≥ 0.70; ≥ 0.60 per type (NFR-07) |
| G3 | Findings are trustworthy | ≤ 0.3 false flags per compliant clip; low-margin findings become `needs_review` |
| G4 | Evidence is real and verifiable | `pw verify-evidence` → VERIFIED n/n |
| G5 | The demo cannot fail | Offline demo mode, backup video, clean-room quickstart ≤ 10 min (NFR-08) |

## 4. Scope Shield
### In scope (MVP)
Upload of one video + one SOP (md/txt/pdf) · SOP compile with human edit · SAM tracking with persistent IDs · interaction timeline · tool identity · step alignment · three deviation types · verification and grounded explanation · SAM-annotated evidence frames/clips (hashed) · Muse Image diagrams (watermarked, QA-checked) · review UI · HTML/PDF report · benchmark with held-out split and ablations · offline demo mode · deployed demo behind an access code.

### Out of scope (Scope Shield: no task may implement these)
| ID | Excluded |
|---|---|
| OOS-1 | Live or streaming camera inference |
| OOS-2 | Training or fine-tuning any model |
| OOS-3 | User accounts, RBAC, multi-tenant, SSO |
| OOS-4 | MES / ERP / QMS integrations |
| OOS-5 | Multi-camera fusion |
| OOS-6 | Identifying, scoring or ranking individual workers; face recognition |
| OOS-7 | Safety-certification or regulatory-compliance claims |
| OOS-8 | Synthetic images presented as evidence |
| OOS-9 | Mobile app |
| OOS-10 | Automatic SOP authoring |

Ideas that survive triage live in the Parking Lot (`06_Plan.md` §5) and are never built without human approval.

## 5. Functional requirements
Each requirement has acceptance criteria (AC) in Given / When / Then form.

| ID | Requirement | Acceptance criteria |
|---|---|---|
| **FR-01** | Ingest a procedure video and an SOP (md/txt/pdf) with caps and validation | **Given** a ≤180 s, ≤500 MB mp4/mov/webm/mkv and a valid SOP, **when** submitted, **then** a run is created and normalised to constant frame rate ≤720p; **given** a wrong magic number, oversize or over-long file, **then** a typed 4xx error is returned and nothing is stored |
| **FR-02** | Compile the SOP into a validated step graph (steps, tools, parts, ordering, critical flags, SAM vocabulary); the user can edit it before the run | **Given** an SOP, **when** compiled, **then** every tool/part string appears in the SOP text, JSON validates against `sop.schema.json`, and the vocabulary includes `hand`; **given** an edit in the UI, **then** the edited graph overrides the compiled one |
| **FR-03** | SAM 3.1 tracks hands, tools and parts with persistent IDs across chunks | **Given** a clip longer than one SAM chunk, **when** perceived, **then** tracks are stitched into global IDs with fragmentation ratio ≤ 1.5 on dev |
| **FR-04** | Deterministic interaction timeline (hold, contact, move, enter/exit) and candidate segments | **Given** tracks, **when** events are extracted, **then** each event cites track IDs and times and `timeline.json` validates; same input → byte-identical output |
| **FR-05** | Per-track tool/part identity vs the SOP vocabulary with confidence | **Given** a tool track, **when** classified, **then** at most one model call is made per track and the label is in the vocabulary or `other`/`unknown` |
| **FR-06** | Step alignment by global constrained decoding; mismatch guard | **Given** segment likelihoods, **when** aligned, **then** steps map to intervals honouring ordering constraints (soft, penalised); **given** an unrelated video, **then** the report status is `procedure_not_recognized` with no deviations |
| **FR-07** | Flag missed, out-of-order and wrong-tool steps | **Given** an aligned run, **when** deviations are derived, **then** each has type, step id, severity (critical → high), time range and ≥ 1 track reference; a compliant clip yields none |
| **FR-08** | Verification pass, calibrated status, grounded short explanation | **Given** a candidate deviation, **when** verified, **then** disagreement yields `needs_review`; the explanation is ≤ 2 sentences, ≤ 40 words, and every timestamp/tool in it exists in the data |
| **FR-09** | Evidence = SAM-annotated real frames + clip, hashed and re-derivable | **Given** a deviation, **then** 2–4 frames with masks, track IDs and timestamps are attached; `pw verify-evidence` re-renders from the source and compares perceptual hashes |
| **FR-10** | Muse Image "what correct looks like" diagram per flagged step, labeled, QA-checked | **Given** a flagged step, **then** one diagram (deduped by step) carries the watermark "AI ILLUSTRATION · NOT EVIDENCE"; QA fails 3× → explicit fallback "no illustration" |
| **FR-11** | Review UI: video, dual-lane timeline, SAM overlay, deviation panel, decisions | **Given** a finished run, **then** a user can scrub, jump between deviations by keyboard, toggle masks, open evidence + diagram, accept/dismiss with a note |
| **FR-12** | Self-contained HTML/PDF audit report | **Given** a finished run, **then** one HTML file (no external references) lists every deviation with evidence, hashes, model versions and thresholds |
| **FR-13** | PW-Bench: ground truth, metrics, baselines, ablation, held-out protocol | **Given** the dev set, **then** `pw-bench run/ablate` produce P/R/F1 per type, false flags per compliant clip, MAE, $/min; the held-out set is locked before tuning and run once |
| **FR-14** | Offline demo mode with frozen cases | **Given** `PW_MODE=demo`, **then** three cases load in ≤ 3 s with zero outbound network calls |
| **FR-15** | Live progress (SSE) with cost and elapsed counters | **Given** a running job, **then** stage start/finish, % and running $ stream; late joiners get a replay |

## 6. Non-functional requirements
| ID | Requirement | Target |
|---|---|---|
| **NFR-01** | Latency | 2-min clip → report ≤ 4 min p50 (live); demo case ≤ 3 s |
| **NFR-02** | Cost | ≤ $1.00 per video-minute; hard per-run cap `PW_SPEND_CAP_USD` (default 3); full ledger |
| **NFR-03** | Reliability | Timeout + ≤ 3 retries + schema validation on every model call; partial-failure → degraded valid report; stages resumable |
| **NFR-04** | Traceability | Every deviation links step id + track ids + timestamps + evidence; report validates against contract |
| **NFR-05** | Security and privacy | Keys never in repo/logs/client; upload validation + caps; access code; rate limit; 24 h retention; no identification or scoring of individuals |
| **NFR-06** | Reproducibility | Pinned deps; deterministic `replay` mode; run manifest; re-derivable evidence; CI green from a clean clone |
| **NFR-07** | Quality (held-out; targets, not promises) | Overall F1 ≥ 0.70 (each type ≥ 0.60) · ≤ 0.3 false flags per compliant clip · timestamp MAE ≤ 1.5 s · Full ≥ baseline B + 0.10 F1 on dev |
| **NFR-08** | Demo robustness | Offline demo mode; backup video; clean-room quickstart ≤ 10 min |
| **NFR-09** | Usability | Every UI state handled; keyboard-operable timeline; readable on a 1080p projector; WCAG AA contrast |

Targets are re-baselined from the T-0.4 / T-0.5 spike ADRs and any change is logged in `06_Plan.md` §7.

## 7. Submission requirement
| ID | Requirement |
|---|---|
| **SUB-01** | Deliver everything the Official Rules require (repo/licence, demo video, write-up, demo link, track and theme statement) by **Nov 4, 12:00 ET (internal)**; official deadline Nov 4, 21:00 ET. Rules are published Oct 26 and read first (T-0.1). |

Judging (from the event page): Indie track = creativity, technical ambition, and whether it works; Startup track = technical execution and holding up in production. Assumed track: Indie (A-1).

## 8. Evaluation protocol (summary; details in 04_TRD §10)
- **PW-Bench:** 3 procedures × (15 dev + 9 held-out) clips, injected deviations, ground truth labeled by the team.
- **Match rule:** same type and step id, time overlap within ±2.0 s. Metrics: P/R/F1 per type and overall, false flags per compliant clip, timestamp MAE, $/min, latency.
- **Ablation:** Full vs raw-video Wonder (A) vs keyframes-only Wonder (B) vs no-aligner vs no-verifier vs no-identity-voting, with bootstrap 95% CIs.
- **Held-out:** locked (sha256) before any tuning, run once on the release candidate.

## 9. Risks and open questions
Top risks are in `06_Plan.md` §6 (SAM limits and mask encoding, Wonder preview stability, false alarms, rules compliance, demo-day failure). Open questions Q-1..Q-5 are in `06_Plan.md` §2 (track choice, API credits, procedures to film, OS mix, Official Rules).

## 10. Glossary
| Term | Meaning |
|---|---|
| SOP | Written standard operating procedure |
| Step graph | Compiled SOP: steps, tools, parts, ordering constraints, critical flags |
| Track | One object followed through the video with a persistent ID (`trk_###`) |
| Segment | A candidate action interval derived from interaction events |
| Deviation | A missed, out-of-order or wrong-tool finding |
| Evidence | Real video frames/clips with SAM masks, hashed and re-derivable |
| Illustration | Muse Image schematic of the correct step; never evidence |
| `needs_review` | Low-margin or verifier-disagreeing finding shown separately instead of as a hard flag |

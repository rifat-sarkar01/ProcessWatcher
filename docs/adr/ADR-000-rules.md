# ADR-000: Official Rules constraints for Process Watcher

- **Status:** Accepted
- **Date:** 2026-10-27
- **Task:** T-0.1 (DOC, serves SUB-01)
- **Deciders:** all owners (O1–O4)
- **Resolves:** Q-5 (repo visibility, licence, video length, team size, pre-existing work)

## Context

`docs/06_Plan.md` assumption **A-10** says the Official Rules were unpublished at plan time and that
no product code may be written until they are read and their constraints logged. T-0.1 exists to
convert that unknown into a decision record, then amend the plan if needed.

Sources read (accessed 2026-10-27):

1. Official Rules = *Hackathon Terms & Conditions ("Official Rules") and Event Waiver*, dated
   October 25, 2026 — <https://cerebralvalley.ai/e/meta-ai-developer-hackathon/waiver>
2. Event page (dates, themes, tracks, prizes, partners) —
   <https://cerebralvalley.ai/e/meta-ai-developer-hackathon>
3. Submission portal (login-gated form; not readable without a participant session) —
   <https://cerebralvalley.ai/e/meta-ai-developer-hackathon/hackathon/submit>

The portal's submission form is behind a participant login, so the field-by-field deliverable list
cannot be read here. Everything below is quoted from sources 1–2; the gap is recorded in
"Open items" and must be closed by a human at T-7.2.

## Decision (the constraints now binding on this repo)

**Deliverables:** One project per participant/team, submitted through the Cerebral Valley portal
(`/e/meta-ai-developer-hackathon/hackathon/submit`). The submission must be the entrant's original
work product, solely owned, and must not violate third-party IP. Submission components must remain
the participant's own work if a third party is contracted for technical assistance. Open-source
software may be included if its licences are followed and the submission builds upon it. The
deliverable *set* at the portal field level (repo link, demo video link, text write-up) is not
readable pre-login and is recorded as an open item.

**Video:** The Official Rules impose **no duration limit** on the demo video. The judged attribute
is quality: "Demo (25%) — whether the Project has a working, impressive demo, whether the product
holds up live, and the quality of the demo video." Plan stays with the 3-minute arc in §1A.

**Repo/licence:** No rule requires the repository to be public, and no rule prescribes a licence
choice. The entrant retains ownership of the Submission and grants the Organizers a perpetual,
irrevocable, worldwide, royalty-free, non-exclusive licence to use/reproduce/publish/display it,
including in marketing and at live events. The submission is warranted as original, solely owned,
and non-infringing. Scoring does not depend on repo visibility, so the repo may stay public under
the existing MIT `LICENSE` (already committed), provided the SAM 3.1 SAM License acknowledgement
required by A-5 stays in the README.

**Pre-existing work:** The rules contain no pre-hackathon cutoff or "built during the event only"
clause; they require the Submission to be the entrant's original, solely owned work. Repo history
is clean on this point: all commits in `D:\ProcessWatcher` are dated 2026-10-27 (after the Oct 26
kickoff), and the planning documents (`docs/01`–`06`) dated 2026-10-25 are our own unpublished
material, not third-party or prior-event code. Keep it that way: **no code copied from another
project, no prior-event submission reused.**

**Deadline UTC:** `2026-11-05T02:00:00Z` — Nov 4, 2026, 21:00 ET, the portal submission deadline.
Related UTC anchors (ET = UTC−4 until Nov 1, then UTC−5; the deadline is therefore UTC−5):

| Event | Local (ET) | UTC |
|---|---|---|
| Hackathon kickoff | Oct 26, 09:00 EDT | 2026-10-26T13:00:00Z |
| **Submissions due** | **Nov 4, 21:00 EST** | **2026-11-05T02:00:00Z** |
| Judging | Nov 4–8 | 2026-11-05T02:00:00Z → 2026-11-09T05:00:00Z |
| Finals / winners | Nov 9 | 2026-11-09 (closing ceremony) |
| Bonus prizes announced | on/about Nov 10 | 2026-11-10 |

Internal hard deadline stays **Nov 4, 12:00 ET = 2026-11-04T17:00:00Z** (5 hours of buffer).

## Other binding constraints (checked, no plan change needed)

- **Team size:** Indie developer track allows teams of **up to four (4)**; A-2 assumes a team of 4 →
  compliant. One individual must be appointed **Representative** and named as such at submission.
  One track only per project, and a project may be entered in one track only → stays **Indie (A-1)**.
- **Judging weights (project, not application):** Impact **30%** · Use of Meta AI Tooling **25%** ·
  Technical Depth & Execution **20%** · Demo **25%**. The plan's demo arc and the "seven things most
  teams will not do" list already target these four; no task moves. The 30% Impact weight justifies
  keeping the three-domain framing (A-8) in the README and the demo narrative.
- **Model tooling credit:** selected participants receive **$150 of Meta Model API credits** for the
  10-day window. This replaces the unknown in Q-2/A-4 with a hard budget: the `PW_SPEND_CAP_USD=3`
  per-run cap and NFR-02 cost target stay, and total spend across spikes + bench must stay under
  $150. The ledger (T-0.7) is now also the credit-burn tracker.
- **Meta AI products named:** Official Rules say "Muse Spark, Glimmer, SAM 3, and any other Meta AI
  products identified on the Event page"; the Event page names Muse Spark, Muse Wonder, Muse Image
  and SAM 3.1. We use **SAM 3.1, Muse Wonder, Muse Image** — the Event page naming governs, and
  Muse Spark stays unused unless an ADR approves it (A-11 unchanged).
- **Eligibility/administration (human actions, not code):** participants must be 18+ and not in a
  sanctioned/prohibited jurisdiction; the waiver and Official Rules must be signed; prizes need a
  W-9 (US) / W-8BEN (non-US) and payout details from the Representative. Nothing in the codebase
  can satisfy these — the human owner must.
- **Confidentiality:** materials shared during the event are not confidential and Organizers get a
  royalty-free perpetual licence to them. Consequence for us: **no employer-confidential procedure
  footage or SOPs** in `bench/`; film only our own props (A-8 procedures are generic).
- **Recording consent:** event sessions may be recorded and the Organizers may use participants'
  names, likeness and submissions for promotion; winners' names/logos may be published. No code
  impact; noted so no one is surprised by demo-video reuse.

## Plan edits made by this ADR

1. `A-10` in `docs/06_Plan.md` §2 is marked resolved by this ADR (rules read; no restructuring
   needed).
2. T-0.1 ticked `[x]` in `docs/06_Plan.md`; evidence line added to `docs/PROGRESS.md`.
3. A row is appended to `docs/06_Plan.md` §7 (Plan Change Log).
4. No task is added, removed, re-scoped or re-ordered: the rules do **not** conflict with the plan.
   The only confirmed additions are administrative (Representative, waiver, tax forms, credit
   budget) and are recorded above for the human owner.

## Consequences

- Product code may now be written (A-10 released): T-0.2 and T-0.3 are unblocked.
- The $150 credit pool is a shared, finite resource: spikes T-0.4/0.5/0.6 must stay time-boxed and
  must prefer `replay`; the ledger must be checked after each live session.
- The submission form's exact fields remain unverified until a logged-in human opens the portal at
  T-7.2. Until then, T-7.2's deliverable checklist carries one open item, not an invented list.

## Open items

| # | Item | Owner | When |
|---|---|---|---|
| 1 | Portal submission field list (repo link? video link? write-up? team roster?) — login required | human (O4) | T-7.2 |
| 2 | Name the team Representative in the submission | human (O4) | T-7.5 |
| 3 | Sign waiver / Official Rules; tax form if winning | human (O4) | before submission |
| 4 | Confirm track = Indie on the portal | human (O4) | T-7.5 |

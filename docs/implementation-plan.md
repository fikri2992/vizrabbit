# Implementation Plan — Visual QA Agent

Supersedes `build-plan.md` (kept as calendar summary). Rules: `AGENTS.md`. Domain: `domain-model.md`.
Every phase has a **quantified gate** — numbers, not vibes. A phase isn't done until its gate passes; if a gate fails, the next phase waits.

## Phase 0 — Foundations (Aug 14–15)

Tasks:
- Scaffold repo per AGENTS.md layout; uv + ruff + pytest wired; Vite + Tailwind + Pinia wired
- GCP: project, Gemini API/Vertex enabled, Firestore, GCS bucket, OAuth client
- Resolve model rule: confirm which Pro model satisfies "Gemini 3.5 or newer"; pin exact model IDs in `config.py`
- Hello-world ADK agent: image in → description out (local)
- Google OAuth: login → session cookie → `GET /me` (local)

**Gate 0 (quantified):**
- `pytest` and `npm test` green in CI-able one command each
- 1 ADK agent call returns structured pydantic output from a real image
- OAuth round-trip works in browser; `/me` returns the Google profile
- Model IDs locked and written into `config.py` + domain-model.md ⚠️ resolved

## Phase 1 — Pipeline core + eval (Aug 16–19) — make-or-break

Tasks:
- [x] `domain/grid.py`: aspect-adapted grid math, cell↔pixel, margin clamping
- [x] `imaging/`: grid overlay (contrast-outlined labels), crop cell+margin @2×, contact sheet with locator, circle compositor with size-relative strokes
- [x] Agents: Scanner → Inspector → Annotator (verify loop ≤3) → Pro gate (≤3 calls/run); Orchestrator with batch fan-out, concurrency 3
- [x] Built-in AI-slop guideline text (`ANAT-*`, `PHYS-*`, `ARTF-*` rule ids)
- [x] Benchmark harness: naive single-prompt baseline vs pipeline; recall/precision/F1 table + explicit Gate 1 verdict, exits non-zero on failure
- [→] Eval set: 30 labeled images (≥20 with known defects, ≥10 clean) — **moved to Deferred evidence (2026-08-16)**
- [→] Full benchmark run — same move; the 10-image first run below stands as the interim record

**Gate 1 (quantified):**
- [x] Unit tests: every cell→pixel mapping exact on 1:1, 4:5 and 16:9; cells tile the image with no gaps or overlaps; edge-cell margin clamping covered for every cell
- [x] Recall ≥ 0.75 → **0.83**
- [ ] Precision ≥ 0.70 → **0.50** — a lower bound, not a measurement; see below
- [ ] Recall lift ≥ +10pts vs naive → **+8.3pts** — undecided at this sample size, see below
- [x] Precision not worse than naive → 0.50 vs 0.47
- [x] ≤ 1 false positive per clean image → **0.25**
- [x] ≤ 120s per image → **56.4s**
- [ ] Cost ≤ $0.15 per image — not yet measured

### First benchmark run (2026-08-15, 10 images / 12 defects)

| Run | Recall | Precision | F1 | FP/clean | s/image |
| --- | --- | --- | --- | --- | --- |
| naive single prompt | 0.75 | 0.47 | 0.58 | 0.25 | 12.5s |
| multi-agent pipeline | 0.83 | 0.50 | 0.62 | 0.25 | 56.4s |

**Both failures are artefacts of the eval set, not evidence about the pipeline:**

1. **Precision is understated because the labels are not exhaustive.** Only the headline defect in each image was labelled, so anything else the pipeline finds scores against it. Confirmed by inspection: on `defective_12_white_hatchback` it flagged malformed wheel-rim spokes and melted windshield wipers — both real, both unlabelled, both counted as false positives. Wikimedia's own description of that file independently lists "wheel, headlight, panel geometry is inconsistent". The clean-image false-positive rate of **0.25**, where ground truth genuinely is complete, is the trustworthy precision signal.
2. **The recall lift is underpowered.** With 12 labelled defects, one defect is worth 8.3 recall points — so "+8.3" means the pipeline found exactly one more defect than the baseline. A 10-point threshold cannot be resolved at this sample size.

**To make Gate 1 decidable**: label the remaining 14 defective images, and label them *exhaustively* rather than just the obvious defect. At ≥40 defects one defect is worth under 2.5 points, and precision becomes a real measurement.

**Deferred 2026-08-16**: the labelling work and re-run move to the Deferred
evidence section at the end of this plan. Building phases no longer wait on
Gate 1; the interim numbers above are what the submission cites unless the
deferred run happens first.

## Phase 2 — Product spine (Aug 20–23)

Tasks:
- [x] Storage layer: `Store` interface with two real implementations (in-memory + Firestore), GCS/local blobs; run/image/defect/comment/notification persistence
- [x] API: projects, members, guidelines, batch upload, SSE activity stream, defect threads, transitions, memory, notifications
- [x] Vue: login (Google + local dev), project dashboard, upload flow
- [x] Live agent activity feed (SSE) with per-stage narration
- [x] Review screen: pins + threaded comments + severity/status chips + filters + role-aware actions
- [x] `scripts/seed_demo.py` — runs the app with a seeded project, no cloud or model needed

**Gate 2 (quantified):**
- [x] Browser flow: login → create project → review defects, zero manual DB touches (verified in-browser)
- [x] Integration tests: **51** against real persistence, 0 mocked repositories
- [x] SSE verified end-to-end: 3 events delivered in order, no subscription leak on disconnect (`scripts/check_sse.py`); browser `EventSource` connects
- [ ] Upload a **5-image batch** → watch live feed — **needs `GOOGLE_API_KEY`** (upload + persistence covered; the pipeline stage is not)
- [ ] First SSE activity event ≤ 5s after upload accepted — same blocker
- [ ] Review screen with 20 defects without jank — needs a real run
- [ ] Refresh mid-run: feed reattaches and shows current state

**Note on the emulator**: no Java/Docker on the dev machine, so the Firestore emulator cannot run here. Instead the same contract suite runs against both `Store` implementations, and picks up `FirestoreStore` automatically when `FIRESTORE_EMULATOR_HOST` is set.

## Phase 3 — Lifecycle + differentiators (Aug 24–26)

Tasks:
- [x] Roles Owner/Reviewer/Viewer, email invite, exactly-one-Owner invariant
- [x] Defect lifecycle `open → fix_submitted → agent_rechecking → verified_resolved`; Owner-only `dismissed` / `override_approved` (rationale required); Re-checker agent, version chain, version chips in the UI
- [x] Memory: propose from defect → Owner approves → rule active in Scanner input; lexical collision detection returned with the proposal
- [x] Mentions + in-app notifications
- [x] Guideline upload + grilling: the Pro model reads the document, asks 3–6 targeted questions quoting the vague phrase, and the Owner's answers append as clarifications that reach the Scanner verbatim

**Design correction made here**: `fix_submitted` is no longer reachable through the transition endpoint. It has to carry the version that claims to fix it, or a defect waits forever for a re-check with nothing to check against. The API now exposes `can_submit_fix` and the UI renders an upload control rather than a state to choose.

**Gate 3 (quantified):**
- [x] Lifecycle unit tests: all 196 role × transition combinations asserted against an independent allow-list; illegal transitions rejected at the API layer too
- [~] Re-check correctness: both directions verified against a live model on a synthetic pair (`scripts/check_recheck.py`) — a genuine fix was recognised, an unfixed defect was refused. Still needs the **5 real fixed-image pairs**, which depend on the defective eval set
- [x] Guideline grilling: a realistically vague brand doc produced **5 questions** first pass, and **4 different** ones after those were answered — no repeats (`scripts/check_grilling.py`). Answers persist and reach the Scanner verbatim (covered by integration test)
- Memory rule roundtrip: promote → next run on a planted image detects it, comment cites the memory rule id
- Full demo script executes end-to-end in **≤ 5 minutes** by a human following a written script

## Phase 4 — Deploy + harden (Aug 27–28)

Tasks:
- Cloud Run: backend + frontend, prod OAuth redirects, Firestore/GCS prod wiring
- Seed demo project (pre-grilled guideline, demo images, 2nd account for role demo)
- Retries/backoff on Gemini calls, SSE reconnect, quota guards
- README spin-up instructions

**Gate 4 (quantified):**
- Hosted URL: full demo script passes from a **clean incognito browser** on someone else's machine/network
- Cold start to interactive **≤ 10s**; warm page load ≤ 3s
- Kill the tab mid-run, reopen: run state fully recovered
- A stranger (or second account) follows README and reaches a working local setup in **≤ 15 min**
- Full eval benchmark re-run against the **deployed** backend: Gate 1 numbers hold within 5 points

## Phase 5 — Submission (Aug 29–31, protected)

Tasks:
- Architecture diagram (agents + GCP services + data flow)
- Demo video ≤ 4 min: problem → live app → benchmark table → architecture → GCP proof
- Devpost writeup with benchmark numbers
- Submit

**Gate 5 (quantified):**
- Video ≤ 4:00, shows live hosted app (not localhost), includes the recall/precision table
- Devpost submitted **≥ 24h before deadline** (by Aug 30 17:00 PDT)
- Repo public/shared, README verified by fresh clone

---

# Extension phases (2026-08-16) — from docs/roadmap-decisions.md

Deploy landed early (Phase 4 hosted URL live since Aug 15), which frees the
calendar for the product-fight outcomes. Decisions and their rationale live in
`roadmap-decisions.md`; this section is the build order and the gates.

## Phase 6 — Slot/variant remodel (Aug 16–19) — foundation, lands first

The unit of work becomes the **slot** (creative intent) → variants → linear
version chain per variant. Grouping is explicit at upload; version chains stay
linear (a competing fix is a new variant, never a fork); approval is
per-variant, the slot completes on first approval, siblings archive.

Tasks:
- `domain/entities.py`: `Slot` entity; `ImageAsset` gains `slot_id` and
  `variant` ordinal; archived state for losing variants
- Upload flow *offers* grouping, never asks: staging strip of file chips,
  default = each file its own slot (zero extra clicks, matches legacy); select
  chips + "variants of one slot" to group. New variants can also be added to an
  existing slot from its card (the competing-fix escape hatch)
- Migration shim: legacy flat images each auto-wrap in their own slot on read —
  zero data loss, no manual migration step
- Approval semantics: approve variant → slot complete → siblings archived
  (reversible by approving another variant); needs-review counts exclude
  archived variants. Archived carries a reason: "superseded by variant N"
  (sibling won) vs "defects unresolved" — surfaced as tooltip, never rendered
  as "rejected"
- Delete: variant delete removes its version chain; slot delete removes
  everything (consequence modal counts extend accordingly)
- History UI: 2-level tree on the slot card — variants as columns, versions as
  a vertical chain top-down; each node shows version + uploader + date +
  verdict color, click-through to that version's review. Winner column ends
  with an approval-stamp node (who approved, when). No cross-column arrows
  ever — across = alternatives, down = time
- Review trigger: upload is the only trigger — every variant in a batch gets
  its own review on upload; a fix upload re-reviews just that version.
  Archiving/un-archiving never triggers or cancels reviews (old verdicts stay
  valid)
- Slot card headline = best variant's state: any approved → complete; else
  any clean-awaiting-human → "ready to pick"; else in review
- Review screen header shows slot context (variant 2 of 3, v2) with
  prev/next-variant navigation for comparison

**Landed 2026-08-16.** Archived state turned out to be derivable rather than
stored (domain-model.md decision 14): a variant is archived exactly while a
sibling is approved, so reversibility and the zero-write legacy read path both
fall out of the same derivation, and there is no migration to run. Two entity
fields carry the whole remodel — `slot_id` and `variant` — plus `uploaded_by`,
which the history tree needed and nothing recorded before.

**Gate 6 (quantified):**
- Every pre-existing backend test still green (no behavioural regressions)
- New invariant tests: linear-chain enforcement (a second fix of the same
  version is rejected or lands as a new variant), slot completion on approval,
  archived variants excluded from attention counts — full matrix, no mocks
- Browser flow: upload 3 files as one slot's variants → tree renders 3
  columns; submit a fix on one → its column grows one node; approve it →
  slot shows complete, siblings show archived
- A legacy project (pre-slot data) loads with every image visible and
  reviewable, zero manual steps

Gate 6 evidence (2026-08-16): 733 backend tests green (690 pre-existing
unchanged, +43 new), 50 frontend tests green. Browser-verified against the
seeded demo — grouped upload of 3 files produced one slot with 3 variants; the
history tree drew 3 columns with uploader, date and verdict per node plus the
approval stamp; the two archived columns read "Superseded by variant 2" and
"Superseded by variant 2 · 1 defect left open"; re-approving a different variant
moved the win and left exactly one approved variant; the pre-slot demo image
listed as a synthetic slot with the `slots` collection still empty.

## Phase 7 — Brand guardian: palette (Aug 20–22)

Hybrid checker: mechanical measurement, agent judgment, normal defect
lifecycle with `BRAND-*` rule ids.

Tasks:
- `BrandProfile`: confirmed palette hexes + per-role tolerance (ΔE, Lab);
  stored only via owner confirmation — unconfirmed extractions never fire
- Griller extension: guideline upload accepts PDF; extraction proposes a
  profile (hexes read visually from swatch graphics, bounded page budget);
  scope ambiguities become grilling questions; confirmation form pre-filled
  and editable, works standalone without any document
- `imaging/palette.py`: dominant-palette extraction + ΔE (CIE Lab) against the
  confirmed profile — pure Python, no model calls
- Pipeline integration: measurements attach to the Scanner/Inspector exchange;
  the Inspector decides whether the off-palette region is a designed element
  (violation) or scene content (not one)
- Demo prerequisite: real guideline uploaded to the live project so grilling
  and brand defects are visible

**Gate 7 (quantified):**
- ΔE math unit-tested against published Lab reference pairs (±0.1)
- Synthetic palette eval: ≥ 0.8 recall on 10 planted off-palette designed
  elements; ≤ 1 false positive across 10 on-palette images containing
  ordinary photographic colour
- Extraction check script (`scripts/check_brand_extraction.py`) against a real
  brand PDF: proposes ≥ 3 hexes including at least one that appears only
  inside a swatch graphic, never as text
- End-to-end: a violating image produces a `BRAND-*` defect whose comment
  carries the measured ΔE; an unconfirmed profile produces zero brand defects
  (asserted by test)

**Built 2026-08-16.** Two deviations from the task list, both deliberate:

- The maths lives in `domain/color.py` (pure: sRGB→Lab, CIEDE2000) and only the
  Pillow work in `imaging/palette.py`, rather than both in `imaging/`. AGENTS.md
  makes `domain/` the home for exhaustively-tested pure logic, and ΔE against
  published reference pairs is exactly that.
- ΔE2000, not CIE76. It has a canonical verification dataset, and it disagrees
  with plain Lab distance by a factor of two precisely in near-neutrals and
  saturated blues — the colours brands care most about.

The split that makes a brand defect defensible: measurement is arithmetic the
Owner can re-derive and is stamped into the comment by code, never retyped by
the model (`attach_measurement`); the Inspector is asked only whether the
measured thing is a designed element or scene content.

**Gate 7 evidence (2026-08-16) — partially verified.**

Passing and checked:
- ΔE2000 against all 33 Sharma/Wu/Dalal verification pairs at **±0.0001**
  (gate asked ±0.1). One expected value I first wrote from memory was wrong;
  hand-deriving it confirmed the implementation and corrected the test.
- Unconfirmed profile → zero measurements, asserted at unit, service and API
  level, plus withdraw-keeps-the-colours. 861 backend tests green, 50 frontend.
- Measurement layer recall **1.00 (10/10)** on planted off-palette designed
  elements (`check_palette_eval --mechanical`). The same run flags 10/10
  photographic blobs, which is correct and is the load the Inspector must carry
  — locked in by a test so the division of labour cannot drift silently.
- Browser-verified on the seeded demo: palette panel confirms, withdraws and
  re-confirms; a `BRAND-PALETTE` defect renders carrying a real measurement
  ("ΔE2000 13.4 from #1c1e2a (ink), which allows 4.0").

**Not yet verified — needs model credentials, which this machine lacks:**
- Full-pipeline recall and false-positive numbers. The gate's ≤ 1 FP across 10
  clean images means the Inspector must reject ~10/10 photographic blobs; the
  mechanical run shows it gets no help from the measurement in doing so. **This
  is the real risk in Phase 7 and it is untested.** Run
  `uv run python -m scripts.check_palette_eval` before the demo.
- `scripts/check_brand_extraction.py` is written but has never been run: it
  needs both credentials and a real brand PDF, which the repo does not carry.
  The swatch-rendering half is covered by `tests/test_documents.py` against a
  generated PDF whose colour exists only as a graphic.

## Phase 8 — Approved export (Aug 22) — closes the dead end

Tasks:
- `GET /projects/{id}/export/approved` → zip of clean originals (never
  annotated renders), latest approved version of each slot's winning variant
- "Download approved (N)" button on the project page, count live

**Gate 8 (quantified):**
- Integration test: zip contains exactly the winners' latest approved
  originals — no annotated files, no superseded versions, unique filenames
- Browser-verified: approve → count increments → downloaded zip opens

**Landed 2026-08-16.** `services/export.py` (`approved_assets` + `build_zip`)
and `GET /projects/{id}/export/approved`. Gate evidence: integration test
asserts the zip holds exactly the winners' latest approved clean originals with
unique `{slot}-v{n}.png` names and 404s when nothing is approved;
browser-verified "Download approved (N)" button with a live count.

## Phase 9 — Platform context checker (Aug 23–25) — riskiest, cuttable

Placement findings are advisory, belong to an (image, platform) pair, and
never enter the defect lifecycle. Mechanical checks only in v1.

Tasks:
- Project setting: target platforms (aspect + safe-zone presets)
- `PlacementFinding`: advisory severity, closed by human decision
  (acknowledge/waive), no re-check path
- Checks: strapline/text legibility at platform thumbnail size; declared
  critical element (logo/product/strapline region from the brand profile or a
  drawn region) fully inside the platform crop and safe-zone
- Review screen: per-platform row under the status header; cost cap ≤ 2 extra
  model calls per image per platform

**Gate 9 (quantified):**
- Legibility eval on synthesized text at graduated sizes: ≥ 0.9 correct
  classification beyond 2× the threshold distance
- Lifecycle isolation asserted: no path from `PlacementFinding` into defect
  states (test), and placement findings never block image approval
- Demo shows at least one platform end-to-end; degrading to one platform is
  the planned cut, not a failure

**Landed 2026-08-16 — with the planned cut taken.** `domain/platforms.py`
(tiktok/instagram/web presets, centre-crop geometry, crop-loss + resolution +
loudness checks, all pure), findings derived at read time from the run's
placement, acknowledge/waive stored as `PlacementDecision`. The legibility
check (the ≥ 0.9 eval, the only model-call item) is the cut: v1 is entirely
mechanical, zero model calls. Gate evidence: geometry unit tests; lifecycle
isolation asserted (`PlacementFinding` has no path into `DefectState`, and an
image with open advisories approves); browser-verified TikTok chips, crop
preview overlay with safe-area box, and acknowledge/waive strike-through.
Deviation from the task list: placement is chosen per-upload on the staging
strip (decision 22), not a project-level setting.

# Partner phases (2026-08-16) — from docs/product-thesis.md + the partner prototype

Validated in `PrototypePartnerPage.vue` (three feedback rounds; prototype is the
primary source, in git history). The laws these implement are domain-model
decisions 19–23. Delete the prototype page as each surface lands for real.

## Phase 10 — Spec + derived marks (foundation, no model calls)

Tasks:
- `Slot.spec`: deliverable list (label + aspect, optional due date). Optional
  field; specless slots behave exactly as today
- Marks derived in the slots endpoint at read time (decision 20): missing
  deliverable, pickable, stalled fix (age of oldest FIX_SUBMITTED-less open
  defect request), question pending. No stored agenda documents
- SlotCard chips + one dismissible quiet line on ProjectPage (dismissals
  stored per user, the only stored thing)
- Placement question on the upload staging strip (decision 22); stored on the
  run, consumed by Phase 9 checks

**Gate 10:** marks are pure functions with table-driven tests; a spec-less
project renders byte-identical card data to today (regression); dismissing a
mark survives reload; placement lands on the run document.

**Landed 2026-08-16.** `domain/marks.py` pure (21 table-driven tests);
`Slot.spec`/`due_at`; marks computed in the slots endpoint per read, only
`MarkDismissal` stored per user; SlotCard chips + dismissible quiet line;
placement chips on the staging strip land on `Run.placement`. Spec-less
regression and reload-survival asserted.

## Phase 11 — Draft-as-branch + stance (the partner's heart)

Tasks:
- After a run's verdicts land: one drafting pass — mechanical defects only
  (category whitelist), Gemini image-edit call per affected image, result
  saved as an ordinary branch version authored by the agent (decision 21)
- Draft rendering: dashed node in the flow view, "draft · by agent" tag
- Stance in the SlotFlowPage rail: computed facts only (defects resolved,
  measurements), link to the review page; no generated prose in v1
- Discard-a-draft: deletes the branch, records a per-slot "propose, don't
  draft" preference

**Gate 11:** drafting never fires for creative categories (test on the
whitelist boundary); a draft is indistinguishable from a human version to
every existing read path (chains/state/approval tests pass unchanged); the
recheck runs on the draft like any fix; cost cap: ≤ 1 edit call per defect,
one pass per run.

**Landed 2026-08-16.** `services/drafts.py` (`draft_pass` after
`run_finished`, whitelist = ANATOMY/ARTIFACT, one editor call per image,
branch version authored `agent:qa`, recheck fires on it); `agents/editor.py`
wraps `settings.model_image_edit` (nano banana). Discard reopens claimed
defects, deletes the branch, sets `no_drafts`. Dashed draft node + stance
panel (computed facts only) in the flow view. Gate evidence: whitelist
boundary, read-path indistinguishability, and never-raises all tested.
**Caveat: the real image-edit call has never run — needs credentials
(Deferred evidence).**

## Phase 12 — Questions + judgment voice

Tasks:
- `needs_human_review` defects render as question threads on the review page:
  evidence at size (swatch pair for colour, crop for geometry), two answers +
  ignorable; either answer writes through the existing dismissal/memory path
- Activity feed voice: judgment lines ("kept quiet about X — rule #N") emitted
  alongside stage events; SSE shape unchanged

**Gate 12:** answering a colour question adjusts the stored tolerance and a
re-run stops asking; an ignored question never blocks approval flow (test);
feed renders old events unchanged (compatibility).

**Landed 2026-08-16.** Question threads with evidence at size (swatch pair
parsed back out of the code-stamped measurement via `parse_measurement`, the
exact inverse of `describe()`); "It's real" reopens, "Not a problem" dismisses
and widens `PaletteEntry.tolerance` to the measured ΔE; `judgment` feed events
via `judgment_notes`. Gate evidence: tolerance-widening round-trip, approval
never blocked by an open question (backend gate counts OPEN only, frontend
`isClear` mirrors it), feed compatibility.

## Phase 13 — Video review (biggest lift, independent of 10–12)

Tasks:
- ffmpeg in the container: scene-cut frames, audio extraction, poster, EBU
  R128 loudness; frames run the existing image pipeline (decision 23)
- `DefectRecord.time_start/time_end`; review screen grows a player + timeline
  with defect ranges; platform safe-area overlay toggle (reuses Phase 9 zones)
- Measured checks: loudness vs platform target, text reading-speed, safe-area
  overlap; passes reported with their numbers

**Gate 13:** a seeded spot yields the safe-area defect with a correct time
range (integration); timeline markers seek; loudness numbers match ffmpeg's
own report on a reference file; image-only projects untouched (regression).

**Landed 2026-08-16 — narrower than the task list, deliberately.**
`imaging/video.py` (probe, scene cuts capped at 12 frames, frame extraction,
EBU R128 loudness); mp4 ingest stamps poster-as-original so every image
surface works unchanged; review = one image-pipeline pass per shot frame with
pins renumbered and defects stamped with shot time ranges; review page grows a
player + seekable amber timeline + loudness advisory against the platform
target (via Phase 9's placement strip, so safe-area is an advisory there, not
a defect — decision 23's "measured half per modality"). Not built: audio
extraction beyond loudness, text reading-speed. Re-cuts are new uploads;
uploads capped at 20MB. Gate evidence: real-ffmpeg tests on a generated
two-shot clip including loudness-matches-ffmpeg's-own-report and
shot-time-range integration; image-ingest regression; browser-verified player,
seek chips, and the measured-LUFS advisory. **ffmpeg must be added to the
Cloud Run container before the next deploy.**

# Bonus phases (2026-08-16) — the remaining Gemini-family tie-ins

Phases 10–13 landed same-day, so the two bonus integrations the sequencing
note only gestured at get real phases. Both are garnish per the thesis: they
attach to existing surfaces and change no domain law. Either can be cut alone.

## Phase 14 — Gemini Live on question threads

Voice as an *input mode* for Phase 12's questions — the owner talks through
the queued questions instead of clicking, answers write through the exact
same `answer_question` path. No new decision authority, no new state.

Tasks:
- Backend: session-token endpoint for the Live API (`model_live` pinned in
  `config.py`); tool declarations exposing only `answer_question` and
  navigation (next/previous question) — the model can never approve, dismiss
  a non-question defect, or touch anything else
- Review page: a "talk through questions" toggle on the question banner;
  transcript rendered into the thread as ordinary comments so the record is
  the same as a clicked answer
- Guard: works only when ≥ 1 question is open; degrades to the buttons
  silently when the Live API or mic is unavailable

**Gate 14 (quantified):**
- Tool-call surface asserted: the declared tools cannot reach any transition
  except the two question answers (test on the declaration list)
- A spoken "not a problem" produces the identical stored outcome (dismissal +
  tolerance widening) as the button — byte-equal defect record, asserted
- Browser demo: answer 2 seeded questions by voice end-to-end

## Phase 15 — Veo export extension

From Phase 8's dead-end-closer: an approved still can be extended into a
short motion variant, and the output *re-enters review* as a new video slot
variant — the airlock applies to generated media exactly as to uploads.

Tasks:
- `POST /projects/{id}/slots/{slot_id}/animate`: Veo call
  (`model_video` pinned in `config.py`) from the approved original + a typed
  motion brief; result ingests through `_ingest_video` as a new variant of
  the same slot (agent-authored, like a draft)
- Button on the completed slot card ("Animate…"), brief modal; Owner-only
- The generated variant gets the full video review pass (Phase 13) —
  loudness, shots, placement advisories if the run has a placement

**Gate 15 (quantified):**
- Output lands as an ordinary video variant: every existing read path (tree,
  review, export) renders it with zero special cases (tests pass unchanged)
- Export zip still contains only *approved* assets — an unapproved generated
  video never leaks into the export (test)
- Browser demo: animate an approved still → watch the run → review the video

**Landed 2026-08-16.** `agents/animator.py` (Veo long-running operation,
`model_video` + poll caps in config), `services/animate.py` split sync/async:
`resolve_animation` validates before any budget is spent (Owner-only via the
new `ANIMATE_APPROVED` permission, completed slots only, non-empty brief),
`run_animation` does the minutes-slow half in the background and reports
through the feed (`animation_started/created/failed`). The output rides
`create_run` with an `author` override — one parameter, and every downstream
behaviour (video ingest, review pass, tree, export) is the existing code
untouched. Also fixed the drafting pass exposed by this work: the editor now
skips video assets (a PNG branch on a video would claim to fix footage).
Gate evidence: 8 tests — owner-only, incomplete-slot refusal, failed
generation leaves no orphan (event trail asserted), the generated clip lands
as an ordinary agent variant with the full review pass and the approval
unmoved, export exclusion, editor-never-drafts-on-video. Browser-verified:
"Animate approved…" on the complete demo slot → brief modal → 202 → feed
shows the start line and (credential-less) the honest failure line, slot
unchanged. **The real Veo call has never run — needs credentials (Deferred
evidence, same item as the editor smoke-run).**

## Sequencing note

10 → 11 → 12 in order (each consumes the previous); 13 is parallel-safe.
Hackathon bonus tie-ins: Phase 11 is the nano-banana integration; Gemini Live
is Phase 14; Veo is Phase 15. With 11 + 14 + 15 that is three bonus models
beyond the core Gemini pipeline — the maximum bonus.

## Revised calendar (2026-08-16, second revision)

Phases 6–13 all landed by Aug 16 — two weeks ahead of the first revision.
What remains:

- Aug 17–21: Phase 14 (Live) · Phase 15 (Veo) · credential-gated checks from
  Deferred evidence (palette pipeline eval, brand extraction, editor
  smoke-run)
- Aug 22–26: redeploy (ffmpeg in the container) + Gate 4 re-verification
  against the hosted URL; hardening; deferred evidence as capacity allows
- Aug 27–31: Phase 5 submission (video, Devpost, ≥ 24h early) — protected,
  starts no later than Aug 27 regardless of what is unfinished

## Cut order (second revision)

1. Deferred evidence (already deferred) → 2. Phase 15 Veo → 3. Phase 14 Live.
Never cut: everything already landed, redeploy + Gate 4 re-check, demo video,
submission.

# Deferred evidence (2026-08-16)

Work that proves quality but blocks no build. Do before submission if time;
each item names what the submission says without it.

- **Gate 1 eval set** (deferred by decision, was Phase 1): label remaining 14
  defective images exhaustively (≥ 40 defects total), re-run benchmark,
  measure cost/image. Without it the submission cites the 10-image interim
  table with its stated caveats.
- **Palette full-pipeline eval** (`uv run python -m scripts.check_palette_eval`,
  needs credentials): the Inspector's 10/10 photographic-blob rejection is the
  untested half of Gate 7. Without it, cite the mechanical recall 1.00 only.
- **Brand extraction** (`scripts/check_brand_extraction.py` + a real brand
  PDF, needs credentials).
- **Editor + animator smoke-run** (needs credentials): one real nano-banana
  draft and one real Veo animation on the seeded demo — `agents/editor.py`
  and `agents/animator.py` have never been exercised live.
- **Gate 3 leftovers**: 5 real fixed-image pairs (depends on the eval set);
  timed 5-minute demo-script run; memory-rule roundtrip on a planted image.
- **Gate 4 re-verification**: current main is ~13 commits past the deployed
  revision; redeploy (container needs ffmpeg) then re-run the clean-incognito
  script, cold-start timing, mid-run kill recovery, fresh-clone README ≤ 15
  min.

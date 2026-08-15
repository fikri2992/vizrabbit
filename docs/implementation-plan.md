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
- [ ] Eval set: 30 labeled images (≥20 with known defects, ≥10 clean) — **needs images + API key**
- [ ] First benchmark run — **blocked on the eval set**

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
- Upload flow asks: new slots (one per file) or variants of one slot
- Migration shim: legacy flat images each auto-wrap in their own slot on read —
  zero data loss, no manual migration step
- Approval semantics: approve variant → slot complete → siblings archived
  (reversible by approving another variant); needs-review counts exclude
  archived variants
- Delete: variant delete removes its version chain; slot delete removes
  everything (consequence modal counts extend accordingly)
- History UI: 2-level tree on the slot card — variants as columns, versions as
  a vertical chain, verdict dot per node, click-through to review
- Review screen header shows slot context (variant 2 of 3, v2)

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

## Phase 8 — Approved export (Aug 22) — closes the dead end

Tasks:
- `GET /projects/{id}/export/approved` → zip of clean originals (never
  annotated renders), latest approved version of each slot's winning variant
- "Download approved (N)" button on the project page, count live

**Gate 8 (quantified):**
- Integration test: zip contains exactly the winners' latest approved
  originals — no annotated files, no superseded versions, unique filenames
- Browser-verified: approve → count increments → downloaded zip opens

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

## Revised calendar

- Aug 16–19 Phase 6 · Aug 20–22 Phase 7 · Aug 22 Phase 8 · Aug 23–25 Phase 9
- Aug 26–28 hardening + outstanding Gate 1/3/4 evidence (exhaustive labels,
  benchmark re-run, 5 real fix pairs, cost/image, fresh-clone README timing)
- Aug 29–31 Phase 5 submission (video, Devpost, ≥ 24h early) — protected

## Cut order (revised)

1. Platform checker (Phase 9) → 2. History-tree polish (fall back to grouped
cards per slot) → 3. Memory collision-grilling → 4. Mentions/notifications.
Never cut: pipeline, benchmark, review screen, re-check lifecycle, slot
remodel once started, brand palette once started, deploy, video.

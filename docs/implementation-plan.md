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
- Pipeline on eval set: **recall ≥ 0.75, precision ≥ 0.70**
- Pipeline beats naive baseline by **≥ +10 points recall** at equal-or-better precision
- False-positive rate on the 10 clean images: **≤ 1 defect per clean image average**
- Latency: **≤ 120s per image** end-to-end (p90 over eval run)
- Cost: **≤ $0.15 per image** (computed from token counts of one eval run)
- If any metric misses → time-boxed 1-day prompt/grid iteration before Phase 2 starts

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
- Roles Owner/Reviewer/Viewer, email invite, exactly-one-Owner invariant
- Defect lifecycle `open → fix_submitted → agent_rechecking → verified_resolved`; Owner-only `dismissed` / `override_approved` (rationale required); re-check agent pass
- Guideline upload + grilling chat (one Q at a time, clarifications appended, editable)
- Memory: propose from defect → Owner approves → rule active in Scanner input; collision-grilling (droppable)
- Mentions + in-app notifications (droppable)

**Gate 3 (quantified):**
- Lifecycle unit tests: **all role × transition combinations** asserted (full matrix, no gaps); illegal transitions rejected at API layer too
- Re-check on eval fixtures (5 fixed-image pairs): **≥ 4/5 fixed defects auto-closed**, 0 falsely closed unfixed defects
- Guideline grilling: uploading the seed brand doc produces **≥ 3 clarifying questions**; answers persist and appear in Scanner input verbatim
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

## Cut order (unchanged)

1. Memory collision-grilling → 2. Mentions/notifications → 3. Grilling UI (fall back to pre-grilled seed). Never cut: pipeline, benchmark, review screen, re-check lifecycle, deploy, video.

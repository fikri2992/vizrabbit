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
- `domain/grid.py`: 8×8 aspect-adapted grid math, cell↔pixel, margin clamping
- `imaging/`: grid overlay (A1–H8, contrast-outlined labels), crop cell+margin @2×, contact sheet, circle compositor
- Agents: Scanner → Inspector → Annotator (verify loop ≤3) → Pro gate (≤3 calls/run); Orchestrator with batch fan-out, concurrency 3
- Built-in AI-slop guideline text
- Eval set: 30 labeled images (≥20 with known defects across all 4 built-in categories, ≥10 clean)
- Benchmark harness: naive single-prompt Gemini vs pipeline; outputs recall/precision/F1 table (markdown)

**Gate 1 (quantified):**
- Unit tests: 64/64 cell→pixel mappings exact; edge-cell margin clamping covered; all grid tests pass on 3 aspect ratios (1:1, 4:5, 16:9)
- Pipeline on eval set: **recall ≥ 0.75, precision ≥ 0.70**
- Pipeline beats naive baseline by **≥ +10 points recall** at equal-or-better precision
- False-positive rate on the 10 clean images: **≤ 1 defect per clean image average**
- Latency: **≤ 120s per image** end-to-end (p90 over eval run)
- Cost: **≤ $0.15 per image** (computed from token counts of one eval run)
- If any metric misses → time-boxed 1-day prompt/grid iteration before Phase 2 starts

## Phase 2 — Product spine (Aug 20–23)

Tasks:
- Firestore schema + GCS storage; run/image/defect/comment persistence
- API: projects, batch upload, SSE activity stream, defects/comments CRUD
- Vue: login, project dashboard (per-image status), upload flow
- Live agent activity feed (SSE)
- Review screen: pins + threaded comments + category/severity/status chips + filters

**Gate 2 (quantified):**
- Browser flow: login → create project → upload **5-image batch** → watch live feed → review defects, zero manual DB touches
- First SSE activity event **≤ 5s** after upload accepted
- Review screen renders an image with **20 defects** without jank; pin click → thread scroll < 100ms perceived
- Integration tests (Firestore emulator): every API route has ≥1 real-persistence test; suite **≥ 25 tests**, 0 mocked repositories
- Refresh mid-run: feed reattaches via SSE and shows current state (no lost run)

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

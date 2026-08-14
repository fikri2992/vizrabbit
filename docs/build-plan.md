# Build Plan — Visual QA Agent

> Superseded by `implementation-plan.md` (quantified gates per phase). This file remains as the calendar overview.

18 days: Aug 14 → Aug 31 (submission 17:00 PDT). Principle: pipeline + eval first (the proof), UI second (the story), collab third (the product), submission assets protected (the deadline).

## Phase 0 — Foundations (Aug 14–15)

- [ ] Repo scaffold: `backend/` (FastAPI + ADK, uv), `frontend/` (Vue 3 + Vite + Tailwind), `eval/`
- [ ] GCP project: enable Vertex AI/Gemini API, Firestore, GCS bucket, OAuth consent screen + client ID
- [ ] Verify Gemini model availability — resolve the ⚠️ 3.1 Pro vs "3.5 or newer" question; lock Flash + Pro model IDs
- [ ] Hello-world ADK agent calling Gemini vision on an image, deployed nowhere yet (local run)
- [ ] Google OAuth login flow (FastAPI session + Vue login page) — skeleton only

**Exit criteria**: one ADK agent describes a local image; login works locally.

## Phase 1 — Pipeline core + eval (Aug 16–19) ← the make-or-break phase

- [ ] Pillow toolkit: grid overlay (8×8 aspect-adapted, A1–H8 labels, contrast outline), cell→pixel mapping, crop cell+margin @2×, contact-sheet compositor, circle drawing
- [ ] Scanner agent: original + gridded → suspect cells (structured output: cell refs + rule ref + hypothesis)
- [ ] Inspector agent: contact sheet → confirm/dismiss + category + severity; dismissal log
- [ ] Annotator agent: circle placement + self-verify loop (max 3) + comment text; confidence tagging
- [ ] Pro gate: final verification, ≤3 calls/run
- [ ] Orchestrator: per-image sequential, batch fan-out capped at 3 concurrent
- [ ] Built-in AI-slop guideline (the always-on rules text)
- [ ] **Eval set: ~30 images with labeled known defects** (generate with Gemini/Imagen + hand-label; include clean images for false-positive rate)
- [ ] **Benchmark harness: naive single-prompt Gemini vs pipeline → recall/precision table** (this table goes in the demo + README)

**Exit criteria**: CLI run on a folder of images produces annotated images + defect JSON; benchmark shows measurable lift (if it doesn't, iterate prompts/grid here before building any UI).

## Phase 2 — Product spine (Aug 20–23)

- [ ] Firestore schema + GCS storage per domain model (projects, runs, images, defects, comments)
- [ ] API: create project, upload batch (run), SSE stream of agent activity, defect/comment CRUD
- [ ] Vue: project dashboard (per-image status), upload flow
- [ ] **Live agent activity feed** (SSE): "Scanner flagged C4… Inspector confirmed anatomy/blocker… Annotator verifying circle (2/3)…" — the wow surface
- [ ] Review screen: image + numbered circle pins + threaded comment sidebar, category/severity/status chips + filters

**Exit criteria**: full flow in browser: login → project → upload batch → watch feed → review defects.

## Phase 3 — Lifecycle + differentiators (Aug 24–26)

- [ ] Roles: Owner/Reviewer/Viewer enforcement (invite by email, exactly one Owner)
- [ ] Defect lifecycle: `open → fix_submitted → agent_rechecking → verified_resolved`; Owner-only dismiss + override-approve (rationale logged); re-check agent pass on new image version
- [ ] Guideline upload + upload-time grilling chat (one question at a time, answers appended as clarifications, editable doc view)
- [ ] Memory: propose-from-defect button → Owner approval → active memory rule fed to Scanner; collision-grilling (droppable)
- [ ] Mentions + in-app notifications (droppable)

**Exit criteria**: demo script runs end-to-end: upload → defects → fix → re-check → verified_resolved → Owner approves image.

## Phase 4 — Deploy + harden (Aug 27–28)

- [ ] Cloud Run: backend + frontend containers, Firestore/GCS wired, OAuth redirect URLs, custom env config
- [ ] Seed demo project: preloaded brand guideline (already grilled), demo images, second account for role demo
- [ ] Failure hardening: agent retries, graceful SSE reconnect, quota backoff
- [ ] README spin-up instructions (judges must reproduce)

**Exit criteria**: hosted URL works from a clean browser; cold-start acceptable.

## Phase 5 — Submission assets (Aug 29–31, protected — do not trade for features)

- [ ] Architecture diagram (agents, GCP services, data flow)
- [ ] ~4-min demo video: problem → live app → benchmark table → architecture → GCP proof
- [ ] Devpost writeup: features, stack, learnings, benchmark numbers
- [ ] Submit by Aug 31 morning, not 16:59 PDT

## Cut order (if behind)

1. Memory collision-grilling (keep promotion)
2. Mentions/notifications
3. Guideline grilling UI → fall back to pre-grilled seeded guideline
4. Never cut: pipeline, eval benchmark, review screen, re-check lifecycle, deploy, video

## Standing risks

- Pipeline lift not provable → detected Phase 1 by benchmark, mitigated by prompt/grid iteration time-boxed there
- Gemini quota/rate limits → concurrency cap 3, backoff, seeded demo data as fallback
- Cloud Run + OAuth config burn → do it Phase 4 start, not last day

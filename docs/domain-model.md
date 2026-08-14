# Domain Model — Visual QA Agent

Enterprise visual QA platform: design/sales/marketing teams collaboratively review AI-generated imagery. An ADK multi-agent pipeline detects defects against guidelines; humans act on them frame.io-style.

Hackathon: All Things Agentic (Devpost). Deadline **2026-08-31 17:00 PDT**. Requires Gemini ≥3.5, a Google agent framework (ADK), and ≥1 GCP service. Deliverables: hosted URL, repo + spin-up instructions, architecture diagram, ~4-min demo video.

## Ubiquitous language

| Term | Meaning |
|---|---|
| **Project** | Workspace owned by a team. Holds members, guidelines, memory rules, runs. |
| **Guideline** | Per-project raw-text rules doc (e.g. brand guideline). Stored as `raw doc + clarifications`, editable. Built-in AI-slop guideline is global and always on. |
| **Clarification** | Q&A pair appended to a guideline, produced by upload-time grilling. |
| **Grilling** | Agent interviews the user one question at a time to resolve ambiguity. Happens (a) at guideline upload, (b) on memory-rule collision. Never mid-scan. |
| **Run** | One batch submission of N images through the pipeline. Uncapped parallel fan-out. |
| **Grid** | 8×8 chess-labeled overlay (A1–H8), aspect-adapted so cells stay near-square. Labels drawn with high-contrast outline. |
| **Suspect cell** | Grid cell flagged by the Scanner as possibly containing a defect. High recall by design. |
| **Contact sheet** | Composite image: full original + zoomed crop (suspect cell + 1-cell margin, 2× upscale) fed to the Inspector. |
| **Defect** | Confirmed issue. Has category, severity, cell refs, circle annotation, comment thread, status. |
| **Dismissal** | Inspector/verifier rejecting a suspect as false positive. Logged, never deleted. |
| **Annotation loop** | Annotator draws circle → looks at its own output → verifies circle lands on defect → adjusts. Max 3 iterations; on max-out, best attempt kept and tagged `needs human review`. |
| **Pro gate** | Final verification pass by the expensive Pro model. Hard cap: 3 Pro calls per run. |
| **Memory rule** | Standing rule promoted from a defect via "add to memory". Checked on all future scans in the project. Collisions with existing rules trigger grilling. |
| **Re-check** | Uploading a fixed image version; agent verifies each open defect is resolved. |

## Agents (ADK)

- **Orchestrator** — fans images out (parallel, uncapped), sequences stages per image.
- **Scanner** — sees original + gridded copy; input: active guidelines + memory rules; output: suspect cells with rule references. Recall-biased.
- **Inspector** — per suspect cell, contact sheet in; confirms/dismisses; assigns category + severity. Precision gate.
- **Annotator** — computes circle from cell coords (Pillow draws; model never draws), runs annotation loop, writes the frame.io comment.
- **Guideline griller** — upload-time interviewer; also handles memory-rule collision grilling.
- Models: **Gemini 3.7 Flash** for Scanner/Inspector/Annotator; **Pro** (⚠️ verify 3.1 Pro qualifies under "3.5 or newer"; else 3.5 Pro) only at the Pro gate, ≤3 calls/run.

## Taxonomy

- Categories: `anatomy | physics | artifact | brand | memory` (extensible later).
- Severity: `blocker | warning | nitpick` — set by Inspector, human-adjustable.
- Defect status: `open | resolved | dismissed | needs_human_review`.

## Entities (Firestore)

- `users` (Google OAuth only)
- `projects` { members[], guidelines[], memoryRules[] }
- `guidelines` { rawText, clarifications[{question, answer}], updatedAt }
- `runs` { projectId, images[] }
- `images` { runId, gcsPaths{original, gridded, annotated}, version, status }
- `defects` { imageId, category, severity, cells[], circle{x,y,r}, confidence, status, ruleRef }
- `comments` { defectId, author (user|agent), body, mentions[] }
- `memoryRules` { sourceDefectId, description, active }
- `notifications` { userId, type(mention|assignment|run_done), read }
- Dismissal log kept per run.

## Decisions (ADR-style, one-liners)

1. Two-stage recall→precision (scan then zoom) — VLMs miss small defects at full res; zoom earns confidence.
2. Self-verifying annotation loop, max 3 iterations, confidence tagging, dismissal-with-log.
3. Raw-text guidelines + grilling; no compiled rule extraction. Grilling at upload only, never mid-scan.
4. Multi-agent ADK pipeline (Sequential/Loop/Parallel primitives) over single agent + tools.
5. Flash for volume, Pro as capped final gate (economics + pitch: "the reviewer's reviewer").
6. Fixed 8×8 aspect-adapted grid; zoom supplies extra resolution, not denser grids.
7. Batch runs, uncapped parallelism (accepted risk: quota exhaustion during demo).
8. Full real product: Google OAuth, real members/@mentions, in-app notifications only (no email), SSE for updates (no multiplayer cursors).
9. Review screen: threads + reply + status, add-to-memory (top differentiator), version re-check (first to drop if squeezed).
10. Stack: Vue 3 + Vite + Tailwind / FastAPI + Python ADK / Firestore + GCS + Cloud Run.

## Open items

- ⚠️ Confirm exact allowed Gemini model list vs "3.5 or newer" — affects Pro-gate model choice.
- Architecture diagram + 4-min video are submission requirements; schedule time for them.

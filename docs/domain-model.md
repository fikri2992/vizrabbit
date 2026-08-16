# Domain Model — Visual QA Agent

Enterprise visual QA platform. Wedge positioning: **QA for AI-generated e-commerce/social assets before publish**. An ADK multi-agent pipeline detects defects against guidelines; humans act on them frame.io-style. Sells to the Brand Owner; design/social/sales get pulled in as participants.

Hackathon: All Things Agentic (Devpost). Deadline **2026-08-31 17:00 PDT**. Requires Gemini ≥3.5, a Google agent framework (ADK), and ≥1 GCP service. Deliverables: hosted URL, repo + spin-up instructions, architecture diagram, ~4-min demo video.

## Ubiquitous language

| Term | Meaning |
|---|---|
| **Project** | Workspace owned by a team. Holds members, guidelines, memory rules, runs. |
| **Guideline** | Per-project raw-text rules doc (e.g. brand guideline). Stored as `raw doc + clarifications`, editable. Built-in AI-slop guideline is global and always on. |
| **Clarification** | Q&A pair appended to a guideline, produced by upload-time grilling. |
| **Grilling** | Agent interviews the user one question at a time to resolve ambiguity. Happens (a) at guideline upload, (b) on memory-rule collision. Never mid-scan. |
| **Run** | One batch submission of N images through the pipeline. Uncapped parallel fan-out. |
| **Slot** | One creative intent — "the hero banner". The unit of work. Holds competing variants; completes when the Owner approves one of them. |
| **Variant** | A competing candidate for a slot, numbered from 1. Owns a linear version chain. Variants never merge and never fork: a competing fix is a new variant. |
| **Version chain** | The strictly linear `v1 → v2 → …` lineage inside one variant, each version a re-check upload. Fixing a version that already has a successor is rejected — add a variant instead. |
| **Archived variant** | A variant of a completed slot that did not win. Derived state, never stored: a variant is archived exactly while a *sibling* is approved. Reads as "superseded by variant N", never "rejected"; approving a different variant reverses it. |
| **Grid** | 8×8 chess-labeled overlay (A1–H8), aspect-adapted so cells stay near-square. Labels drawn with high-contrast outline. |
| **Suspect cell** | Grid cell flagged by the Scanner as possibly containing a defect. High recall by design. |
| **Contact sheet** | Composite image: full original + zoomed crop (suspect cell + 1-cell margin, 2× upscale) fed to the Inspector. |
| **Defect** | Confirmed issue. Has category, severity, cell refs, circle annotation, region (tight pixel extent from the cell span — what the review UI outlines as a rounded box), comment thread, status. |
| **Marker visibility** | Idle canvas shows numbered pins only; a marker's geometry draws when its pin, rail card, or selection makes it active. Frame.io model: the image stays clean. |
| **Dismissal** | Inspector/verifier rejecting a suspect as false positive. Logged, never deleted. |
| **Annotation loop** | Annotator draws circle → looks at its own output → verifies circle lands on defect → adjusts. Max 3 iterations; on max-out, best attempt kept and tagged `needs human review`. |
| **Pro gate** | Final verification pass by the expensive Pro model. Hard cap: 3 Pro calls per run. |
| **Memory rule** | Standing rule promoted from a defect via "add to memory". Checked on all future scans in the project. Collisions with existing rules trigger grilling. |
| **Re-check** | Uploading a fixed image version; agent verifies each open defect is resolved. Core: it is the only path to `verified_resolved`. |
| **Review thread** | A human-anchored annotation: drawn shapes (circle/rect/arrow/freehand) + a comment, pinned to the image. Shares one pin sequence with defects. Frame.io model: every comment is anchored. |
| **Ask agent** | A review thread flagged for inspection: the drawn region maps to grid cells, the Inspector runs on that crop with the human's question as hypothesis, and replies in the thread. A confirmed finding becomes a real defect carrying the thread's pin. |
| **Brand profile** | A project's confirmed palette: approved hexes, each with a role and its own ΔE2000 tolerance. Proposed by extraction, inert until the Owner confirms it. |
| **Palette measurement** | Mechanical, per grid cell: dominant colours quantised out of the region and compared to the profile by ΔE2000. Arithmetic the Owner can re-derive — never a model's opinion of a colour. |
| **Off-palette region** | A measurement further from its nearest brand colour than that colour's tolerance. Evidence, not a defect: only the Inspector deciding it is a *designed* element makes it one. |
| **Designed vs scene content** | The judgement the palette checker turns on. A logo, type, packaging or graphic panel is governed by the palette; skin, sky, food, foliage, fabric and reflections are not. |
| **Brand Owner** | The one accountable member per project. Answers grilling, gates memory promotion, controls approval/overrides, owns false positives. |
| **Delete image** | Owner-only. Removes an upload's whole version lineage — assets, defects, threads, comments, dismissals, blobs. The one place records die with their image; "dismissals are never deleted" holds while the image exists. |

## Agents (ADK)

- **Orchestrator** — fans images out (parallel, uncapped), sequences stages per image.
- **Scanner** — sees original + gridded copy; input: active guidelines + memory rules; output: suspect cells with rule references. Recall-biased.
- **Inspector** — per suspect cell, contact sheet in; confirms/dismisses; assigns category + severity. Precision gate.
- **Annotator** — computes circle from cell coords (Pillow draws; model never draws), runs annotation loop, writes the frame.io comment.
- **Guideline griller** — upload-time interviewer; also handles memory-rule collision grilling.
- Models (verified 2026-08-14): **`gemini-3.7-flash`** (GA 2026-08-13) for Scanner/Inspector/Annotator; **`gemini-3.1-pro`** only at the Pro gate, ≤3 calls/run. There is no `gemini-3.5-pro` — the Pro line went 3 → 3.1. Rule compliance rests on 3.7 Flash being the primary model; 3.1 Pro is GA on Vertex AI, preview-only on the Gemini API.

## Taxonomy

- Categories: `anatomy | physics | artifact | brand | memory` (extensible later).
- Severity: `blocker | warning | nitpick` — set by Inspector, human-adjustable.
- Defect lifecycle: `open → fix_submitted → agent_rechecking → verified_resolved`. Plus `needs_human_review` (annotation loop maxed out). Two Owner-only exits: `dismissed` (false positive) and `override_approved` (rationale logged). Reviewers cannot manually resolve.

## Roles

- **Owner** (exactly one, brand/marketing lead): authoritative grilling respondent; approves memory-rule promotions (anyone proposes); severity overrides; dismiss/override-approve; "Approved" = Owner marked it, full stop.
- **Reviewer** (design, social): comment, reply, submit fixed versions, propose memory rules.
- **Viewer** (sales): read + comment only.

## Entities (Firestore)

- `users` (Google OAuth only)
- `projects` { members[{userId, role: owner|reviewer|viewer}], guidelines[], memoryRules[] } — exactly one owner
- `guidelines` { rawText, clarifications[{question, answer}], updatedAt }
- `runs` { projectId, images[] }
- `slots` { projectId, name } — a creative intent; variants live on the images that point at it
- `brand_profiles` { projectId, entries[{hex, role, tolerance}], proposed[], confirmedBy } — one per project, id derived from it; `entries` is only ever written by a confirmation
- `images` { runId, slotId, variant, gcsPaths{original, gridded, annotated}, version, status } — `slotId: ""` marks pre-slot legacy data, wrapped into a synthetic one-variant slot on read
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
7. Batch runs, concurrency capped at 3 parallel image pipelines (demo/quota reliability).
8. Full real product: Google OAuth, real members/@mentions, in-app notifications only (no email), SSE for updates (no multiplayer cursors).
9. Review screen: threads + reply, add-to-memory (top differentiator), version re-check (core — it is the defect lifecycle). Droppable tail if squeezed: mentions/notifications first, memory-collision grilling second (keep promotion itself).
11. Eval benchmark (week 1): ~30 images with known defects; naive single-prompt Gemini vs pipeline; recall/precision table shown in demo. Proves the workflow beats a wrapper.
12. One accountable Brand Owner per project; resolution flows through agent re-check, never manual resolve (see Roles + lifecycle).
10. Stack: Vue 3 + Vite + Tailwind / FastAPI + Python ADK / Firestore + GCS + Cloud Run.
13. Slot → variants → linear version chain. Grouping is *offered* at upload (default: one slot per file), never a blocking question. Approval is per-variant and completes the slot.
14. Archived is derived from "a sibling is approved", not a stored flag. A slot holds at most one approved variant, so approving another simply moves the approval — reversibility, and no migration, fall out of the derivation.
15. Upload is the only review trigger. Every variant in a batch is reviewed on arrival; a fix re-checks only its own version; archiving and un-archiving never start or cancel a review, because an archived variant's verdicts stay true.
16. Brand palettes are proposed by extraction and only ever enforced by Owner confirmation. An unconfirmed profile raises nothing — not "everything passes", not "everything fails". Silence is the honest answer when nobody has said what the brand colours are.
17. The palette checker is split so each half does what it is good at: ΔE2000 measures (pure arithmetic, cited in the defect comment so the Owner can re-derive it), and the Inspector judges only whether the measured thing is a designed element or scene content. A brand defect therefore never rests on a model's opinion of a colour.
18. Guideline PDFs are rendered to page images, not just text-extracted, with a hard page budget. The colours worth catching are the ones printed as a swatch with no hex beside them, and those are invisible to a text reader.

## Open items

- ~~Confirm allowed Gemini model list~~ — resolved 2026-08-14, see Agents. Residual decision: if the "3.5 or newer" rule is read strictly by version number, drop the Pro gate and run `gemini-3.7-flash` throughout.
- Architecture diagram + 4-min video are submission requirements; schedule time for them.
- `gcloud` CLI not installed on dev machine — needed for Phase 4 deploy.

## Reference (verified 2026-08-14)

- ADK docs now live at **adk.dev** (`google.github.io/adk-docs` 301s there). `google-adk` 2.7.0, Python ≥3.10.
- Primitives: `from google.adk.agents import SequentialAgent, LoopAgent, ParallelAgent, LlmAgent`. `LoopAgent(max_iterations=N)` is the documented bounded-loop path (ADK 2.0 Graph Workflows exist but document no iteration cap — use LoopAgent for the annotation loop).
- Images: `google.genai.types.Part.from_bytes(data=..., mime_type=...)` inside `types.Content(role="user", parts=[...])`. Structured output: `LlmAgent(output_schema=PydanticModel, output_key="...")`. Gotcha: `output_schema` + `tools` together requires Gemini 3.x.
- ADK recommends the Artifacts service for images (`context.save_artifact(...)`), passing artifact *names* to tools rather than raw bytes.
- Deploy: `adk deploy cloud_run --project --region --service_name --app_name --port --artifact_service_uri=gs://<bucket> <AGENT_PATH>`. Sessions/artifacts vanish on instance recycle unless `*_service_uri` flags are set.

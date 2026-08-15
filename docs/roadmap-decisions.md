# Roadmap decisions — the product fight of 2026-08-16

A record of the user-perspective debate (design / social / marketing personas),
what was decided, and what stays open. Supersedes nothing; extends
domain-model.md once each item is implemented (golden rule: behaviour lands in
domain-model.md when it becomes real).

## Where the fight started

The single-asset review screen is the microscope; two of three personas mostly
need the conveyor belt around it. Design thinks in batches of AI-generated
variants; social needs go/no-go and files out; marketing needs provable brand
enforcement and audit. Three chosen workstreams: variant/version model with a
flow-chart history UI, platform context checker, and closing the approved-asset
dead end — plus a brand-guardian analyzer added during the fight.

## Decisions

### 1. The unit of work becomes the slot (agreed direction)

- Today a project holds flat images; the wedge (AI-generation workflows)
  produces N candidates per creative intent. Remodel: **slot → variants →
  linear version chain per variant**.
- Grouping is **explicit at upload** ("new asset" vs "variants of one asset")
  — never inferred from filenames or similarity; inference misgroups and
  poisons the graph.
- **Version chains stay linear.** A competing fix of the same version is not a
  fork — it is another variant. All branching lives at the variant level, so
  the history UI is a strict 2-level tree, not a DAG.
- Approval is per-variant. A slot completes when ≥1 variant is approved;
  siblings become archived (not rejected); multiple approvals allowed (A/B).
- Blast radius acknowledged: delete semantics, pin sequences, list endpoints,
  eval harness. Costliest remodel so far and still right — it must land
  first because export and platform findings hang off it.

### 2. Brand guardian (added mid-fight; reuses the existing lifecycle)

- Today brand checking is prose-only: guideline text handed to a vision model.
  A real brand system is structured facts (palette, logo, typography).
- **Hybrid architecture**: mechanical analyzers measure (palette extraction,
  ΔE in Lab against declared hexes — deterministic, cheap, eval-able); the
  agent judges whether the measurement matters (colour rules bind designed
  elements, not the world inside a photo). Same scanner→inspector shape.
- Colour violations are ordinary defects (BRAND-xx rule refs, normal
  lifecycle) — no new finding type needed.
- **Profile source: freeform PDF in, owner-confirmed profile as the store.**
  Brand books are PDFs with hexes inside swatch graphics — must be read
  visually (Gemini ingests PDF pages natively). The griller extracts a
  *proposed* profile and asks scope questions ("does the palette bind photo
  backgrounds?"); the owner confirms via an editable pre-filled form; the
  enforcer trusts **only confirmed values**. Form alone works for teams with
  no PDF. Provenance chain: book page → extraction → owner confirmation →
  rule fired. Cap extraction cost (bounded pages) by design.
- v1 scope: palette only. Logo presence = stretch (reference assets come free
  from the same PDF). Typography identification: refused pre-deadline.

### 3. Platform context checker (riskiest; last)

- Three sub-checks: thumbnail-scale legibility, crop survival per aspect
  (4:5 / 9:16 / 1:1), platform safe-zones.
- These are findings about an **(image, placement) pair**, not the image —
  they don't fit `open → fix_submitted → verified_resolved` (re-upload doesn't
  fix a crop). Proposed: a separate advisory **placement finding**, closed by
  decision, not re-check. (Open decision #3 below.)
- Platform targets declared per project in Settings.
- v1 scope: mechanical only — text legibility at target size, declared
  critical element inside crop/safe-zone. No taste judgments; cost caps by
  design (image × platform multiplies calls).

### 4. Approved-asset export (cheap; second)

- Approval is currently a dead end. Minimal honest close: **"Download
  approved (N)"** — zip of clean originals (never annotated renders), latest
  approved version per slot winner. Export unit depends on the slot model,
  hence sequenced after it.
- v2 carrot, not now: per-platform pre-validated renditions.

### 5. Sequencing

**Slot/variant remodel → brand palette checker → approved export → platform
checker.** Brand lands early because it reuses the defect lifecycle and
finally proves the brand category end-to-end (an open Gate item). Platform
checker can degrade to a one-platform demo without killing the story.
Deadline: 2026-08-31.

## Facts corrected during the fight

- **Grilling is fully implemented** (agent, API, Settings → Brand guidelines
  UI; live-verified: 5 questions, then 4 different ones on re-grill). It looks
  missing only because the user's project has no guideline uploaded. Demo
  prerequisite: upload a real guideline so the feature is visible.
- Brand category end-to-end proof remains an open gate item; the brand
  guardian is where it lands.

## Open decisions (need the user's call before build)

1. Slot remodel commitment confirmed? (Recommended yes — it *is* the product.)
2. Approval semantics: slot completes on first approval with siblings
   archived, multiple approvals allowed — confirmed?
3. Placement findings as a separate advisory lifecycle vs stretching the
   defect lifecycle. (Recommended: separate.)
4. Platform checker v1 mechanical-only — confirmed?
5. Brand profile via griller extraction + confirmation form (agreed in
   principle 2026-08-16); palette-only v1 — confirmed?

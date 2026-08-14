# AGENTS.md — Codebase Rules

Read `docs/domain-model.md` first. Its vocabulary (Scanner, Inspector, Annotator, suspect cell, contact sheet, Brand Owner, memory rule, re-check…) is the ubiquitous language — use these exact names in code, files, APIs, and UI copy. Never invent synonyms (no "issue" for defect, no "workspace" for project).

## Repo layout

```
backend/
  app/
    domain/    # PURE logic, zero I/O: grid math, lifecycle transitions, taxonomy, mention parsing
    imaging/   # Pillow toolkit: grid overlay, crops, contact sheets, circles (file I/O only)
    agents/    # ADK agents + prompts/ (prompts as .md files next to the agent)
    api/       # FastAPI routers, SSE
    infra/     # Firestore, GCS, auth adapters
    eval/      # benchmark harness: dataset loader, scoring, baseline, runner
  tests/       # mirrors app/ structure
eval/          # eval DATA: images/ (git-ignored), labels.json, output/ — see eval/README.md
frontend/
  src/
    pages/     # route-level components
    components/
    stores/    # Pinia, options syntax
docs/
```

## Frontend rules (Vue 3 + Vite + Tailwind)

- **Options API only.** No `<script setup>`, no Composition API in components. Pinia stores use **options syntax** (`state/getters/actions`), not setup stores.
- SFCs, one component per file, PascalCase filenames.
- Tailwind utility classes in templates; no separate CSS files except `main.css` for tokens. No CSS-in-JS.
- State that crosses components lives in a Pinia store; props/emits otherwise. No event buses.
- API calls only in stores/actions, never in components. One `api.js` module wraps fetch + SSE.
- No component libraries (Vuetify etc.) — Tailwind + hand-rolled. Icons: lucide static SVGs.

## Backend rules (Python 3.12 + FastAPI + ADK)

- **uv** for deps, **ruff** for lint+format, full type hints, **pydantic v2** models for every agent structured output and API schema.
- `app/domain/` is sacred: pure functions, no imports from infra/agents/api, fully unit-tested.
- Agents return pydantic-validated structured output; the model never emits free-form coordinates — cell refs only, `domain/grid.py` converts cells→pixels.
- Prompts live in versioned `.md` files beside their agent, never inline strings.
- Firestore via official SDK directly, no ORM. GCS paths built in one module (`infra/storage.py`).
- All model IDs, caps (3 verify iterations, 3 Pro calls, concurrency 3) in `config.py` — never scattered as literals.

## Testing philosophy — NO MOCK THEATER

Banned: unit tests that mock the thing under test's collaborators just to assert the mock was called. If a test needs 3+ mocks, it's testing the mocks — delete it.

What we write instead, in priority order:

1. **Real unit tests on pure logic** (`domain/`): grid math (cell↔pixel, aspect adaptation, margin clamping at edges), lifecycle transition rules (who may move a defect to which state), taxonomy validation, mention parsing. Real inputs → asserted outputs, zero mocks. This is where exhaustive cases live (all 64 cells, all role×transition combos).
2. **Real imaging tests** (`imaging/`): run Pillow on fixture images, assert measurable properties (grid line positions, crop dimensions, circle center within cell bounds). Golden-file comparisons where pixel-exact matters.
3. **Integration tests** (`api/` + `infra/`): FastAPI TestClient with real requests, real persistence and real signed sessions — no mocked repositories. Storage has two *real* implementations behind one interface (`InMemoryStore`/`FirestoreStore`, `LocalBlobStore`/`GcsBlobStore`); one contract suite runs against both, and picks up Firestore automatically when `FIRESTORE_EMULATOR_HOST` is set. A store that genuinely stores and queries is not a mock.
   - Endless-stream endpoints (SSE) cannot be tested through TestClient — it never signals disconnect, so consuming the response hangs instead of failing. Those get a script against a real uvicorn server (`scripts/check_sse.py`).
4. **Eval harness as the agent test** (`eval/`): agents are NOT unit tested with mocked Gemini — that proves nothing. Agent quality is measured by the benchmark (recall/precision on the labeled eval set, real API calls). A small 5-image smoke eval runs on demand; the full 30-image benchmark runs before any prompt change merges.

pytest for backend; frontend logic worth testing lives in stores/domain helpers → vitest, same no-mock rule (component snapshot tests: skip, low value).

## Git

- `main` stays deployable. Feature branches, small commits, imperative messages.
- Never commit: `.env`, service-account keys, eval images >5MB (GCS/LFS them).

## Golden rules

1. Cell refs, not pixels, at every model boundary.
2. Every defect cites its rule (built-in, guideline, or memory rule id).
3. Dismissals are logged, never deleted.
4. Only the agent moves a defect to `verified_resolved`; only the Owner dismisses or override-approves.
5. If a behavior isn't in `docs/domain-model.md`, it doesn't exist — update the doc first.

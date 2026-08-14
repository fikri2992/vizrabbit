# Visual QA Agent

Multi-agent visual QA for AI-generated e-commerce and social assets. A Google ADK pipeline
scans images against brand and physics guidelines, zooms into suspect regions to confirm what
it found, draws its own annotations and then checks its own work — producing frame.io-style
review threads that a brand owner can act on.

- **Docs**: [domain model](docs/domain-model.md) · [implementation plan](docs/implementation-plan.md) · [codebase rules](AGENTS.md)
- **Stack**: Vue 3 (Options API) + Vite + Tailwind · FastAPI + Google ADK · Firestore + GCS + Cloud Run
- **Models**: `gemini-3.7-flash` (Scanner, Inspector, Annotator) · `gemini-3.1-pro` (final gate, ≤3 calls per run)

## How it works

```
                        ┌─ Scanner ──────── original + 8x8 labelled grid -> suspect cells
Orchestrator (≤3 images ├─ Inspector ────── contact sheet per cell -> confirm / dismiss
in parallel)            ├─ Annotator ────── draw circle -> re-read own output -> adjust (≤3)
                        └─ Pro gate ─────── final verification, ≤3 calls per run
```

Defects never get closed by hand. A reviewer uploads a fixed version and the agent decides:
`open → fix_submitted → agent_rechecking → verified_resolved`. Only the project's Brand Owner
may dismiss a false positive or override-approve with a logged rationale.

## Prerequisites

- Python ≥3.12 and [uv](https://docs.astral.sh/uv/)
- Node ≥20
- A Google Cloud project with the Gemini API (or Vertex AI) enabled
- `gcloud` CLI — only needed for deployment

## Setup

```bash
cp backend/.env.example backend/.env
```

Fill in `backend/.env`:

| Variable | Where it comes from |
| --- | --- |
| `GOOGLE_API_KEY` | [aistudio.google.com](https://aistudio.google.com/apikey) — or set `USE_VERTEX_AI=true` and use `gcloud auth application-default login` |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Cloud Console → APIs & Services → Credentials → OAuth client ID (Web application) |
| `SESSION_SECRET` | Any long random string |
| `GCP_PROJECT`, `GCS_BUCKET` | Your project id and a bucket you own (needed from Phase 2) |

The OAuth client's **Authorised redirect URI** must be exactly `http://localhost:8000/auth/callback`,
and its **Authorised JavaScript origin** `http://localhost:5173`.

## Run

```bash
cd backend && uv sync && uv run uvicorn app.api.main:app --reload --port 8000
```

```bash
cd frontend && npm install && npm run dev
```

Open http://localhost:5173. Vite proxies `/api` and `/auth` to the backend, so the session
cookie works without CORS juggling.

## Verify

```bash
cd backend && uv run pytest && uv run ruff check .
```

```bash
cd frontend && npm test
```

Check the wiring end-to-end — real model call, real image, validated structured output:

```bash
cd backend && uv run python -m app.agents.smoke path/to/image.png
```

## Testing philosophy

No mock theater. Pure domain logic (grid maths, the lifecycle state machine) gets exhaustive
real unit tests; the API gets real requests through `TestClient` with real persistence; and the
agents are not unit tested at all — their quality is measured by the eval harness in `eval/`,
which runs the real pipeline against a labelled defect set and reports recall and precision
against a naive single-prompt baseline. See [AGENTS.md](AGENTS.md).

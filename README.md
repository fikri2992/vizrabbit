# Visual QA Agent

**Live:** https://visual-qa-718560154436.asia-southeast2.run.app

Multi-agent visual QA for AI-generated e-commerce and social assets. A Google ADK pipeline
scans images against brand and physics guidelines, zooms into suspect regions to confirm what
it found, draws its own annotations and then checks its own work — producing frame.io-style
review threads that a brand owner can act on.

- **Docs**: [architecture](docs/architecture.html) · [domain model](docs/domain-model.md) · [implementation plan](docs/implementation-plan.md) · [codebase rules](AGENTS.md)
- **Stack**: Vue 3 (Options API) + Vite + Tailwind · FastAPI + Google ADK · Firestore + GCS + Cloud Run
- **Models**: `gemini-3.7-flash` (Scanner, Inspector, Annotator) · `gemini-3.1-pro-preview` (final gate, ≤3 calls per run)

## How it works

```
                        ┌─ Scanner ──────── original + labelled grid -> suspect cells
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

Everything except the Gemini key is optional for a first run: without `GCP_PROJECT`/`GCS_BUCKET`
the app stores documents in memory and images on disk, and without OAuth you can set
`ALLOW_DEV_LOGIN=true` to sign in by email. That flag is refused automatically whenever any
cloud storage is configured, so it cannot be live on a deployment.

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

Check the live activity stream against a real server:

```bash
cd backend && uv run python -m scripts.check_sse
```

Explore the review screen without a Gemini key, using a seeded project:

```bash
cd backend && ALLOW_DEV_LOGIN=true uv run python -m scripts.seed_demo
```

## Deploy

One Cloud Run service serves both the API and the built Vue app, so there is a single
origin: no CORS, no second deployment, and the session cookie just works.

```bash
gcloud run deploy visual-qa --source . --region asia-southeast2 --allow-unauthenticated --memory 2Gi --cpu 2 --timeout 900
```

Set on the service (`--set-env-vars`): `USE_VERTEX_AI=true`, `VERTEX_LOCATION=global`,
`GCP_PROJECT`, `GCS_BUCKET`, `SESSION_SECRET`, and — once you know the service URL —
`FRONTEND_ORIGIN=<url>` and `OAUTH_REDIRECT_URI=<url>/auth/callback`.

Concurrency is capped and the service runs a single worker on purpose: the SSE event
bus is per-process, so a second worker would split subscribers across processes that
cannot see each other's events.

Because `GCP_PROJECT` and `GCS_BUCKET` are set on a deployment, `ALLOW_DEV_LOGIN` is
refused there automatically — a deployed instance can only be signed into with Google.

## Testing philosophy

No mock theater. Pure domain logic (grid maths, the lifecycle state machine) gets exhaustive
real unit tests; the API gets real requests through `TestClient` with real persistence; and the
agents are not unit tested at all — their quality is measured by the eval harness in `eval/`,
which runs the real pipeline against a labelled defect set and reports recall and precision
against a naive single-prompt baseline. See [AGENTS.md](AGENTS.md).

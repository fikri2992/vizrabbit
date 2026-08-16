import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app.api import auth, projects, review, runs, slots, threads
from app.config import settings

logger = logging.getLogger("app.api")

app = FastAPI(title="Visual QA Agent", version="0.1.0")

app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, same_site="lax")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    """Say what actually broke instead of "Internal Server Error".

    A bare 500 sends whoever is debugging to the server logs, and on Cloud Run
    that is a different window and a minute of scrolling. Members-only routes and
    an internal tool: the exception type and message are worth far more in the
    browser than the small amount they give away. The traceback still goes to the
    log, and only the one-line summary crosses the wire.

    Firestore's missing-index error is the case that earns this: its message
    carries the console URL that creates the index, and swallowing it turns a
    30-second fix into an investigation.
    """
    logger.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {exc}".strip()[:2000]},
    )


app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(runs.router)
app.include_router(slots.router)
app.include_router(review.router)
app.include_router(review.notifications_router)
app.include_router(threads.router)


def mount_frontend(application: FastAPI, dist: "Path | None" = None) -> bool:
    """Serve the built Vue app from this service, if it was bundled into the image.

    One service means one origin: no CORS, no second deployment, and the session
    cookie simply works. Unknown paths fall back to index.html so client-side routes
    survive a refresh — but /api and /auth are left alone so a mistyped API path
    still 404s instead of quietly returning HTML.
    """
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    dist = (dist or Path(__file__).resolve().parents[2] / "static").resolve()
    index = dist / "index.html"
    if not index.exists():
        return False

    if (dist / "assets").is_dir():
        application.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @application.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        # An unmatched API path is a bug, not a client route. Returning index.html
        # with a 200 would hide it and leave the caller parsing HTML as JSON.
        if path.startswith(("api/", "auth/")):
            raise HTTPException(404, "not found")

        candidate = (dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(dist):
            return FileResponse(candidate)
        return FileResponse(index)

    return True


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "models": {"flash": settings.model_flash, "pro": settings.model_pro},
        "caps": {
            "annotation_iterations": settings.max_annotation_iterations,
            "pro_calls_per_run": settings.max_pro_calls_per_run,
            "concurrent_images": settings.max_concurrent_images,
        },
    }


# Registered last: the SPA catch-all must not shadow the API routes above.
mount_frontend(app)

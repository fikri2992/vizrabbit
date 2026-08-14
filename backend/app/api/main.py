from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.api import auth
from app.config import settings

app = FastAPI(title="Visual QA Agent", version="0.1.0")

app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, same_site="lax")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)


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

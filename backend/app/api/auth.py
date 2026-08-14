"""Google OAuth — the only sign-in path (domain-model.md decision 8)."""

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

SESSION_USER_KEY = "user"


@router.get("/login")
async def login(request: Request):
    if not settings.google_client_id:
        raise HTTPException(500, "GOOGLE_CLIENT_ID is not configured")
    return await oauth.google.authorize_redirect(request, settings.oauth_redirect_uri)


@router.get("/callback")
async def callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as exc:
        raise HTTPException(401, f"OAuth failed: {exc.error}") from exc

    claims = token.get("userinfo") or {}
    if not claims.get("email"):
        raise HTTPException(401, "Google returned no email")

    request.session[SESSION_USER_KEY] = {
        "id": claims["sub"],
        "email": claims["email"],
        "name": claims.get("name", ""),
        "picture": claims.get("picture", ""),
    }
    return RedirectResponse(settings.frontend_origin)


@router.get("/me")
async def me(request: Request):
    user = request.session.get(SESSION_USER_KEY)
    if not user:
        raise HTTPException(401, "not signed in")
    return user


@router.post("/logout")
async def logout(request: Request):
    request.session.pop(SESSION_USER_KEY, None)
    return JSONResponse({"ok": True})


def current_user(request: Request) -> dict:
    """FastAPI dependency — 401s unauthenticated callers."""
    user = request.session.get(SESSION_USER_KEY)
    if not user:
        raise HTTPException(401, "not signed in")
    return user

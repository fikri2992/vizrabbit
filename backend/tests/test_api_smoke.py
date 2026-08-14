"""Real requests against the real app via TestClient — no mocked routers.

Firestore-backed routes get emulator-based tests in Phase 2; these cover the
Phase 0 spine: app boots, config is exposed, auth gates correctly.
"""

import base64
import json

import itsdangerous
import pytest
from fastapi.testclient import TestClient

from app.api.auth import SESSION_USER_KEY
from app.api.main import app
from app.config import settings


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _signed_session_cookie(payload: dict) -> str:
    """Mint the cookie exactly as Starlette's SessionMiddleware does."""
    signer = itsdangerous.TimestampSigner(settings.session_secret)
    data = base64.b64encode(json.dumps(payload).encode())
    return signer.sign(data).decode()


def test_health_reports_configured_models_and_caps(client):
    response = client.get("/api/health")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert body["models"]["flash"] == settings.model_flash
    assert body["caps"]["annotation_iterations"] == 3
    assert body["caps"]["pro_calls_per_run"] == 3
    assert body["caps"]["concurrent_images"] == 3


def test_flash_model_satisfies_the_hackathon_rule():
    """'Gemini 3.5 or newer' — the primary model must not silently regress."""
    major, minor = (int(part) for part in settings.model_flash.split("-")[1].split("."))
    assert (major, minor) >= (3, 5), settings.model_flash


def test_me_is_401_when_signed_out(client):
    assert client.get("/auth/me").status_code == 401


def test_me_returns_the_session_user(client):
    """Drive a real signed session cookie through a real request."""
    signed = _signed_session_cookie(
        {SESSION_USER_KEY: {"id": "42", "email": "owner@acme.com", "name": "Owner", "picture": ""}}
    )
    response = client.get("/auth/me", cookies={"session": signed})

    assert response.status_code == 200
    assert response.json()["email"] == "owner@acme.com"


def test_current_user_dependency_rejects_a_tampered_cookie(client):
    assert client.get("/auth/me", cookies={"session": "not-a-real-signature"}).status_code == 401


def test_logout_is_idempotent(client):
    assert client.post("/auth/logout").json() == {"ok": True}
    assert client.post("/auth/logout").json() == {"ok": True}


def test_login_without_credentials_fails_loudly(client, monkeypatch):
    """Misconfiguration must surface as a 500, not a confusing redirect."""
    monkeypatch.setattr(settings, "google_client_id", "")
    response = client.get("/auth/login", follow_redirects=False)
    assert response.status_code == 500


def test_session_key_is_stable():
    """The cookie payload key is a wire contract between requests."""
    assert SESSION_USER_KEY == "user"

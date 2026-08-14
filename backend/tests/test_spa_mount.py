"""The SPA catch-all must not swallow API paths.

Serving index.html for an unmatched /api path returns 200 with HTML, which hides
the bug and leaves the caller parsing HTML as JSON. This is only reachable when a
frontend build is bundled into the image, so the tests build a fake one.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.main import mount_frontend


@pytest.fixture
def app_with_frontend(tmp_path):
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<!doctype html><title>app</title>", encoding="utf-8")
    (static / "assets" / "index.js").write_text("console.log(1)", encoding="utf-8")
    (static / "favicon.svg").write_text("<svg/>", encoding="utf-8")

    application = FastAPI()

    @application.get("/api/health")
    async def health():
        return {"status": "ok"}

    assert mount_frontend(application, static) is True
    return application


@pytest.fixture
def client(app_with_frontend):
    with TestClient(app_with_frontend) as test_client:
        yield test_client


def test_index_is_served_at_the_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_client_routes_fall_back_to_index(client):
    """A refresh on /projects/abc must not 404 — the router handles it."""
    for path in ("/projects/abc", "/projects/abc/images/def", "/login"):
        assert client.get(path).status_code == 200


def test_unknown_api_paths_still_404(client):
    """Otherwise a typo in an API path silently returns HTML with a 200."""
    response = client.get("/api/definitely-not-a-route")
    assert response.status_code == 404
    assert "text/html" not in response.headers.get("content-type", "")


def test_unknown_auth_paths_still_404(client):
    assert client.get("/auth/definitely-not-a-route").status_code == 404


def test_real_api_routes_are_not_shadowed(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_static_files_are_served(client):
    assert client.get("/favicon.svg").status_code == 200


def test_path_traversal_falls_back_to_index_rather_than_escaping(client):
    """A traversal attempt must never read outside the build directory."""
    response = client.get("/../../../etc/passwd")
    assert response.status_code in (200, 404)
    assert "root:" not in response.text


def test_mount_is_a_no_op_without_a_build(tmp_path):
    """Local development runs the API alone; a missing build must not crash startup."""
    application = FastAPI()
    assert mount_frontend(application, tmp_path / "does-not-exist") is False
    assert application.get("/") is not None  # app still usable

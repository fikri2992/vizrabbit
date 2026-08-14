"""The dev-login escape hatch must stay shut unless explicitly and safely opened.

This is an authentication bypass. It is worth having — a fresh clone can be run and
reviewed without OAuth credentials — but only if it cannot possibly be live in a
deployed environment. These tests are the guard on that.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.config import settings


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def local_dev(monkeypatch):
    """A machine with the flag on and no cloud configuration."""
    monkeypatch.setattr(settings, "allow_dev_login", True)
    monkeypatch.setattr(settings, "gcp_project", "")
    monkeypatch.setattr(settings, "gcs_bucket", "")


def test_dev_login_is_off_by_default():
    assert settings.allow_dev_login is False
    assert settings.dev_login_allowed is False


def test_the_route_does_not_exist_when_disabled(client):
    response = client.post("/auth/dev-login", json={"email": "a@b.com"})
    assert response.status_code == 404


def test_the_flag_alone_does_not_open_it_on_a_cloud_deployment(monkeypatch):
    """A stray env var on Cloud Run must not create a sign-in bypass."""
    monkeypatch.setattr(settings, "allow_dev_login", True)
    monkeypatch.setattr(settings, "gcp_project", "my-prod-project")
    monkeypatch.setattr(settings, "gcs_bucket", "")
    assert settings.dev_login_allowed is False

    monkeypatch.setattr(settings, "gcp_project", "")
    monkeypatch.setattr(settings, "gcs_bucket", "my-prod-bucket")
    assert settings.dev_login_allowed is False


def test_a_cloud_deployment_refuses_the_route(client, monkeypatch):
    monkeypatch.setattr(settings, "allow_dev_login", True)
    monkeypatch.setattr(settings, "gcp_project", "my-prod-project")

    assert client.post("/auth/dev-login", json={"email": "a@b.com"}).status_code == 404


def test_it_signs_you_in_locally(client, local_dev):
    response = client.post("/auth/dev-login", json={"email": "Owner@Acme.com", "name": "Ola"})

    assert response.status_code == 200
    assert response.json()["email"] == "owner@acme.com"
    assert response.json()["name"] == "Ola"

    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "owner@acme.com"


def test_the_same_email_is_always_the_same_user(client, local_dev):
    first = client.post("/auth/dev-login", json={"email": "a@b.com"}).json()
    second = client.post("/auth/dev-login", json={"email": "A@B.com"}).json()
    assert first["id"] == second["id"]


def test_it_derives_a_name_when_none_is_given(client, local_dev):
    assert client.post("/auth/dev-login", json={"email": "dee@acme.com"}).json()["name"] == "dee"


@pytest.mark.parametrize("email", ["", "   ", "not-an-email"])
def test_it_rejects_rubbish_emails(client, local_dev, email):
    assert client.post("/auth/dev-login", json={"email": email}).status_code == 400


def test_config_tells_the_sign_in_page_what_works(client, local_dev):
    body = client.get("/auth/config").json()
    assert body["dev_login"] is True
    assert body["google"] is False


def test_config_hides_dev_login_when_disabled(client):
    assert client.get("/auth/config").json()["dev_login"] is False

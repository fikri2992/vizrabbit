"""Settings must reach the Google SDK, which reads os.environ rather than our config.

Without this bridge everything in .env is invisible to google-genai and the client
fails with "No API key was provided" no matter how carefully .env was filled in.
"""

import pytest

from app.config import export_genai_environment, settings


@pytest.fixture
def env():
    return {}


def test_api_key_mode_exports_the_key(monkeypatch, env):
    monkeypatch.setattr(settings, "use_vertex_ai", False)
    monkeypatch.setattr(settings, "google_api_key", "AIza-test-key")

    export_genai_environment(env)

    assert env["GOOGLE_API_KEY"] == "AIza-test-key"
    assert env["GOOGLE_GENAI_USE_VERTEXAI"] == "false"


def test_vertex_mode_exports_project_and_location(monkeypatch, env):
    monkeypatch.setattr(settings, "use_vertex_ai", True)
    monkeypatch.setattr(settings, "gcp_project", "my-project")
    monkeypatch.setattr(settings, "vertex_location", "global")

    export_genai_environment(env)

    assert env["GOOGLE_GENAI_USE_VERTEXAI"] == "true"
    assert env["GOOGLE_CLOUD_PROJECT"] == "my-project"
    assert env["GOOGLE_CLOUD_LOCATION"] == "global"


def test_gemini_region_is_independent_of_where_the_app_is_hosted(monkeypatch, env):
    """These models are only served globally; hosting region must not leak into it."""
    monkeypatch.setattr(settings, "use_vertex_ai", True)
    monkeypatch.setattr(settings, "gcp_project", "my-project")
    monkeypatch.setattr(settings, "gcp_location", "asia-southeast2")
    monkeypatch.setattr(settings, "vertex_location", "global")

    export_genai_environment(env)

    assert env["GOOGLE_CLOUD_LOCATION"] == "global"


def test_vertex_mode_does_not_export_an_api_key(monkeypatch, env):
    """Setting both would leave which backend is used ambiguous."""
    monkeypatch.setattr(settings, "use_vertex_ai", True)
    monkeypatch.setattr(settings, "google_api_key", "AIza-test-key")
    monkeypatch.setattr(settings, "gcp_project", "my-project")

    export_genai_environment(env)

    assert "GOOGLE_API_KEY" not in env


def test_a_real_shell_export_wins_over_the_env_file(monkeypatch, env):
    monkeypatch.setattr(settings, "use_vertex_ai", False)
    monkeypatch.setattr(settings, "google_api_key", "from-dotenv")
    env["GOOGLE_API_KEY"] = "from-shell"

    applied = export_genai_environment(env)

    assert env["GOOGLE_API_KEY"] == "from-shell"
    assert "GOOGLE_API_KEY" not in applied


def test_nothing_is_exported_when_nothing_is_configured(monkeypatch, env):
    monkeypatch.setattr(settings, "use_vertex_ai", False)
    monkeypatch.setattr(settings, "google_api_key", "")

    assert export_genai_environment(env) == {}
    assert env == {}


def test_it_reports_what_it_set(monkeypatch, env):
    monkeypatch.setattr(settings, "use_vertex_ai", False)
    monkeypatch.setattr(settings, "google_api_key", "AIza-test-key")

    applied = export_genai_environment(env)

    assert set(applied) == {"GOOGLE_API_KEY", "GOOGLE_GENAI_USE_VERTEXAI"}

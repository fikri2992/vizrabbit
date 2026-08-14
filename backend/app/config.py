"""Single source of truth for models, caps, and environment config.

AGENTS.md golden rule: no scattered literals. Every cap and model ID lives here.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Models -----------------------------------------------------------
    # Hackathon rule: "Gemini 3.5 or newer". Verified 2026-08-14 against
    # ai.google.dev/gemini-api/docs/models.
    #
    #   gemini-3.7-flash  GA 2026-08-13. Satisfies the rule unambiguously.
    #                     Primary model: Scanner, Inspector, Annotator.
    #   gemini-3.1-pro    Final gate only, <= max_pro_calls_per_run. NOTE: there is
    #                     no gemini-3.5-pro — the Pro line went 3 -> 3.1. 3.1 Pro is
    #                     newer by release date but lower by version number, so the
    #                     rule is satisfied by 3.7 Flash being the primary model.
    #                     Verified 2026-08-15: on Vertex the id that resolves is
    #                     `gemini-3.1-pro-preview`; plain `gemini-3.1-pro` 404s.
    model_flash: str = "gemini-3.7-flash"
    model_pro: str = "gemini-3.1-pro-preview"

    # --- Pipeline caps (domain-model.md decisions 2, 5, 7) ----------------
    grid_cols: int = 8
    grid_rows: int = 8
    zoom_margin_cells: int = 1
    zoom_upscale: int = 2
    max_annotation_iterations: int = 3
    max_pro_calls_per_run: int = 3
    max_concurrent_images: int = 3

    # --- Model call resilience --------------------------------------------
    # Quota limits are routine, not exceptional: one batch fans out into many
    # concurrent calls. Total attempts, including the first.
    max_model_retries: int = 4
    model_retry_base_seconds: float = 2.0
    model_retry_max_seconds: float = 30.0

    # --- Google Cloud -----------------------------------------------------
    #: AI Studio key. Leave empty and set ``use_vertex_ai`` to authenticate through
    #: Vertex AI with Application Default Credentials instead.
    google_api_key: str = ""
    gcp_project: str = ""
    #: Region for Cloud Run, GCS and friends.
    gcp_location: str = "us-central1"
    #: Region for Gemini specifically. These models are served from the *global*
    #: endpoint — regional endpoints 404 for them — so this is deliberately separate
    #: from ``gcp_location``, which follows wherever the rest of the app is hosted.
    vertex_location: str = "global"
    gcs_bucket: str = ""
    firestore_database: str = "(default)"
    use_vertex_ai: bool = False

    # --- Auth -------------------------------------------------------------
    google_client_id: str = ""
    google_client_secret: str = ""
    session_secret: str = "dev-only-insecure-secret"
    oauth_redirect_uri: str = "http://localhost:8000/auth/callback"
    frontend_origin: str = "http://localhost:5173"

    #: Local-only sign-in so the app can be run without configuring OAuth. Refused
    #: whenever the app is pointed at real cloud infrastructure — see
    #: ``dev_login_allowed``. Off unless explicitly switched on.
    allow_dev_login: bool = False

    @property
    def dev_login_allowed(self) -> bool:
        """Two independent conditions, so a stray env var alone cannot open it up:
        the flag must be set *and* the app must not be wired to real GCP storage."""
        return self.allow_dev_login and not self.gcp_project and not self.gcs_bucket

    @property
    def total_cells(self) -> int:
        return self.grid_cols * self.grid_rows


settings = Settings()


def export_genai_environment(target: dict[str, str] | None = None) -> dict[str, str]:
    """Publish our settings as the environment variables google-genai reads.

    pydantic-settings parses ``.env`` into this object, but the Google SDK looks at
    ``os.environ`` directly — so without this, everything configured in ``.env`` is
    invisible to it and the client falls back to "no API key was provided".

    Existing environment variables win: a real shell export should always beat a
    file. Returns the variables that were set, for diagnostics.
    """
    import os

    target = os.environ if target is None else target

    wanted: dict[str, str] = {}
    if settings.use_vertex_ai:
        wanted["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
        if settings.gcp_project:
            wanted["GOOGLE_CLOUD_PROJECT"] = settings.gcp_project
        if settings.vertex_location:
            wanted["GOOGLE_CLOUD_LOCATION"] = settings.vertex_location
    elif settings.google_api_key:
        wanted["GOOGLE_GENAI_USE_VERTEXAI"] = "false"
        wanted["GOOGLE_API_KEY"] = settings.google_api_key

    applied = {key: value for key, value in wanted.items() if not target.get(key)}
    target.update(applied)
    return applied


export_genai_environment()

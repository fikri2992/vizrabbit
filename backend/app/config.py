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
    #                     GA on Vertex AI; preview-only on the Gemini API.
    model_flash: str = "gemini-3.7-flash"
    model_pro: str = "gemini-3.1-pro"

    # --- Pipeline caps (domain-model.md decisions 2, 5, 7) ----------------
    grid_cols: int = 8
    grid_rows: int = 8
    zoom_margin_cells: int = 1
    zoom_upscale: int = 2
    max_annotation_iterations: int = 3
    max_pro_calls_per_run: int = 3
    max_concurrent_images: int = 3

    # --- Google Cloud -----------------------------------------------------
    gcp_project: str = ""
    gcp_location: str = "us-central1"
    gcs_bucket: str = ""
    firestore_database: str = "(default)"
    use_vertex_ai: bool = False

    # --- Auth -------------------------------------------------------------
    google_client_id: str = ""
    google_client_secret: str = ""
    session_secret: str = "dev-only-insecure-secret"
    oauth_redirect_uri: str = "http://localhost:8000/auth/callback"
    frontend_origin: str = "http://localhost:5173"

    @property
    def total_cells(self) -> int:
        return self.grid_cols * self.grid_rows


settings = Settings()

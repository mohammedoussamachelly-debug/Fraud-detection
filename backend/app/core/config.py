from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Backend runtime configuration, loaded from environment variables / .env.

    Phase 1-4 settings: app metadata, the api_service database connection,
    CORS, and the ML artifact path. Phase 5 adds auth settings: the JWT
    signing key/algorithm/expiry for human (analyst/senior_analyst/admin)
    sessions, and a separate static `service_api_key` for the machine
    `service` principal (docs/api-contracts.md §0) used by
    ingestion/scoring jobs — never a user row, never case-decision rights.
    """

    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = (
        "postgresql+psycopg2://api_service:api_service_dev_password@localhost:5432/sentinelai"
    )
    cors_origins: str = "http://localhost:5173"

    # Directory containing `<version_label>/model.joblib` + `metadata.json` +
    # `shap_background.joblib` subfolders, plus `active_version.txt`
    # pointing at which one to serve — written by `ml/training/train.py`.
    # Default assumes the backend runs with `backend/` as cwd (both local
    # dev and the current Docker image); see docs/ml-pipeline.md for the
    # Docker-mount caveat.
    ml_artifacts_dir: str = "../ml/artifacts"

    # Dev-only defaults, same pattern as `database_url` above: every real
    # deployment overrides these via environment variables (see
    # infra/.env.example); nothing here is a production credential.
    jwt_secret_key: str = "dev_jwt_secret_change_me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    service_api_key: str = "dev_service_api_key_change_me"

    # Phase 6: LangGraph investigation agents (app/agents/). `llm_provider`
    # is the only thing that selects real-vs-mock inference — "mock" (the
    # default, and the only mode this environment can actually run, since
    # no API key is configured anywhere here) never calls out to a real
    # model and always labels its output accordingly
    # (app/agents/llm.py::MockLLMProvider). Switching to "anthropic" or
    # "openai" requires the matching *_API_KEY to be set; if it isn't,
    # `get_llm_provider()` raises rather than silently falling back to
    # mock, so a misconfigured deployment fails loudly instead of quietly
    # mislabeling mock output as real.
    llm_provider: str = "mock"
    llm_model_name: str = "mock-deterministic-v1"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    agent_node_timeout_seconds: float = 30.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

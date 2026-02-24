from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- Required ---
    database_url: str
    auth_secret: str
    anthropic_api_key: str

    # --- Sentry (optional) ---
    sentry_dsn: str | None = None
    sentry_environment: str = "development"
    sentry_traces_sample_rate: float = 0.1

    # --- Optional (degrade gracefully) ---
    voyage_api_key: str | None = None
    upstash_redis_rest_url: str | None = None
    upstash_redis_rest_token: str | None = None

    # SMTP
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_pass: str | None = None
    smtp_from: str = "noreply@qanoon.ai"

    # AWS S3
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_s3_bucket: str = "qanoonai-uploads"
    aws_s3_region: str = "ap-south-1"

    # Frontend
    frontend_url: str = "https://qanoon.ai"

    # CORS
    cors_origins: str = "http://localhost:3000"

    # AI Models
    ai_models: dict[str, str] = {
        "analyze": "claude-sonnet-4-20250514",
        "generate": "claude-sonnet-4-20250514",
        "regenerate": "claude-sonnet-4-20250514",
        "chat": "claude-sonnet-4-20250514",
        "rank_precedents": "claude-haiku-4-5-20251001",
        "research": "claude-sonnet-4-20250514",
        "title_generation": "claude-haiku-4-5-20251001",
    }

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()  # type: ignore[call-arg]

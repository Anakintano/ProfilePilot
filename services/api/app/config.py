from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://profilepilot:profilepilot@localhost:5432/profilepilot"
    redis_url: str = "redis://localhost:6379/0"

    auth_mode: str = "dev"  # "dev" | "supabase"
    supabase_url: str = ""
    supabase_jwt_secret: str = ""

    storage_mode: str = "local"  # "local" | "r2"
    storage_dir: str = "/data/uploads"

    cors_origins: str = "http://localhost:3000"

    # Beta quotas (spec section 2, "Persistence and controls")
    max_analyses_per_user_per_day: int = 2
    max_running_jobs_per_user: int = 1
    max_provider_attempts_per_stage: int = 3

    upload_url_ttl_seconds: int = 900
    upload_lifecycle_hours: int = 24

    secret_key: str = "dev-only-insecure-secret-change-in-production"
    max_upload_bytes: int = 20 * 1024 * 1024
    max_pdf_pages: int = 15
    max_image_dimension_px: int = 6000

    # Global (not per-user) budget on real LLM provider calls (Groq/OpenRouter),
    # separate from the per-IP/per-account request throttle in rate_limit.py.
    llm_global_rate_limit_per_minute: int = 20

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()

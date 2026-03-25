"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """App settings. All values can be overridden via environment variables."""

    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres@127.0.0.1:54322/lazy_matcher"
    )
    DATABASE_URL_SYNC: str = (
        "postgresql://postgres:postgres@127.0.0.1:54322/lazy_matcher"
    )

    # Upstash Redis
    UPSTASH_REDIS_URL: str = ""
    UPSTASH_REDIS_TOKEN: str = ""

    # LLM Scoring
    GEMINI_AI_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash-lite"
    OPENROUTER_KEY: str = ""
    OPENROUTER_MODEL: str = "stepfun/step-3.5-flash:free"
    USE_LLM_SCORING: bool = True
    LLM_BATCH_SIZE: int = 5  # Max jobs per LLM call for batch scoring

    # Worker
    WORKER_POLL_INTERVAL: float = 2.0
    WORKER_CONCURRENCY: int = 2
    WORKER_BATCH_SIZE: int = 1

    # API
    API_PREFIX: str = "/api/v1"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # Scoring weights (must sum to 1.0)
    WEIGHT_SKILLS: float = 0.5
    WEIGHT_EXPERIENCE: float = 0.3
    WEIGHT_LOCATION: float = 0.2

    model_config = {
        "env_file": "../.env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()

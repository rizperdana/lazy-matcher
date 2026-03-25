"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """App settings. All values can be overridden via environment variables."""

    DATABASE_URL: str = "postgresql://neondb_owner:npg_UZ8qwH3tdmNo@ep-purple-silence-a1qdlxvr-pooler.ap-southeast-1.aws.neon.tech/neondb?ssl=require"
    DATABASE_URL_SYNC: str = ""

    # Upstash Redis
    UPSTASH_REDIS_REST_URL: str = ""
    UPSTASH_REDIS_REST_TOKEN: str = ""

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

    def model_post_init(self, __context):
        """Ensure DATABASE_URL has asyncpg driver and derive DATABASE_URL_SYNC."""
        # Add asyncpg driver if plain postgresql://
        if (
            self.DATABASE_URL
            and self.DATABASE_URL.startswith("postgresql://")
            and "+asyncpg://" not in self.DATABASE_URL
        ):
            self.DATABASE_URL = self.DATABASE_URL.replace(
                "postgresql://", "postgresql+asyncpg://", 1
            )
        if not self.DATABASE_URL_SYNC:
            if self.DATABASE_URL:
                self.DATABASE_URL_SYNC = self.DATABASE_URL.replace(
                    "postgresql+asyncpg://", "postgresql://"
                )
            else:
                self.DATABASE_URL_SYNC = "postgresql://neondb_owner:npg_UZ8qwH3tdmNo@ep-purple-silence-a1qdlxvr-pooler.ap-southeast-1.aws.neon.tech/neondb?ssl=require"


@lru_cache
def get_settings() -> Settings:
    return Settings()

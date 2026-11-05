"""
AndhaKaanun API — Environment Configuration
Loads and validates all environment variables at startup.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    app_name: str = "AndhaKaanun LegalAI"
    app_version: str = "2.0.0"
    debug: bool = False
    environment: str = "development"  # development | staging | production

    # --- Groq ---
    # Set GROQ_API_KEY, GROQ_MODEL_PRIMARY, GROQ_MODEL_FALLBACK in .env
    # List the models your key can use: GET https://api.groq.com/openai/v1/models
    groq_api_key: str
    groq_model_primary: str = "openai/gpt-oss-120b"  # override via GROQ_MODEL_PRIMARY
    groq_model_fallback: str = "openai/gpt-oss-20b"  # override via GROQ_MODEL_FALLBACK
    groq_timeout_seconds: int = 30
    groq_temperature: float = 0.1
    groq_max_tokens: int = 4096

    # --- Pinecone ---
    pinecone_api_key: str
    pinecone_index: str = "andhakaanun-legal"
    pinecone_env: str = "us-east-1-aws"
    pinecone_timeout_seconds: int = 2

    # --- PostgreSQL ---
    database_url: str
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 3600  # 1 hour

    # --- Rate Limiting ---
    rate_limit_per_hour: int = 10

    # --- CORS ---
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def async_database_url(self) -> str:
        """Ensure the database URL uses asyncpg driver."""
        url = self.database_url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    """Singleton settings instance — cached after first call."""
    return Settings()

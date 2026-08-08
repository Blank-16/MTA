from functools import lru_cache
from typing import Literal

from pydantic import PostgresDsn, RedisDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Literal["development", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # Database
    database_url: PostgresDsn
    postgres_user: str
    postgres_password: str
    postgres_db: str
    db_pool_min_size: int = 2
    db_pool_max_size: int = 10
    db_pool_max_waiting: int = 20
    db_pool_max_idle: float = 300.0

    # Redis
    redis_url: RedisDsn

    # OpenAI
    openai_api_key: str
    fine_tuned_model_id: str
    # Used to tag stored messages — tracks which model version produced a response
    model_version: str = "1.0.0"

    # Auth
    jwt_secret_key: str
    jwt_algorithm: Literal["HS256", "HS384", "HS512", "RS256", "RS384", "RS512"] = "HS256"
    access_token_expire_minutes: int = 60

    # Internal
    internal_api_key: str
    backend_url: str = "http://backend:8000"

    # Observability
    langfuse_public_key: str
    langfuse_secret_key: str
    langfuse_host: str = "https://cloud.langfuse.com"

    # Rate limiting
    rate_limit_requests: int = 20
    rate_limit_window_seconds: int = 600

    # Input constraints
    max_message_chars: int = 2000
    max_input_tokens: int = 400
    max_context_turns: int = 4  # prior conversation turns fed to LLM

    # RAG
    rag_min_similarity: float = 0.72
    rag_top_k: int = 5
    rag_fetch_k: int = 20
    rag_lambda_mult: float = 0.6

    @field_validator("jwt_secret_key")
    @classmethod
    def jwt_secret_must_be_strong(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("jwt_secret_key must be at least 32 characters")
        return v

    @field_validator("rag_min_similarity")
    @classmethod
    def similarity_in_range(cls, v: float) -> float:
        if not 0.0 < v < 1.0:
            raise ValueError("rag_min_similarity must be between 0 and 1 exclusive")
        return v

    @model_validator(mode="after")
    def reject_insecure_defaults_in_production(self) -> "Settings":
        if self.environment == "production":
            insecure = {"changeme", "secret", "password", "test"}
            for field in ("jwt_secret_key", "internal_api_key", "postgres_password"):
                if getattr(self, field).lower() in insecure:
                    raise ValueError(f"{field} uses an insecure default in production")
        return self

    @property
    def psycopg_conninfo(self) -> str:
        # Strip SQLAlchemy driver prefix — psycopg pool uses libpq conninfo
        return str(self.database_url).replace("postgresql+psycopg://", "postgresql://")

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings: Settings = get_settings()

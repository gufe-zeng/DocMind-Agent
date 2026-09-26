from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DocMind-Agent"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    postgres_dsn: str = "postgresql://docmind:docmind@127.0.0.1:5432/docmind"
    redis_url: str = "redis://127.0.0.1:6379/0"

    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_api_key: str | None = None

    llm_base_url: str = "http://127.0.0.1:8000/v1"
    llm_api_key: str = "EMPTY"
    llm_model: str = "Qwen/Qwen3-0.6B"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

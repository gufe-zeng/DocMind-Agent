from functools import lru_cache

from pydantic import Field
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

    upload_dir: str = "/app/data/uploads"
    embedding_cache_dir: str = "/app/data/embed_cache"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    reranker_model: str = "BAAI/bge-reranker-base"
    rag_candidate_k: int = 8
    rag_evidence_k: int = 2
    rag_max_evidence_chars: int = 160
    rag_max_answer_tokens: int = 128
    # Local 1.11GB CPU BGE inference can exceed 90s. The budget covers the
    # full retrieve/rerank/Qwen call; bounded to avoid unbounded requests.
    rag_cpu_timeout_seconds: float = Field(default=420.0, ge=300.0, le=600.0)
    embedding_vector_size: int = 512
    max_upload_bytes: int = 10 * 1024 * 1024
    max_chunks_per_document: int = 1000

    session_ttl_seconds: int = 3600
    session_max_turns: int = 6
    session_lock_seconds: int = 300

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

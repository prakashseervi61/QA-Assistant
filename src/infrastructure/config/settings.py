"""Application configuration settings using Pydantic BaseSettings."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    APP_NAME: str = "Marginalia"

    # LLM Provider
    LLM_PROVIDER: Literal["gemini"] = "gemini"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # Embedding Provider
    EMBEDDING_PROVIDER: Literal["huggingface"] = "huggingface"
    HUGGINGFACE_MODEL: str = "all-MiniLM-L6-v2"

    # Vector Store
    CHROMA_PERSIST_DIR: str = "./data/chroma"
    CHROMA_COLLECTION_NAME: str = "documents"

    # Conversation history storage (SQLite)
    # A local file, so history survives restarts with no database server.
    HISTORY_DB_PATH: str = "./data/history.db"

    # Document Processing
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    MAX_FILE_SIZE_MB: int = 50

    # API
    # Loopback by default: the API holds every ingested document, so binding
    # it to all interfaces would expose the corpus to the whole LAN.
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # Reranker
    # ON by default: reranks the top-k vector hits by relevance to the
    # question, which noticeably improves citation precision. Costs one
    # CrossEncoder scoring pass per query (see RERANKER_MODEL).
    ENABLE_RERANKING: bool = True
    RERANKER_MODEL: str = "BAAI/bge-reranker-v2-m3"

    # Hybrid Search
    ENABLE_HYBRID_SEARCH: bool = False

    # Semantic Chunking
    # ON by default: chunks split on semantic boundaries at ingestion
    # rather than fixed-size windows, so retrieved context stays coherent.
    ENABLE_SEMANTIC_CHUNKING: bool = True
    SEMANTIC_SIMILARITY_THRESHOLD: float = 0.5
    SEMANTIC_MIN_CHUNK_SIZE: int = 100
    SEMANTIC_MAX_CHUNK_SIZE: int = 2000

    # Incremental Ingestion (optional — OFF by default)
    # When enabled, re-uploading a byte-identical file (same SHA-256
    # content hash) returns a "duplicate detected" result instead of
    # re-parsing, re-embedding, and re-storing it.
    ENABLE_INCREMENTAL_INGESTION: bool = False

    # Token Usage Tracking
    ENABLE_USAGE_TRACKING: bool = True

    # Guardrails (ON by default, non-blocking)
    # When ENABLE_GUARDRAILS is true, the RAG pipeline runs input checks
    # (PII + prompt injection) before retrieval and output checks
    # (groundedness + PII leak) after generation. Violations are flagged
    # but never block the pipeline unless GUARDRAIL_BLOCK_VIOLATIONS is
    # true (see src/infrastructure/guardrails/).
    ENABLE_GUARDRAILS: bool = True
    GUARDRAIL_BLOCK_VIOLATIONS: bool = False
    GUARDRAIL_GROUNDEDNESS_THRESHOLD: float = 0.2

    # Prompt Versioning
    # PROMPT_VERSION selects the RAG system-prompt template (see
    # src/infrastructure/llm/prompt_registry.py). Unknown versions fall
    # back to the v1 template with a logged warning.
    PROMPT_VERSION: str = "v1"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Returns:
        Cached Settings instance.
    """
    return Settings()

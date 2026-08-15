"""Application configuration settings using Pydantic BaseSettings."""

from functools import lru_cache
from typing import Literal

from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The bundled development secret. Validation refuses to run with it once
# authentication is enabled, so a misconfigured deployment can never
# ship with the well-known default.
_DEV_SECRET_KEY = "dev-secret-change-me"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    APP_NAME: str = "QA Assistant"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # LLM Provider
    LLM_PROVIDER: Literal["gemini", "openai", "anthropic", "deepseek"] = "gemini"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_MODEL: str = "deepseek-v4-flash"

    # Embedding Provider
    EMBEDDING_PROVIDER: Literal["gemini", "openai", "huggingface"] = "huggingface"
    GEMINI_EMBEDDING_MODEL: str = "text-embedding-004"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    HUGGINGFACE_MODEL: str = "all-MiniLM-L6-v2"

    # Vector Store
    CHROMA_PERSIST_DIR: str = "./data/chroma"
    CHROMA_COLLECTION_NAME: str = "documents"

    # Database (optional)
    # When set, conversations persist in PostgreSQL; otherwise the app keeps
    # using in-memory storage. Requires the optional deps: sqlalchemy, asyncpg.
    DATABASE_URL: str | None = None

    # Document Processing
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    MAX_FILE_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: list[str] = [".pdf", ".docx", ".txt"]

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # Reranker
    ENABLE_RERANKING: bool = False
    RERANKER_MODEL: str = "BAAI/bge-reranker-v2-m3"

    # Hybrid Search
    ENABLE_HYBRID_SEARCH: bool = False

    # Query Rewriting
    ENABLE_QUERY_REWRITING: bool = False
    QUERY_REWRITING_VARIANTS: int = 3

    # Parent-Child Retrieval
    ENABLE_PARENT_CHILD: bool = False
    PARENT_CHUNK_SIZE: int = 2000
    CHILD_CHUNK_SIZE: int = 200
    CHILD_CHUNK_OVERLAP: int = 50

    # Semantic Chunking
    ENABLE_SEMANTIC_CHUNKING: bool = False
    SEMANTIC_SIMILARITY_THRESHOLD: float = 0.5
    SEMANTIC_MIN_CHUNK_SIZE: int = 100
    SEMANTIC_MAX_CHUNK_SIZE: int = 2000

    # Chunk Enrichment
    ENABLE_CHUNK_ENRICHMENT: bool = False
    ENABLE_CHUNK_ENRICHMENT_SUMMARIES: bool = False
    CHUNK_ENRICHMENT_MAX_KEYWORDS: int = 10

    # Incremental Ingestion (optional — OFF by default)
    # When enabled, re-uploading a byte-identical file (same SHA-256
    # content hash) returns a "duplicate detected" result instead of
    # re-parsing, re-embedding, and re-storing it.
    ENABLE_INCREMENTAL_INGESTION: bool = False

    # Token Usage Tracking
    ENABLE_USAGE_TRACKING: bool = True

    # Observability / Tracing
    ENABLE_TRACING: bool = False
    TRACING_ENDPOINT: str = "http://localhost:6006/v1/traces"
    TRACING_SERVICE_NAME: str = "qa-assistant"

    # Authentication (optional — OFF by default)
    # When ENABLE_AUTH is true, every API endpoint except /api/health
    # requires a valid JWT bearer token (see src/infrastructure/auth/).
    ENABLE_AUTH: bool = False
    SECRET_KEY: str = _DEV_SECRET_KEY
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    # API key exchanged for a short-lived JWT via POST /api/auth/token
    # (see src/presentation/api/routes/auth.py). When empty (the
    # default), the token endpoint rejects every request.
    AUTH_API_KEY: str = ""

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str, info: ValidationInfo) -> str:
        """Refuse the bundled dev secret when authentication is enabled."""
        if info.data.get("ENABLE_AUTH") and v == _DEV_SECRET_KEY:
            raise ValueError(
                "SECRET_KEY must be overridden with a long random value "
                "when ENABLE_AUTH is true"
            )
        return v

    # Rate Limiting (optional — OFF by default)
    # When ENABLE_RATE_LIMITING is true, each client IP is limited to
    # RATE_LIMIT_MAX_REQUESTS requests per RATE_LIMIT_WINDOW_SECONDS using
    # an in-memory sliding window (see src/infrastructure/ratelimit/).
    ENABLE_RATE_LIMITING: bool = False
    RATE_LIMIT_MAX_REQUESTS: int = 60
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Guardrails (optional — OFF by default)
    # When ENABLE_GUARDRAILS is true, the RAG pipeline runs input checks
    # (PII + prompt injection) before retrieval and output checks
    # (groundedness + PII leak) after generation. Violations are flagged
    # but never block the pipeline unless GUARDRAIL_BLOCK_VIOLATIONS is
    # true (see src/infrastructure/guardrails/).
    ENABLE_GUARDRAILS: bool = False
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

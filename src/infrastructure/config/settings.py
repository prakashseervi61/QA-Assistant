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
    EMBEDDING_PROVIDER: Literal["gemini", "openai", "huggingface"] = "gemini"
    GEMINI_EMBEDDING_MODEL: str = "text-embedding-004"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    HUGGINGFACE_MODEL: str = "all-MiniLM-L6-v2"

    # Vector Store
    CHROMA_PERSIST_DIR: str = "./data/chroma"
    CHROMA_COLLECTION_NAME: str = "documents"

    # Document Processing
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    MAX_FILE_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: list[str] = [".pdf", ".docx", ".txt"]

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Returns:
        Cached Settings instance.
    """
    return Settings()

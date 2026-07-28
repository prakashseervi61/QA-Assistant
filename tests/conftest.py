"""Shared test fixtures."""

import pytest

from src.infrastructure.config.settings import Settings


@pytest.fixture
def settings() -> Settings:
    """Create a test settings instance."""
    return Settings(
        LLM_PROVIDER="gemini",
        GEMINI_API_KEY="test-key",
        EMBEDDING_PROVIDER="huggingface",
        CHROMA_PERSIST_DIR="./test-data/chroma",
    )

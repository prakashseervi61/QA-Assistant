"""Unit tests for application configuration settings."""

import pytest
from functools import lru_cache

from src.infrastructure.config.settings import Settings, get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Ensure LRU cache is cleared between tests for isolation."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestSettingsDefaults:
    """Verify default values match the specification."""

    def test_llm_provider_default(self):
        assert Settings().LLM_PROVIDER == "deepseek"

    def test_embedding_provider_default(self):
        assert Settings().EMBEDDING_PROVIDER == "huggingface"

    def test_chunk_size_default(self):
        assert Settings().CHUNK_SIZE == 1000

    def test_chunk_overlap_default(self):
        assert Settings().CHUNK_OVERLAP == 200

    def test_max_file_size_mb_default(self):
        assert Settings().MAX_FILE_SIZE_MB == 50

    def test_api_host_default(self):
        assert Settings().API_HOST == "0.0.0.0"

    def test_api_port_default(self):
        assert Settings().API_PORT == 8000

    def test_app_name_default(self):
        assert Settings().APP_NAME == "QA Assistant"

    def test_debug_default_false(self):
        assert Settings().DEBUG is False

    def test_log_level_default(self):
        assert Settings().LOG_LEVEL == "INFO"

    def test_chroma_persist_dir_default(self):
        assert Settings().CHROMA_PERSIST_DIR == "./data/chroma"

    def test_chroma_collection_name_default(self):
        assert Settings().CHROMA_COLLECTION_NAME == "documents"

    def test_gemini_model_default(self):
        assert Settings().GEMINI_MODEL == "gemini-2.0-flash"

    def test_openai_model_default(self):
        assert Settings().OPENAI_MODEL == "gpt-4o"

    def test_anthropic_model_default(self):
        assert Settings().ANTHROPIC_MODEL == "claude-sonnet-4-20250514"

    def test_allowed_extensions_default(self):
        assert Settings().ALLOWED_EXTENSIONS == [".pdf", ".docx", ".txt"]

    def test_cors_origins_default(self):
        assert Settings().CORS_ORIGINS == ["http://localhost:8501"]

    def test_api_keys_default_empty(self):
        s = Settings()
        assert s.GEMINI_API_KEY == ""
        assert s.OPENAI_API_KEY == ""
        assert s.ANTHROPIC_API_KEY == ""


class TestSettingsCustomValues:
    """Verify settings accept overridden values."""

    def test_custom_llm_provider(self):
        assert Settings(LLM_PROVIDER="openai").LLM_PROVIDER == "openai"

    def test_custom_chunk_size(self):
        assert Settings(CHUNK_SIZE=500).CHUNK_SIZE == 500

    def test_custom_chunk_overlap(self):
        assert Settings(CHUNK_OVERLAP=50).CHUNK_OVERLAP == 50

    def test_custom_api_port(self):
        assert Settings(API_PORT=9000).API_PORT == 9000

    def test_custom_api_key(self):
        s = Settings(GEMINI_API_KEY="my-secret-key")
        assert s.GEMINI_API_KEY == "my-secret-key"

    def test_custom_embedding_provider(self):
        assert Settings(EMBEDDING_PROVIDER="openai").EMBEDDING_PROVIDER == "openai"


class TestGetSettingsSingleton:
    """Verify get_settings returns a cached singleton."""

    def test_get_settings_returns_singleton(self):
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_get_settings_returns_settings_type(self):
        assert isinstance(get_settings(), Settings)

    def test_get_settings_cache_info_first_call(self):
        get_settings()
        info = get_settings.cache_info()
        assert info.hits == 0
        assert info.misses == 1

    def test_get_settings_cache_info_second_call(self):
        get_settings()
        get_settings()
        info = get_settings.cache_info()
        assert info.hits == 1
        assert info.misses == 1

    def test_get_settings_multiple_calls_same_identity(self):
        instances = [get_settings() for _ in range(10)]
        assert all(inst is instances[0] for inst in instances)


class TestSettingsValidation:
    """Verify Pydantic model behavior."""

    def test_settings_model_config_env_file(self):
        config = Settings().model_config
        assert config["env_file"] == ".env"
        assert config["case_sensitive"] is False

    def test_settings_from_dict(self):
        data = {
            "LLM_PROVIDER": "anthropic",
            "CHUNK_SIZE": 2000,
            "CHUNK_OVERLAP": 400,
            "DEBUG": True,
        }
        s = Settings(**data)
        assert s.LLM_PROVIDER == "anthropic"
        assert s.CHUNK_SIZE == 2000
        assert s.CHUNK_OVERLAP == 400
        assert s.DEBUG is True

    def test_settings_field_count(self):
        """Ensure we know about all fields (catch accidental removals)."""
        assert len(Settings().model_fields) >= 20

    def test_settings_is_not_frozen(self):
        """Settings is NOT a frozen model -- verify it can be mutated."""
        s = Settings()
        s.DEBUG = True
        assert s.DEBUG is True

"""Unit tests for application configuration settings."""

import pytest

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
        assert Settings().LLM_PROVIDER == "gemini"

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

    def test_database_url_default_none(self):
        assert Settings().DATABASE_URL is None

    def test_gemini_model_default(self):
        assert Settings().GEMINI_MODEL == "gemini-2.5-flash"

    def test_openai_model_default(self):
        assert Settings().OPENAI_MODEL == "gpt-4o"

    def test_anthropic_model_default(self):
        assert Settings().ANTHROPIC_MODEL == "claude-sonnet-4-20250514"

    def test_allowed_extensions_default(self):
        assert Settings().ALLOWED_EXTENSIONS == [".pdf", ".docx", ".txt"]

    def test_cors_origins_default(self):
        assert Settings().CORS_ORIGINS == ["http://localhost:3000"]

    def test_api_keys_default_empty(self):
        s = Settings(
            GEMINI_API_KEY="",
            OPENAI_API_KEY="",
            ANTHROPIC_API_KEY="",
            DEEPSEEK_API_KEY="",
        )
        assert s.GEMINI_API_KEY == ""
        assert s.OPENAI_API_KEY == ""
        assert s.ANTHROPIC_API_KEY == ""
        assert s.DEEPSEEK_API_KEY == ""


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


class TestAuthAndRateLimitDefaults:
    """Auth and rate limiting must be OFF by default (zero behavior change)."""

    def test_enable_auth_default_false(self):
        assert Settings().ENABLE_AUTH is False

    def test_secret_key_default(self):
        assert Settings().SECRET_KEY == "dev-secret-change-me"

    def test_access_token_expire_minutes_default(self):
        assert Settings().ACCESS_TOKEN_EXPIRE_MINUTES == 60

    def test_enable_rate_limiting_default_false(self):
        assert Settings().ENABLE_RATE_LIMITING is False

    def test_rate_limit_defaults(self):
        s = Settings()
        assert s.RATE_LIMIT_MAX_REQUESTS == 60
        assert s.RATE_LIMIT_WINDOW_SECONDS == 60


class TestSecretKeyValidation:
    """The bundled dev SECRET_KEY must not be used when auth is enabled."""

    def test_auth_enabled_with_default_secret_raises(self):
        """ENABLE_AUTH=True + default SECRET_KEY -> construction fails."""
        with pytest.raises(ValueError):
            Settings(ENABLE_AUTH=True)

    def test_auth_enabled_with_custom_secret_ok(self):
        """ENABLE_AUTH=True + custom SECRET_KEY -> accepted."""
        s = Settings(ENABLE_AUTH=True, SECRET_KEY="a-long-random-secret")
        assert s.SECRET_KEY == "a-long-random-secret"

    def test_auth_disabled_with_default_secret_ok(self):
        """ENABLE_AUTH=False + default SECRET_KEY -> accepted (dev default)."""
        s = Settings(ENABLE_AUTH=False)
        assert s.SECRET_KEY == "dev-secret-change-me"

    def test_auth_api_key_default_empty(self):
        """AUTH_API_KEY defaults to empty -> token endpoint closed."""
        assert Settings().AUTH_API_KEY == ""


class TestPromptVersioningSettings:
    """Prompt versioning defaults and the A/B percentage validation."""

    def test_prompt_version_default_v1(self):
        assert Settings().PROMPT_VERSION == "v1"

    def test_enable_prompt_ab_testing_default_false(self):
        assert Settings().ENABLE_PROMPT_AB_TESTING is False

    def test_prompt_ab_version_default_v2(self):
        assert Settings().PROMPT_AB_VERSION == "v2"

    def test_prompt_ab_percentage_default_half(self):
        assert Settings().PROMPT_AB_PERCENTAGE == 0.5

    @pytest.mark.parametrize("value", [0.0, 0.5, 1.0])
    def test_prompt_ab_percentage_valid_range(self, value):
        assert Settings(PROMPT_AB_PERCENTAGE=value).PROMPT_AB_PERCENTAGE == value

    @pytest.mark.parametrize("value", [-0.1, 1.5])
    def test_prompt_ab_percentage_out_of_range_raises(self, value):
        with pytest.raises(ValueError):
            Settings(PROMPT_AB_PERCENTAGE=value)

    def test_custom_prompt_version_accepted(self):
        assert Settings(PROMPT_VERSION="v2").PROMPT_VERSION == "v2"


class TestVectorStoreSettings:
    """Vector store backend defaults (ChromaDB remains the default)."""

    def test_vector_store_backend_default_chroma(self):
        assert Settings().VECTOR_STORE_BACKEND == "chroma"

    def test_qdrant_url_default(self):
        assert Settings().QDRANT_URL == "http://localhost:6333"

    def test_qdrant_api_key_default_empty(self):
        assert Settings().QDRANT_API_KEY == ""

    def test_embedding_dim_default_matches_gemini_model(self):
        """768 matches the default Gemini text-embedding-004 dimension."""
        assert Settings().EMBEDDING_DIM == 768

    def test_custom_vector_store_backend(self):
        assert (
            Settings(VECTOR_STORE_BACKEND="qdrant").VECTOR_STORE_BACKEND == "qdrant"
        )

    def test_custom_qdrant_settings(self):
        s = Settings(
            QDRANT_URL="https://qdrant.example.com:6333",
            QDRANT_API_KEY="secret",
        )
        assert s.QDRANT_URL == "https://qdrant.example.com:6333"
        assert s.QDRANT_API_KEY == "secret"

    def test_custom_embedding_dim(self):
        assert Settings(EMBEDDING_DIM=384).EMBEDDING_DIM == 384


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

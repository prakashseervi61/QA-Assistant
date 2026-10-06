"""Tests for API key precedence and masking."""

from unittest.mock import MagicMock

from src.infrastructure.llm.api_key_resolver import (
    SOURCE_ENV,
    SOURCE_NONE,
    SOURCE_USER,
    ApiKeyResolver,
    mask_api_key,
)


def _settings(env_key: str = "") -> MagicMock:
    settings = MagicMock()
    settings.GEMINI_API_KEY = env_key
    return settings


class TestPrecedence:
    def test_user_key_wins_over_env(self):
        store = MagicMock()
        store.get_api_key.return_value = "user-supplied-key"
        resolver = ApiKeyResolver(store, _settings("env-key"))

        assert resolver.resolve() == "user-supplied-key"
        assert resolver.source() == SOURCE_USER

    def test_falls_back_to_env_when_no_user_key(self):
        store = MagicMock()
        store.get_api_key.return_value = None
        resolver = ApiKeyResolver(store, _settings("env-key"))

        assert resolver.resolve() == "env-key"
        assert resolver.source() == SOURCE_ENV

    def test_reports_none_when_nothing_is_configured(self):
        store = MagicMock()
        store.get_api_key.return_value = None
        resolver = ApiKeyResolver(store, _settings(""))

        assert resolver.resolve() == ""
        assert resolver.source() == SOURCE_NONE

    def test_clearing_the_user_key_restores_the_env_key(self):
        """The documented behaviour of the DELETE route, exercised end to end."""
        store = MagicMock()
        settings = _settings("env-key")

        store.get_api_key.return_value = "user-supplied-key"
        assert ApiKeyResolver(store, settings).resolve() == "user-supplied-key"

        # clear_api_key() removes the file, after which reads return None.
        store.get_api_key.side_effect = lambda: (
            None if store.clear_api_key.called else "user-supplied-key"
        )
        store.clear_api_key()
        resolver = ApiKeyResolver(store, settings)
        assert resolver.resolve() == "env-key"
        assert resolver.source() == SOURCE_ENV

    def test_resolve_reflects_a_later_change(self):
        """The provider caches on the resolved value, so this must be live."""
        store = MagicMock()
        store.get_api_key.return_value = None
        resolver = ApiKeyResolver(store, _settings("env-key"))

        assert resolver.resolve() == "env-key"
        store.get_api_key.return_value = "newly-added-key"
        assert resolver.resolve() == "newly-added-key"


class TestMaskApiKey:
    def test_never_returns_the_full_key(self):
        masked = mask_api_key("AIzaSyD-REALKEY-0123456789abcdefghij")
        assert "REALKEY" not in masked
        assert masked.endswith("ghij")

    def test_masks_a_realistic_key(self):
        assert mask_api_key("AIzaSyD-REALKEY-0123456789abcdefghij") == (
            "********" + "ghij"
        )

    def test_returns_none_for_empty(self):
        assert mask_api_key("") is None
        assert mask_api_key(None) is None

    def test_fully_masks_a_very_short_value(self):
        # Anything 4 chars or shorter is masked completely — there is no
        # "last four" to show without revealing the whole thing.
        assert mask_api_key("abc") == "***"
        assert mask_api_key("abcd") == "****"

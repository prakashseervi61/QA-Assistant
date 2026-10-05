"""Unit tests for the prompt version registry."""

import logging

from src.infrastructure.llm.prompt_registry import (
    DEFAULT_PROMPT_VERSION,
    PROMPT_VERSIONS,
    get_prompt,
)


class TestPromptVersions:
    """PROMPT_VERSIONS content and get_prompt behaviour."""

    def test_v1_is_the_default_template(self):
        """The default version must resolve to the v1 template.

        Replaces a tautological test that compared v1 against
        ``RAGEngine.PROMPT_TEMPLATE`` — an alias that was itself defined as
        ``PROMPT_VERSIONS["v1"]``, so it could never fail. This asserts the
        property that actually matters: v1 is what ships by default.
        """
        assert get_prompt(DEFAULT_PROMPT_VERSION) == PROMPT_VERSIONS["v1"]

    def test_returns_v1_template(self):
        assert get_prompt("v1") == PROMPT_VERSIONS["v1"]

    def test_returns_v2_template(self):
        assert get_prompt("v2") == PROMPT_VERSIONS["v2"]

    def test_v1_and_v2_are_distinct(self):
        assert PROMPT_VERSIONS["v2"] != PROMPT_VERSIONS["v1"]

    def test_all_versions_have_format_placeholders(self):
        for template in PROMPT_VERSIONS.values():
            assert "{context}" in template
            assert "{question}" in template

    def test_v2_is_a_groundedness_focused_variant(self):
        assert "only the provided context" in PROMPT_VERSIONS["v2"]
        assert "does not contain the answer" in PROMPT_VERSIONS["v2"]

    def test_unknown_version_falls_back_to_v1_with_warning(self, caplog):
        with caplog.at_level(
            logging.WARNING, logger="src.infrastructure.llm.prompt_registry"
        ):
            prompt = get_prompt("does-not-exist")
        assert prompt == PROMPT_VERSIONS["v1"]
        assert "does-not-exist" in caplog.text

    def test_fallback_template_still_formats(self):
        prompt = get_prompt("bogus").format(context="ctx", question="q?")
        assert "ctx" in prompt
        assert "q?" in prompt

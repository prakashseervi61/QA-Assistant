"""Unit tests for the prompt version registry."""

import logging

from src.application.services.rag_engine import RAGEngine
from src.infrastructure.llm.prompt_registry import PROMPT_VERSIONS, get_prompt


class TestPromptVersions:
    """PROMPT_VERSIONS content and get_prompt behaviour."""

    def test_v1_is_byte_identical_to_current_engine_template(self):
        """v1 must be the current system prompt verbatim (no behavior change)."""
        assert PROMPT_VERSIONS["v1"] == RAGEngine.PROMPT_TEMPLATE

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

"""Tests for structured output generation."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.dto.structured_answer import StructuredAnswer
from src.infrastructure.llm.structured_output import (
    StructuredOutputError,
    build_structured_prompt,
    generate_structured_answer,
    parse_structured_response,
)


class TestStructuredPrompt:
    def test_prompt_contains_context_and_schema(self):
        """Prompt includes context snippets and asks for JSON."""
        context = [
            {
                "marker": "[1]",
                "content": "RAG stands for retrieval augmented generation.",
            },
            {"marker": "[2]", "content": "Citations map to source chunks."},
        ]
        prompt = build_structured_prompt(
            question="What is RAG?",
            context=context,
        )
        assert "What is RAG?" in prompt
        assert "RAG stands for retrieval" in prompt
        assert "[1]" in prompt
        assert "[2]" in prompt
        assert "json" in prompt.lower()

    def test_prompt_exposes_chunk_id_and_source(self):
        """Regression: the context block must show chunk_id/source so the
        model can reference real chunk IDs instead of fabricating them."""
        context = [
            {
                "marker": "[1]",
                "content": "RAG stands for retrieval augmented generation.",
                "chunk_id": "chunk-uuid-1",
                "source": "paper.pdf",
            },
        ]
        prompt = build_structured_prompt(question="What is RAG?", context=context)
        assert "chunk-uuid-1" in prompt
        assert "paper.pdf" in prompt
        assert "[1] (paper.pdf / chunk-uuid-1)" in prompt

    def test_prompt_requires_known_chunk_ids(self):
        """Prompt instructs the model to only cite shown chunk IDs."""
        prompt = build_structured_prompt(question="q", context=[])
        assert "chunk_id MUST be one of the chunk IDs shown" in prompt


class TestParseStructuredResponse:
    def test_parses_plain_json(self):
        raw = (
            '{"answer": "RAG is retrieval augmented generation.", '
            '"citations": [{"chunk_id": "c1", "source": "doc.pdf", '
            '"excerpt": "RAG stands for..."}], "confidence": 0.9}'
        )
        result = parse_structured_response(raw)
        assert result.answer == "RAG is retrieval augmented generation."
        assert len(result.citations) == 1
        assert result.citations[0].chunk_id == "c1"
        assert result.confidence == pytest.approx(0.9)

    def test_parses_json_from_markdown_fence(self):
        raw = '```json\n{"answer": "x", "citations": [], "confidence": 0.5}\n```'
        result = parse_structured_response(raw)
        assert result.answer == "x"
        assert result.confidence == pytest.approx(0.5)

    def test_raises_on_invalid_json(self):
        with pytest.raises(StructuredOutputError):
            parse_structured_response("this is not json at all")


class TestGenerateStructuredAnswer:
    @pytest.mark.asyncio
    async def test_generate_calls_llm_and_parses(self):
        """End-to-end generation with mocked LLM (via generate_json)."""
        llm = AsyncMock()
        llm.generate_json = AsyncMock(
            return_value=(
                '{"answer": "RAG is X.", '
                '"citations": [{"chunk_id": "c1", "source": "a.pdf", '
                '"excerpt": "RAG is X"}], "confidence": 0.8}'
            )
        )
        llm.generate = AsyncMock(return_value="unused")
        llm.get_model_name = MagicMock(return_value="test-model")

        chunks = [
            MagicMock(
                id="c1",
                content="RAG is X",
                metadata={"filename": "a.pdf"},
                chunk_index=0,
            ),
        ]
        result = await generate_structured_answer(
            llm_provider=llm,
            question="What is RAG?",
            chunks=chunks,
        )
        assert isinstance(result, StructuredAnswer)
        assert result.answer == "RAG is X."
        assert result.citations[0].source == "a.pdf"
        assert result.citations[0].chunk_id == "c1"
        llm.generate_json.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_generate_graceful_on_parse_failure(self):
        """Parse failure raises StructuredOutputError (not silent garbage)."""
        llm = AsyncMock()
        llm.generate_json = AsyncMock(return_value="total garbage response")

        chunks = [MagicMock(id="c1", content="x", metadata={}, chunk_index=0)]
        with pytest.raises(StructuredOutputError):
            await generate_structured_answer(
                llm_provider=llm, question="q", chunks=chunks
            )

    @pytest.mark.asyncio
    async def test_generate_json_failure_falls_back_to_generate(self):
        """If generate_json raises, generate() is used as a fallback."""
        llm = AsyncMock()
        llm.generate_json = AsyncMock(side_effect=RuntimeError("json mode down"))
        llm.generate = AsyncMock(
            return_value=('{"answer": "RAG is X.", "citations": [], "confidence": 0.7}')
        )

        chunks = [MagicMock(id="c1", content="RAG is X", metadata={}, chunk_index=0)]
        result = await generate_structured_answer(
            llm_provider=llm, question="What is RAG?", chunks=chunks
        )
        assert result.answer == "RAG is X."
        llm.generate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_drops_citations_with_unknown_chunk_ids(self):
        """Citations referencing chunks outside the retrieved set are dropped."""
        llm = AsyncMock()
        llm.generate_json = AsyncMock(
            return_value=(
                '{"answer": "RAG is X.", '
                '"citations": ['
                '{"chunk_id": "c1", "source": "a.pdf", "excerpt": "ok"}, '
                '{"chunk_id": "made-up-id", "source": "a.pdf", '
                '"excerpt": "fabricated"}'
                "], "
                '"confidence": 0.8}'
            )
        )

        chunks = [
            MagicMock(
                id="c1",
                content="RAG is X",
                metadata={"filename": "a.pdf"},
                chunk_index=0,
            ),
        ]
        result = await generate_structured_answer(
            llm_provider=llm,
            question="What is RAG?",
            chunks=chunks,
        )
        assert len(result.citations) == 1
        assert result.citations[0].chunk_id == "c1"
        assert result.citations[0].excerpt == "ok"

    @pytest.mark.asyncio
    async def test_falls_back_to_generate_when_generate_json_missing(self):
        """Providers without generate_json still work via generate()."""
        llm = AsyncMock()
        # Simulate a provider that never defines generate_json.
        llm.generate_json = None
        llm.generate = AsyncMock(
            return_value=('{"answer": "RAG is X.", "citations": [], "confidence": 0.7}')
        )

        chunks = [MagicMock(id="c1", content="RAG is X", metadata={}, chunk_index=0)]
        result = await generate_structured_answer(
            llm_provider=llm, question="What is RAG?", chunks=chunks
        )
        assert result.answer == "RAG is X."
        llm.generate.assert_awaited_once()

"""Tests for chunk enrichment (metadata extraction)."""

from src.domain.value_objects.chunk import Chunk


class TestChunkEnricher:
    """Tests for the ChunkEnricher."""

    def test_extracts_title_from_heading(self):
        """A short line without a period at the start is detected as a title."""
        from src.infrastructure.document_processing.chunk_enricher import ChunkEnricher

        enricher = ChunkEnricher()
        text = "Introduction\nThis document covers the basics of machine learning."
        chunk = Chunk(content=text, metadata={}, chunk_index=0)
        enriched = enricher.enrich_chunk(chunk)
        assert "title" in enriched.metadata
        assert enriched.metadata["title"] == "Introduction"

    def test_no_title_when_text_is_plain_paragraph(self):
        """No title extracted when there's no heading-like line."""
        from src.infrastructure.document_processing.chunk_enricher import ChunkEnricher

        enricher = ChunkEnricher()
        text = "This is a plain paragraph without any heading structure at all."
        chunk = Chunk(content=text, metadata={}, chunk_index=0)
        enriched = enricher.enrich_chunk(chunk)
        assert "title" not in enriched.metadata or not enriched.metadata["title"]

    def test_extracts_section_path(self):
        """Numeric section headers form a section path."""
        from src.infrastructure.document_processing.chunk_enricher import ChunkEnricher

        enricher = ChunkEnricher()
        text = "3. Data Models\nThe data model defines entities."
        chunk = Chunk(content=text, metadata={}, chunk_index=0)
        enriched = enricher.enrich_chunk(chunk)
        assert "section_path" in enriched.metadata
        assert "Data Models" in enriched.metadata["section_path"]

    def test_extracts_keywords(self):
        """Keywords include capitalized technical terms, joined as a string."""
        from src.infrastructure.document_processing.chunk_enricher import ChunkEnricher

        enricher = ChunkEnricher(max_keywords=5)
        text = (
            "The RAG pipeline uses ChromaDB for vector search and "
            "LangChain for orchestration."
        )
        chunk = Chunk(content=text, metadata={}, chunk_index=0)
        enriched = enricher.enrich_chunk(chunk)
        assert "keywords" in enriched.metadata
        keywords = enriched.metadata["keywords"]
        # ChromaDB metadata only accepts scalars, so keywords are stored
        # as a comma-joined string (M2).
        assert isinstance(keywords, str)
        assert len(keywords) > 0
        # At least one of the technical terms appears
        assert any(
            k.lower() in {"rag", "chromadb", "langchain", "vector"}
            for k in keywords.split(",")
        )

    def test_keywords_round_trip_scalar_through_chroma_serializer(self):
        """Keywords survive the ChromaDB metadata serializer as a scalar.

        Round-trip: enrichment produces a scalar string, and
        ``ChromaStore._serialize_metadata`` stores it unchanged (no
        str(list) mangling like ``"['RAG', 'ChromaDB']"``).
        """
        from src.infrastructure.document_processing.chunk_enricher import ChunkEnricher
        from src.infrastructure.vector_store.chroma_store import ChromaStore

        enricher = ChunkEnricher(max_keywords=5)
        chunk = Chunk(
            content="The RAG pipeline uses ChromaDB and LangChain together.",
            metadata={},
            chunk_index=0,
        )
        enriched = enricher.enrich_chunk(chunk)
        serialized = ChromaStore._serialize_metadata(enriched)

        stored = serialized["keywords"]
        assert isinstance(stored, str)
        assert "[" not in stored  # not a str(list) artifact
        assert "RAG" in stored
        assert "ChromaDB" in stored
        # And it can be safely filtered on / round-tripped by ChromaDB.
        assert enriched.metadata["keywords"] == stored

    def test_stopwords_not_extracted_as_keywords(self):
        """Capitalized sentence starts (stopwords) are not keywords (N8)."""
        from src.infrastructure.document_processing.chunk_enricher import ChunkEnricher

        enricher = ChunkEnricher(max_keywords=10)
        text = (
            "The RAG pipeline is robust. However, latency matters. "
            "This system uses ChromaDB. These vectors are dense."
        )
        chunk = Chunk(content=text, metadata={}, chunk_index=0)
        enriched = enricher.enrich_chunk(chunk)
        keywords = enriched.metadata["keywords"].split(",")
        assert "The" not in keywords
        assert "However" not in keywords
        assert "This" not in keywords
        assert "These" not in keywords
        # Real technical terms still surface (case-insensitive — the
        # frequency fallback may return them lowercased)
        assert any(k.lower() in {"rag", "chromadb"} for k in keywords)

    def test_enrich_preserves_original_metadata(self):
        """Original metadata fields survive enrichment."""
        from src.infrastructure.document_processing.chunk_enricher import ChunkEnricher

        enricher = ChunkEnricher()
        chunk = Chunk(
            content="1. Overview\nThis is an overview.",
            metadata={"filename": "doc.pdf", "document_id": "abc"},
            chunk_index=3,
        )
        enriched = enricher.enrich_chunk(chunk)
        assert enriched.metadata["filename"] == "doc.pdf"
        assert enriched.metadata["document_id"] == "abc"
        assert enriched.chunk_index == 3

    def test_enrich_batch(self):
        """enrich_batch processes multiple chunks."""
        from src.infrastructure.document_processing.chunk_enricher import ChunkEnricher

        enricher = ChunkEnricher()
        chunks = [
            Chunk(
                content="1. Intro\nFirst section content.",
                metadata={},
                chunk_index=0,
            ),
            Chunk(
                content="2. Details\nSecond section content.",
                metadata={},
                chunk_index=1,
            ),
        ]
        enriched = enricher.enrich_batch(chunks)
        assert len(enriched) == 2
        for e in enriched:
            assert "section_path" in e.metadata

    def test_summary_generation_when_llm_available(self):
        """Summary is generated when an LLM provider is passed."""
        from src.infrastructure.document_processing.chunk_enricher import ChunkEnricher

        class FakeLLM:
            async def generate(self, prompt, **kwargs):
                return "This is a summary of the chunk."

        import asyncio

        async def run():
            enricher = ChunkEnricher(llm_provider=FakeLLM(), generate_summaries=True)
            chunk = Chunk(content="Some content here.", metadata={}, chunk_index=0)
            enriched = await enricher.enrich_chunk_async(chunk)
            assert enriched.metadata.get("summary") == "This is a summary of the chunk."

        asyncio.run(run())

    def test_no_summary_when_disabled(self):
        """No summary generated when generate_summaries is False."""
        from src.infrastructure.document_processing.chunk_enricher import ChunkEnricher

        enricher = ChunkEnricher(generate_summaries=False)
        chunk = Chunk(content="Some content.", metadata={}, chunk_index=0)
        enriched = enricher.enrich_chunk(chunk)
        assert "summary" not in enriched.metadata

    def test_empty_content(self):
        """Empty content produces no metadata additions."""
        from src.infrastructure.document_processing.chunk_enricher import ChunkEnricher

        enricher = ChunkEnricher()
        chunk = Chunk(content="", metadata={}, chunk_index=0)
        enriched = enricher.enrich_chunk(chunk)
        assert enriched.metadata.get("keywords") == ""

    def test_title_not_mistaken_for_numbered_list_item(self):
        """Numbered list items are not titles."""
        from src.infrastructure.document_processing.chunk_enricher import ChunkEnricher

        enricher = ChunkEnricher()
        text = "1. First item in a list\n2. Second item in a list\nSome body text."
        chunk = Chunk(content=text, metadata={}, chunk_index=0)
        enriched = enricher.enrich_chunk(chunk)
        title = enriched.metadata.get("title")
        assert title != "1. First item in a list"

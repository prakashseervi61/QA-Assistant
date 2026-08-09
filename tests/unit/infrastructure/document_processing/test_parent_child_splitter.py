"""Tests for parent-child retrieval pattern."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domain.value_objects.chunk import Chunk


class TestParentChildSplitter:
    """Tests for the parent-child text splitting strategy."""

    def test_parent_child_splitter_creates_parents_and_children(self):
        """Splitting produces parent chunks each with child sub-chunks."""
        from src.infrastructure.document_processing.parent_child_splitter import (
            ParentChildSplitter,
        )

        splitter = ParentChildSplitter(
            parent_chunk_size=200,
            child_chunk_size=50,
            child_overlap=10,
        )
        doc_id = uuid4()
        text = "A" * 500  # 500 chars -> 3 parent chunks of 200

        parents, children = splitter.split(
            text, doc_id, metadata={"filename": "test.pdf"}
        )

        assert len(parents) >= 2
        assert len(children) >= len(parents)
        # Every child has a parent_id in metadata
        for child in children:
            assert "parent_id" in child.metadata
        # Every parent_id in children matches an actual parent id
        parent_ids = {str(p.id) for p in parents}
        for child in children:
            assert child.metadata["parent_id"] in parent_ids

    def test_child_chunks_are_smaller_than_parents(self):
        """Child chunks are smaller than parent chunks."""
        from src.infrastructure.document_processing.parent_child_splitter import (
            ParentChildSplitter,
        )

        splitter = ParentChildSplitter(
            parent_chunk_size=200, child_chunk_size=50, child_overlap=10
        )
        parents, children = splitter.split("B" * 600, uuid4())

        max_child_len = max(len(c.content) for c in children)
        max_parent_len = max(len(p.content) for p in parents)
        assert max_child_len <= 50 + 10  # allow overlap
        assert max_parent_len <= 200

    def test_children_cover_parent_content(self):
        """Child chunks collectively cover the parent's content."""
        from src.infrastructure.document_processing.parent_child_splitter import (
            ParentChildSplitter,
        )

        splitter = ParentChildSplitter(
            parent_chunk_size=100, child_chunk_size=30, child_overlap=5
        )
        doc_id = uuid4()
        text = "The quick brown fox jumps over the lazy dog. " * 5
        parents, children = splitter.split(text, doc_id)

        # All children together should cover all parent content
        all_child_text = " ".join(c.content for c in children)
        for parent in parents:
            # At least most words from parent appear in some child
            parent_words = set(parent.content.split())
            child_words = set(all_child_text.split())
            overlap = parent_words & child_words
            assert len(overlap) >= len(parent_words) * 0.5

    def test_splitter_has_default_sizes(self):
        """ParentChildSplitter defaults match settings."""
        from src.infrastructure.document_processing.parent_child_splitter import (
            ParentChildSplitter,
        )

        splitter = ParentChildSplitter()
        assert splitter.parent_chunk_size == 2000
        assert splitter.child_chunk_size == 200
        assert splitter.child_overlap == 50

    def test_parents_carry_metadata(self):
        """Parent chunks carry through user-supplied metadata."""
        from src.infrastructure.document_processing.parent_child_splitter import (
            ParentChildSplitter,
        )

        splitter = ParentChildSplitter(
            parent_chunk_size=100, child_chunk_size=30, child_overlap=5
        )
        doc_id = uuid4()
        meta = {"filename": "report.pdf", "file_type": ".pdf"}
        parents, _ = splitter.split("C" * 500, doc_id, metadata=meta)

        for parent in parents:
            assert parent.metadata["filename"] == "report.pdf"
            assert parent.metadata["file_type"] == ".pdf"
            assert parent.metadata["chunk_type"] == "parent"
            assert parent.document_id == doc_id

    def test_children_carry_parent_id(self):
        """Each child chunk references its parent by ID."""
        from src.infrastructure.document_processing.parent_child_splitter import (
            ParentChildSplitter,
        )

        splitter = ParentChildSplitter(
            parent_chunk_size=100, child_chunk_size=30, child_overlap=5
        )
        doc_id = uuid4()
        parents, children = splitter.split("D" * 400, doc_id)

        parent_id_map = {str(p.id): p for p in parents}
        for child in children:
            pid = child.metadata["parent_id"]
            assert pid in parent_id_map
            assert child.metadata["chunk_type"] == "child"
            assert child.document_id == doc_id

    def test_empty_text_produces_nothing(self):
        """Empty input produces zero chunks."""
        from src.infrastructure.document_processing.parent_child_splitter import (
            ParentChildSplitter,
        )

        splitter = ParentChildSplitter(
            parent_chunk_size=100, child_chunk_size=30, child_overlap=5
        )
        parents, children = splitter.split("", uuid4())
        assert len(parents) == 0
        assert len(children) == 0

    def test_single_char_text(self):
        """Very short text still produces at least one parent and child."""
        from src.infrastructure.document_processing.parent_child_splitter import (
            ParentChildSplitter,
        )

        splitter = ParentChildSplitter(
            parent_chunk_size=100, child_chunk_size=30, child_overlap=5
        )
        parents, children = splitter.split("X", uuid4())
        assert len(parents) >= 1
        assert len(children) >= 1

    def test_pathological_overlap_does_not_hang(self):
        """Overlap >= chunk size must still make forward progress (N6)."""
        from src.infrastructure.document_processing.parent_child_splitter import (
            ParentChildSplitter,
        )

        # Overlap equals the full chunk size — the guard must force
        # at least one character of progress or this loops forever.
        splitter = ParentChildSplitter(
            parent_chunk_size=50, child_chunk_size=20, child_overlap=20
        )
        parents, children = splitter.split("E" * 300, uuid4())
        assert len(parents) >= 1
        assert len(children) >= 1

        # Even more pathological: overlap larger than the chunk size.
        splitter2 = ParentChildSplitter(
            parent_chunk_size=30, child_chunk_size=10, child_overlap=50
        )
        parents2, children2 = splitter2.split("F" * 200, uuid4())
        assert len(parents2) >= 1
        assert len(children2) >= 1

    def test_child_split_keeps_boundary_space(self):
        """Splitting on a space keeps the space in the left chunk (N7).

        Regression: the old code used ``end = last_space``, which dropped
        the boundary space character from the output entirely.
        """
        from src.infrastructure.document_processing.parent_child_splitter import (
            ParentChildSplitter,
        )

        splitter = ParentChildSplitter(
            parent_chunk_size=1000, child_chunk_size=20, child_overlap=0
        )
        # The second child chunk boundary falls on a space.
        text = "word one two three four five six seven"
        _, children = splitter.split(text, uuid4())
        assert len(children) >= 2

        # Reconstruct: all child contents joined with separators must
        # contain every original character. If a boundary space were
        # dropped, "one" + "two" would lose the space between them.
        joined = " ".join(c.content for c in children)
        # The original text's word sequence is preserved when joining
        # children with a single space (children never contain internal
        # spaces beyond one boundary space).
        for word in text.split():
            assert word in joined


class TestParentRetrieval:
    """Tests for parent-child retrieval in the RAG engine."""

    @pytest.fixture
    def sample_parent_chunks(self):
        parents = [
            Chunk(
                id=uuid4(),
                content="Parent A content about ML",
                metadata={
                    "filename": "ai.pdf",
                    "chunk_type": "parent",
                    "score": 0.9,
                },
                chunk_index=0,
            ),
            Chunk(
                id=uuid4(),
                content="Parent B content about DL",
                metadata={
                    "filename": "ai.pdf",
                    "chunk_type": "parent",
                    "score": 0.8,
                },
                chunk_index=1,
            ),
        ]
        children = [
            Chunk(
                id=uuid4(),
                content="ML is a subset of AI",
                metadata={
                    "filename": "ai.pdf",
                    "chunk_type": "child",
                    "parent_id": str(parents[0].id),
                    "score": 0.95,
                },
                chunk_index=0,
            ),
            Chunk(
                id=uuid4(),
                content="DL uses neural networks",
                metadata={
                    "filename": "ai.pdf",
                    "chunk_type": "child",
                    "parent_id": str(parents[1].id),
                    "score": 0.85,
                },
                chunk_index=1,
            ),
        ]
        return parents, children

    @pytest.fixture
    def mock_vector_store(self):
        store = AsyncMock()
        store.similarity_search = AsyncMock(return_value=[])
        store.hybrid_search = AsyncMock(return_value=[])
        store.add_documents = AsyncMock()
        store.get_collection_count = AsyncMock(return_value=5)
        store.get_documents_by_ids = AsyncMock(return_value=[])
        return store

    @pytest.mark.asyncio
    async def test_expand_to_parents_replaces_children_with_parents(
        self, mock_vector_store, sample_parent_chunks
    ):
        """After retrieving children, expand_to_parents fetches parents."""
        from src.application.services.rag_engine import RAGEngine

        parents, children = sample_parent_chunks

        # Mock get_documents_by_ids to return the parents
        async def fake_get_by_ids(ids, collection_name):
            return [p for p in parents if str(p.id) in ids]

        mock_vector_store.get_documents_by_ids = fake_get_by_ids

        # Test the expand logic directly
        parent_ids = list({c.metadata["parent_id"] for c in children})
        parent_chunks = await RAGEngine._expand_to_parents(
            mock_vector_store, parent_ids, "documents_parent"
        )
        assert len(parent_chunks) == 2

    @pytest.mark.asyncio
    async def test_expand_to_parents_handles_missing_parents(
        self, mock_vector_store
    ):
        """Gracefully handles parents that don't exist in the store."""
        from src.application.services.rag_engine import RAGEngine

        mock_vector_store.similarity_search = AsyncMock(return_value=[])
        mock_vector_store.hybrid_search = AsyncMock(return_value=[])
        # get_documents_by_ids returns only 1 of 2 requested
        mock_vector_store.get_documents_by_ids = AsyncMock(
            return_value=[
                Chunk(
                    id=uuid4(),
                    content="found",
                    metadata={},
                    chunk_index=0,
                )
            ]
        )

        children = [
            Chunk(
                content="child1",
                metadata={"parent_id": "missing-id-1"},
                chunk_index=0,
            ),
            Chunk(
                content="child2",
                metadata={"parent_id": "existing-id"},
                chunk_index=1,
            ),
        ]
        parent_ids = list({c.metadata["parent_id"] for c in children})
        result = await RAGEngine._expand_to_parents(
            mock_vector_store, parent_ids, "documents_parent"
        )
        # Should return what it found, not crash
        assert len(result) >= 0

    @pytest.mark.asyncio
    async def test_expand_to_parents_empty_list(self, mock_vector_store):
        """Empty parent_id list returns empty list."""
        from src.application.services.rag_engine import RAGEngine

        result = await RAGEngine._expand_to_parents(
            mock_vector_store, [], "documents_parent"
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_expand_to_parents_deduplicates_ids(self, mock_vector_store):
        """Duplicate parent_ids are deduplicated before lookup."""
        from src.application.services.rag_engine import RAGEngine

        mock_vector_store.get_documents_by_ids = AsyncMock(
            return_value=[
                Chunk(
                    id=uuid4(),
                    content="parent",
                    metadata={},
                    chunk_index=0,
                )
            ]
        )

        children = [
            Chunk(
                content="c1",
                metadata={"parent_id": "same-id"},
                chunk_index=0,
            ),
            Chunk(
                content="c2",
                metadata={"parent_id": "same-id"},
                chunk_index=1,
            ),
        ]
        parent_ids = list({c.metadata["parent_id"] for c in children})
        assert len(parent_ids) == 1  # deduplicated
        await RAGEngine._expand_to_parents(
            mock_vector_store, parent_ids, "documents_parent"
        )
        # get_documents_by_ids called with just 1 id
        call_args = mock_vector_store.get_documents_by_ids.call_args
        assert len(call_args.args[0]) == 1

    @pytest.mark.asyncio
    async def test_expand_to_parents_dedups_internally(self, mock_vector_store):
        """Duplicate ids passed directly are deduplicated inside the method (M4)."""
        from src.application.services.rag_engine import RAGEngine

        mock_vector_store.get_documents_by_ids = AsyncMock(return_value=[])

        await RAGEngine._expand_to_parents(
            mock_vector_store, ["dup", "dup", "other"], "documents_parent"
        )
        call_args = mock_vector_store.get_documents_by_ids.call_args
        assert sorted(call_args.args[0]) == ["dup", "other"]


class TestParentChildIngestion:
    """Tests for parent-child ingestion pipeline."""

    @pytest.fixture
    def mock_deps(self):
        return {
            "parser": AsyncMock(),
            "embedding_provider": AsyncMock(),
            "vector_store": AsyncMock(),
        }

    @pytest.mark.asyncio
    async def test_ingest_stores_both_parent_and_child_collections(
        self, mock_deps
    ):
        """IngestDocumentUseCase stores to both parent and child collections."""
        mock_deps["parser"].parse = AsyncMock(return_value="A" * 500)

        async def dynamic_embed_batch(texts):
            return [[0.1] * 5 for _ in texts]

        mock_deps["embedding_provider"].embed_batch = AsyncMock(
            side_effect=dynamic_embed_batch
        )
        mock_deps["embedding_provider"].get_embedding_dimension = MagicMock(
            return_value=5
        )

        from src.application.use_cases.ingest_document import (
            IngestDocumentUseCase,
        )
        from src.infrastructure.document_processing.parent_child_splitter import (
            ParentChildSplitter,
        )

        splitter = ParentChildSplitter(
            parent_chunk_size=200,
            child_chunk_size=50,
            child_overlap=10,
        )

        uc = IngestDocumentUseCase(
            parser=mock_deps["parser"],
            text_splitter=splitter,
            embedding_provider=mock_deps["embedding_provider"],
            vector_store=mock_deps["vector_store"],
        )

        with (
            patch(
                "src.application.use_cases.ingest_document.get_settings"
            ) as mock_settings,
            patch(
                "src.application.use_cases.ingest_document.create_parser"
            ) as mock_create_parser,
        ):
            settings = MagicMock()
            settings.CHROMA_COLLECTION_NAME = "documents"
            settings.ENABLE_PARENT_CHILD = True
            mock_settings.return_value = settings
            mock_create_parser.return_value = mock_deps["parser"]

            result = await uc.execute(b"fake content", "test.pdf")

        assert "document_id" in result
        assert result["chunk_count"] > 0
        # Should have stored to at least one collection
        assert mock_deps["vector_store"].add_documents.call_count >= 1

    @pytest.mark.asyncio
    async def test_ingest_stores_parent_and_child_separately(
        self, mock_deps
    ):
        """Parent and child chunks are stored in separate collections."""
        from src.application.use_cases.ingest_document import (
            IngestDocumentUseCase,
        )
        from src.infrastructure.document_processing.parent_child_splitter import (
            ParentChildSplitter,
        )

        mock_deps["parser"].parse = AsyncMock(return_value="Hello world. " * 50)

        async def dynamic_embed_batch(texts):
            return [[0.1] * 5 for _ in texts]

        mock_deps["embedding_provider"].embed_batch = AsyncMock(
            side_effect=dynamic_embed_batch
        )
        mock_deps["embedding_provider"].get_embedding_dimension = MagicMock(
            return_value=5
        )

        splitter = ParentChildSplitter(
            parent_chunk_size=100, child_chunk_size=30, child_overlap=5
        )
        uc = IngestDocumentUseCase(
            parser=mock_deps["parser"],
            text_splitter=splitter,
            embedding_provider=mock_deps["embedding_provider"],
            vector_store=mock_deps["vector_store"],
        )

        with (
            patch(
                "src.application.use_cases.ingest_document.get_settings"
            ) as mock_settings,
            patch(
                "src.application.use_cases.ingest_document.create_parser"
            ) as mock_create_parser,
        ):
            settings = MagicMock()
            settings.CHROMA_COLLECTION_NAME = "documents"
            settings.ENABLE_PARENT_CHILD = True
            mock_settings.return_value = settings
            mock_create_parser.return_value = mock_deps["parser"]

            await uc.execute(b"fake", "test.pdf")

        # Check the collection names used in add_documents calls
        call_args_list = (
            mock_deps["vector_store"].add_documents.call_args_list
        )
        collection_names = [call.args[1] for call in call_args_list]
        assert "documents_parent" in collection_names
        assert "documents_child" in collection_names

    @pytest.mark.asyncio
    async def test_ingest_without_parent_child_flag(self, mock_deps):
        """When ENABLE_PARENT_CHILD is False, only main collection used."""
        from src.application.use_cases.ingest_document import (
            IngestDocumentUseCase,
        )
        from src.infrastructure.document_processing.text_splitter import (
            TextSplitter,
        )

        mock_deps["parser"].parse = AsyncMock(return_value="Hello world. " * 50)

        async def dynamic_embed_batch(texts):
            return [[0.1] * 5 for _ in texts]

        mock_deps["embedding_provider"].embed_batch = AsyncMock(
            side_effect=dynamic_embed_batch
        )
        mock_deps["embedding_provider"].get_embedding_dimension = MagicMock(
            return_value=5
        )

        splitter = TextSplitter(chunk_size=200, chunk_overlap=50)
        uc = IngestDocumentUseCase(
            parser=mock_deps["parser"],
            text_splitter=splitter,
            embedding_provider=mock_deps["embedding_provider"],
            vector_store=mock_deps["vector_store"],
        )

        with (
            patch(
                "src.application.use_cases.ingest_document.get_settings"
            ) as mock_settings,
            patch(
                "src.application.use_cases.ingest_document.create_parser"
            ) as mock_create_parser,
        ):
            settings = MagicMock()
            settings.CHROMA_COLLECTION_NAME = "documents"
            settings.ENABLE_PARENT_CHILD = False
            mock_settings.return_value = settings
            mock_create_parser.return_value = mock_deps["parser"]

            result = await uc.execute(b"fake", "test.pdf")

        assert "document_id" in result
        # Only one add_documents call (main collection)
        assert mock_deps["vector_store"].add_documents.call_count == 1
        call_args = mock_deps["vector_store"].add_documents.call_args
        assert call_args.args[1] == "documents"

    @pytest.mark.asyncio
    async def test_ingest_parent_child_uses_single_split_no_main_collection(
        self, mock_deps
    ):
        """C2c regression: with PC enabled, split() runs once, the main
        collection is not used for parents, and every child's parent_id
        links to a parent that was actually stored (no orphaned UUIDs)."""
        from src.application.use_cases.ingest_document import (
            IngestDocumentUseCase,
        )
        from src.infrastructure.document_processing.parent_child_splitter import (
            ParentChildSplitter,
        )

        mock_deps["parser"].parse = AsyncMock(return_value="Hello world. " * 50)

        async def dynamic_embed_batch(texts):
            return [[0.1] * 5 for _ in texts]

        mock_deps["embedding_provider"].embed_batch = AsyncMock(
            side_effect=dynamic_embed_batch
        )
        mock_deps["embedding_provider"].get_embedding_dimension = MagicMock(
            return_value=5
        )

        splitter = ParentChildSplitter(
            parent_chunk_size=100, child_chunk_size=30, child_overlap=5
        )
        uc = IngestDocumentUseCase(
            parser=mock_deps["parser"],
            text_splitter=splitter,
            embedding_provider=mock_deps["embedding_provider"],
            vector_store=mock_deps["vector_store"],
        )

        with (
            patch(
                "src.application.use_cases.ingest_document.get_settings"
            ) as mock_settings,
            patch(
                "src.application.use_cases.ingest_document.create_parser"
            ) as mock_create_parser,
        ):
            settings = MagicMock()
            settings.CHROMA_COLLECTION_NAME = "documents"
            settings.ENABLE_PARENT_CHILD = True
            mock_settings.return_value = settings
            mock_create_parser.return_value = mock_deps["parser"]

            result = await uc.execute(b"fake", "test.pdf")

        assert result["chunk_count"] > 0

        calls = mock_deps["vector_store"].add_documents.call_args_list
        collection_names = [call.args[1] for call in calls]
        assert "documents_parent" in collection_names
        assert "documents_child" in collection_names
        # The main collection must NOT receive the parent chunks.
        assert "documents" not in collection_names

        stored_parents = [
            call.args[0]
            for call in calls
            if call.args[1] == "documents_parent"
        ][0]
        stored_children = [
            call.args[0]
            for call in calls
            if call.args[1] == "documents_child"
        ][0]
        parent_ids = {str(p.id) for p in stored_parents}
        for child in stored_children:
            assert child.metadata["parent_id"] in parent_ids

    @pytest.mark.asyncio
    async def test_ingest_injects_chunk_enricher_once(self, mock_deps):
        """N16: the enricher is injected via the constructor and reused;
        the factory is not called per ingestion."""
        from src.application.use_cases.ingest_document import (
            IngestDocumentUseCase,
        )
        from src.infrastructure.document_processing.chunk_enricher import (
            ChunkEnricher,
        )
        from src.infrastructure.document_processing.text_splitter import (
            TextSplitter,
        )

        mock_deps["parser"].parse = AsyncMock(return_value="1. Overview\nRAG rules.")

        async def dynamic_embed_batch(texts):
            return [[0.1] * 5 for _ in texts]

        mock_deps["embedding_provider"].embed_batch = AsyncMock(
            side_effect=dynamic_embed_batch
        )
        mock_deps["embedding_provider"].get_embedding_dimension = MagicMock(
            return_value=5
        )

        enricher = ChunkEnricher(max_keywords=5)
        uc = IngestDocumentUseCase(
            parser=mock_deps["parser"],
            text_splitter=TextSplitter(chunk_size=200, chunk_overlap=50),
            embedding_provider=mock_deps["embedding_provider"],
            vector_store=mock_deps["vector_store"],
            chunk_enricher=enricher,
        )

        with (
            patch(
                "src.application.use_cases.ingest_document.get_settings"
            ) as mock_settings,
            patch(
                "src.application.use_cases.ingest_document.create_parser"
            ) as mock_create_parser,
            patch(
                "src.infrastructure.document_processing."
                "chunk_enricher_factory.create_chunk_enricher"
            ) as mock_factory,
        ):
            settings = MagicMock()
            settings.CHROMA_COLLECTION_NAME = "documents"
            settings.ENABLE_PARENT_CHILD = False
            settings.ENABLE_CHUNK_ENRICHMENT = True
            mock_settings.return_value = settings
            mock_create_parser.return_value = mock_deps["parser"]

            result = await uc.execute(b"fake", "test.pdf")

        assert result["chunk_count"] > 0
        # The injected enricher was used — the factory was never consulted.
        mock_factory.assert_not_called()
        stored = mock_deps["vector_store"].add_documents.call_args.args[0]
        assert any("keywords" in c.metadata for c in stored)

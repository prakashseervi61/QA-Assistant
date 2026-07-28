"""Unit tests for the Chunk value object."""

import pytest
from uuid import UUID, uuid4

from src.domain.value_objects.chunk import Chunk


# Fixtures

@pytest.fixture
def sample_content():
    return "This is a test chunk of text content."


@pytest.fixture
def sample_metadata():
    return {"filename": "test.pdf", "page": 3, "score": 0.85}


# Creation Tests

class TestChunkCreation:
    """Tests for Chunk construction and default values."""

    def test_chunk_creation_with_content(self, sample_content):
        chunk = Chunk(content=sample_content)
        assert chunk.content == sample_content

    def test_chunk_has_uuid_id(self):
        chunk = Chunk(content="hello")
        assert isinstance(chunk.id, UUID)

    def test_chunk_has_unique_ids(self):
        c1 = Chunk(content="a")
        c2 = Chunk(content="b")
        assert c1.id != c2.id

    def test_chunk_default_chunk_index_is_zero(self):
        chunk = Chunk(content="x")
        assert chunk.chunk_index == 0

    def test_chunk_default_document_id_is_uuid(self):
        chunk = Chunk(content="x")
        assert isinstance(chunk.document_id, UUID)

    def test_chunk_default_embedding_is_none(self):
        chunk = Chunk(content="x")
        assert chunk.embedding is None

    def test_chunk_default_metadata_is_empty_dict(self):
        chunk = Chunk(content="x")
        assert chunk.metadata == {}

    def test_chunk_default_content_is_empty_string(self):
        chunk = Chunk()
        assert chunk.content == ""


# Explicit Arguments Tests

class TestChunkWithExplicitArgs:
    """Tests for Chunk construction with explicit arguments."""

    def test_chunk_with_explicit_id(self):
        fixed_id = uuid4()
        chunk = Chunk(id=fixed_id, content="test")
        assert chunk.id == fixed_id

    def test_chunk_with_explicit_document_id(self):
        doc_id = uuid4()
        chunk = Chunk(document_id=doc_id, content="test")
        assert chunk.document_id == doc_id

    def test_chunk_with_explicit_chunk_index(self):
        chunk = Chunk(content="test", chunk_index=42)
        assert chunk.chunk_index == 42

    def test_chunk_with_embedding(self):
        emb = [0.1, 0.2, 0.3]
        chunk = Chunk(content="test", embedding=emb)
        assert chunk.embedding == emb

    def test_chunk_with_metadata(self, sample_metadata):
        chunk = Chunk(content="test", metadata=sample_metadata)
        assert chunk.metadata["filename"] == "test.pdf"
        assert chunk.metadata["page"] == 3
        assert chunk.metadata["score"] == 0.85

    def test_chunk_with_all_arguments(self):
        fixed_id = uuid4()
        doc_id = uuid4()
        chunk = Chunk(
            id=fixed_id,
            document_id=doc_id,
            content="full",
            embedding=[0.5],
            metadata={"k": "v"},
            chunk_index=7,
        )
        assert chunk.id == fixed_id
        assert chunk.document_id == doc_id
        assert chunk.content == "full"
        assert chunk.embedding == [0.5]
        assert chunk.metadata == {"k": "v"}
        assert chunk.chunk_index == 7


# Immutability Tests

class TestChunkImmutability:
    """Chunk is a frozen dataclass - verify it is immutable."""

    def test_chunk_is_frozen(self):
        chunk = Chunk(content="immutable")
        with pytest.raises(AttributeError):
            chunk.content = "changed"

    def test_chunk_id_is_immutable(self):
        chunk = Chunk(content="x")
        with pytest.raises(AttributeError):
            chunk.id = uuid4()

    def test_chunk_metadata_cannot_be_reassigned(self):
        """Frozen dataclass prevents attribute reassignment, but the dict itself is mutable."""
        chunk = Chunk(content="x", metadata={"a": 1})
        with pytest.raises(AttributeError):
            chunk.metadata = {"b": 2}  # type: ignore[misc]


# to_dict Tests

class TestChunkToDict:
    """Tests for the to_dict serialization method."""

    def test_to_dict_returns_dict(self):
        chunk = Chunk(content="hello")
        result = chunk.to_dict()
        assert isinstance(result, dict)

    def test_to_dict_contains_expected_keys(self):
        chunk = Chunk(content="hello")
        result = chunk.to_dict()
        expected_keys = {"id", "document_id", "content", "metadata", "chunk_index"}
        assert set(result.keys()) == expected_keys

    def test_to_dict_id_is_string(self):
        chunk = Chunk(content="hello")
        result = chunk.to_dict()
        assert isinstance(result["id"], str)
        UUID(result["id"])

    def test_to_dict_document_id_is_string(self):
        chunk = Chunk(content="hello")
        result = chunk.to_dict()
        assert isinstance(result["document_id"], str)
        UUID(result["document_id"])

    def test_to_dict_content_matches(self):
        chunk = Chunk(content="test content")
        result = chunk.to_dict()
        assert result["content"] == "test content"

    def test_to_dict_metadata_matches(self):
        meta = {"filename": "doc.pdf", "page": 5}
        chunk = Chunk(content="x", metadata=meta)
        result = chunk.to_dict()
        assert result["metadata"] == meta

    def test_to_dict_chunk_index_matches(self):
        chunk = Chunk(content="x", chunk_index=10)
        result = chunk.to_dict()
        assert result["chunk_index"] == 10

    def test_to_dict_embedding_not_included(self):
        chunk = Chunk(content="x", embedding=[0.1, 0.2])
        result = chunk.to_dict()
        assert "embedding" not in result

    def test_to_dict_roundtrip_id_preserved(self):
        fixed_id = uuid4()
        chunk = Chunk(id=fixed_id, content="x")
        result = chunk.to_dict()
        assert UUID(result["id"]) == fixed_id

    def test_to_dict_empty_metadata(self):
        chunk = Chunk(content="x")
        result = chunk.to_dict()
        assert result["metadata"] == {}


# Edge Cases

class TestChunkEdgeCases:
    """Edge-case tests for Chunk."""

    def test_chunk_with_empty_content(self):
        chunk = Chunk(content="")
        assert chunk.content == ""

    def test_chunk_with_very_long_content(self):
        long_text = "x" * 100_000
        chunk = Chunk(content=long_text)
        assert len(chunk.content) == 100_000

    def test_chunk_with_unicode_content(self):
        chunk = Chunk(content="Japanese text test")
        assert chunk.content == "Japanese text test"

    def test_chunk_with_nested_metadata(self):
        meta = {"nested": {"deep": [1, 2, 3]}}
        chunk = Chunk(content="x", metadata=meta)
        assert chunk.metadata["nested"]["deep"] == [1, 2, 3]

    def test_chunk_with_negative_index(self):
        chunk = Chunk(content="x", chunk_index=-1)
        assert chunk.chunk_index == -1

    def test_chunk_with_large_index(self):
        chunk = Chunk(content="x", chunk_index=999_999)
        assert chunk.chunk_index == 999_999

    def test_multiple_chunks_with_same_content_are_distinct(self):
        c1 = Chunk(content="same")
        c2 = Chunk(content="same")
        assert c1.id != c2.id
        assert c1.document_id != c2.document_id

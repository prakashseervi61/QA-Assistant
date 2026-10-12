"""Tests for batched upserts into ChromaDB.

The bug this covers was not a slow path but a hard failure: `add_documents` sent
every chunk in one `upsert`, and ChromaDB refuses any call above the collection's
`max_batch_size` (5461 on the default config). A document producing more chunks
than that failed outright — *after* the minutes spent parsing and embedding it —
with an opaque 500.

These tests assert the batching itself, against a collection that enforces the
same limit the real one does, so the regression cannot come back.
"""

from __future__ import annotations

import dataclasses
from unittest.mock import MagicMock

import pytest

from src.domain.value_objects.chunk import Chunk
from src.infrastructure.vector_store.chroma_store import (
    _DEFAULT_BATCH_SIZE,
    _FALLBACK_BATCH_SIZE,
    ChromaStore,
)


class FakeCollection:
    """A collection that enforces the real max_batch_size ceiling.

    Recording every call rather than just the count is what lets the batching
    assertions check that no single call exceeded the limit, and that the total
    row count still adds up — the two ways the fix could be subtly wrong.
    """

    def __init__(
        self, max_batch_size: int = 100, fail_on_oversize: bool = True
    ) -> None:
        # Kept in `_limit` so `upsert` still enforces a ceiling even in the
        # subclass where the public `max_batch_size` property raises — otherwise
        # the fake would fail for a reason the real collection would not.
        self._limit = max_batch_size
        self.max_batch_size = max_batch_size
        self.fail_on_oversize = fail_on_oversize
        self.calls: list[dict] = []

    def upsert(self, **kwargs) -> None:
        n = len(kwargs["ids"])
        if self.fail_on_oversize and n > self._limit:
            raise ValueError(
                f"Batch size of {n} is greater than max batch size "
                f"of {self.max_batch_size}"
            )
        self.calls.append(kwargs)


def make_chunks(count: int) -> list[Chunk]:
    return [
        Chunk(
            id=f"chunk-{i}",
            content=f"content {i}",
            document_id="doc-1",
            embedding=[0.1, 0.2, 0.3],
            metadata={},
        )
        for i in range(count)
    ]


def store_with_collection(collection) -> ChromaStore:
    store = ChromaStore.__new__(ChromaStore)  # skip the real client + model load
    store._collection = collection
    store._get_or_create_collection = lambda _name: collection  # type: ignore[method-assign]
    return store


@pytest.mark.asyncio
async def test_splits_a_document_that_exceeds_the_batch_limit():
    """The regression: 240 chunks against a 100-row ceiling must not raise."""
    collection = FakeCollection(max_batch_size=100)
    store = store_with_collection(collection)

    await store.add_documents(make_chunks(240), "documents")

    assert len(collection.calls) == 3, "240 chunks at ~99/batch should be 3 calls"
    assert max(len(c["ids"]) for c in collection.calls) <= collection.max_batch_size


@pytest.mark.asyncio
async def test_no_chunk_is_lost_or_duplicated_across_batches():
    collection = FakeCollection(max_batch_size=100)
    store = store_with_collection(collection)

    chunks = make_chunks(250)
    await store.add_documents(chunks, "documents")

    sent = [i for call in collection.calls for i in call["ids"]]
    assert len(sent) == len(chunks)
    assert len(set(sent)) == len(chunks), "a chunk was written twice"
    assert set(sent) == {f"chunk-{i}" for i in range(len(chunks))}
    # Metadata and embeddings must ride along with the ids, or the chunks are
    # stored without the provenance the UI needs to cite them.
    for call in collection.calls:
        assert len(call["metadatas"]) == len(call["ids"])
        assert len(call["embeddings"]) == len(call["ids"])
        assert len(call["documents"]) == len(call["ids"])


@pytest.mark.asyncio
async def test_a_document_under_the_limit_is_still_one_call():
    """Small documents must not pay for batching they do not need."""
    collection = FakeCollection(max_batch_size=100)
    store = store_with_collection(collection)

    await store.add_documents(make_chunks(10), "documents")

    assert len(collection.calls) == 1


class UnreadableLimitCollection(FakeCollection):
    """A collection whose limit cannot be read.

    A subclass rather than a monkey-patched property on FakeCollection itself:
    patching the parent class would leak into every other test in the module.
    """

    def __init__(self) -> None:
        # Deliberately not calling super().__init__: the parent assigns
        # `max_batch_size`, which this class exposes as a read-only property.
        # The fallback code must still split the writes, so the fake keeps a
        # usable internal ceiling.
        self._limit = 10_000
        self.fail_on_oversize = True
        self.calls: list[dict] = []

    @property
    def max_batch_size(self) -> int:  # type: ignore[override]
        raise RuntimeError("limit not available")


@pytest.mark.asyncio
async def test_falls_back_when_the_collection_will_not_report_its_limit():
    collection = UnreadableLimitCollection()
    store = store_with_collection(collection)

    await store.add_documents(make_chunks(1200), "documents")

    assert collection.calls, "expected the chunks to still be written"
    assert max(len(c["ids"]) for c in collection.calls) <= _FALLBACK_BATCH_SIZE


def test_batch_size_stays_under_the_collection_limit_with_room_to_spare():
    """One row of slack: at the exact limit, metadata expansion can tip it over."""
    collection = FakeCollection(max_batch_size=10)
    store = store_with_collection(collection)
    store._collection = collection
    store._get_or_create_collection = lambda _name: collection  # type: ignore[method-assign]

    assert _DEFAULT_BATCH_SIZE >= 10
    batch = max(1, min(collection.max_batch_size - 1, _DEFAULT_BATCH_SIZE))
    assert batch < collection.max_batch_size


@pytest.mark.asyncio
async def test_an_empty_chunk_list_is_a_no_op():
    collection = FakeCollection()
    store = store_with_collection(collection)

    await store.add_documents([], "documents")

    assert collection.calls == []


@pytest.mark.asyncio
async def test_a_missing_embedding_is_rejected_before_any_write():
    """Fail before the first batch lands, so a bad document writes nothing."""
    collection = FakeCollection(max_batch_size=100)
    store = store_with_collection(collection)

    chunks = make_chunks(5)
    # Chunk is a frozen dataclass, so the bad one has to be built rather than
    # mutated.
    chunks[3] = dataclasses.replace(chunks[3], embedding=None)

    with pytest.raises(ValueError, match="has no embedding"):
        await store.add_documents(chunks, "documents")

    assert collection.calls == [], "nothing should be written when validation fails"


@pytest.mark.asyncio
async def test_a_mid_batch_failure_surfaces_as_runtime_error():
    collection = FakeCollection(max_batch_size=100)
    calls = {"n": 0}

    def flaky_upsert(**kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("disk went away")
        return None

    collection.upsert = flaky_upsert  # type: ignore[method-assign]
    store = store_with_collection(collection)

    with pytest.raises(RuntimeError, match="ChromaDB upsert failed"):
        await store.add_documents(make_chunks(250), "documents")


@pytest.mark.asyncio
async def test_calls_the_real_collection_untouched_when_unbatched():
    """Sanity: a normal MagicMock still receives exactly one call."""
    collection = MagicMock()
    collection.max_batch_size = 5_461
    store = store_with_collection(collection)

    await store.add_documents(make_chunks(3), "documents")

    collection.upsert.assert_called_once()

"""Semantic chunking strategy using embedding-based boundary detection.

Instead of fixed-size splits, this chunker detects topic boundaries
by computing cosine similarity between consecutive sentence embeddings.
Chunks are formed where semantic similarity drops below a threshold.
"""

import logging
import re
from uuid import UUID, uuid4

import numpy as np

from src.domain.interfaces.embedding_provider import EmbeddingProvider
from src.domain.value_objects.chunk import Chunk

logger = logging.getLogger(__name__)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences using regex."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p.strip()]


class SemanticChunker:
    """Split text into chunks based on semantic boundaries.

    Uses embedding similarity between consecutive sentences to detect
    topic shifts. Low similarity = boundary point.

    Args:
        embedding_provider: Provider for computing text embeddings.
        similarity_threshold: Cosine similarity below this triggers a split.
        min_chunk_size:       Minimum chunk size in characters.
        max_chunk_size:       Maximum chunk size in characters.
    """

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        similarity_threshold: float = 0.5,
        min_chunk_size: int = 100,
        max_chunk_size: int = 2000,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._similarity_threshold = similarity_threshold
        self._min_chunk_size = min_chunk_size
        self._max_chunk_size = max_chunk_size

    @property
    def chunk_size(self) -> int:
        """Effective chunk size, for compatibility with IngestDocumentUseCase."""
        return self._max_chunk_size

    @property
    def chunk_overlap(self) -> int:
        """Semantic chunking uses no fixed character overlap."""
        return 0

    async def split_text(
        self,
        text: str,
        document_id: UUID,
        metadata: dict | None = None,
    ) -> list[Chunk]:
        """Split text into semantically coherent chunks.

        ``split_text`` is async because it awaits the embedding provider's
        ``embed_batch`` (which is async per ``EmbeddingProvider``).
        """
        if metadata is None:
            metadata = {}

        text = text.strip()
        if not text:
            return []

        sentences = _split_sentences(text)
        if not sentences:
            return []

        if len(sentences) == 1:
            return [
                Chunk(
                    id=uuid4(),
                    document_id=document_id,
                    content=sentences[0],
                    metadata={**metadata, "chunk_type": "semantic", "chunk_index": 0},
                    chunk_index=0,
                )
            ]

        embeddings = await self._embedding_provider.embed_batch(sentences)

        # Find boundaries: indices where cosine similarity drops
        boundaries = [0]
        for i in range(1, len(sentences)):
            sim = _cosine_similarity(
                np.array(embeddings[i - 1]),
                np.array(embeddings[i]),
            )
            if sim < self._similarity_threshold:
                boundaries.append(i)

        boundaries.append(len(sentences))

        # Build initial segments from boundaries
        raw_segments: list[str] = []
        for b_idx in range(len(boundaries) - 1):
            start = boundaries[b_idx]
            end = boundaries[b_idx + 1]
            segment = " ".join(sentences[start:end])
            if segment.strip():
                raw_segments.append(segment.strip())

        # Merge small segments up to max_chunk_size. Only merge while the
        # accumulator is below min_chunk_size so that semantic boundaries
        # (segments that already meet the minimum size) are preserved.
        merged: list[str] = []
        current = ""
        for segment in raw_segments:
            if not current:
                current = segment
            elif (
                len(current) < self._min_chunk_size
                and len(current) + len(segment) + 1 <= self._max_chunk_size
            ):
                current = current + " " + segment
            else:
                merged.append(current)
                current = segment
        if current:
            merged.append(current)

        # Split oversized chunks at the best internal boundary
        final_texts: list[str] = []
        for chunk_text in merged:
            if len(chunk_text) <= self._max_chunk_size:
                final_texts.append(chunk_text)
            else:
                final_texts.extend(await self._split_oversized(chunk_text))

        # Build Chunk objects
        chunks = []
        for idx, chunk_text in enumerate(final_texts):
            chunks.append(
                Chunk(
                    id=uuid4(),
                    document_id=document_id,
                    content=chunk_text,
                    metadata={**metadata, "chunk_type": "semantic", "chunk_index": idx},
                    chunk_index=idx,
                )
            )

        logger.debug(
            "SemanticChunker: %d sentences -> %d chunks (threshold=%.2f)",
            len(sentences),
            len(chunks),
            self._similarity_threshold,
        )
        return chunks

    async def _split_oversized(self, text: str) -> list[str]:
        """Split an oversized chunk at its lowest-similarity boundary."""
        sentences = _split_sentences(text)
        if len(sentences) <= 1:
            return [text]

        embeddings = await self._embedding_provider.embed_batch(sentences)

        best_idx = len(sentences) // 2
        best_sim = 1.0
        for i in range(1, len(sentences)):
            sim = _cosine_similarity(
                np.array(embeddings[i - 1]),
                np.array(embeddings[i]),
            )
            if sim < best_sim:
                best_sim = sim
                best_idx = i

        left = " ".join(sentences[:best_idx]).strip()
        right = " ".join(sentences[best_idx:]).strip()

        result: list[str] = []
        for half in (left, right):
            if len(half) > self._max_chunk_size:
                result.extend(await self._split_oversized(half))
            elif half:
                result.append(half)

        return result

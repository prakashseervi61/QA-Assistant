"""BGE reranker implementation using sentence-transformers CrossEncoder."""

import math
from dataclasses import replace

from sentence_transformers import CrossEncoder

from src.domain.interfaces.reranker import Reranker
from src.domain.value_objects.chunk import Chunk


class BEReranker(Reranker):
    """Reranker backed by a BGE CrossEncoder model.

    Uses ``sentence_transformers.CrossEncoder`` to score (query, chunk)
    pairs and returns the top-k most relevant chunks.
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3") -> None:
        self._model = CrossEncoder(model_name)

    def rerank(
        self,
        query: str,
        chunks: list[Chunk],
        top_k: int = 5,
    ) -> list[Chunk]:
        """Rerank *chunks* by relevance to *query*.

        Steps:
            1. Build (query, content) pairs.
            2. Score pairs with the CrossEncoder.
            3. Normalize raw logits to [0, 1] via sigmoid.
            4. Attach ``rerank_score`` to each chunk's metadata.
            5. Sort descending by ``rerank_score`` and return top_k.
        """
        if not chunks:
            return []

        pairs = [(query, chunk.content) for chunk in chunks]
        scores = self._model.predict(pairs)

        # Normalize scores to [0, 1] using sigmoid
        normalized = [1.0 / (1.0 + math.exp(-float(s))) for s in scores]

        # Attach rerank_score to a copy of each chunk's metadata
        scored_chunks: list[Chunk] = []
        for chunk, score in zip(chunks, normalized):
            new_meta = {**chunk.metadata, "rerank_score": round(score, 4)}
            scored_chunks.append(replace(chunk, metadata=new_meta))

        scored_chunks.sort(key=lambda c: c.metadata["rerank_score"], reverse=True)
        return scored_chunks[:top_k]

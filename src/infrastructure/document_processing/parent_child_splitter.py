"""Parent-child text splitting strategy.

Splits text into large parent chunks for context and small child
chunks for precise retrieval. Children are linked to parents via
the ``parent_id`` metadata field.
"""

import logging
from uuid import UUID, uuid4

from src.domain.value_objects.chunk import Chunk

logger = logging.getLogger(__name__)


class ParentChildSplitter:
    """Split text into parent chunks with child sub-chunks.

    Args:
        parent_chunk_size: Target size for parent chunks (in characters).
        child_chunk_size:  Target size for child chunks (in characters).
        child_overlap:     Overlap between consecutive child chunks.
    """

    def __init__(
        self,
        parent_chunk_size: int = 2000,
        child_chunk_size: int = 200,
        child_overlap: int = 50,
    ) -> None:
        self.parent_chunk_size = parent_chunk_size
        self.child_chunk_size = child_chunk_size
        self.child_overlap = child_overlap
        # Expose as chunk_size/chunk_overlap for TextSplitter compatibility
        self.chunk_size = parent_chunk_size
        self.chunk_overlap = child_overlap

    async def split_text(
        self,
        text: str,
        document_id: UUID,
        metadata: dict | None = None,
    ) -> list[Chunk]:
        """Split text into parent chunks (compatibility with TextSplitter).

        Returns only the parent chunks as a flat list, suitable for use
        as a drop-in replacement for :meth:`TextSplitter.split_text`.
        The ``async`` signature matches :class:`SemanticChunker` so callers
        can ``await`` either splitter.
        """
        if metadata is None:
            metadata = {}
        parents, _children = self.split(text, document_id, metadata)
        return parents

    def split(
        self,
        text: str,
        document_id: UUID,
        metadata: dict | None = None,
    ) -> tuple[list[Chunk], list[Chunk]]:
        """Split text into parent and child chunks.

        Returns:
            A tuple of (parent_chunks, child_chunks).
        """
        if metadata is None:
            metadata = {}

        parents = self._split_parents(text, document_id, metadata)
        children = self._split_children(parents, document_id, metadata)

        logger.debug(
            "ParentChildSplitter: %d parents, %d children from %d chars",
            len(parents),
            len(children),
            len(text),
        )
        return parents, children

    def _split_parents(
        self, text: str, document_id: UUID, metadata: dict
    ) -> list[Chunk]:
        parents: list[Chunk] = []
        start = 0
        idx = 0

        while start < len(text):
            end = min(start + self.parent_chunk_size, len(text))

            # Try to break at sentence boundary
            if end < len(text):
                last_period = text.rfind(".", start, end)
                last_newline = text.rfind("\n", start, end)
                split_point = max(last_period, last_newline)
                if split_point > start:
                    end = split_point + 1

            content = text[start:end].strip()
            if content:
                parent_id = uuid4()
                parents.append(
                    Chunk(
                        id=parent_id,
                        document_id=document_id,
                        content=content,
                        metadata={
                            **metadata,
                            "chunk_type": "parent",
                            "chunk_index": idx,
                        },
                        chunk_index=idx,
                    )
                )
                idx += 1

            # Guard against pathological overlap (>= chunk size): always
            # advance by at least one character to avoid an infinite loop.
            start = max(end - self.child_overlap, end - 1) if end < len(text) else end

        return parents

    def _split_children(
        self, parents: list[Chunk], document_id: UUID, metadata: dict
    ) -> list[Chunk]:
        children: list[Chunk] = []
        child_idx = 0

        for parent in parents:
            text = parent.content
            start = 0

            while start < len(text):
                end = min(start + self.child_chunk_size, len(text))

                if end < len(text):
                    last_space = text.rfind(" ", start, end)
                    if last_space > start:
                        # +1 keeps the boundary space in the left chunk so
                        # no character is silently dropped.
                        end = last_space + 1

                content = text[start:end].strip()
                if content:
                    children.append(
                        Chunk(
                            id=uuid4(),
                            document_id=document_id,
                            content=content,
                            metadata={
                                **metadata,
                                "chunk_type": "child",
                                "parent_id": str(parent.id),
                                "chunk_index": child_idx,
                            },
                            chunk_index=child_idx,
                        )
                    )
                    child_idx += 1

                # Guard against pathological overlap (>= chunk size):
                # always advance by at least one character.
                start = (
                    max(end - self.child_overlap, end - 1)
                    if end < len(text)
                    else end
                )

        return children

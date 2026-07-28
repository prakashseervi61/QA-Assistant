from uuid import UUID, uuid4

from src.domain.value_objects.chunk import Chunk
from src.infrastructure.config.settings import get_settings


class TextSplitter:
    def __init__(
        self,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ):
        settings = get_settings()
        self.chunk_size = chunk_size if chunk_size is not None else settings.CHUNK_SIZE
        self.chunk_overlap = (
            chunk_overlap if chunk_overlap is not None else settings.CHUNK_OVERLAP
        )

    def split_text(
        self, text: str, document_id: UUID, metadata: dict = None
    ) -> list[Chunk]:
        if metadata is None:
            metadata = {}

        chunks = []
        start = 0
        chunk_index = 0

        while start < len(text):
            end = start + self.chunk_size

            if end < len(text):
                last_period = text.rfind(".", start, end)
                last_newline = text.rfind("\n", start, end)
                split_point = max(last_period, last_newline)

                if split_point > start:
                    end = split_point + 1

            chunk_content = text[start:end].strip()

            if chunk_content:
                chunk = Chunk(
                    id=uuid4(),
                    document_id=document_id,
                    content=chunk_content,
                    metadata={**metadata, "chunk_index": chunk_index},
                    chunk_index=chunk_index,
                )
                chunks.append(chunk)
                chunk_index += 1

            start = end - self.chunk_overlap

        return chunks

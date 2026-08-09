"""Chunk enrichment: extract titles, section paths, and keywords per chunk.

Deterministic, dependency-free metadata extraction (regex/heuristics) that
runs after text splitting and before embedding. Optional LLM-based summaries
can be enabled separately to control cost.
"""

import logging
import re
from collections import Counter

from src.domain.value_objects.chunk import Chunk

logger = logging.getLogger(__name__)


_NUMBERED_HEADING_RE = re.compile(r"^\s*(\d+(\.\d+)*)[\.\)]?\s+(.+)$")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-]+")

# Capitalized words that are usually sentence starts rather than keywords.
_STOPWORDS = frozenset(
    {
        "The",
        "This",
        "However",
        "These",
        "Those",
        "There",
        "And",
        "But",
        "For",
        "With",
        "From",
        "That",
        "What",
        "When",
        "Where",
        "Which",
        "While",
    }
)
_STOPWORDS_LOWER = frozenset(w.lower() for w in _STOPWORDS)


def _looks_like_heading(line: str) -> bool:
    """Heuristic: short line, starts with a capital, no trailing period."""
    line = line.strip()
    if not line or len(line) > 80:
        return False
    if line.endswith((".", "!", "?", ";")):
        return False
    # Must start with a capital letter, a number, or a markdown heading marker
    if not (line[0].isupper() or line[0].isdigit() or line.startswith("#")):
        return False
    return True


def _is_list_item(line: str, prev_line: str, next_line: str) -> bool:
    """Return True if a numbered line is a list item rather than a heading.

    A numbered line adjacent to at least one other numbered line is treated
    as a list item (e.g. "1. First item" followed by "2. Second item"),
    whereas an isolated numbered line is a section heading.
    """
    if not _NUMBERED_HEADING_RE.match(line.strip()):
        return False
    prev_is_numbered = bool(
        prev_line and _NUMBERED_HEADING_RE.match(prev_line.strip())
    )
    next_is_numbered = bool(
        next_line and _NUMBERED_HEADING_RE.match(next_line.strip())
    )
    return prev_is_numbered or next_is_numbered


def _extract_title(lines: list[str]) -> str | None:
    """Return the first heading-like line as the title."""
    for i, line in enumerate(lines[:10]):
        prev_line = lines[i - 1] if i > 0 else ""
        next_line = lines[i + 1] if i + 1 < len(lines) else ""
        if _looks_like_heading(line) and not _is_list_item(line, prev_line, next_line):
            cleaned = re.sub(r"^#{1,6}\s+", "", line.strip())
            return cleaned
    return None


def _extract_section_path(lines: list[str]) -> str | None:
    """Detect numbered headers and build a section path like '3 > Data Models'."""
    for i, line in enumerate(lines[:10]):
        prev_line = lines[i - 1] if i > 0 else ""
        next_line = lines[i + 1] if i + 1 < len(lines) else ""
        if _is_list_item(line, prev_line, next_line):
            continue
        m = _NUMBERED_HEADING_RE.match(line.strip())
        if m:
            number = m.group(1)
            title = m.group(3).strip()
            return f"{number} > {title}"
    return None


def _extract_keywords(text: str, max_keywords: int = 10) -> list[str]:
    """Extract key terms: capitalized words + frequent terms, deduplicated."""
    words = _WORD_RE.findall(text)
    if not words:
        return []

    # Candidate keywords: capitalized words (proper nouns/technical terms),
    # excluding stopwords that are usually capitalized sentence starts.
    candidates = [
        w
        for w in words
        if w[0].isupper() and len(w) > 2 and w not in _STOPWORDS
    ]
    # Fall back to frequency-based
    if len(candidates) < 3:
        counter = Counter(
            w.lower() for w in words if len(w) > 3
        )
        candidates = [
            w
            for w, _ in counter.most_common(10)
            if w not in _STOPWORDS_LOWER
        ]

    # Deduplicate case-insensitively, keep order
    seen = set()
    result = []
    for w in candidates:
        key = w.lower()
        if key not in seen:
            seen.add(key)
            result.append(w)
    return result[:max_keywords]


class ChunkEnricher:
    """Enrich chunks with titles, section paths, keywords, and optional summaries.

    Args:
        llm_provider:       Optional LLM provider for summary generation.
        generate_summaries: Whether to generate LLM summaries (costly).
        max_keywords:       Maximum number of keywords per chunk.
    """

    def __init__(
        self,
        llm_provider: object | None = None,
        generate_summaries: bool = False,
        max_keywords: int = 10,
    ) -> None:
        self._llm_provider = llm_provider
        self._generate_summaries = generate_summaries
        self._max_keywords = max_keywords

    def enrich_chunk(self, chunk: Chunk) -> Chunk:
        """Enrich a single chunk's metadata (sync, deterministic)."""
        lines = chunk.content.split("\n")

        title = _extract_title(lines)
        section_path = _extract_section_path(lines)
        keywords = _extract_keywords(chunk.content, self._max_keywords)

        new_metadata = dict(chunk.metadata)
        if title:
            new_metadata["title"] = title
        if section_path:
            new_metadata["section_path"] = section_path
        # ChromaDB metadata only accepts scalar values, so keywords are
        # stored as a comma-joined string rather than a list.
        new_metadata["keywords"] = ",".join(keywords)

        return Chunk(
            id=chunk.id,
            document_id=chunk.document_id,
            content=chunk.content,
            embedding=chunk.embedding,
            metadata=new_metadata,
            chunk_index=chunk.chunk_index,
        )

    def enrich_batch(self, chunks: list[Chunk]) -> list[Chunk]:
        """Enrich multiple chunks."""
        return [self.enrich_chunk(c) for c in chunks]

    async def enrich_chunk_async(self, chunk: Chunk) -> Chunk:
        """Enrich a chunk, optionally generating an LLM summary."""
        enriched = self.enrich_chunk(chunk)
        if self._generate_summaries and self._llm_provider is not None:
            try:
                summary = await self._llm_provider.generate(
                    f"Summarize the following text in 2-3 sentences:\n\n{chunk.content}"
                )
                metadata = dict(enriched.metadata)
                metadata["summary"] = summary
                enriched = Chunk(
                    id=enriched.id,
                    document_id=enriched.document_id,
                    content=enriched.content,
                    embedding=enriched.embedding,
                    metadata=metadata,
                    chunk_index=enriched.chunk_index,
                )
            except Exception as exc:
                logger.warning("Summary generation failed: %s", exc)
        return enriched

    async def enrich_batch_async(self, chunks: list[Chunk]) -> list[Chunk]:
        """Enrich multiple chunks, generating summaries if enabled."""
        return [await self.enrich_chunk_async(c) for c in chunks]

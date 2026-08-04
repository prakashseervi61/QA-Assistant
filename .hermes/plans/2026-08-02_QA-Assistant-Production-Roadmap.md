# QA-Assistant: Production-Ready RAG Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Transform the current PDF QA Assistant from a clean prototype into a production-ready RAG system with hybrid search, reranking, query rewriting, observability, evaluation, multi-tenancy, and agentic capabilities.

**Architecture:** Clean Architecture (Domain → Application → Infrastructure → Presentation) with provider-agnostic interfaces. Each phase adds a new infrastructure implementation behind existing interfaces — zero breaking changes to domain/application layers.

**Tech Stack Additions:**
- **Reranking:** `sentence-transformers.CrossEncoder` (BAAI/bge-reranker-v2-m3, local)
- **Hybrid Search:** Chroma native hybrid (BM25 + dense) → Qdrant for production
- **PDF Parsing:** `pymupdf` + `marker-pdf` (layout-aware, tables as markdown)
- **Observability:** `arize-phoenix` (local tracing) + `langsmith` (optional managed)
- **Evaluation:** `ragas` + `deepeval` (CI gates)
- **Database:** `sqlalchemy` + `asyncpg` (Postgres) + `alembic` (migrations)
- **Auth:** `fastapi-users` + `slowapi` (JWT + rate limiting)
- **Queue:** `celery` + `redis` (async ingestion)
- **Structured Output:** `instructor` (Pydantic + JSON mode)
- **Guardrails:** `guardrails-ai` (PII, injection, hallucination)

---

## Phase 1: Core Retrieval Quality (Week 1-2) — HIGH IMPACT

### Task 1.1: Add Reranker Interface & BGE Implementation

**Objective:** Add cross-encoder reranking stage after vector retrieval to improve precision@k.

**Files:**
- Create: `src/domain/interfaces/reranker.py`
- Create: `src/infrastructure/rerankers/bge_reranker.py`
- Create: `src/infrastructure/rerankers/factory.py`
- Modify: `src/application/services/rag_engine.py` (wire reranker)
- Modify: `src/infrastructure/config/settings.py` (add RERANKER_MODEL, ENABLE_RERANKING)
- Test: `tests/unit/application/services/test_rag_engine_rerank.py`

**Step 1: Write failing test**
```python
# tests/unit/application/services/test_rag_engine_rerank.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.application.services.rag_engine import RAGEngine
from src.domain.value_objects.chunk import Chunk

@pytest.fixture
def mock_reranker():
    reranker = AsyncMock()
    reranker.rerank = AsyncMock(return_value=[
        Chunk(content="Most relevant", metadata={"score": 0.95}),
        Chunk(content="Less relevant", metadata={"score": 0.7}),
    ])
    return reranker

@pytest.mark.asyncio
async def test_query_calls_reranker_after_retrieval(rag_engine, mock_reranker, mock_vector_store, sample_chunks):
    rag_engine._reranker = mock_reranker
    mock_vector_store.similarity_search.return_value = sample_chunks
    
    await rag_engine.query("test question")
    
    mock_reranker.rerank.assert_awaited_once()
    call_args = mock_reranker.rerank.call_args
    assert call_args.kwargs["query"] == "test question"
    assert len(call_args.kwargs["chunks"]) == 3
    assert call_args.kwargs["top_k"] == 5
```

**Step 2: Run test to verify failure**
```bash
pytest tests/unit/application/services/test_rag_engine_rerank.py::test_query_calls_reranker_after_retrieval -v
# Expected: FAIL — AttributeError: 'RAGEngine' object has no attribute '_reranker'
```

**Step 3: Write minimal implementation**

```python
# src/domain/interfaces/reranker.py
from abc import ABC, abstractmethod
from src.domain.value_objects.chunk import Chunk

class Reranker(ABC):
    @abstractmethod
    async def rerank(self, query: str, chunks: list[Chunk], top_k: int) -> list[Chunk]:
        """Re-rank chunks by relevance to query. Return top_k."""
        ...
```

```python
# src/infrastructure/rerankers/bge_reranker.py
import asyncio
import logging
from sentence_transformers import CrossEncoder
from src.domain.interfaces.reranker import Reranker
from src.domain.value_objects.chunk import Chunk

logger = logging.getLogger(__name__)

class BGEReranker(Reranker):
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        self._model_name = model_name
        self._model = None
    
    def _load(self):
        if self._model is None:
            logger.info("Loading BGE reranker: %s", self._model_name)
            self._model = CrossEncoder(self._model_name, max_length=512)
    
    async def rerank(self, query: str, chunks: list[Chunk], top_k: int) -> list[Chunk]:
        self._load()
        if not chunks:
            return []
        
        pairs = [[query, chunk.content] for chunk in chunks]
        scores = await asyncio.to_thread(self._model.predict, pairs)
        
        scored = list(zip(chunks, scores))
        scored.sort(key=lambda x: x[1], reverse=True)
        
        # Update chunk metadata with rerank score
        for chunk, score in scored[:top_k]:
            chunk.metadata["rerank_score"] = float(score)
        
        return [chunk for chunk, _ in scored[:top_k]]
```

```python
# src/infrastructure/rerankers/factory.py
from src.domain.interfaces.reranker import Reranker
from src.infrastructure.config.settings import get_settings

def create_reranker() -> Reranker | None:
    settings = get_settings()
    if not getattr(settings, "ENABLE_RERANKING", False):
        return None
    
    model = getattr(settings, "RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
    from src.infrastructure.rerankers.bge_reranker import BGEReranker
    return BGEReranker(model_name=model)
```

```python
# src/application/services/rag_engine.py (modifications)
# In __init__:
def __init__(self, ..., reranker: Reranker | None = None) -> None:
    self._reranker = reranker

# In query() after retrieval (line ~114):
if self._reranker and chunks:
    logger.debug("Reranking %d chunks", len(chunks))
    chunks = await self._reranker.rerank(question, chunks, k)
    logger.info("Reranked to top %d chunks", len(chunks))

# In _compute_confidence() — prefer rerank_score if available:
def _compute_confidence(self, chunks: list) -> float:
    if not chunks:
        return 0.0
    scores = []
    for chunk in chunks:
        # Prefer rerank_score, fallback to similarity score
        score = chunk.metadata.get("rerank_score") or chunk.metadata.get("score", 0.0)
        if isinstance(score, (int, float)):
            scores.append(float(score))
    return sum(scores) / len(scores) if scores else 0.0
```

```python
# src/infrastructure/config/settings.py (additions)
RERANKER_MODEL: str = "BAAI/bge-reranker-v2-m3"
ENABLE_RERANKING: bool = True
```

```python
# src/presentation/api/app.py (wire reranker)
from src.infrastructure.rerankers.factory import create_reranker

def _wire_dependencies(settings: Settings) -> None:
    # ... existing code ...
    reranker = create_reranker()
    rag_engine = RAGEngine(
        llm_provider=llm_provider,
        embedding_provider=embedding_provider,
        vector_store=vector_store,
        reranker=reranker,  # NEW
    )
    # ...
```

**Step 4: Run test to verify pass**
```bash
pytest tests/unit/application/services/test_rag_engine_rerank.py::test_query_calls_reranker_after_retrieval -v
# Expected: PASS
```

**Step 5: Commit**
```bash
git add src/domain/interfaces/reranker.py src/infrastructure/rerankers/ src/application/services/rag_engine.py src/infrastructure/config/settings.py src/presentation/api/app.py tests/unit/application/services/test_rag_engine_rerank.py
git commit -m "feat: add BGE reranker for improved retrieval precision"
```

---

### Task 1.2: Add Hybrid Search (BM25 + Vector) to VectorStore Interface

**Objective:** Enable keyword + semantic search fusion for better recall on exact matches.

**Files:**
- Modify: `src/domain/interfaces/vector_store.py` (add hybrid_search method)
- Modify: `src/infrastructure/vector_store/chroma_store.py` (implement hybrid_search)
- Modify: `src/application/services/rag_engine.py` (use hybrid_search)
- Test: `tests/unit/infrastructure/vector_store/test_chroma_hybrid.py`

**Step 1: Write failing test**
```python
# tests/unit/infrastructure/vector_store/test_chroma_hybrid.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.infrastructure.vector_store.chroma_store import ChromaStore
from src.domain.value_objects.chunk import Chunk

@pytest.fixture
def chroma_store():
    with patch("chromadb.PersistentClient"):
        store = ChromaStore(persist_directory="/tmp/test")
        store._client = MagicMock()
        return store

@pytest.mark.asyncio
async def test_hybrid_search_calls_chroma_with_query_text_and_embedding(chroma_store):
    mock_collection = MagicMock()
    mock_collection.query.return_value = {
        "ids": [["chunk-1"]],
        "documents": [["test content"]],
        "embeddings": [[[0.1, 0.2]]],
        "metadatas": [[{"filename": "test.pdf", "chunk_index": 0, "score": 0.9}]],
        "distances": [[0.1]],
    }
    chroma_store._client.get_collection.return_value = mock_collection
    
    query_embedding = [0.1, 0.2, 0.3]
    query_text = "test query"
    
    results = await chroma_store.hybrid_search(
        query_embedding=query_embedding,
        query_text=query_text,
        k=5,
        collection_name="documents",
    )
    
    mock_collection.query.assert_called_once()
    call_kwargs = mock_collection.query.call_args.kwargs
    assert "query_embeddings" in call_kwargs
    assert "query_texts" in call_kwargs
    assert call_kwargs["query_texts"] == [query_text]
    assert len(results) == 1
```

**Step 2: Run test to verify failure**
```bash
pytest tests/unit/infrastructure/vector_store/test_chroma_hybrid.py -v
# Expected: FAIL — AttributeError: 'ChromaStore' object has no attribute 'hybrid_search'
```

**Step 3: Write minimal implementation**

```python
# src/domain/interfaces/vector_store.py (add to VectorStore ABC)
@abstractmethod
async def hybrid_search(
    self,
    query_embedding: list[float],
    query_text: str,
    k: int,
    collection_name: str,
    filter: dict | None = None,
) -> list[Chunk]:
    """Hybrid search combining vector similarity and BM25 keyword search."""
    ...
```

```python
# src/infrastructure/vector_store/chroma_store.py (add method)
async def hybrid_search(
    self,
    query_embedding: list[float],
    query_text: str,
    k: int,
    collection_name: str,
    filter: dict | None = None,
) -> list[Chunk]:
    """Hybrid search using Chroma's native query_texts + query_embeddings."""
    
    def _query() -> list[Chunk]:
        try:
            collection = self._client.get_collection(collection_name)
        except ValueError:
            return []
        
        if collection.count() == 0:
            return []
        
        # Chroma hybrid: pass both query_embeddings and query_texts
        results = collection.query(
            query_embeddings=[query_embedding],
            query_texts=[query_text],
            n_results=min(k, collection.count()),
            where=filter,
            include=["documents", "embeddings", "metadatas", "distances"],
        )
        
        chunks: list[Chunk] = []
        if not results or not results.get("ids"):
            return chunks
        
        ids = results["ids"][0]
        documents = results.get("documents", [[]])[0]
        embeddings = results.get("embeddings", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        
        num_ids = len(ids)
        for idx in range(num_ids):
            metadata = dict(metadatas[idx]) if len(metadatas) > idx else {}
            document_id_str = metadata.pop("document_id", None)
            chunk_index = int(metadata.pop("chunk_index", 0))
            
            # Chroma returns cosine distance; convert to similarity
            if len(distances) > idx:
                metadata["score"] = round(1.0 - float(distances[idx]), 4)
            
            from uuid import UUID
            embedding_list = list(embeddings[idx]) if len(embeddings) > idx else None
            
            chunk = Chunk(
                id=UUID(ids[idx]),
                document_id=UUID(document_id_str) if document_id_str else None,
                content=documents[idx] if len(documents) > idx else "",
                embedding=embedding_list,
                metadata=metadata,
                chunk_index=chunk_index,
            )
            chunks.append(chunk)
        
        return chunks
    
    try:
        return await asyncio.to_thread(_query)
    except Exception as exc:
        logger.error("ChromaDB hybrid search failed: %s", exc)
        raise RuntimeError(f"ChromaDB hybrid search failed: {exc}") from exc
```

```python
# src/application/services/rag_engine.py (modify query method)
async def query(self, question: str, top_k: int | None = None) -> dict:
    k = top_k or self.DEFAULT_TOP_K
    
    # 1. Embed the question
    query_embedding = await self._embedding.embed(question)
    
    # 2. Hybrid search (vector + BM25)
    logger.debug("Hybrid searching vector store (top_k=%d)", k)
    collection = self._settings.CHROMA_COLLECTION_NAME
    chunks = await self._vector_store.hybrid_search(
        query_embedding=query_embedding,
        query_text=question,
        k=k,
        collection_name=collection,
    )
    # ... rest unchanged
```

**Step 4: Run test to verify pass**
```bash
pytest tests/unit/infrastructure/vector_store/test_chroma_hybrid.py -v
# Expected: PASS
```

**Step 5: Commit**
```bash
git add src/domain/interfaces/vector_store.py src/infrastructure/vector_store/chroma_store.py src/application/services/rag_engine.py tests/unit/infrastructure/vector_store/test_chroma_hybrid.py
git commit -m "feat: add hybrid search (BM25 + dense) via Chroma native query_texts"
```

---

### Task 1.3: Upgrade PDF Parser to PyMuPDF + Marker

**Objective:** Replace PyPDF2 with layout-aware parsing that extracts tables as Markdown, preserves headers, and handles multi-column layouts.

**Files:**
- Create: `src/infrastructure/document_processing/marker_parser.py`
- Modify: `src/infrastructure/document_processing/parser_factory.py` (prefer Marker for PDF)
- Modify: `src/infrastructure/document_processing/pdf_parser.py` (fallback to PyMuPDF)
- Test: `tests/unit/infrastructure/document_processing/test_marker_parser.py`

**Step 1: Write failing test**
```python
# tests/unit/infrastructure/document_processing/test_marker_parser.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.infrastructure.document_processing.marker_parser import MarkerParser

@pytest.mark.asyncio
async def test_marker_parser_extracts_tables_as_markdown():
    parser = MarkerParser()
    
    # Mock marker's convert_single_pdf
    with patch("marker.convert_single_pdf") as mock_convert:
        mock_convert.return_value = (
            "# Header\n\nContent\n\n| Table | Header |\n|-------|--------|\n| Cell 1 | Cell 2 |",
            {"images": {}},
            {"page_count": 1},
        )
        
        import io
        fake_pdf = io.BytesIO(b"%PDF-1.4 fake")
        result = await parser.parse(fake_pdf)
        
        assert "| Table | Header |" in result
        assert "Cell 1" in result
        assert "Cell 2" in result
```

**Step 2: Run test to verify failure**
```bash
pytest tests/unit/infrastructure/document_processing/test_marker_parser.py -v
# Expected: FAIL — ModuleNotFoundError: No module named 'marker'
```

**Step 3: Write minimal implementation**

```python
# src/infrastructure/document_processing/marker_parser.py
import io
import logging
from typing import BinaryIO
from src.domain.interfaces.document_parser import DocumentParser

logger = logging.getLogger(__name__)

class MarkerParser(DocumentParser):
    """PDF parser using Marker (layout-aware, extracts tables as Markdown)."""
    
    def __init__(self, use_llm: bool = False, llm_model: str = "gemini-1.5-flash"):
        self._use_llm = use_llm
        self._llm_model = llm_model
        self._converter = None
    
    def _load_converter(self):
        if self._converter is None:
            try:
                from marker.convert import convert_single_pdf
                from marker.config.parser import ConfigParser
                from marker.models import create_model_dict
                
                config = ConfigParser({})
                if self._use_llm:
                    config["use_llm"] = True
                    config["llm_model"] = self._llm_model
                
                self._converter = lambda pdf_stream: convert_single_pdf(
                    pdf_stream,
                    config=config,
                    model_dict=create_model_dict(),
                )
                logger.info("Marker converter loaded (use_llm=%s)", self._use_llm)
            except ImportError:
                raise ImportError("pip install marker-pdf")
    
    async def parse(self, file: BinaryIO) -> str:
        self._load_converter()
        
        # Reset stream position
        file.seek(0)
        pdf_bytes = file.read()
        pdf_stream = io.BytesIO(pdf_bytes)
        
        try:
            # Marker's convert_single_pdf is sync; run in thread pool
            import asyncio
            full_text, images, metadata = await asyncio.to_thread(
                self._converter, pdf_stream
            )
            
            logger.info("Marker parsed PDF: %d chars, %d pages", len(full_text), metadata.get("page_count", 0))
            return full_text
        except Exception as exc:
            logger.error("Marker parsing failed: %s", exc)
            raise RuntimeError(f"Marker PDF parsing failed: {exc}") from exc
    
    def get_supported_extensions(self) -> list[str]:
        return [".pdf"]
```

```python
# src/infrastructure/document_processing/parser_factory.py (modify)
def create_parser(extension: str) -> DocumentParser:
    extension = extension.lower()
    
    if extension == ".pdf":
        # Try Marker first, fallback to PyMuPDF
        try:
            from src.infrastructure.document_processing.marker_parser import MarkerParser
            return MarkerParser()
        except ImportError:
            logger.warning("Marker not available, falling back to PyMuPDF")
            from src.infrastructure.document_processing.pdf_parser import PDFParser
            return PDFParser()
    
    elif extension == ".docx":
        from src.infrastructure.document_processing.docx_parser import DocxParser
        return DocxParser()
    
    elif extension == ".txt":
        from src.infrastructure.document_processing.txt_parser import TxtParser
        return TxtParser()
    
    else:
        raise ValueError(f"No parser for extension: {extension}")
```

```python
# src/infrastructure/document_processing/pdf_parser.py (upgrade to PyMuPDF)
import io
import fitz  # PyMuPDF
from src.domain.interfaces.document_parser import DocumentParser

class PDFParser(DocumentParser):
    """Fallback PDF parser using PyMuPDF (fitz)."""
    
    async def parse(self, file: BinaryIO) -> str:
        file.seek(0)
        pdf_bytes = file.read()
        
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text_parts = []
        
        for page_num, page in enumerate(doc):
            # Extract text with structure preservation
            text = page.get_text("text", sort=True)
            if text.strip():
                text_parts.append(f"[Page {page_num + 1}]\n{text}")
            
            # Extract tables as markdown
            tabs = page.find_tables()
            for table in tabs:
                md_table = table.to_markdown()
                if md_table:
                    text_parts.append(f"[Page {page_num + 1} Table]\n{md_table}")
        
        doc.close()
        return "\n\n".join(text_parts)
    
    def get_supported_extensions(self) -> list[str]:
        return [".pdf"]
```

**Step 4: Run test to verify pass**
```bash
pip install marker-pdf pymupdf
pytest tests/unit/infrastructure/document_processing/test_marker_parser.py -v
# Expected: PASS
```

**Step 5: Commit**
```bash
git add src/infrastructure/document_processing/marker_parser.py src/infrastructure/document_processing/pdf_parser.py src/infrastructure/document_processing/parser_factory.py tests/unit/infrastructure/document_processing/test_marker_parser.py
git commit -m "feat: upgrade PDF parsing to Marker (layout-aware) + PyMuPDF fallback"
```

---

### Task 1.4: Add Metadata Filtering to Retrieval

**Objective:** Enable filtering by document_id, filename, tags, date ranges at query time.

**Files:**
- Modify: `src/domain/interfaces/vector_store.py` (add filter to similarity_search & hybrid_search)
- Modify: `src/infrastructure/vector_store/chroma_store.py` (pass filter to Chroma where clause)
- Modify: `src/application/services/rag_engine.py` (accept filter param)
- Modify: `src/application/use_cases/query_document.py` (pass filter from API)
- Modify: `src/presentation/api/routes/chat.py` (add filter to request DTO)
- Test: `tests/unit/application/services/test_rag_engine_filter.py`

**Step 1: Write failing test**
```python
# tests/unit/application/services/test_rag_engine_filter.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.application.services.rag_engine import RAGEngine
from src.domain.value_objects.chunk import Chunk

@pytest.mark.asyncio
async def test_query_passes_filter_to_vector_store(rag_engine, mock_vector_store, mock_embedding_provider):
    mock_vector_store.hybrid_search = AsyncMock(return_value=[])
    
    await rag_engine.query("test", top_k=5, filter={"document_id": "doc-123"})
    
    mock_vector_store.hybrid_search.assert_awaited_once()
    call_kwargs = mock_vector_store.hybrid_search.call_args.kwargs
    assert call_kwargs["filter"] == {"document_id": "doc-123"}
```

**Step 2: Run test to verify failure**
```bash
pytest tests/unit/application/services/test_rag_engine_filter.py -v
# Expected: FAIL — TypeError: query() got unexpected keyword argument 'filter'
```

**Step 3: Write minimal implementation**

```python
# src/domain/interfaces/vector_store.py (modify both methods)
@abstractmethod
async def similarity_search(
    self, query_embedding: list[float], k: int, collection_name: str, filter: dict | None = None
) -> list[Chunk]: ...

@abstractmethod
async def hybrid_search(
    self, query_embedding: list[float], query_text: str, k: int, collection_name: str, filter: dict | None = None
) -> list[Chunk]: ...
```

```python
# src/infrastructure/vector_store/chroma_store.py (modify both methods)
# In similarity_search _query():
results = collection.query(
    query_embeddings=[query_embedding],
    n_results=min(k, collection.count()),
    where=filter,  # ADD THIS
    include=["documents", "embeddings", "metadatas", "distances"],
)

# In hybrid_search _query():
results = collection.query(
    query_embeddings=[query_embedding],
    query_texts=[query_text],
    n_results=min(k, collection.count()),
    where=filter,  # ADD THIS
    include=["documents", "embeddings", "metadatas", "distances"],
)
```

```python
# src/application/services/rag_engine.py (modify query signature)
async def query(self, question: str, top_k: int | None = None, filter: dict | None = None) -> dict:
    k = top_k or self.DEFAULT_TOP_K
    
    query_embedding = await self._embedding.embed(question)
    
    collection = self._settings.CHROMA_COLLECTION_NAME
    chunks = await self._vector_store.hybrid_search(
        query_embedding=query_embedding,
        query_text=question,
        k=k,
        collection_name=collection,
        filter=filter,  # PASS FILTER
    )
    # ... rest unchanged
```

```python
# src/application/use_cases/query_document.py (modify execute)
async def execute(self, question: str, conversation_id: str | None = None, top_k: int = 5, filter: dict | None = None) -> dict:
    # ...
    rag_result = await self._rag_engine.query(question=question, top_k=top_k, filter=filter)
    # ...
```

```python
# src/presentation/api/routes/chat.py (modify QueryRequest DTO and endpoint)
# In dto/requests.py - add to QueryRequest:
filter: dict | None = None

# In chat.py query_documents endpoint:
result = await use_case.execute(
    question=request.question,
    conversation_id=request.conversation_id,
    top_k=request.top_k,
    filter=request.filter,  # PASS FILTER
)
```

**Step 4: Run test to verify pass**
```bash
pytest tests/unit/application/services/test_rag_engine_filter.py -v
# Expected: PASS
```

**Step 5: Commit**
```bash
git add src/domain/interfaces/vector_store.py src/infrastructure/vector_store/chroma_store.py src/application/services/rag_engine.py src/application/use_cases/query_document.py src/presentation/api/routes/chat.py src/application/dto/requests.py tests/unit/application/services/test_rag_engine_filter.py
git commit -m "feat: add metadata filtering to retrieval (document_id, tags, etc.)"
```

---

## Phase 2: Retrieval Intelligence (Week 2-3) — HIGH IMPACT

### Task 2.1: Query Rewriting (Multi-Query + HyDE)

**Objective:** Generate multiple query variants, retrieve for each, fuse results via RRF.

**Files:**
- Create: `src/domain/interfaces/query_rewriter.py`
- Create: `src/application/services/query_rewriter.py` (LLM-based multi-query + HyDE)
- Create: `src/infrastructure/llm/query_rewriter_factory.py`
- Modify: `src/application/services/rag_engine.py` (integrate rewriter)
- Test: `tests/unit/application/services/test_query_rewriter.py`

**Step 1: Write failing test**
```python
# tests/unit/application/services/test_query_rewriter.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.application.services.query_rewriter import QueryRewriterService

@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.generate = AsyncMock(return_value="""1. What is machine learning?
2. Define ML
3. Machine learning explanation""")
    return llm

@pytest.mark.asyncio
async def test_rewrite_generates_multiple_queries(mock_llm):
    rewriter = QueryRewriterService(llm_provider=mock_llm)
    queries = await rewriter.rewrite("What is ML?", num_queries=3)
    
    assert len(queries) == 3
    assert "machine learning" in queries[0].lower()
    mock_llm.generate.assert_awaited_once()
```

**Step 2-5: Implement following TDD pattern** (similar structure — skipped for brevity)

**Key Implementation:**
```python
# src/domain/interfaces/query_rewriter.py
from abc import ABC, abstractmethod

class QueryRewriter(ABC):
    @abstractmethod
    async def rewrite(self, query: str, num_queries: int = 3) -> list[str]:
        """Generate rewritten query variants for improved recall."""
        ...

# src/application/services/query_rewriter.py
class QueryRewriterService(QueryRewriter):
    MULTI_QUERY_PROMPT = """Generate {num_queries} diverse search queries that would help answer the original question.
    Original: {query}
    Queries (one per line, no numbering):"""
    
    HYDE_PROMPT = """Write a hypothetical answer to the question. Be detailed and specific.
    Question: {query}
    Hypothetical answer:"""
    
    def __init__(self, llm_provider, embedding_provider, vector_store):
        self._llm = llm_provider
        self._embedding = embedding_provider
        self._vector_store = vector_store
    
    async def rewrite(self, query: str, num_queries: int = 3) -> list[str]:
        # Multi-query rewriting
        prompt = self.MULTI_QUERY_PROMPT.format(num_queries=num_queries, query=query)
        response = await self._llm.generate(prompt)
        queries = [q.strip() for q in response.strip().split("\n") if q.strip()]
        queries = [query] + queries[:num_queries-1]  # Include original
        return queries
    
    async def hyde_embed(self, query: str) -> list[float]:
        """Generate hypothetical document embedding (HyDE)."""
        prompt = self.HYDE_PROMPT.format(query=query)
        hypothetical = await self._llm.generate(prompt)
        return await self._embedding.embed(hypothetical)
```

```python
# src/application/services/rag_engine.py (integrate)
async def query(self, question: str, top_k: int | None = None, filter: dict | None = None, use_query_rewriting: bool = False) -> dict:
    k = top_k or self.DEFAULT_TOP_K
    
    if use_query_rewriting and self._query_rewriter:
        # Generate multiple queries
        queries = await self._query_rewriter.rewrite(question, num_queries=3)
        
        # Retrieve for each query, fuse via RRF
        all_chunks = []
        for q in queries:
            q_emb = await self._embedding.embed(q)
            chunks = await self._vector_store.hybrid_search(q_emb, q, k, self._settings.CHROMA_COLLECTION_NAME, filter)
            all_chunks.append(chunks)
        
        # Reciprocal Rank Fusion
        chunks = self._rrf_fuse(all_chunks, k)
    else:
        # Single query path (existing)
        query_embedding = await self._embedding.embed(question)
        chunks = await self._vector_store.hybrid_search(...)
    
    # ... rest unchanged

def _rrf_fuse(self, all_chunks: list[list[Chunk]], k: int) -> list[Chunk]:
    """Reciprocal Rank Fusion across multiple query results."""
    from collections import defaultdict
    
    chunk_scores = defaultdict(float)
    chunk_map = {}
    
    for rank_list in all_chunks:
        for rank, chunk in enumerate(rank_list):
            chunk_id = str(chunk.id)
            # RRF score: 1 / (k + rank + 1), k=60 default
            chunk_scores[chunk_id] += 1.0 / (60 + rank + 1)
            if chunk_id not in chunk_map:
                chunk_map[chunk_id] = chunk
    
    # Sort by fused score
    sorted_chunks = sorted(chunk_map.values(), key=lambda c: chunk_scores[str(c.id)], reverse=True)
    return sorted_chunks[:k]
```

---

### Task 2.2: Parent-Child Retrieval (Auto-Merging)

**Objective:** Store small chunks (children) for precision, large chunks (parents) for context. Retrieve children, return parent context.

**Files:**
- Create: `src/domain/value_objects/parent_chunk.py`
- Create: `src/application/use_cases/ingest_parent_document.py`
- Modify: `src/infrastructure/vector_store/chroma_store.py` (add parent collection)
- Modify: `src/application/services/rag_engine.py` (parent retrieval logic)
- Test: `tests/unit/application/services/test_parent_retrieval.py`

---

### Task 2.3: Semantic Chunking (Embedding-Based)

**Objective:** Replace fixed-size chunking with semantic boundary detection using embedding similarity.

**Files:**
- Create: `src/infrastructure/document_processing/semantic_splitter.py`
- Modify: `src/infrastructure/document_processing/text_splitter.py` (add strategy parameter)
- Test: `tests/unit/infrastructure/document_processing/test_semantic_splitter.py`

---

### Task 2.4: Chunk Enrichment (Metadata Extractor)

**Objective:** Extract document title, section headers, entities, summaries per chunk.

**Files:**
- Create: `src/application/services/metadata_extractor.py`
- Create: `src/domain/interfaces/metadata_extractor.py`
- Modify: `src/application/use_cases/ingest_document.py` (enrich before embed)
- Test: `tests/unit/application/services/test_metadata_extractor.py`

---

## Phase 3: Observability & Evaluation (Week 3-4) — MEDIUM IMPACT

### Task 3.1: Phoenix Tracing Integration

**Files:**
- Create: `src/infrastructure/observability/phoenix_tracer.py`
- Modify: `src/application/services/rag_engine.py` (add @traceable decorators)
- Modify: `src/presentation/api/app.py` (init tracer)
- docker-compose.yml: add phoenix service

### Task 3.2: RAGAS Evaluation Pipeline

**Files:**
- Create: `eval/ragas_eval.py` (golden dataset + metrics)
- Create: `eval/golden_dataset.jsonl` (QA pairs)
- Modify: `.github/workflows/ci.yml` (add eval stage)
- Test: `eval/test_ragas_metrics.py`

### Task 3.3: Token Usage & Cost Tracking

**Files:**
- Create: `src/infrastructure/llm/token_tracker.py`
- Modify: LLM providers (wrap generate with tracking)
- Create: `src/presentation/api/routes/usage.py` (GET /api/usage)

### Task 3.4: Structured Output for Citations

**Files:**
- Create: `src/application/dto/structured_answer.py` (Pydantic model)
- Modify: `src/application/services/rag_engine.py` (use Instructor)
- Modify: LLM providers (add JSON mode support)

---

## Phase 4: Production Hardening (Week 4-5) — MEDIUM IMPACT

### Task 4.1: PostgreSQL Conversation Repository

**Files:**
- Create: `src/infrastructure/repositories/postgres_conversation_repository.py`
- Create: `alembic/env.py` + migrations
- Modify: `src/infrastructure/config/settings.py` (DATABASE_URL)
- Modify: `src/presentation/api/app.py` (wire based on env)

### Task 4.2: API Authentication + Rate Limiting

**Files:**
- Create: `src/infrastructure/auth/` (FastAPI-Users setup)
- Modify: `src/presentation/api/app.py` (add auth middleware)
- Modify: All routes (add Depends(current_active_user))
- Test: `tests/integration/test_auth.py`

### Task 4.3: Incremental Ingestion (Hash-Based)

**Files:**
- Modify: `src/application/use_cases/ingest_document.py` (compute SHA256, check existing)
- Modify: `src/domain/entities/document.py` (add content_hash field)
- Test: `tests/unit/application/use_cases/test_incremental_ingest.py`

### Task 4.4: Guardrails Integration

**Files:**
- Create: `src/infrastructure/guardrails/` (PII, injection, hallucination checks)
- Modify: `src/application/services/rag_engine.py` (pre/post guardrails)
- Test: `tests/unit/infrastructure/guardrails/test_guardrails.py`

### Task 4.5: Frontend Streaming Migration

**Files:**
- Modify: `src/presentation/react/src/components/ChatWidget.jsx` (use EventSource)
- Modify: `src/presentation/react/src/api.js` (add stream function)

---

## Phase 5: Advanced & Scale (Week 6+) — LOW IMPACT

### Task 5.1: Qdrant Vector Store Implementation

### Task 5.2: GraphRAG / Knowledge Graph

### Task 5.3: LangGraph Agentic RAG

### Task 5.4: Prompt Versioning / A/B Testing

### Task 5.5: Kubernetes Deployment

---

## Verification Checklist per Phase

| Phase | Verification Command | Success Criteria |
|-------|---------------------|------------------|
| 1 | `pytest tests/ -k "rerank or hybrid or marker or filter" -v` | All new tests pass; existing tests still pass |
| 2 | `pytest tests/ -k "rewrite or parent or semantic or enrich" -v` | All new tests pass; recall@10 improves >15% |
| 3 | `pytest eval/ -v` + open Phoenix UI | RAGAS faithfulness >0.8, traces visible |
| 4 | `pytest tests/integration/test_auth.py -v` + load test | Auth works; 100 req/s sustained |
| 5 | Deploy to staging K8s | Horizontal scaling works |

---

## References & Implementation Patterns

| Feature | Reference Implementation | Key Pattern |
|---------|-------------------------|-------------|
| **Reranking** | `sentence-transformers.CrossEncoder` + `langchain.retrievers.ContextualCompressionRetriever` | Cross-encoder on top-k |
| **Hybrid Search** | Chroma `query_texts` + `query_embeddings` / Qdrant `prefetch` + RRF | Native vector store fusion |
| **Query Rewriting** | LangChain `MultiQueryRetriever` / LlamaIndex `QueryRewriter` | LLM generates variants → RRF |
| **HyDE** | LlamaIndex `HyDEQueryTransform` / LangChain `HypotheticalDocumentEmbedder` | Embed hypothetical answer |
| **Parent-Child** | LangChain `ParentDocumentRetriever` / LlamaIndex `AutoMergingRetriever` | Small chunks index, large chunks retrieve |
| **Semantic Chunking** | LlamaIndex `SemanticSplitterNodeParser` | Embedding similarity boundaries |
| **Evaluation** | RAGAS (faithfulness, answer_relevancy, context_precision, context_recall) | LLM-as-judge metrics |
| **Observability** | Phoenix (Arize) / LangSmith / LangFuse | OpenTelemetry traces |
| **PDF Parsing** | Marker / Docling / Unstructured.io | Layout-aware + table extraction |
| **Guardrails** | Guardrails AI / NeMo Guardrails | Rail spec validation |

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| BGE reranker slow on CPU | Use `onnxruntime` quantization; batch rerank; optional GPU |
| Marker heavy dependencies | Make optional; fallback to PyMuPDF; Docker layer caching |
| Phoenix adds latency | Sample 10% traces in prod; async export |
| RAGAS needs LLM calls | Run eval async in CI; cache golden embeddings |
| Migration to Qdrant breaks | Keep Chroma interface; dual-write during transition |

---

## Next Steps

1. **Start Phase 1 Task 1.1** — Reranker interface + BGE implementation (highest ROI)
2. **Run baseline evaluation** before any changes (save current RAGAS scores)
3. **Enable Phoenix** immediately for free observability
4. **Commit after every task** — frequent, small commits

---

**Plan saved to:** `.hermes/plans/2026-08-02_QA-Assistant-Production-Roadmap.md`

Ready to execute using subagent-driven-development. Shall I proceed with Phase 1 Task 1.1?
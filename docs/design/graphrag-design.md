# GraphRAG / Knowledge Graph — Design Proposal

> **Status: Design proposal — not implemented.**
> Exploratory design document only. No code, no settings changes, no tests, no commits.
> Created: 2026-08-10 · Repo: QA-Assistant · Branch: main · HEAD: `b0fb457`

---

## 1. Problem Statement

**Capability gap.** Current retrieval is purely vector/lexical over flat chunks. `RAGEngine.query()` and `query_stream()` embed the question and retrieve top-k chunks from `ChromaStore.similarity_search()` / `hybrid_search()` (optionally expanded to parents and reranked). This answers *single-hop* questions well but cannot traverse *relationships* between entities that live in different chunks or documents. Multi-hop questions — e.g. *"Which suppliers does the vendor named in the Q3 report use?"* — must be answered by the LLM guessing connections that were never retrieved, or they fail with `NO_RELEVANT_CONTEXT_MESSAGE`. There is no entity-centric view of the corpus and no cross-document synthesis.

**Value vs. effort.** The production roadmap (`.hermes/plans/2026-08-02_QA-Assistant-Production-Roadmap.md`, Task 5.2) labels GraphRAG **LOW IMPACT** within Phase 5 "Advanced & Scale (Week 6+)". That label is fair:

- **Value (modest):** higher recall on relational/multi-hop questions; entity browsing; better cross-document answers. For the current profile — single user, uploaded PDF/DOCX/TXT documents, mostly single-hop factual QA — the realistic hit-rate gain is small.
- **Effort (high):** an LLM extraction pass over every chunk at ingest (token cost + ingest latency), a second storage layer with delete/update coherence against Chroma, entity-resolution quality work, and a new retrieval path that must be evaluated with the existing `eval/` RAGAS harness before it can be trusted.

The gap is real but not currently user-facing; the fix is expensive relative to the corpus it serves.

---

## 2. Proposed Architecture

### Layers (Clean Architecture placement)

| Layer | New / Changed | Responsibility |
|---|---|---|
| **Domain** | NEW `src/domain/interfaces/knowledge_graph.py` — `KnowledgeGraphStore` ABC mirroring the `VectorStore` pattern (`add_entities`, `add_relations`, `local_search(seed_ids, max_hops, k)`, `delete_by_document_id`, `get_stats`). NEW value objects `src/domain/value_objects/entity.py` (`Entity`) and `relation.py` (`Relation`), analogous to `Chunk` | Contracts; no framework imports |
| **Application** | NEW `src/application/services/graph_extraction_service.py` — orchestrates per-chunk extraction, resolution, and writes. MODIFIED `src/application/use_cases/ingest_document.py` — optional post-embed graph build step | Orchestration, feature-gating |
| **Infrastructure** | NEW `src/infrastructure/knowledge_graph/networkx_store.py` (default backend) and `neo4j_store.py` (optional). MODIFIED `src/infrastructure/llm/prompt_registry.py` — extraction prompt template (JSON mode) | Persistence + LLM extraction, all framework code |
| **Presentation** | Unchanged initially; only touched if entity browsing becomes a product feature | — |

### Data flow

**Ingest (additive to `IngestDocumentUseCase`, behind `ENABLE_GRAPH_RAG`):**

```
parse → split → enrich → embed → store (existing path, untouched)
                              ∥  (NEW, parallel/async, feature-gated)
           chunk → LLM extraction (generate_json) → resolve/dedupe → write graph store
```

Extraction reuses the configured `LLMProvider` via its existing `generate_json()` (already proven in `src/infrastructure/llm/structured_output.py`); no new provider is needed and `LLMProviderFactory` is unchanged.

**Query (additive to both `RAGEngine.query()` and `query_stream()`):**

```
embed → similarity/hybrid search → [NEW] graph expansion of retrieved chunks
      → union + dedupe → parent-child expand → rerank → prompt → generate
```

The new step: collect entity names mentioned in retrieved chunks (stored as `entity_mentions` in chunk metadata during ingest), run a bounded local traversal (`GRAPH_MAX_HOPS`), map relations back to their provenance `chunk_id`s, union with the vector results, and dedupe. Every existing step is untouched; when the flag is off the step is a no-op and behavior is byte-identical.

### Additive / feature-gated fit

Exactly mirrors the established convention used throughout `rag_engine.py` (`getattr(settings, "ENABLE_...", False)` — cf. `ENABLE_QUERY_REWRITING`, `ENABLE_PARENT_CHILD`, `ENABLE_HYBRID_SEARCH`). The graph store is injected as an optional dependency into `RAGEngine` (like `reranker` / `query_rewriter` today) and into `IngestDocumentUseCase` (like `chunk_enricher`). All defaults OFF.

---

## 3. Data Model Changes

### Entity / relation extraction

- One LLM call per chunk (JSON mode via `generate_json`) returning `[{entity: name, type, description}]` and `[{source, target, type, description}]`.
- Entity resolution: canonical normalization (case-fold, whitespace collapse), dedupe by canonical name; relations weighted by co-occurrence count.
- Full provenance on every record: `document_id`, `chunk_id` (and `chunk_index`), so citations can be traced back to chunks and deletes can cascade — the same provenance discipline `ChromaStore` applies via `_build_chroma_metadata()`.

### Storage options

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **networkx** (in-memory + JSON persistence under `./data/graph`, mirroring `CHROMA_PERSIST_DIR=./data/chroma`) | Zero new infrastructure; pure-Python; cheap bounded traversal; matches the local-first pattern of ChromaDB | No graph query language; memory-bound; rebuild from extraction on cache loss | **Default backend** |
| **Neo4j** | Real Cypher queries, scale, community tooling | Requires a server (ops burden); heavyweight dependency; overkill for single-user corpus | **Optional backend** behind `GRAPH_STORE_BACKEND="neo4j"` |
| **Postgres tables** (`entities`, `relations`) | Reuses the existing optional `postgres` extra (`sqlalchemy` + `asyncpg`) and `DATABASE_URL` | SQL joins are awkward for multi-hop traversal; schema churn; only viable when `DATABASE_URL` is already set | **Fallback** if a DB becomes mandatory |

### Indexing flow

```
per-chunk extraction → normalization/resolution → upsert entities (with chunk_ids list)
→ upsert relations (weight, provenance) → per-document cascade delete on re-upload/delete
```

Re-uploads are already deduplicated by content hash when `ENABLE_INCREMENTAL_INGESTION` is on (`compute_content_hash` in `ingest_document.py`); the graph build is skipped for duplicates, preventing extraction drift.

---

## 4. Integration Points

### Modules that would change (when the feature is built)

- `src/infrastructure/config/settings.py` — new flags (below)
- `src/domain/interfaces/knowledge_graph.py`, `src/domain/value_objects/entity.py`, `src/domain/value_objects/relation.py` — **new**
- `src/infrastructure/knowledge_graph/` (`networkx_store.py`, optional `neo4j_store.py`) — **new**
- `src/application/services/graph_extraction_service.py` — **new**
- `src/application/use_cases/ingest_document.py` — optional graph-build step (pattern: `_enrich_chunks`)
- `src/application/services/rag_engine.py` — optional expansion step in both `query()` and `query_stream()`
- `src/infrastructure/llm/prompt_registry.py` — extraction prompt template (separate from `PROMPT_VERSIONS`)
- `pyproject.toml` — new optional-dependency extras

### New settings (all default OFF / empty)

| Setting | Default | Purpose |
|---|---|---|
| `ENABLE_GRAPH_RAG` | `False` | Master gate for the whole feature |
| `GRAPH_STORE_BACKEND` | `"networkx"` | `"networkx"` \| `"neo4j"` \| `"postgres"` |
| `GRAPH_PERSIST_DIR` | `"./data/graph"` | networkx persistence location |
| `GRAPH_EXTRACTION_BATCH_SIZE` | `10` | Chunks per extraction batch (cost/latency control) |
| `GRAPH_MAX_HOPS` | `2` | Traversal depth bound at query time |
| `GRAPH_EXPANSION_K` | `3` | Max graph-derived chunks added per query |
| `GRAPH_NEO4J_URL` / `GRAPH_NEO4J_USER` / `GRAPH_NEO4J_PASSWORD` | `""` | Only validated when backend is `neo4j` |

### New optional dependencies + why

- `networkx>=3.0` — default in-process graph backend; pure Python, no native build. New extra: `graphrag = ["networkx>=3.0"]`.
- `neo4j>=5.0` — driver for the optional server backend only. New extra: `graphrag-neo4j = ["neo4j>=5.0"]`.

This mirrors the existing extras pattern (`tracing`, `postgres`) in `pyproject.toml`. Extraction needs **no** new AI dependency — it reuses the configured `LLMProvider`.

---

## 5. Risks & Mitigations

Aligned with the roadmap risk table (lines 980–988).

| Risk | Mitigation |
|---|---|
| **Extraction cost** — one LLM call per chunk; a 50 MB PDF can be hundreds of chunks | `GRAPH_EXTRACTION_BATCH_SIZE` batching; skip extraction for small/trivial docs; skip duplicates via existing `compute_content_hash`; run extraction only while the flag is on |
| **Ingest latency** — extraction serializes the upload path | Run graph build as a background task after the vector write succeeds; upload response returns on the existing path, matching the roadmap's "make heavy work optional/async" stance |
| **Entity quality** — LLM hallucinated entities/relations poison the graph | Prompt constraints (entities must appear in chunk text); description + confidence fields; provenance (`chunk_id`) kept on every record so bad edges are traceable and removable |
| **Dependency weight** — Neo4j server + driver | Default backend is networkx (pure Python); Neo4j is an extra the deployment must opt into — same policy as the roadmap's "Marker heavy dependencies → make optional" |
| **Dual-store consistency** — Chroma and graph drift on delete/re-upload | `delete_by_document_id` cascade; duplicate detection skips re-extraction; graph is internal-only, so document listing (`ChromaStore.list_documents`) is unaffected |
| **Query latency** — traversal at request time | Bounded traversal (`GRAPH_MAX_HOPS=2`, `GRAPH_EXPANSION_K=3`) on an in-memory graph is sub-millisecond; measured via existing `ENABLE_TRACING` spans (cf. roadmap "Phoenix adds latency → sample 10% in prod") |

---

## 6. Decision Recommendation

**Defer** (revisit only if evaluation or user demand justifies it).

1. The roadmap itself rates GraphRAG **LOW IMPACT** (Phase 5), and no committed milestone depends on it.
2. The current corpus — user-uploaded documents, single-user, predominantly single-hop factual QA — is well served by the existing vector/hybrid/parent-child retrieval stack; multi-hop questions are rare and unquantified.
3. Cost is disproportionate: per-chunk LLM extraction, a second storage layer with lifecycle coherence, and entity-resolution tuning for a modest recall gain.
4. The deferral cost is ~zero: the graph is an independent store, so adding it later requires no migration of existing Chroma data and no change to the `RAGEngine` response contract.
5. Concrete revisit triggers: (a) `eval/` RAGAS scores on a curated multi-hop question set show a measurable recall gap; (b) users request entity navigation or cross-document synthesis; (c) corpus grows beyond roughly a thousand chunks with measured retrieval failures.

---

## 7. Phased Rollout Sketch (if adopted)

**Phase 1 — Foundation (no behavior change).** `KnowledgeGraphStore` interface + networkx store + `Entity`/`Relation` value objects + extraction service, all behind `ENABLE_GRAPH_RAG` (off). Unit tests only. `RAGEngine` untouched.

**Phase 2 — Retrieval.** Graph-expansion step added to `query()` and `query_stream()`; RAGAS eval harness (existing `eval/`) compares baseline vs. graph-augmented on single-hop and multi-hop question sets; tune `GRAPH_EXPANSION_K` / `GRAPH_MAX_HOPS`.

**Phase 3 — Hardening.** Delete/update coherence with incremental ingestion; background extraction task; optional Neo4j backend and Postgres persistence; tracing spans; documentation.

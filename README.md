# Marginalia

A production-grade **Retrieval-Augmented Generation (RAG)** question-answering app. Upload PDF, DOCX, or TXT documents, ask questions in natural language, and get grounded answers with source citations and a confidence score.

[![CI](https://github.com/prakashseervi61/QA-Assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/prakashseervi61/QA-Assistant/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ed)](#docker)

---

## Highlights

- **Multi-format ingestion** — PDF (PyMuPDF with PyPDF2 fallback), DOCX, and TXT
- **Full RAG pipeline** — embed → retrieve → rerank → generate, with citations and confidence
- **4 LLM providers** — Gemini, OpenAI, Anthropic, DeepSeek (OpenAI-compatible) via a single config line
- **3 embedding providers** — Gemini, OpenAI, and local HuggingFace (no API key, free)
- **Advanced retrieval (opt-in)** — hybrid search, query rewriting with Reciprocal Rank Fusion (RRF), BGE cross-encoder reranking, parent-child retrieval, semantic chunking, and chunk enrichment
- **Streaming answers** — Server-Sent Events endpoint for token-by-token output
- **Conversations** — multi-turn history, persistable to PostgreSQL, restorable from the UI
- **Safety & ops (opt-in)** — JWT authentication, per-IP rate limiting, PII / prompt-injection / hallucination guardrails, token-usage tracking, and OpenTelemetry tracing
- **Clean Architecture** — `domain → application → infrastructure → presentation` with dependency injection

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                       React + Vite + Tailwind                  │
│            Documents · Chat · Recent · Collections · Settings  │
└───────────────────────────────┬────────────────────────────────┘
                                │  /api/*   (Vite proxy / nginx)
┌───────────────────────────────▼────────────────────────────────┐
│                         FastAPI + Uvicorn                      │
│  auth (JWT) · rate limiting · CORS                             │
│  routes: health · auth · documents · chat · usage              │
└───────────────────────────────┬────────────────────────────────┘
                                │ use cases (query · ingest · conversation)
┌───────────────────────────────▼────────────────────────────────┐
│                         RAGEngine                               │
│  guardrails → query rewrite → embed → hybrid/vector search →   │
│  parent-child expand → rerank → prompt (versioned) → LLM        │
└───────┬───────────────┬────────────────┬───────────────────────┘
        │               │                │
┌───────▼──────┐ ┌──────▼───────┐ ┌──────▼───────────────────────┐
│ LLM factory  │ │  Embeddings  │ │ ChromaDB vector store        │
│ gemini/openai│ │ gemini/openai│ │ (+ conversations repository: │
│ anthropic/   │ │ huggingface  │ │ in-memory or PostgreSQL)     │
│ deepseek     │ │              │ │                              │
└──────────────┘ └──────────────┘ └──────────────────────────────┘
```

## Features in Detail

### Ingestion pipeline

`file bytes → parse → split → (enrich) → embed → store`

- **Parsers**: PyMuPDF (primary) with PyPDF2 fallback, python-docx, plain text, and a Marker-PDF backend for complex layouts.
- **Chunking strategies** (pick one via config):
  - **Fixed-size** (`TextSplitter`) — sentence-boundary-aware, default `CHUNK_SIZE=1000`, `CHUNK_OVERLAP=200`.
  - **Semantic chunking** (`ENABLE_SEMANTIC_CHUNKING`) — splits on embedding-similarity dips.
  - **Parent-child** (`ENABLE_PARENT_CHILD`) — retrieves small child chunks, expands them to their larger parents for the LLM prompt.
- **Chunk enrichment** (`ENABLE_CHUNK_ENRICHMENT`) — adds extracted keywords and (optionally, `ENABLE_CHUNK_ENRICHMENT_SUMMARIES`) summaries to chunk metadata.
- **Incremental ingestion** (`ENABLE_INCREMENTAL_INGESTION`) — re-uploading a byte-identical file (same SHA-256 content hash) is detected as a duplicate and skipped without re-parsing/embedding.

### Retrieval & generation

- **Hybrid search** (`ENABLE_HYBRID_SEARCH`) — combines dense vector similarity with BM25 keyword search.
- **Query rewriting** (`ENABLE_QUERY_REWRITING`) — the LLM generates diverse query variants; results are fused with **Reciprocal Rank Fusion** (RRF). HyDE embeddings are implemented (see `query_rewriter.py`) but not yet wired into the query path.
- **Reranking** (`ENABLE_RERANKING`) — `BAAI/bge-reranker-v2-m3` cross-encoder re-scores retrieved chunks.
- **Versioned prompts** (`PROMPT_VERSION`) — system prompts live in a registry; unknown versions fall back to `v1` with a logged warning.
- **Structured output** — an engine-level option (`use_structured_output=True` on `RAGEngine.query`) returns a JSON answer with per-chunk citations. Not exposed via an env var yet because the chat API contract does not carry the citations field end-to-end.
- **Graceful no-context handling** — the engine distinguishes "no documents uploaded" from "nothing relevant found" and returns a friendly message instead of failing.

### Safety & observability (all opt-in)

- **Guardrails** (`ENABLE_GUARDRAILS`) — regex-based PII detection (email, phone, SSN, credit card, IP), prompt-injection detection, and a groundedness (hallucination) heuristic. Flag-only by default; block with `GUARDRAIL_BLOCK_VIOLATIONS`.
- **Authentication** (`ENABLE_AUTH`) — HMAC-SHA256 JWT-shaped tokens (stdlib only, no third-party lib), an API-key → token endpoint, and PBKDF2 password hashing helpers.
- **Rate limiting** (`ENABLE_RATE_LIMITING`) — in-memory sliding window per client IP.
- **Usage tracking** (`ENABLE_USAGE_TRACKING`, default on) — records per-call LLM token usage and estimated cost; exposed via `GET /api/usage`.
- **Tracing** (`ENABLE_TRACING`) — OpenTelemetry spans (retrieval, rerank, generation) exported to Phoenix or any OTLP endpoint.

---

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+ and npm (frontend)
- An LLM provider API key (Gemini is the default; Google AI Studio free tier works)

### 1. Clone & install

```bash
git clone https://github.com/prakashseervi61/QA-Assistant.git
cd QA-Assistant
python -m venv .venv
# Windows: .venv\Scripts\activate   ·   macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Frontend dependencies

```bash
cd src/presentation/react
npm install
```

### 3. Configure

```bash
cp .env.example .env
```

Edit `.env` and set your LLM key. The defaults are **Gemini** for the LLM and **HuggingFace (local)** for embeddings — zero API cost for embeddings:

```bash
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key_here
EMBEDDING_PROVIDER=huggingface
```

### 4. Run

One command (Git Bash):

```bash
bash scripts/start_all.sh
```

Or two terminals:

```bash
# Terminal 1 — API
uvicorn src.presentation.api.app:create_app --factory --reload --port 8000

# Terminal 2 — Frontend (from repo root)
cd src\presentation\react   # Windows
npm run dev
```

### 5. Open

| Service | URL |
|---|---|
| Frontend (React) | http://localhost:3000 |
| API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |

The Vite dev server proxies `/api/*` to `http://localhost:8000` (`src/presentation/react/vite.config.js`), so the frontend and API work together with no extra setup.

## Docker

```bash
docker compose up --build
```

| Service | Host port | Notes |
|---|---|---|
| API (uvicorn) | 8000 | Boots the `create_app` factory; healthcheck on `/api/health` |
| Frontend (nginx) | 3000 | Serves the built React app; `proxy_buffering off` keeps SSE flowing |
| Phoenix (tracing) | 6006 | Optional OTLP trace collector (`ENABLE_TRACING=true`) |

- ChromaDB persists in the `chroma_data` volume (mounted at `/data/chroma`).
- `.env` values are passed to the API container via `environment` (`LLM_PROVIDER`, `GEMINI_API_KEY`, `EMBEDDING_PROVIDER`, chunking settings, tracing settings). Set `GEMINI_API_KEY` before `compose up`.
- The frontend container waits for the API healthcheck to pass before starting.

## Configuration Reference

All settings load from `.env` or environment variables via `pydantic-settings` (`src/infrastructure/config/settings.py`). Every variable is optional — the code default is shown.

### Core

| Variable | Default | Description |
|---|---|---|
| `APP_NAME` | `Marginalia` | FastAPI app title |
| `DEBUG` | `false` | Reserved — enable debug mode |
| `LOG_LEVEL` | `INFO` | Reserved — logging level |
| `LLM_PROVIDER` | `gemini` | `gemini`, `openai`, `anthropic`, `deepseek` |
| `GEMINI_API_KEY` | `""` | Required when using Gemini |
| `GEMINI_MODEL` | `gemini-2.5-flash` | |
| `OPENAI_API_KEY` | `""` | Required when using OpenAI |
| `OPENAI_MODEL` | `gpt-4o` | |
| `ANTHROPIC_API_KEY` | `""` | Required when using Anthropic |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | |
| `DEEPSEEK_API_KEY` | `""` | Required when using DeepSeek |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | |
| `EMBEDDING_PROVIDER` | `huggingface` | `gemini`, `openai`, `huggingface` (local, free) |
| `GEMINI_EMBEDDING_MODEL` | `text-embedding-004` | |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | |
| `HUGGINGFACE_MODEL` | `all-MiniLM-L6-v2` | Local model, downloaded on first use |
| `CHROMA_PERSIST_DIR` | `./data/chroma` | ChromaDB storage directory |
| `CHROMA_COLLECTION_NAME` | `documents` | ChromaDB collection name |
| `CHUNK_SIZE` | `1000` | Characters per chunk |
| `CHUNK_OVERLAP` | `200` | Overlap between consecutive chunks |
| `MAX_FILE_SIZE_MB` | `50` | Reserved — not enforced by the API |
| `ALLOWED_EXTENSIONS` | `[".pdf", ".docx", ".txt"]` | Accepted upload extensions |
| `API_HOST` | `0.0.0.0` | Reserved — uvicorn launched with explicit host |
| `API_PORT` | `8000` | Reserved — uvicorn launched with explicit port |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed CORS origins (JSON list) |
| `DATABASE_URL` | `None` | PostgreSQL URL for persistent conversations (requires `pip install -e ".[postgres]"`); unset = in-memory storage |

### Advanced RAG (feature flags)

| Variable | Default | Description |
|---|---|---|
| `ENABLE_RERANKING` | `false` | Re-score retrieved chunks with a BGE cross-encoder |
| `RERANKER_MODEL` | `BAAI/bge-reranker-v2-m3` | |
| `ENABLE_HYBRID_SEARCH` | `false` | Dense vector + BM25 keyword search |
| `ENABLE_QUERY_REWRITING` | `false` | LLM multi-query variants fused with RRF |
| `QUERY_REWRITING_VARIANTS` | `3` | Total queries (original + variants) |
| `ENABLE_PARENT_CHILD` | `false` | Retrieve children, prompt with parents |
| `PARENT_CHUNK_SIZE` | `2000` | |
| `CHILD_CHUNK_SIZE` | `200` | |
| `CHILD_CHUNK_OVERLAP` | `50` | |
| `ENABLE_SEMANTIC_CHUNKING` | `false` | Split on embedding-similarity dips |
| `SEMANTIC_SIMILARITY_THRESHOLD` | `0.5` | |
| `SEMANTIC_MIN_CHUNK_SIZE` | `100` | |
| `SEMANTIC_MAX_CHUNK_SIZE` | `2000` | |
| `ENABLE_CHUNK_ENRICHMENT` | `false` | Extract keywords into chunk metadata |
| `ENABLE_CHUNK_ENRICHMENT_SUMMARIES` | `false` | Also add LLM-generated summaries |
| `CHUNK_ENRICHMENT_MAX_KEYWORDS` | `10` | |
| `ENABLE_INCREMENTAL_INGESTION` | `false` | Skip byte-identical re-uploads (SHA-256 dedup) |
| `PROMPT_VERSION` | `v1` | RAG system-prompt template version |

> Parent-child retrieval overrides semantic chunking in the upload route; both are off by default. Enable at most one chunking mode at a time.

### Safety & ops

| Variable | Default | Description |
|---|---|---|
| `ENABLE_AUTH` | `false` | Require a JWT bearer token on all routes except `/api/health` and `/api/auth/token` |
| `SECRET_KEY` | `dev-secret-change-me` | HMAC signing key; **must** be overridden when `ENABLE_AUTH=true` (startup fails otherwise) |
| `AUTH_API_KEY` | `""` | API key exchanged for a JWT via `POST /api/auth/token`; empty = endpoint rejects all keys |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | JWT lifetime |
| `ENABLE_RATE_LIMITING` | `false` | Per-IP sliding-window rate limit (in-memory, resets on restart) |
| `RATE_LIMIT_MAX_REQUESTS` | `60` | |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | |
| `ENABLE_GUARDRAILS` | `false` | PII + prompt-injection input checks, groundedness + PII-leak output checks |
| `GUARDRAIL_BLOCK_VIOLATIONS` | `false` | Flag-only by default; set `true` to block flagged inputs before the LLM |
| `GUARDRAIL_GROUNDEDNESS_THRESHOLD` | `0.2` | Below this score the output is flagged |
| `ENABLE_USAGE_TRACKING` | `true` | Record LLM token usage & cost; exposes `GET /api/usage` |
| `ENABLE_TRACING` | `false` | Emit OpenTelemetry spans to `TRACING_ENDPOINT` |
| `TRACING_ENDPOINT` | `http://localhost:6006/v1/traces` | OTLP HTTP endpoint |
| `TRACING_SERVICE_NAME` | `qa-assistant` | Service name reported to the trace backend |

### Optional dependency extras

```bash
pip install -e ".[tracing]"    # OpenTelemetry (required for ENABLE_TRACING)
pip install -e ".[postgres]"   # SQLAlchemy + asyncpg (required for DATABASE_URL)
```

Tracing degrades gracefully: if enabled but the packages are missing, the app logs a warning and uses a no-op tracer.

---

## API Reference

All routes are served under the `/api` prefix. `/api/health` and `/api/auth/token` are public; everything else requires a valid JWT when `ENABLE_AUTH=true` and is subject to rate limiting when `ENABLE_RATE_LIMITING=true`.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Liveness/readiness probe |
| `POST` | `/api/auth/token` | Exchange an API key for a JWT |
| `POST` | `/api/documents/upload` | Upload & ingest a document (multipart field `file`) |
| `GET` | `/api/documents` | List ingested documents |
| `DELETE` | `/api/documents/{id}` | Delete a document and its chunks |
| `POST` | `/api/query` | Ask a question (non-streaming) |
| `POST` | `/api/query/stream` | Ask a question (streaming SSE) |
| `GET` | `/api/conversations` | List recent conversations (max 10, newest first) |
| `GET` | `/api/conversations/{id}` | Get a conversation's messages |
| `GET` | `/api/usage` | LLM token usage summary & recent records |

### `GET /api/health`

```json
{ "status": "healthy", "version": "0.1.0", "vector_store": "initialized" }
```

### `POST /api/auth/token`

Request:

```json
{ "api_key": "your_api_key_here" }
```

Response (the key is compared in constant time; any mismatch returns `401`):

```json
{ "access_token": "<jwt>", "token_type": "bearer", "expires_in": 3600 }
```

Use the token as `Authorization: Bearer <jwt>`.

### `POST /api/documents/upload`

Multipart form with a single `file` field. Accepts `.pdf`, `.docx`, `.txt`. Returns `400` for an unsupported type, empty file, or missing filename; `500` if ingestion fails.

```json
{
  "document_id": "3f0c...",
  "filename": "report.pdf",
  "chunk_count": 12,
  "message": "Successfully ingested 'report.pdf'. 12 chunks stored."
}
```

With `ENABLE_INCREMENTAL_INGESTION=true`, a byte-identical re-upload returns `"status": "duplicate"` and skips processing.

### `GET /api/documents`

```json
{
  "documents": [
    {
      "id": "3f0c...",
      "filename": "report.pdf",
      "content_type": ".pdf",
      "file_size": 1048576,
      "chunk_count": 12,
      "created_at": "2026-07-31T10:00:00"
    }
  ],
  "total": 1
}
```

Returns an empty list (HTTP 200) when no documents have been uploaded.

### `DELETE /api/documents/{id}`

```json
{ "message": "Document 3f0c... deleted successfully." }
```

### `POST /api/query`

Request body:

```json
{ "question": "What are the key findings?", "top_k": 5, "conversation_id": null, "metadata_filter": null }
```

- `question` — required, 1–5000 characters
- `top_k` — optional, 1–20 (default 5)
- `conversation_id` — optional UUID; omit to start a new conversation
- `metadata_filter` — optional scalar dict, e.g. `{"document_id": "abc"}`

Response:

```json
{
  "answer": "The report finds that...",
  "sources": [
    { "content": "excerpt (first 500 chars)", "metadata": { "filename": "report.pdf", "chunk_index": 3 }, "score": 0.87, "chunk_index": 3 }
  ],
  "confidence": 0.81,
  "conversation_id": "3f0c...",
  "message_id": "9a2b..."
}
```

Status codes: `400` invalid question / filter / conversation ID · `404` conversation not found · `429` LLM quota or rate-limit exceeded · `500` RAG pipeline failure.

When no documents exist yet, `answer` is a friendly "no documents uploaded" message; when documents exist but nothing matched, it explains no relevant context was found.

### `POST /api/query/stream`

Same request body as `/api/query`. Responds with `text/event-stream` (`Cache-Control: no-cache`, `Connection: keep-alive`, `X-Accel-Buffering: no`). Each event is JSON with a `type` field:

- `chunk` — incremental answer text: `{"type": "chunk", "content": "..."}`
- `done` — final summary with answer, sources, confidence, and conversation/message IDs
- `error` — error message: `{"type": "error", "message": "..."}`
- `blocked` — (with guardrails) an input check blocked the query
- Terminates with `data: [DONE]`

Contract: even on LLM quota/rate-limit errors the response stays HTTP 200 and emits an `error` event followed by `[DONE]`, so streaming clients always see well-formed termination.

> The current React UI calls the non-streaming `POST /api/query`; the SSE endpoint is part of the API contract for token-by-token clients.

### `GET /api/conversations`

```json
[
  { "id": "3f0c...", "title": "What are the key findings?", "created_at": "...", "updated_at": "...", "message_count": 4 }
]
```

Only conversations with at least one message are returned, newest first (limit 10).

### `GET /api/conversations/{id}`

```json
[
  { "id": "9a2b...", "role": "user", "content": "What are the key findings?", "sources": [], "created_at": "..." }
]
```

Status codes: `400` invalid UUID · `404` conversation not found.

### `GET /api/usage`

```json
{
  "requests": 3,
  "prompt_tokens": 300,
  "completion_tokens": 150,
  "total_tokens": 450,
  "est_cost_usd": 0.0012,
  "recent": [
    { "model": "gemini-2.5-flash", "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150, "timestamp": 1789123456.78, "request_id": "..." }
  ]
}
```

Optional query param `limit` (1–100, default 10). Zeroed totals and an empty `recent` list when `ENABLE_USAGE_TRACKING=false`. Records are per-process and reset on restart.

---

## Frontend

A responsive React SPA (Tailwind CSS) with a slide-in chat panel (mobile) that is always visible on desktop. Five sidebar views:

| View | What it does |
|---|---|
| **Documents** | Upload (drag & drop or file picker), list, and delete documents; shows ingestion status and chunk counts |
| **Chat** | Ask questions with a conversation selector (last conversation persists in `localStorage`); answers render `[Source N]` markers with an expandable **SOURCES** panel showing each cited chunk and its score |
| **Recent** | Lists past conversations (title, message count, relative time); click to reopen the conversation in Chat |
| **Collections** | Placeholder — grouping documents is planned |
| **Bookmarks** | Placeholder — saving answers is planned |
| **Settings** | Static read-only overview of how the app is configured |

## Testing & Quality

```bash
# All tests — 445 total (434 in tests/, 11 in eval/ — matches CI)
python -m pytest -q

# Lint & formatting (exactly what CI enforces)
python -m ruff check src/ eval/ tests/
python -m ruff format --check src/ eval/ tests/

# Type check (best-effort — see note)
python -m mypy src/
```

- **mypy** is configured `strict` and runs in CI with `continue-on-error: true` — it is **not** a gate. Treat failures as best-effort/optional.
- **CI** (`.github/workflows/ci.yml`) runs on every push/PR to `main`:
  1. **Lint + Type Check** — `ruff check`, `ruff format --check`, `mypy` (non-blocking)
  2. **Tests** — `pytest` on Python 3.10 / 3.11 / 3.12
  3. **Docker Build** — API and frontend images

## Evaluation

RAG quality can be measured offline with [RAGAS](https://docs.ragas.io/) against a golden dataset (`eval/golden_dataset.jsonl`): faithfulness, answer_relevancy, context_precision, context_recall.

```bash
# Live evaluation against a running pipeline (first 3 questions)
python eval/ragas_eval.py --sample 3

# Offline evaluation of pre-generated results
python eval/ragas_eval.py --offline eval/sample_results.jsonl
```

The harness exits non-zero when a metric falls below its threshold. Unit tests: `python -m pytest eval/ -q`. See `eval/README.md` for details. (The RAGAS job was removed from CI — it requires LLM provider secrets; run it locally when needed.)

## Project Structure

```
src/
├── domain/                  # Entities, interfaces (ports), value objects
│   ├── entities/            # Document, Message, Conversation
│   ├── interfaces/          # LLM, embeddings, repos, vector store, reranker, rewriter
│   └── value_objects/       # Chunk
├── application/             # Use cases & business logic
│   ├── use_cases/           # IngestDocument, QueryDocument, Conversation
│   ├── services/            # RAGEngine, QueryRewriterService
│   └── dto/                 # Request/response DTOs
├── infrastructure/          # Adapters & external implementations
│   ├── config/              # Settings (pydantic-settings)
│   ├── auth/                # JWT-shaped tokens (stdlib HMAC-SHA256)
│   ├── llm/                 # Gemini, OpenAI, Anthropic, DeepSeek + prompt registry
│   ├── embeddings/          # Gemini, OpenAI, HuggingFace factories
│   ├── document_processing/ # PDF/DOCX/TXT/Marker parsers, splitters, enrichers
│   ├── vector_store/        # ChromaDB (persistent, cosine, hybrid)
│   ├── rerankers/           # BGE cross-encoder reranker
│   ├── guardrails/          # PII / injection / groundedness checks
│   ├── ratelimit/           # In-memory sliding-window limiter
│   ├── observability/       # OpenTelemetry tracer
│   └── repositories/        # Conversation repos (in-memory, Postgres)
└── presentation/            # Interfaces
    ├── api/                 # FastAPI app factory + routes (health/auth/documents/chat/usage)
    └── react/               # React + Vite + Tailwind frontend
deploy/
└── nginx.conf               # Frontend image config (SSE-friendly proxy)
scripts/
└── start_all.sh             # Starts uvicorn + Vite together
tests/                       # Unit + integration tests (434)
eval/                        # RAGAS offline evaluation harness (11 tests)
data/                        # Local ChromaDB persistence (CHROMA_PERSIST_DIR)
```

## Troubleshooting

### Gemini returns HTTP 429 / "quota exceeded"

The Google AI Studio project behind `GEMINI_API_KEY` has no billing account linked, so the free tier reports `limit: 0`. Enable billing at https://aistudio.google.com (free to link; Gemini 2.5 Flash includes ~250 free requests/day). The app degrades gracefully:

- `POST /api/query` → HTTP 429 with a friendly message.
- `POST /api/query/stream` → HTTP 200, then `{"type": "error", "message": ...}` followed by `[DONE]`.

### Conversation history resets when the API restarts

Conversations are stored **in-memory** by default (`MemoryConversationRepository`). Page refreshes are safe — the UI persists the last conversation ID in `localStorage` — but history is lost when the API process restarts. Documents and their embeddings in ChromaDB are persistent. Set `DATABASE_URL` (and install `.[postgres]`) for persistent conversations.

### First HuggingFace embedding call is slow

The local model (`all-MiniLM-L6-v2`, ~80–100 MB) is downloaded from the HuggingFace Hub on first use and cached. The first run needs internet; subsequent runs are offline.

### Startup fails with "SECRET_KEY must be overridden"

You set `ENABLE_AUTH=true` but left the bundled dev secret. Generate a long random value, e.g. `python -c "import secrets; print(secrets.token_urlsafe(64))"`, and set it in `.env`.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite, Tailwind CSS |
| Backend API | FastAPI + Uvicorn |
| Vector Store | ChromaDB (persistent, cosine + hybrid search) |
| LLM Providers | Gemini, OpenAI, Anthropic, DeepSeek |
| Embedding Providers | Gemini, OpenAI, HuggingFace (sentence-transformers) |
| Document Parsing | PyMuPDF (primary), PyPDF2 (fallback), python-docx, Marker-PDF |
| Reranking | BGE cross-encoder (`bge-reranker-v2-m3`) |
| Auth | JWT-shaped tokens (stdlib HMAC-SHA256, no third-party lib) |
| Configuration | pydantic-settings |
| Observability | OpenTelemetry → Phoenix (optional) |
| Deployment | Docker Compose + nginx |
| Architecture | Clean Architecture + dependency injection |
| Python | 3.10+ (3.11 in Docker) |
| Node.js | 18+ |

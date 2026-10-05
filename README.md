# Marginalia

A production-grade **Retrieval-Augmented Generation (RAG)** question-answering app. Upload PDF, DOCX, or TXT documents, ask questions in natural language, and get grounded answers with source citations and a confidence score.

[![CI](https://github.com/prakashseervi61/QA-Assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/prakashseervi61/QA-Assistant/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ed)](#docker)

---

## Highlights

- **Multi-format ingestion** — PDF (PyMuPDF with PyPDF2 fallback), DOCX, and TXT
- **Full RAG pipeline** — embed → retrieve → rerank → generate, with citations and confidence
- **One LLM provider** — Gemini. ponytail: the factory was a switch over four; only Gemini is wired up, so the switch is gone. Re-add it when a second provider is genuinely in use.
- **One embedding provider** — local HuggingFace sentence-transformers (no API key, no data leaves the machine)
- **Retrieval** — hybrid search (opt-in), BGE cross-encoder reranking (on), semantic chunking (on), guardrails (on, flag-only)
- **Streaming answers** — Server-Sent Events endpoint for token-by-token output
- **Conversations** — multi-turn history, persistable to PostgreSQL, restorable from the UI
- **Safety & ops (opt-in)** — JWT authentication, per-IP rate limiting, PII / prompt-injection / hallucination guardrails, token-usage tracking, and OpenTelemetry tracing
- **Clean Architecture** — `domain → application → infrastructure → presentation` with dependency injection

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                       React + Vite + Tailwind                  │
│            Chat · Documents · Collections · History · Settings  │
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
│  rerank → prompt (versioned) → LLM                              │
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
- **Incremental ingestion** (`ENABLE_INCREMENTAL_INGESTION`) — re-uploading a byte-identical file (same SHA-256 content hash) is detected as a duplicate and skipped without re-parsing/embedding.

### Retrieval & generation

- **Hybrid search** (`ENABLE_HYBRID_SEARCH`) — combines dense vector similarity with BM25 keyword search.
- **Reranking** (`ENABLE_RERANKING`) — `BAAI/bge-reranker-v2-m3` cross-encoder re-scores retrieved chunks.
- **Versioned prompts** (`PROMPT_VERSION`) — system prompts live in a registry; unknown versions fall back to `v1` with a logged warning.
- **Structured output** — an engine-level option (`use_structured_output=True` on `RAGEngine.query`) returns a JSON answer with per-chunk citations. Not exposed via an env var yet because the chat API contract does not carry the citations field end-to-end.
- **Graceful no-context handling** — the engine distinguishes "no documents uploaded" from "nothing relevant found" and returns a friendly message instead of failing.

### Safety & observability (all opt-in)

- **Guardrails** (`ENABLE_GUARDRAILS`) — regex-based PII detection (email, phone, SSN, credit card, IP), prompt-injection detection, and a groundedness (hallucination) heuristic. Flag-only by default; block with `GUARDRAIL_BLOCK_VIOLATIONS`.
- **Usage tracking** (`ENABLE_USAGE_TRACKING`, default on) — records per-call LLM token usage and estimated cost; exposed via `GET /api/usage`.

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
| `LLM_PROVIDER` | `gemini` | `gemini` (only) |
| `GEMINI_API_KEY` | `""` | Required when using Gemini |
| `GEMINI_MODEL` | `gemini-2.5-flash` | |
| `EMBEDDING_PROVIDER` | `huggingface` | `huggingface` (only, local, free) |
| `HUGGINGFACE_MODEL` | `all-MiniLM-L6-v2` | Local model, downloaded on first use |
| `CHROMA_PERSIST_DIR` | `./data/chroma` | ChromaDB storage directory |
| `CHROMA_COLLECTION_NAME` | `documents` | ChromaDB collection name |
| `CHUNK_SIZE` | `1000` | Characters per chunk |
| `CHUNK_OVERLAP` | `200` | Overlap between consecutive chunks |
| `MAX_FILE_SIZE_MB` | `50` | Hard upload limit. Larger uploads are rejected with `413` before the body is buffered |
| `ALLOWED_EXTENSIONS` | `[".pdf", ".docx", ".txt"]` | Accepted upload extensions |
| `API_HOST` | `127.0.0.1` | Loopback by default — the API serves every ingested document, so it is not exposed to the LAN unless you deliberately change this |
| `API_PORT` | `8000` | Reserved — uvicorn launched with explicit port |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed CORS origins (JSON list) |

### Advanced RAG (feature flags)

| Variable | Default | Description |
|---|---|---|
| `ENABLE_RERANKING` | `false` | Re-score retrieved chunks with a BGE cross-encoder |
| `RERANKER_MODEL` | `BAAI/bge-reranker-v2-m3` | |
| `ENABLE_HYBRID_SEARCH` | `false` | Dense vector + BM25 keyword search |
| `ENABLE_SEMANTIC_CHUNKING` | `false` | Split on embedding-similarity dips |
| `SEMANTIC_SIMILARITY_THRESHOLD` | `0.5` | |
| `SEMANTIC_MIN_CHUNK_SIZE` | `100` | |
| `SEMANTIC_MAX_CHUNK_SIZE` | `2000` | |
| `ENABLE_INCREMENTAL_INGESTION` | `false` | Skip byte-identical re-uploads (SHA-256 dedup) |
| `PROMPT_VERSION` | `v1` | RAG system-prompt template version |

> Parent-child retrieval overrides semantic chunking in the upload route; both are off by default. Enable at most one chunking mode at a time.

### Safety & ops

| Variable | Default | Description |
|---|---|---|
| `ENABLE_GUARDRAILS` | `false` | PII + prompt-injection input checks, groundedness + PII-leak output checks |
| `GUARDRAIL_BLOCK_VIOLATIONS` | `false` | Flag-only by default; set `true` to block flagged inputs before the LLM |
| `GUARDRAIL_GROUNDEDNESS_THRESHOLD` | `0.2` | Below this score the output is flagged |
| `ENABLE_USAGE_TRACKING` | `true` | Record LLM token usage & cost; exposes `GET /api/usage` |

### Optional dependency extras

```bash
```

Tracing degrades gracefully: if enabled but the packages are missing, the app logs a warning and uses a no-op tracer.

---

## API Reference

All routes are served under the `/api` prefix. The API binds **127.0.0.1** by default, so it is reachable only from this machine — that loopback boundary is the access control, which is why there is no auth layer. Set `API_HOST=0.0.0.0` only if you put your own auth in front of it.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Liveness/readiness probe |
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

A responsive React SPA (Tailwind CSS). Every view has its own URL (`/`, `/documents`, `/collections`, `/history`, `/bookmarks`, `/settings`), so pages are linkable, bookmarkable and reachable with the back/forward buttons. Navigation is a left rail on desktop and a bottom bar on mobile:

| View | What it does |
|---|---|
| **Documents** | Upload (drag & drop or file picker), list, and delete documents; shows ingestion status and chunk counts |
| **Chat** | Ask questions with a conversation selector (last conversation persists in `localStorage`); answers render `[Source N]` markers with an expandable **Referenced Sources** panel showing each cited chunk and its score, plus a **confidence** badge so a weakly-grounded answer is visibly distinguishable from a well-sourced one |
| **History** | Every past conversation, saved to disk so it survives restarts, grouped by Today/Yesterday/Earlier, with a title filter and per-conversation delete; click to reopen it in Chat |
| **Collections** | Placeholder — grouping documents is planned |
| **Bookmarks** | Placeholder — saving answers is planned |
| **Settings** | Static read-only overview of how the app is configured |

## Testing & Quality

```bash
# All tests — 339 total (328 in tests/, 11 in eval/ — matches CI)
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
│   ├── llm/                 # Gemini provider + prompt registry
│   ├── embeddings/          # HuggingFace provider
│   ├── document_processing/ # PDF/DOCX/TXT/Marker parsers, splitters, enrichers
│   ├── vector_store/        # ChromaDB (persistent, cosine, hybrid)
│   ├── rerankers/           # BGE cross-encoder reranker
│   ├── guardrails/          # PII / injection / groundedness checks
│   ├── ratelimit/           # In-memory sliding-window limiter
│   ├── observability/       # OpenTelemetry tracer
│   └── repositories/        # SQLite conversation history
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

Conversations are stored in a local SQLite file (`data/history.db`), so history survives a restart. Documents and their embeddings in ChromaDB are persistent too. If the history file cannot be opened the API fails to start rather than silently discarding your history.

### First HuggingFace embedding call is slow

The local model (`all-MiniLM-L6-v2`, ~80–100 MB) is downloaded from the HuggingFace Hub on first use and cached. The first run needs internet; subsequent runs are offline.

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

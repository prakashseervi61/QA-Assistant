# QA Assistant

A Document Q&A application powered by Retrieval-Augmented Generation (RAG). Upload documents, ask questions in natural language, and get accurate answers sourced directly from your content.

Built with **FastAPI** (backend), **React + Vite + Tailwind CSS** (frontend), **ChromaDB** (vector store), and a provider-agnostic architecture for swapping LLMs and embedding models via a single config change.

## Features

- **Multi-format ingestion** — PDF, DOCX, and TXT files with sentence-boundary-aware chunking
- **RAG pipeline** — embed, retrieve, and generate answers with source citations and a confidence score
- **Streaming responses** — Server-Sent Events endpoint (`/api/query/stream`) for real-time token-by-token output
- **4 LLM providers** — Gemini, OpenAI, Anthropic, DeepSeek (OpenAI-compatible)
- **3 embedding providers** — Gemini, OpenAI, HuggingFace (runs locally, no API key needed)
- **Conversation memory** — multi-turn conversations; the UI restores the last conversation on page refresh
- **Clean Architecture** — domain, application, infrastructure, presentation layers

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+ and npm (for the frontend)
- Git Bash on Windows (only if you want the one-command `scripts/start_all.sh`; native cmd/PowerShell instructions are below)
- An API key for at least one LLM provider (Gemini is the default; the Google AI Studio free tier works)

### 1. Clone and install

```bash
git clone https://github.com/prakashseervi61/QA-Assistant.git
cd QA-Assistant
python -m venv .venv
# Activate the venv (Windows: .venv\Scripts\activate, macOS/Linux: source .venv/bin/activate)
pip install -e ".[dev]"
```

### 2. Install frontend dependencies

```bash
cd src/presentation/react
npm install
cd ../..
```

> Build the frontend for production (used by the Docker image) with `npm run build` inside `src/presentation/react`.

### 3. Configure

```bash
cp .env.example .env
```

Edit `.env` and set your LLM provider API key. The defaults use **Gemini** for the LLM and **HuggingFace** (local) for embeddings — zero API cost for embeddings:

```bash
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key_here
EMBEDDING_PROVIDER=huggingface
```

### 4. Run

**One command (Git Bash):**

```bash
bash scripts/start_all.sh
```

This starts uvicorn (API) and Vite (frontend) together.

**Or two terminals (any shell, including Windows cmd/PowerShell):**

```bash
# Terminal 1 — API
uvicorn src.presentation.api.app:create_app --factory --reload --port 8000

# Terminal 2 — Frontend (from the repo root)
cd src\presentation\react   # Windows
npm run dev
```

### 5. Open

| Service | URL |
|---|---|
| Frontend (React) | http://localhost:3000 |
| API | http://localhost:8000 |
| Swagger docs | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |

The Vite dev server proxies `/api/*` to `http://localhost:8000` (see `src/presentation/react/vite.config.js`), so the frontend and API work together with no extra setup.

## Docker

```bash
docker compose up --build
```

| Service | Port | Notes |
|---|---|---|
| API (uvicorn) | 8000 | Boots the `create_app` factory |
| Frontend (nginx) | 3000 | Serves the built React app and proxies `/api/` → `api:8000` |

Details:

- The frontend image builds the React app with Node 18, then serves it via nginx (`deploy/nginx.conf`). `proxy_buffering off` keeps Server-Sent Events flowing.
- ChromaDB persists in the `chroma_data` Docker volume (mounted at `/data/chroma`).
- `.env` values are passed to the API container via compose `environment`: `LLM_PROVIDER`, `GEMINI_API_KEY`, `EMBEDDING_PROVIDER`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, and `CHROMA_PERSIST_DIR`. Set `GEMINI_API_KEY` in `.env` before running compose so the API container picks it up.
- The API container runs a healthcheck against `GET /api/health`; the frontend waits for it to pass.

## Configuration Reference

All settings live in `.env` (or as environment variables) and are loaded via `pydantic-settings` (see `src/infrastructure/config/settings.py`). Every variable is optional — the code defaults are shown below.

| Variable | Default | Description |
|---|---|---|
| `APP_NAME` | `QA Assistant` | FastAPI app title |
| `DEBUG` | `false` | Reserved — enable debug mode |
| `LOG_LEVEL` | `INFO` | Reserved — logging level |
| `LLM_PROVIDER` | `gemini` | LLM backend — `gemini`, `openai`, `anthropic`, `deepseek` |
| `GEMINI_API_KEY` | `""` | Gemini API key (required if using Gemini) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model name |
| `OPENAI_API_KEY` | `""` | OpenAI API key (required if using OpenAI) |
| `OPENAI_MODEL` | `gpt-4o` | OpenAI model name |
| `ANTHROPIC_API_KEY` | `""` | Anthropic API key (required if using Anthropic) |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | Anthropic model name |
| `DEEPSEEK_API_KEY` | `""` | DeepSeek API key (required if using DeepSeek) |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | DeepSeek model name |
| `EMBEDDING_PROVIDER` | `gemini` | Embedding backend — `gemini`, `openai`, `huggingface` |
| `GEMINI_EMBEDDING_MODEL` | `text-embedding-004` | Gemini embedding model |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model |
| `HUGGINGFACE_MODEL` | `all-MiniLM-L6-v2` | Local HuggingFace model (384-dim) |
| `CHROMA_PERSIST_DIR` | `./data/chroma` | ChromaDB storage directory |
| `CHROMA_COLLECTION_NAME` | `documents` | ChromaDB collection name |
| `CHUNK_SIZE` | `1000` | Characters per document chunk |
| `CHUNK_OVERLAP` | `200` | Overlap between consecutive chunks |
| `MAX_FILE_SIZE_MB` | `50` | Reserved — not enforced by the API |
| `ALLOWED_EXTENSIONS` | `[".pdf", ".docx", ".txt"]` | Accepted upload extensions |
| `API_HOST` | `0.0.0.0` | Reserved — uvicorn is launched with an explicit host |
| `API_PORT` | `8000` | Reserved — uvicorn is launched with an explicit port |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed CORS origins (JSON list) |

> **Note on the embedding default:** the code default for `EMBEDDING_PROVIDER` is `gemini`, but the shipped `.env.example` and `docker-compose.yml` set it to `huggingface` — a local, free, keyless default. Either works; switch by changing a single line.

Switching providers is a single-line change — no code modifications needed.

## Project Structure

```
src/
├── domain/                  # Entities, interfaces, value objects
│   ├── entities/            # Document, Message, Conversation
│   ├── interfaces/          # Abstract contracts (LLM, embeddings, repos, vector store)
│   └── value_objects/       # Chunk
├── application/             # Use cases and business logic
│   ├── use_cases/           # IngestDocument, QueryDocument, Conversation
│   ├── services/            # RAGEngine (embed → retrieve → generate)
│   └── dto/                 # Request/response DTOs
├── infrastructure/          # External implementations
│   ├── config/              # Settings (pydantic-settings)
│   ├── llm/                 # Gemini, OpenAI, Anthropic, DeepSeek providers
│   ├── embeddings/          # Gemini, OpenAI, HuggingFace providers
│   ├── document_processing/ # PDF, DOCX, TXT parsers + text splitter
│   ├── vector_store/        # ChromaDB store (persistent, cosine distance)
│   └── repositories/        # In-memory conversation store
└── presentation/            # Interfaces
    ├── api/                 # FastAPI REST API (app factory + routes)
    │   └── routes/          # health, documents, chat
    └── react/               # React + Vite + Tailwind frontend
        ├── src/             # App, API client, components
        └── vite.config.js   # Dev server on :3000, proxies /api → :8000
deploy/
└── nginx.conf               # nginx config for the Docker frontend image
scripts/
└── start_all.sh             # Starts uvicorn + Vite together
tests/                       # Unit tests (unit/, integration/, e2e/)
data/                        # Local ChromaDB persistence (CHROMA_PERSIST_DIR)
```

## API Endpoints

All routes are served under the `/api` prefix.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Liveness/readiness probe |
| `POST` | `/api/documents/upload` | Upload and ingest a document (multipart field `file`) |
| `GET` | `/api/documents` | List ingested documents |
| `DELETE` | `/api/documents/{id}` | Delete a document and its chunks |
| `POST` | `/api/query` | Ask a question (non-streaming) |
| `POST` | `/api/query/stream` | Ask a question (streaming SSE) |
| `GET` | `/api/conversations` | List recent conversations (max 10, newest first) |
| `GET` | `/api/conversations/{id}` | Get conversation messages |

### `GET /api/health`

```json
{ "status": "healthy", "version": "0.1.0", "vector_store": "initialized" }
```

### `POST /api/documents/upload`

Multipart form with a single `file` field. Accepts `.pdf`, `.docx`, `.txt` (400 for anything else, an empty file, or a missing filename; 500 if ingestion fails).

```json
{
  "document_id": "3f0c...",
  "filename": "report.pdf",
  "chunk_count": 12,
  "message": "Successfully ingested 'report.pdf'. 12 chunks stored."
}
```

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

### `DELETE /api/documents/{id}`

```json
{ "message": "Document 3f0c... deleted successfully." }
```

### `POST /api/query`

Request body:

```json
{ "question": "What are the key findings?", "top_k": 5, "conversation_id": null }
```

- `question` — required, 1–5000 characters
- `top_k` — optional, 1–20 (default 5)
- `conversation_id` — optional UUID; omit to start a new conversation

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

Status codes: `400` invalid question or conversation ID format · `404` conversation not found · `429` LLM quota/rate-limit exceeded (friendly message) · `500` RAG pipeline failure.

### `POST /api/query/stream`

Same request body as `/api/query`. Responds with `text/event-stream` (headers: `Cache-Control: no-cache`, `Connection: keep-alive`, `X-Accel-Buffering: no`). Each event is JSON with a `type` field:

- `chunk` — incremental answer text: `{"type": "chunk", "content": "..."}`
- `done` — final summary with sources and metadata: `{"type": "done", "answer": "...", "sources": [...], "confidence": 0.81, "conversation_id": "...", "message_id": "..."}`
- `error` — error message: `{"type": "error", "message": "..."}`
- Terminates with `data: [DONE]`

Contract: even on LLM quota/rate-limit errors the response stays HTTP 200 and emits an `error` event followed by `[DONE]`, so streaming clients always see a well-formed termination.

> The current React UI calls the non-streaming `POST /api/query`; the SSE endpoint is part of the API contract for token-by-token clients.

### `GET /api/conversations`

```json
[
  { "id": "3f0c...", "title": "What are the key findings?", "created_at": "...", "updated_at": "...", "message_count": 4 }
]
```

Only conversations that contain at least one message are returned, newest first (limit 10).

### `GET /api/conversations/{id}`

```json
[
  { "id": "9a2b...", "role": "user", "content": "What are the key findings?", "sources": [], "created_at": "..." }
]
```

Status codes: `400` invalid UUID · `404` conversation not found.

## Testing

```bash
# Run all tests (153 tests)
python -m pytest tests/ -q

# Lint (and formatting, as enforced in CI)
python -m ruff check src tests
python -m ruff format --check src tests

# Type check (best effort — see note)
python -m mypy src
```

- `mypy` is configured (`strict`) and runs in CI with `continue-on-error: true` — it is **not** a gate. It may fail in some local environments (e.g. missing numpy stubs pulled in transitively); treat it as best-effort/optional.
- CI (`pytest` on Python 3.10/3.11/3.12, ruff, Docker builds) runs on every push/PR to `main`.

## Troubleshooting

### Gemini returns HTTP 429 / "quota exceeded"

The Google AI Studio project behind `GEMINI_API_KEY` has no billing account linked, so the free tier reports `limit: 0`. Fix: enable billing at https://aistudio.google.com (billing is free to link; Gemini 2.5 Flash includes ~250 free requests/day). The app degrades gracefully:

- `POST /api/query` → HTTP 429 with a friendly message pointing to Google AI Studio.
- `POST /api/query/stream` → HTTP 200, then `{"type": "error", "message": ...}` followed by `[DONE]`.

### Conversation history resets when the API restarts

Conversations are stored **in-memory** (`MemoryConversationRepository`). Page refreshes are safe — the UI persists the last conversation ID in `localStorage` and restores it on load — but history is lost whenever the API server process restarts. Documents and their embeddings in ChromaDB are persistent.

### First HuggingFace embedding call is slow

The local embedding model (`all-MiniLM-L6-v2`, ~80–100 MB) is downloaded from the HuggingFace Hub on first use and then cached. An internet connection is required on the first run; subsequent runs are offline.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite, Tailwind CSS |
| Backend API | FastAPI + Uvicorn |
| Vector Store | ChromaDB (persistent, cosine distance) |
| LLM Providers | Gemini, OpenAI, Anthropic, DeepSeek |
| Embedding Providers | Gemini, OpenAI, HuggingFace (sentence-transformers) |
| Document Parsing | PyPDF2, python-docx |
| Configuration | pydantic-settings |
| Deployment | Docker Compose + nginx |
| Architecture | Clean Architecture (Domain → Application → Infrastructure → Presentation) |
| Python | 3.10+ (3.11 in Docker) |
| Node.js | 18+ |

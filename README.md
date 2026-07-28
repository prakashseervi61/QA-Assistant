# QA Assistant

A Document Q&A application powered by Retrieval-Augmented Generation (RAG). Upload documents, ask questions in natural language, and get accurate answers sourced directly from your content.

Built with **FastAPI** (backend), **Streamlit** (frontend), **ChromaDB** (vector store), and a provider-agnostic architecture for swapping LLMs and embedding models via a single config change.

## Features

- **Multi-format ingestion** — PDF, DOCX, and TXT files with sentence-boundary-aware chunking
- **RAG pipeline** — embed, retrieve, and generate answers with source citations
- **Streaming responses** — Server-Sent Events for real-time token-by-token output
- **4 LLM providers** — Gemini, OpenAI, Anthropic, DeepSeek (OpenAI-compatible)
- **3 embedding providers** — Gemini, OpenAI, HuggingFace (runs locally, no API key needed)
- **Conversation memory** — multi-turn conversations with full history
- **Clean Architecture** — domain, application, infrastructure, presentation layers

## Quick Start

### Prerequisites

- Python 3.10+
- An API key for at least one LLM provider (DeepSeek free tier works out of the box)

### 1. Clone and install

```bash
git clone https://github.com/prakashseervi61/QA-Assistant.git
cd QA-Assistant
pip install -e ".[dev]"
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` with your provider and API key. The defaults use **DeepSeek** (free tier) for LLM and **HuggingFace** (local) for embeddings — zero API cost:

```bash
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your_key_here
EMBEDDING_PROVIDER=huggingface
```

### 3. Run

**Manual:**

```bash
# Terminal 1 — API
uvicorn src.presentation.api.app:create_app --factory --reload --port 8000

# Terminal 2 — UI
streamlit run src/presentation/streamlit/app.py --server.port 8501
```

**Or both at once:**

```bash
bash scripts/start_all.sh
```

### 4. Open

| Service | URL |
|---|---|
| Streamlit UI | http://localhost:8501 |
| API | http://localhost:8000 |
| Swagger docs | http://localhost:8000/docs |

## Docker

```bash
docker compose up --build
```

| Service | Port |
|---|---|
| API | 8000 |
| Frontend | 8501 |

ChromaDB data persists in a Docker volume (`chroma_data`).

## Configuration Reference

All settings live in `.env` and are loaded via `pydantic-settings`:

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | LLM backend — `gemini`, `openai`, `anthropic`, `deepseek` |
| `EMBEDDING_PROVIDER` | `gemini` | Embedding backend — `gemini`, `openai`, `huggingface` |
| `GEMINI_API_KEY` | `""` | Gemini API key (required if using Gemini) |
| `OPENAI_API_KEY` | `""` | OpenAI API key (required if using OpenAI) |
| `ANTHROPIC_API_KEY` | `""` | Anthropic API key (required if using Anthropic) |
| `DEEPSEEK_API_KEY` | `""` | DeepSeek API key (required if using DeepSeek) |
| `CHUNK_SIZE` | `1000` | Characters per document chunk |
| `CHUNK_OVERLAP` | `200` | Overlap between consecutive chunks |
| `CHROMA_PERSIST_DIR` | `./data/chroma` | ChromaDB storage directory |
| `API_PORT` | `8000` | API server port |
| `DEBUG` | `false` | Enable debug mode |

Switching providers is a single-line change — no code modifications needed.

## Project Structure

```
src/
├── domain/                  # Entities, interfaces, value objects
│   ├── entities/            # Document, Message, Conversation
│   ├── interfaces/          # Abstract contracts (LLM, embeddings, repos, vector store)
│   └── value_objects/       # Chunk
├── application/             # Use cases and business logic
│   ├── use_cases/           # IngestDocument, QueryDocument
│   ├── services/            # RAGEngine (embed → retrieve → generate)
│   └── dto/                 # Request/response DTOs
├── infrastructure/          # External implementations
│   ├── config/              # Settings (pydantic-settings)
│   ├── llm/                 # Gemini, OpenAI, Anthropic, DeepSeek providers
│   ├── embeddings/          # Gemini, OpenAI, HuggingFace providers
│   ├── document_processing/ # PDF, DOCX, TXT parsers + text splitter
│   ├── vector_store/        # ChromaDB store
│   └── repositories/        # In-memory conversation store
└── presentation/            # Interfaces
    ├── api/                 # FastAPI REST API
    │   └── routes/          # health, documents, chat
    └── streamlit/           # Streamlit UI
        ├── pages/           # Documents page, Chat page
        └── components/      # Shared UI components
```

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/documents/upload` | Upload and ingest a document |
| `GET` | `/api/documents` | List ingested documents |
| `DELETE` | `/api/documents/{id}` | Delete a document |
| `POST` | `/api/query` | Ask a question (non-streaming) |
| `POST` | `/api/query/stream` | Ask a question (streaming SSE) |
| `GET` | `/api/conversations` | List conversations |
| `GET` | `/api/conversations/{id}` | Get conversation messages |

## Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=src --cov-report=html

# Lint and type check
ruff check src/
mypy src/
```

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Streamlit |
| Backend API | FastAPI + Uvicorn |
| Vector Store | ChromaDB |
| LLM Providers | Gemini, OpenAI, Anthropic, DeepSeek |
| Embedding Providers | Gemini, OpenAI, HuggingFace (sentence-transformers) |
| Document Parsing | PyPDF2, python-docx |
| Configuration | pydantic-settings |
| Architecture | Clean Architecture (Domain → Application → Infrastructure → Presentation) |
| Python | 3.10+ |

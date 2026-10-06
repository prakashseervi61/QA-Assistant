<h1 align="center">Marginalia</h1>

<p align="center">
  <em>Answers from your documents — grounded, cited, and linkable.</em>
</p>

<p align="center">
  <a href="#quickstart">Quickstart</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#api">API</a> ·
  <a href="#configuration">Configuration</a> ·
  <a href="#contributing">Contributing</a>
</p>

---

## What it is

A local-first retrieval-augmented generation (RAG) app. Drop in PDF, DOCX, or TXT
files, ask questions in plain language, and get an answer assembled from *your*
documents — with the cited chunks shown underneath and a confidence score so a
weakly-grounded answer is visibly distinguishable from a well-sourced one.

Everything runs on your machine. The only network call is to the LLM provider;
embeddings are computed locally, and both your documents and your conversation
history live on disk.

## Highlights

- **Every conversation is a URL** — `/chat/<id>` makes a chat linkable, shareable,
  and survivable across a refresh; back and forward step between chats.
- **Local embeddings** — `all-MiniLM-L6-v2` via sentence-transformers. No
  embedding API key, no document text leaving the machine, no per-token cost.
- **Streaming answers** — Server-Sent Events with a live retrieval trace, so you
  see *guardrails → retrieving → reranking → generating* as it happens.
- **Semantic chunking + BGE reranking on by default** — chunks split on meaning
  rather than fixed windows, and the top hits are re-scored by a cross-encoder
  before they reach the model.
- **Deduplicating ingestion** — a byte-identical re-upload is detected by
  SHA-256 and skipped instead of re-embedded.
- **Guardrails included** — PII and prompt-injection checks on input,
  groundedness and PII-leak checks on output.
- **Clean Architecture** — `domain → application → infrastructure → presentation`,
  wired by a single app factory.

## Quickstart

**Prerequisites:** Python 3.10+, Node.js 18+, and a Gemini API key
([Google AI Studio](https://aistudio.google.com) has a free tier).

```bash
git clone https://github.com/prakashseervi61/QA-Assistant.git
cd QA-Assistant

# API dependencies
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Frontend dependencies
cd src/presentation/react && npm install && cd -

# Configure
cp .env.example .env               # Windows: copy .env.example .env
```

Set the one required key in `.env`:

```bash
GEMINI_API_KEY=your_key_here
```

Then run both halves:

```bash
scripts/start_all.sh               # macOS / Linux
scripts\start_all.bat              # Windows
```

Or drive them separately:

```bash
uvicorn src.presentation.api.app:create_app --factory --reload --port 8000
cd src/presentation/react && npm run dev
```

| Service | URL |
| --- | --- |
| App | <http://localhost:3000> |
| API | <http://localhost:8000> |
| Swagger UI | <http://localhost:8000/docs> |

The Vite dev server proxies `/api/*` to port 8000, so the two halves work
together with no CORS setup.

### Docker

```bash
docker compose up --build
```

Serves the built app on port 3000 and the API on port 8000. ChromaDB persists
in the `chroma_data` volume; the frontend waits for the API healthcheck before
serving. Set `GEMINI_API_KEY` in `.env` first — Compose passes it into the
container.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  React + Vite + Tailwind                                     │
│  /chat/:id · /documents · /history · /settings               │
└───────────────────────────┬──────────────────────────────────┘
                            │  /api/*  (Vite proxy → nginx)
┌───────────────────────────▼──────────────────────────────────┐
│  FastAPI                                                      │
│  CORS · upload limits · routes: health documents chat usage   │
└───────────────────────────┬──────────────────────────────────┘
                            │  QueryDocument · IngestDocument
┌───────────────────────────▼──────────────────────────────────┐
│  RAGEngine                                                    │
│  guardrails → embed → retrieve → rerank →                    │
│  prompt (versioned) → generate → guardrails                  │
└──────┬──────────────────┬──────────────────┬──────────────────┘
       │                  │                  │
┌──────▼───────┐   ┌──────▼────────┐  ┌──────▼──────────────────┐
│ Gemini       │   │ HuggingFace   │  │ ChromaDB (vectors)      │
│ google-genai │   │ local, free   │  │ + SQLite (history)      │
└──────────────┘   └───────────────┘  └─────────────────────────┘
```

### How a question becomes an answer

1. **Guardrails** — the question is scanned for PII and prompt injection.
2. **Retrieve** — semantic search over ChromaDB (optionally hybrid with BM25).
3. **Rerank** — a BGE cross-encoder re-scores the top hits by relevance to the
   question, which is what makes the citations precise.
4. **Generate** — a versioned prompt (`PROMPT_VERSION`) is sent to Gemini.
5. **Guardrails again** — groundedness and PII-leak checks on the answer.
6. **Persist** — both turns are written to SQLite under the conversation id.

## Configuration

Every setting is optional; the code default applies when unset. Copy
`.env.example` to `.env` to override. Full list with defaults lives in
`src/infrastructure/config/settings.py`.

### Core

| Variable | Default | Purpose |
| --- | --- | --- |
| `GEMINI_API_KEY` | `""` | **Required.** No key, no answers. |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Generation model |
| `HUGGINGFACE_MODEL` | `all-MiniLM-L6-v2` | Embedding model, cached after first use |
| `CHROMA_PERSIST_DIR` | `./data/chroma` | Vector store location |
| `HISTORY_DB_PATH` | `./data/history.db` | Conversation history (SQLite) |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `1000` / `200` | Fixed-size chunking window |
| `MAX_FILE_SIZE_MB` | `50` | Hard upload ceiling; larger files get `413` |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed browser origins |

### Retrieval

| Variable | Default | Purpose |
| --- | --- | --- |
| `ENABLE_RERANKING` | `true` | BGE cross-encoder re-scoring |
| `RERANKER_MODEL` | `BAAI/bge-reranker-v2-m3` | |
| `ENABLE_SEMANTIC_CHUNKING` | `true` | Split on meaning, not fixed windows |
| `ENABLE_HYBRID_SEARCH` | `false` | Blend dense vectors with BM25 keywords |
| `ENABLE_INCREMENTAL_INGESTION` | `false` | Skip byte-identical re-uploads |
| `PROMPT_VERSION` | `v1` | System-prompt template; unknown falls back to `v1` |

> Enable at most one chunking mode at a time — semantic and fixed-size chunking
> solve the same problem, and running both means one silently wins.

### Guardrails

| Variable | Default | Purpose |
| --- | --- | --- |
| `ENABLE_GUARDRAILS` | `true` | Run the input/output checks at all |
| `GUARDRAIL_BLOCK_VIOLATIONS` | `false` | Flag-only by default; set `true` to reject |
| `GUARDRAIL_GROUNDEDNESS_THRESHOLD` | `0.2` | Below this, the answer is flagged |
| `ENABLE_USAGE_TRACKING` | `true` | Token usage + estimated cost |

## API

All routes are under `/api`. The API binds **loopback only** — that boundary is
the access control, which is why there is no auth layer. Don't expose it to a
LAN without putting your own auth in front.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Liveness + vector-store status |
| `POST` | `/api/documents/upload` | Ingest a document (multipart `file`) |
| `GET` | `/api/documents` | List ingested documents |
| `DELETE` | `/api/documents/{id}` | Delete a document and its chunks |
| `POST` | `/api/query` | Ask a question |
| `POST` | `/api/query/stream` | Ask a question, streamed over SSE |
| `GET` | `/api/conversations` | List conversations, newest first |
| `GET` | `/api/conversations/{id}` | Messages in a conversation |
| `DELETE` | `/api/conversations/{id}` | Delete a conversation |
| `GET` | `/api/usage` | Token usage and estimated cost |

### `GET /api/health`

```json
{ "status": "healthy", "version": "0.1.0", "vector_store": "initialized" }
```

### `POST /api/documents/upload`

Accepts `.pdf`, `.docx`, `.txt`. Returns `400` for an unsupported type, an
empty file, or a missing filename; `413` over `MAX_FILE_SIZE_MB`; `500` if
ingestion fails.

```json
{
  "document_id": "3f0c…",
  "filename": "report.pdf",
  "chunk_count": 12,
  "message": "Successfully ingested 'report.pdf'. 12 chunks stored."
}
```

With `ENABLE_INCREMENTAL_INGESTION=true`, a byte-identical re-upload returns
`"status": "duplicate"` and skips the work.

### `POST /api/query`

```json
{ "question": "What are the key findings?", "top_k": 5, "conversation_id": null }
```

`question` is 1–5000 characters; `top_k` is 1–20 (default 5); `conversation_id`
continues an existing thread.

```json
{
  "answer": "The report finds that…",
  "sources": [
    { "content": "excerpt", "metadata": { "filename": "report.pdf", "chunk_index": 3 }, "score": 0.87 }
  ],
  "confidence": 0.81,
  "conversation_id": "3f0c…",
  "message_id": "9a2b…"
}
```

`400` invalid input · `404` unknown conversation · `429` LLM quota exceeded ·
`500` pipeline failure.

With no documents you get a friendly "upload something" answer rather than an
error; with documents but no relevant match, it says so instead of guessing.

### `POST /api/query/stream`

Same body, `text/event-stream` response. Events carry a `type`:

| Type | Meaning |
| --- | --- |
| `stage` | Live retrieval trace (`rewriting`, `retrieving`, …) |
| `chunk` | Incremental answer text |
| `done` | Final answer, sources, confidence, and ids |
| `error` | Human-readable failure |
| `blocked` | Guardrails rejected the question |

Always terminates with `data: [DONE]`. Quota and rate-limit errors still return
HTTP 200 followed by an `error` event, so streaming clients never see a
truncated stream.

## Frontend

A React SPA with a neo-brutalist design system — hard 3px borders, flat offset
shadows, no gradients. Navigation is a left rail on desktop and a bottom bar on
mobile, and every view has a real URL.

| Route | What it does |
| --- | --- |
| `/chat` | A fresh conversation |
| `/chat/:id` | That conversation — linkable and refresh-safe |
| `/documents` | Upload (drop or pick), list, delete, with chunk counts |
| `/history` | Past conversations grouped by day, filterable, deletable |
| `/settings` | Read-only overview of how the app is configured |

Answers render inline `[Source N]` markers; tapping one expands the cited chunk
and its relevance score in a **Referenced Sources** panel.

## Testing

```bash
python -m pytest -q              # 325 tests (314 unit/integration + 11 eval)

python -m ruff check src/ tests/ eval/
python -m ruff format --check src/ tests/ eval/
python -m mypy src/             # strict, but non-blocking in CI
```

CI (`.github/workflows/ci.yml`) runs lint + type check, the suite on Python
3.10 / 3.11 / 3.12, and both Docker image builds on every push and PR.

Frontend tests and build:

```bash
cd src/presentation/react
npm test          # 34 tests
npm run build
```

### Measuring answer quality

RAG quality is measurable, not a matter of opinion. `eval/` scores the pipeline
with [RAGAS](https://docs.ragas.io/) against a golden set — faithfulness,
answer relevancy, context precision, and recall:

```bash
python eval/ragas_eval.py --sample 3                          # live, needs a key
python eval/ragas_eval.py --offline eval/sample_results.jsonl # offline
```

The harness exits non-zero when a metric drops below threshold. It is not in CI
because it needs provider secrets; run it locally before changing the pipeline.

## Project layout

```
src/
├── domain/              # Entities, ports (interfaces), value objects
├── application/         # Use cases, RAGEngine, DTOs
├── infrastructure/
│   ├── config/          # pydantic-settings
│   ├── llm/             # Gemini provider + prompt registry
│   ├── embeddings/      # HuggingFace (local)
│   ├── document_processing/  # PDF / DOCX / TXT parsers, splitters
│   ├── vector_store/    # ChromaDB
│   ├── rerankers/       # BGE cross-encoder
│   ├── guardrails/      # PII, injection, groundedness
│   └── repositories/    # SQLite conversation history
└── presentation/
    ├── api/             # FastAPI factory + routes
    └── react/           # React + Vite + Tailwind
eval/                    # RAGAS harness + golden dataset
deploy/nginx.conf        # SSE-friendly frontend proxy
scripts/                 # start_all / stop_all
```

## Troubleshooting

**`429 quota exceeded` from Gemini.** The AI Studio project behind the key has
no billing account, so the free tier reports `limit: 0`. Linking billing at
<https://aistudio.google.com> is free and includes a daily request allowance.
The app degrades cleanly either way: `/api/query` returns `429` with a readable
message, and `/api/query/stream` returns `200` followed by an `error` event.

**The first query is slow.** `all-MiniLM-L6-v2` (~90 MB) downloads from the
HuggingFace Hub on first use, then runs offline from cache. The BGE reranker
downloads the same way.

**History looks empty after a restart.** It shouldn't — conversations live in
`HISTORY_DB_PATH` and persist. If the file can't be opened the API fails to
start rather than silently discarding your history, which is the intended
behaviour: fail loudly instead of quietly losing data.

**Nothing loads in the browser.** Check the API is up (`curl
localhost:8000/api/health`) and that `.env` has a `GEMINI_API_KEY`. A missing
key surfaces as a query-time error, not a startup failure.

## Tech stack

| Layer | Choice |
| --- | --- |
| Frontend | React 18, Vite, Tailwind CSS, react-router-dom, framer-motion |
| API | FastAPI, Uvicorn, Pydantic v2 |
| Retrieval | ChromaDB, BGE cross-encoder reranking |
| Generation | Gemini via `google-genai` |
| Embeddings | `sentence-transformers`, run locally |
| Parsing | PyMuPDF (primary) → PyPDF2 (fallback), python-docx |
| History | SQLite (stdlib `sqlite3`) |
| Config | pydantic-settings |
| Deploy | Docker Compose + nginx |

## Contributing

```bash
pip install -e ".[dev]"
python -m ruff check src/ tests/ eval/ && python -m ruff format src/ tests/ eval/
python -m pytest -q
```

Keep the layers honest: `domain` imports nothing from the layers above it, and
new behaviour belongs in a use case rather than a route. Mark deliberate
shortcuts with a `ponytail:` comment explaining what was given up, so the next
person knows whether it is load-bearing.

## License

No license file is present yet. Add one before publishing this publicly —
without it, the default copyright applies and others have no right to use it.

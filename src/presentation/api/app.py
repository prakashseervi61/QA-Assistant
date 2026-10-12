"""FastAPI application factory."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.application.services.rag_engine import RAGEngine
from src.application.use_cases.query_document import QueryDocumentUseCase
from src.infrastructure.config.settings import Settings, get_settings
from src.infrastructure.embeddings.huggingface_embeddings import (
    HuggingFaceEmbeddingProvider,
)
from src.infrastructure.guardrails.guardrail_manager import create_guardrail_manager
from src.infrastructure.llm.api_key_resolver import ApiKeyResolver
from src.infrastructure.llm.gemini_provider import GeminiProvider
from src.infrastructure.llm.token_tracker import TokenTracker, TrackingLLMProvider
from src.infrastructure.repositories.conversation_repository_factory import (
    create_conversation_repository,
)
from src.infrastructure.repositories.json_secret_store import JsonSecretStore
from src.infrastructure.rerankers.factory import create_reranker
from src.infrastructure.vector_store.chroma_store import ChromaStore
from src.presentation.api.routes import chat, documents, health, usage
from src.presentation.api.routes import settings as settings_routes

logger = logging.getLogger(__name__)


def _wire_dependencies(settings: Settings) -> TokenTracker:
    """Build shared infrastructure and inject it into the routers.

    Creates a single LLM provider, embedding provider, and ChromaStore so
    that chat and document routes operate on the same instances.

    Returns:
        The shared :class:`TokenTracker` used to record LLM usage.
    """
    tracker = TokenTracker()
    # The resolver decides which credential is active: a key the user entered
    # in Settings wins, otherwise the .env value. Passing a resolver rather
    # than a fixed string is what lets a new key take effect without a restart.
    secret_store = JsonSecretStore(settings.SECRETS_FILE_PATH)
    api_key_resolver = ApiKeyResolver(secret_store, settings)
    # ponytail: these two providers used to be built by factory functions that
    # switched over four LLMs and three embedding providers. Only Gemini and
    # local HuggingFace remain, so the factory was a pass-through with one
    # implementation — construct them directly and re-add a factory when a
    # second provider is genuinely in use.
    llm_provider = GeminiProvider(
        api_key=settings.GEMINI_API_KEY,
        model=settings.GEMINI_MODEL,
        key_resolver=api_key_resolver.resolve,
    )
    if settings.ENABLE_USAGE_TRACKING:
        llm_provider = TrackingLLMProvider(llm_provider, tracker)
    embedding_provider = HuggingFaceEmbeddingProvider(
        model_name=settings.HUGGINGFACE_MODEL
    )
    vector_store = ChromaStore(persist_directory=settings.CHROMA_PERSIST_DIR)

    reranker = create_reranker()

    rag_engine = RAGEngine(
        llm_provider=llm_provider,
        embedding_provider=embedding_provider,
        vector_store=vector_store,
        reranker=reranker,
        guardrail_manager=create_guardrail_manager(),
    )
    conversation_repository = create_conversation_repository()
    query_use_case = QueryDocumentUseCase(rag_engine, conversation_repository)

    chat.set_query_use_case(query_use_case)
    chat.set_conversation_repository(conversation_repository)
    documents.configure(
        vector_store=vector_store,
        embedding_provider=embedding_provider,
    )
    settings_routes.configure(
        resolver=api_key_resolver,
        store=secret_store,
        vector_store=vector_store,
        conversation_repository=conversation_repository,
    )

    logger.info(
        "Wired application dependencies: llm=%s embeddings=%s",
        settings.LLM_PROVIDER,
        settings.EMBEDDING_PROVIDER,
    )
    return tracker


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        settings: Optional settings instance. Uses get_settings() if not provided.

    Returns:
        Configured FastAPI application.
    """
    if settings is None:
        settings = get_settings()

    tracker = _wire_dependencies(settings)
    usage.set_tracker(tracker)

    app = FastAPI(
        title=settings.APP_NAME,
        description="Document Q&A Assistant API using RAG",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Stop FastAPI echoing the rejected value back to the caller.
    #
    # The default handler copies Pydantic's `input` field — the *entire*
    # offending value — into the response body. A 1 MB question therefore came
    # back as a 1 MB 422 that repeated the whole payload, and anything the user
    # typed (including whatever they pasted) ends up duplicated in client logs,
    # proxies and browser devtools. The location, type, message and constraint
    # are all the caller needs; the value is not.
    @app.exception_handler(RequestValidationError)
    async def _validation_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = []
        for error in exc.errors():
            detail = {k: v for k, v in error.items() if k != "input"}
            # `ctx` can hold the offending exception object, which is not JSON
            # serialisable and is of no use to a client.
            detail.pop("ctx", None)
            errors.append(detail)
        return JSONResponse(status_code=422, content={"detail": errors})

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes. The API binds loopback by default, so there is no
    # per-request auth layer; health stays separate for liveness probes.
    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(
        settings_routes.router,
        prefix="/api",
        tags=["settings"],
    )
    app.include_router(
        documents.router,
        prefix="/api",
        tags=["documents"],
    )
    app.include_router(
        chat.router,
        prefix="/api",
        tags=["chat"],
    )
    # usage router defines its own /api/usage path — no prefix.
    app.include_router(usage.router, tags=["usage"])

    return app

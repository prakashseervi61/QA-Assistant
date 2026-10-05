"""FastAPI application factory."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.application.services.rag_engine import RAGEngine
from src.application.use_cases.conversation import (
    DeleteConversationUseCase,
    GetConversationUseCase,
    ListConversationsUseCase,
)
from src.application.use_cases.query_document import QueryDocumentUseCase
from src.infrastructure.config.settings import Settings, get_settings
from src.infrastructure.embeddings.huggingface_embeddings import (
    HuggingFaceEmbeddingProvider,
)
from src.infrastructure.guardrails.guardrail_manager import create_guardrail_manager
from src.infrastructure.llm.gemini_provider import GeminiProvider
from src.infrastructure.llm.token_tracker import TokenTracker, TrackingLLMProvider
from src.infrastructure.repositories.conversation_repository_factory import (
    create_conversation_repository,
)
from src.infrastructure.vector_store.chroma_store import ChromaStore
from src.presentation.api.routes import chat, documents, health, usage

logger = logging.getLogger(__name__)

def _wire_dependencies(settings: Settings) -> TokenTracker:
    """Build shared infrastructure and inject it into the routers.

    Creates a single LLM provider, embedding provider, and ChromaStore so
    that chat and document routes operate on the same instances.

    Returns:
        The shared :class:`TokenTracker` used to record LLM usage.
    """
    tracker = TokenTracker()
    # ponytail: these two providers used to be built by factory functions that
    # switched over four LLMs and three embedding providers. Only Gemini and
    # local HuggingFace remain, so the factory was a pass-through with one
    # implementation — construct them directly and re-add a factory when a
    # second provider is genuinely in use.
    llm_provider = GeminiProvider(
        api_key=settings.GEMINI_API_KEY, model=settings.GEMINI_MODEL
    )
    if settings.ENABLE_USAGE_TRACKING:
        llm_provider = TrackingLLMProvider(llm_provider, tracker)
    embedding_provider = HuggingFaceEmbeddingProvider(
        model_name=settings.HUGGINGFACE_MODEL
    )
    vector_store = ChromaStore(persist_directory=settings.CHROMA_PERSIST_DIR)

    from src.infrastructure.rerankers.factory import create_reranker

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

    conversation_list_use_case = ListConversationsUseCase(conversation_repository)
    conversation_get_use_case = GetConversationUseCase(conversation_repository)
    conversation_delete_use_case = DeleteConversationUseCase(conversation_repository)

    chat.set_query_use_case(query_use_case)
    chat.set_conversation_list_use_case(conversation_list_use_case)
    chat.set_conversation_get_use_case(conversation_get_use_case)
    chat.set_conversation_delete_use_case(conversation_delete_use_case)
    documents.configure(
        vector_store=vector_store,
        embedding_provider=embedding_provider,
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

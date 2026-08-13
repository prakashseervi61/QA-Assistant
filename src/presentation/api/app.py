"""FastAPI application factory."""

import logging

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.application.services.rag_engine import RAGEngine
from src.application.use_cases.conversation import (
    GetConversationUseCase,
    ListConversationsUseCase,
)
from src.application.use_cases.query_document import QueryDocumentUseCase
from src.infrastructure.auth.jwt_auth import get_current_user_dependency
from src.infrastructure.config.settings import Settings, get_settings
from src.infrastructure.embeddings.factory import EmbeddingProviderFactory
from src.infrastructure.guardrails.guardrail_manager import create_guardrail_manager
from src.infrastructure.llm.factory import LLMProviderFactory
from src.infrastructure.llm.token_tracker import TokenTracker, TrackingLLMProvider
from src.infrastructure.ratelimit.limiter import rate_limit_dependency
from src.infrastructure.repositories.conversation_repository_factory import (
    create_conversation_repository,
)
from src.infrastructure.vector_store.vector_store_factory import (
    create_vector_store,
)
from src.presentation.api.routes import auth, chat, documents, health, usage

logger = logging.getLogger(__name__)

# Applied to every router except health. Both dependencies are no-ops when
# auth/rate limiting are disabled (the defaults), so existing endpoints
# behave exactly as before.
PROTECTED_ROUTER_DEPENDENCIES = [
    Depends(get_current_user_dependency),
    Depends(rate_limit_dependency),
]


def _wire_dependencies(settings: Settings) -> TokenTracker:
    """Build shared infrastructure and inject it into the routers.

    Creates a single LLM provider, embedding provider, and vector store
    (ChromaDB by default, Qdrant when configured) so that chat and
    document routes operate on the same instances.

    Returns:
        The shared :class:`TokenTracker` used to record LLM usage.
    """
    tracker = TokenTracker()
    llm_provider = LLMProviderFactory.create(settings)
    if settings.ENABLE_USAGE_TRACKING:
        llm_provider = TrackingLLMProvider(llm_provider, tracker)
    embedding_provider = EmbeddingProviderFactory.create(settings)
    vector_store = create_vector_store()

    from src.infrastructure.rerankers.factory import create_reranker

    reranker = create_reranker()

    from src.infrastructure.llm.query_rewriter_factory import (
        create_query_rewriter,
    )

    query_rewriter = create_query_rewriter(
        llm_provider, embedding_provider, vector_store
    )

    from src.infrastructure.observability.tracer import create_tracer

    tracer = create_tracer()

    rag_engine = RAGEngine(
        llm_provider=llm_provider,
        embedding_provider=embedding_provider,
        vector_store=vector_store,
        reranker=reranker,
        query_rewriter=query_rewriter,
        tracer=tracer,
        guardrail_manager=create_guardrail_manager(),
    )
    conversation_repository = create_conversation_repository()
    query_use_case = QueryDocumentUseCase(rag_engine, conversation_repository)

    conversation_list_use_case = ListConversationsUseCase(conversation_repository)
    conversation_get_use_case = GetConversationUseCase(conversation_repository)

    chat.set_query_use_case(query_use_case)
    chat.set_conversation_list_use_case(conversation_list_use_case)
    chat.set_conversation_get_use_case(conversation_get_use_case)
    documents.configure(
        vector_store=vector_store,
        embedding_provider=embedding_provider,
    )

    logger.info(
        "Wired application dependencies: llm=%s embeddings=%s vector_store=%s",
        settings.LLM_PROVIDER,
        settings.EMBEDDING_PROVIDER,
        settings.VECTOR_STORE_BACKEND,
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

    # Register routes.
    # Health stays public (liveness probes must not require auth); all
    # other routers get the auth + rate-limit dependencies (no-ops when
    # disabled).
    app.include_router(health.router, prefix="/api", tags=["health"])
    # The token endpoint stays public — it is how clients obtain a JWT.
    # It is deliberately NOT part of PROTECTED_ROUTER_DEPENDENCIES.
    app.include_router(auth.router, prefix="/api", tags=["auth"])
    app.include_router(
        documents.router,
        prefix="/api",
        tags=["documents"],
        dependencies=PROTECTED_ROUTER_DEPENDENCIES,
    )
    app.include_router(
        chat.router,
        prefix="/api",
        tags=["chat"],
        dependencies=PROTECTED_ROUTER_DEPENDENCIES,
    )
    # usage router defines its own /api/usage path — no prefix.
    app.include_router(
        usage.router,
        tags=["usage"],
        dependencies=PROTECTED_ROUTER_DEPENDENCIES,
    )

    return app

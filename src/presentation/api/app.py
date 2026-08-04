"""FastAPI application factory."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.application.services.rag_engine import RAGEngine
from src.application.use_cases.conversation import (
    GetConversationUseCase,
    ListConversationsUseCase,
)
from src.application.use_cases.query_document import QueryDocumentUseCase
from src.infrastructure.config.settings import Settings, get_settings
from src.infrastructure.embeddings.factory import EmbeddingProviderFactory
from src.infrastructure.llm.factory import LLMProviderFactory
from src.infrastructure.repositories.memory_conversation_repository import (
    MemoryConversationRepository,
)
from src.infrastructure.vector_store.chroma_store import ChromaStore
from src.presentation.api.routes import chat, documents, health

logger = logging.getLogger(__name__)


def _wire_dependencies(settings: Settings) -> None:
    """Build shared infrastructure and inject it into the routers.

    Creates a single LLM provider, embedding provider, and ChromaStore so
    that chat and document routes operate on the same instances.
    """
    llm_provider = LLMProviderFactory.create(settings)
    embedding_provider = EmbeddingProviderFactory.create(settings)
    vector_store = ChromaStore(persist_directory=settings.CHROMA_PERSIST_DIR)

    from src.infrastructure.rerankers.factory import create_reranker

    reranker = create_reranker()

    rag_engine = RAGEngine(
        llm_provider=llm_provider,
        embedding_provider=embedding_provider,
        vector_store=vector_store,
        reranker=reranker,
    )
    conversation_repository = MemoryConversationRepository()
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
        "Wired application dependencies: llm=%s embeddings=%s",
        settings.LLM_PROVIDER,
        settings.EMBEDDING_PROVIDER,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        settings: Optional settings instance. Uses get_settings() if not provided.

    Returns:
        Configured FastAPI application.
    """
    if settings is None:
        settings = get_settings()

    _wire_dependencies(settings)

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

    # Register routes
    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(documents.router, prefix="/api", tags=["documents"])
    app.include_router(chat.router, prefix="/api", tags=["chat"])

    return app

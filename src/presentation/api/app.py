"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.infrastructure.config.settings import Settings, get_settings
from src.presentation.api.routes import health, documents, chat


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application.
    
    Args:
        settings: Optional settings instance. Uses get_settings() if not provided.
        
    Returns:
        Configured FastAPI application.
    """
    if settings is None:
        settings = get_settings()

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

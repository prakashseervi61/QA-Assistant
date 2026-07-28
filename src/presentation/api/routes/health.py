"""Health check endpoints."""

from fastapi import APIRouter

from src.application.dto.responses import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Liveness and readiness probe."""
    return HealthResponse(
        status="healthy",
        version="0.1.0",
        vector_store="initialized",
    )

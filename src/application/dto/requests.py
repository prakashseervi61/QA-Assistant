"""Request DTOs for API endpoints."""

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Request model for document querying."""

    question: str = Field(..., min_length=1, max_length=5000)
    top_k: int = Field(default=5, ge=1, le=20)
    conversation_id: str | None = Field(
        default=None, description="Optional conversation ID to continue"
    )

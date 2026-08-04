"""Request DTOs for API endpoints."""

from pydantic import BaseModel, Field, field_validator


class QueryRequest(BaseModel):
    """Request model for document querying."""

    question: str = Field(..., min_length=1, max_length=5000)
    top_k: int = Field(default=5, ge=1, le=20)
    conversation_id: str | None = Field(
        default=None, description="Optional conversation ID to continue"
    )
    metadata_filter: dict[str, object] | None = Field(
        default=None,
        description="Optional metadata filter (e.g. {\"document_id\": \"abc\"})",
    )

    @field_validator("metadata_filter")
    @classmethod
    def validate_metadata_filter(
        cls, v: dict[str, object] | None
    ) -> dict[str, object] | None:
        if v is None:
            return v
        allowed_types = (str, int, float, bool)
        for key, value in v.items():
            if not isinstance(key, str):
                raise ValueError(
                    f"Filter key must be str, got {type(key).__name__}"
                )
            if not isinstance(value, allowed_types):
                raise ValueError(
                    f"Filter value for '{key}' must be one of {allowed_types}, "
                    f"got {type(value).__name__}"
                )
        return v

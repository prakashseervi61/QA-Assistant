"""Structured answer DTOs with citation support."""

from pydantic import BaseModel, Field


class Citation(BaseModel):
    """A single citation linking an answer claim to a source chunk."""

    chunk_id: str = Field(description="ID of the source chunk")
    source: str = Field(description="Source filename or document name")
    page: int | None = Field(default=None, description="Page number if known")
    excerpt: str = Field(description="Short text excerpt from the source")


class StructuredAnswer(BaseModel):
    """The structured LLM answer with citations."""

    answer: str = Field(description="The final answer text")
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

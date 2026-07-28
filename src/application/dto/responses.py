"""Response DTOs for API endpoints."""

from pydantic import BaseModel, Field


class IngestResponse(BaseModel):
    """Response model for document ingestion."""

    document_id: str
    filename: str
    chunk_count: int
    message: str


class SourceChunk(BaseModel):
    """A source chunk used in generating a response."""

    content: str
    metadata: dict = Field(default_factory=dict)
    score: float = 0.0
    chunk_index: int = 0


class QueryResponse(BaseModel):
    """Response model for document querying."""

    answer: str
    sources: list[SourceChunk] = Field(default_factory=list)
    confidence: float = 0.0
    conversation_id: str | None = None
    message_id: str | None = None


class MessageResponse(BaseModel):
    """Response model for a single message in a conversation."""

    id: str
    role: str
    content: str
    sources: list[SourceChunk] = Field(default_factory=list)
    created_at: str


class ConversationResponse(BaseModel):
    """Response model for a conversation."""

    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0


class DocumentInfo(BaseModel):
    """Document metadata in list response."""

    id: str
    filename: str
    content_type: str
    file_size: int
    chunk_count: int
    created_at: str


class DocumentListResponse(BaseModel):
    """Response model for listing documents."""

    documents: list[DocumentInfo] = Field(default_factory=list)
    total: int = 0


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str
    version: str
    vector_store: str = "unknown"

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.document_schemas import DocumentMetadata


class Paper(BaseModel):
    id: str
    title: str
    source: Literal["pubmed", "biorxiv", "medrxiv", "patent", "conference"]
    doi: str | None = None
    published_at: datetime | None = None
    citation_count: int = 0


class IngestionRequest(BaseModel):
    source: Literal["pubmed", "biorxiv", "medrxiv", "patent", "conference"]
    query: str
    schedule: str | None = None


class IngestionJob(BaseModel):
    id: str
    source: str
    query: str
    status: Literal[
        "queued", "scheduled", "running", "completed", "failed", "cancelled"
    ]
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    schedule: str | None = None
    next_run_at: datetime | None = None
    documents_total: int = 0
    documents_processed: int = 0
    documents_failed: int = 0
    retry_count: int = 0
    backoff_until: datetime | None = None
    error_message: str | None = None
    dead_letter_count: int = 0
    dead_letter_items: list[dict[str, Any]] = Field(default_factory=list)


class DocumentParseRequest(BaseModel):
    format: Literal["pdf", "xml", "html", "nxml", "jats"]
    content: str


class DocumentParseResponse(BaseModel):
    metadata: DocumentMetadata
    duplicate: bool = False
    metrics: dict[str, int] = Field(default_factory=dict)

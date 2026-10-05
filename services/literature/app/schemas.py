from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.document_schemas import DocumentMetadata


class Paper(BaseModel):
    id: str
    title: str
    source: Literal["pubmed", "clinicaltrials", "regulatory", "biorxiv", "medrxiv", "patent", "conference"]
    doi: str | None = None
    published_at: datetime | None = None
    citation_count: int = 0
    pmid: str | None = None
    pmcid: str | None = None
    abstract: str | None = None
    authors: list[Any] = Field(default_factory=list)
    journal: str | None = None
    source_id: str | None = None
    publication_date_source: str | None = None
    retrieved_at: datetime | None = None
    ingested_at: datetime | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    extracted_entities: list[dict[str, Any]] = Field(default_factory=list)
    extracted_relationships: list[dict[str, Any]] = Field(default_factory=list)
    canonical_entity_id: str | None = None
    reconciliation_status: str | None = None


class IngestionRequest(BaseModel):
    source: Literal["pubmed", "clinicaltrials", "regulatory", "biorxiv", "medrxiv", "patent", "conference"]
    query: str
    schedule: str | None = None
    page_size: int = Field(default=50, ge=1, le=1000)


class IngestionJob(BaseModel):
    id: str
    source: str
    query: str
    status: str
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
    checkpoint: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None


class DocumentParseRequest(BaseModel):
    format: Literal["pdf", "xml", "html", "nxml", "jats"]
    content: str


class DocumentParseResponse(BaseModel):
    metadata: DocumentMetadata
    duplicate: bool = False
    metrics: dict[str, int] = Field(default_factory=dict)

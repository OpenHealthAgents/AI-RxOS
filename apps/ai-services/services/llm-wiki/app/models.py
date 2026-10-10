from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WikiCompileRequest(BaseModel):
    """Exactly the payload services/literature's LLMWikiClient.update_wiki()
    posts to POST /api/v1/wiki/compile -- see
    services/literature/app/integrations/wiki_client.py:66-74."""

    document: dict[str, Any] = Field(default_factory=dict)
    entities: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    tenant: dict[str, Any] = Field(default_factory=dict)
    chunks: list[dict[str, Any]] = Field(default_factory=list)


class PageResult(BaseModel):
    id: str
    category: str
    slug: str
    entity_id: str
    version: int


class WikiCompileResponse(BaseModel):
    # The literature client never parses this body (any 2xx is treated as
    # success -- wiki_client.py:77-79); shaped for the new read endpoints
    # and for tests/tooling that do want the created page ids back.
    success: bool = True
    method: str = "http"
    status: str = "completed"
    pages: list[PageResult] = Field(default_factory=list)


class WikiQueryRequest(BaseModel):
    """Exactly the payload services/search's LLMWikiProvider posts to
    POST /llmwiki/query -- see
    services/search/internal/search/providers_placeholder.go:64-69."""

    embedding: list[float] = Field(default_factory=list)
    limit: int = 10
    organization_id: str | None = None
    workspace_id: str | None = None


class WikiHit(BaseModel):
    """Field names/casing match services/search's Hit struct exactly
    (services/search/internal/search/opensearch.go:161-169)."""

    id: str
    score: float
    title: str
    snippet: str
    source: str | None = None
    citationCount: int | None = None
    graphScore: float | None = None
    rrfScore: float | None = None


class WikiQueryResponse(BaseModel):
    items: list[WikiHit] = Field(default_factory=list)


class VersionSummary(BaseModel):
    version: int
    created_at: str


class PageVersionDetail(BaseModel):
    version: int
    document: dict[str, Any]
    entity: dict[str, Any]
    summary: dict[str, Any]
    relationships: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    chunks: list[dict[str, Any]]
    provenance: dict[str, Any]
    created_at: str


class PageDetail(BaseModel):
    id: str
    organization_id: str | None
    workspace_id: str | None
    project_id: str | None
    category: str
    slug: str
    entity_id: str | None
    title: str | None
    current_version: int
    created_at: str
    updated_at: str
    latest_version: PageVersionDetail | None = None

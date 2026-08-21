from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import require_api_key
from app.core.config import get_settings
from app.deps import get_repository
from app.models import (
    PageDetail,
    PageVersionDetail,
    VersionSummary,
    WikiCompileRequest,
    WikiCompileResponse,
    WikiHit,
    WikiQueryRequest,
    WikiQueryResponse,
)
from app.repository import TenantScope, ValidationError, WikiRepository

router = APIRouter(dependencies=[Depends(require_api_key)])


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _parse_page_id(page_id: str) -> str:
    try:
        return str(uuid.UUID(page_id))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="page not found") from exc


def _tenant_from_query(organization_id: str | None, workspace_id: str | None) -> TenantScope:
    try:
        return TenantScope.from_dict({"organization_id": organization_id, "workspace_id": workspace_id})
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/api/v1/wiki/compile", response_model=WikiCompileResponse, status_code=status.HTTP_201_CREATED)
async def compile_wiki(
    body: WikiCompileRequest, repo: WikiRepository = Depends(get_repository)
) -> WikiCompileResponse:
    try:
        tenant = TenantScope.from_dict(body.tenant)
        pages = await repo.compile_pages(
            tenant=tenant,
            document=body.document,
            entities=body.entities,
            summary=body.summary,
            relationships=body.relationships,
            evidence=body.evidence,
            chunks=body.chunks,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return WikiCompileResponse(pages=pages)


@router.post("/llmwiki/query", response_model=WikiQueryResponse)
async def query_wiki(
    body: WikiQueryRequest, repo: WikiRepository = Depends(get_repository)
) -> WikiQueryResponse:
    settings = get_settings()
    limit = min(max(body.limit or settings.query_default_limit, 1), settings.query_max_limit)
    try:
        tenant = TenantScope.from_dict(
            {"organization_id": body.organization_id, "workspace_id": body.workspace_id}
        )
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    rows = await repo.query_pages(tenant, limit)
    items = []
    for i, row in enumerate(rows):
        summary = row.get("summary") or {}
        snippet = str(summary.get("concise_summary") or "")[:280]
        items.append(
            WikiHit(
                id=str(row["id"]),
                score=round(1.0 - i * 0.01, 4),
                title=row.get("title") or row.get("slug") or "",
                snippet=snippet,
                source="llm-wiki",
            )
        )
    return WikiQueryResponse(items=items)


@router.get("/api/v1/wiki/pages/{page_id}", response_model=PageDetail)
async def get_page(
    page_id: str,
    organization_id: str | None = Query(default=None),
    workspace_id: str | None = Query(default=None),
    repo: WikiRepository = Depends(get_repository),
) -> PageDetail:
    page_id = _parse_page_id(page_id)
    tenant = _tenant_from_query(organization_id, workspace_id)
    result = await repo.get_page(tenant, page_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="page not found")

    page = result["page"]
    version = result["version"]
    latest_version = None
    if version is not None:
        latest_version = PageVersionDetail(
            version=version["version"],
            document=version["document"],
            entity=version["entity"],
            summary=version["summary"],
            relationships=version["relationships"],
            evidence=version["evidence"],
            chunks=version["chunks"],
            provenance=version["provenance"],
            created_at=_iso(version["created_at"]),
        )
    return PageDetail(
        id=str(page["id"]),
        organization_id=page["organization_id"],
        workspace_id=page["workspace_id"],
        project_id=page["project_id"],
        category=page["category"],
        slug=page["slug"],
        entity_id=page["entity_id"],
        title=page["title"],
        current_version=page["current_version"],
        created_at=_iso(page["created_at"]),
        updated_at=_iso(page["updated_at"]),
        latest_version=latest_version,
    )


@router.get("/api/v1/wiki/pages/{page_id}/versions", response_model=list[VersionSummary])
async def list_page_versions(
    page_id: str,
    organization_id: str | None = Query(default=None),
    workspace_id: str | None = Query(default=None),
    repo: WikiRepository = Depends(get_repository),
) -> list[VersionSummary]:
    page_id = _parse_page_id(page_id)
    tenant = _tenant_from_query(organization_id, workspace_id)
    versions = await repo.list_versions(tenant, page_id)
    if versions is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="page not found")
    return [VersionSummary(version=v["version"], created_at=_iso(v["created_at"])) for v in versions]


@router.get("/api/v1/wiki/pages/{page_id}/versions/{version}", response_model=PageVersionDetail)
async def get_page_version(
    page_id: str,
    version: int,
    organization_id: str | None = Query(default=None),
    workspace_id: str | None = Query(default=None),
    repo: WikiRepository = Depends(get_repository),
) -> PageVersionDetail:
    page_id = _parse_page_id(page_id)
    tenant = _tenant_from_query(organization_id, workspace_id)
    row = await repo.get_version(tenant, page_id, version)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="version not found")
    return PageVersionDetail(
        version=row["version"],
        document=row["document"],
        entity=row["entity"],
        summary=row["summary"],
        relationships=row["relationships"],
        evidence=row["evidence"],
        chunks=row["chunks"],
        provenance=row["provenance"],
        created_at=_iso(row["created_at"]),
    )


@router.get("/api/v1/wiki/pages", response_model=PageDetail)
async def find_page(
    category: str = Query(...),
    slug: str = Query(...),
    organization_id: str | None = Query(default=None),
    workspace_id: str | None = Query(default=None),
    repo: WikiRepository = Depends(get_repository),
) -> PageDetail:
    tenant = _tenant_from_query(organization_id, workspace_id)
    page = await repo.find_page(tenant, category=category, slug=slug)
    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="page not found")
    return await get_page(str(page["id"]), organization_id, workspace_id, repo)

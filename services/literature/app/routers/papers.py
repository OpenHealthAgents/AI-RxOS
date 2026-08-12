from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import get_current_user
from app.database.postgres import postgres_manager
from app.schemas import Paper

router = APIRouter(prefix="/papers", tags=["Papers"])

auth_dependency = Depends(get_current_user)


@router.get("", response_model=dict)
async def list_papers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict[str, object]:
    offset = (page - 1) * page_size
    if postgres_manager.pool is None:
        from app.main import _PAPERS
        items = list(_PAPERS.values())[offset : offset + page_size]
        return {
            "items": items,
            "total": len(_PAPERS),
            "page": page,
            "pageSize": page_size,
        }

    async with postgres_manager.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT id::text, title, source, doi, published_at, citation_count
            FROM literature_papers
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
            """,
            page_size,
            offset,
        )
        total = await connection.fetchval("SELECT COUNT(*) FROM literature_papers")

    return {
        "items": [dict(row) for row in rows],
        "total": total,
        "page": page,
        "pageSize": page_size,
    }


@router.get("/{paper_id}", response_model=Paper)
async def get_paper(
    paper_id: UUID,
    auth_payload: dict[str, str] = auth_dependency,
) -> Paper:
    if postgres_manager.pool is None:
        from app.main import _PAPERS
        paper = _PAPERS.get(str(paper_id))
        if paper is None:
            raise HTTPException(status_code=404, detail="paper not found")
        published_at_val = paper.get("publishedAt")
        from datetime import datetime
        published_at_dt = None
        if isinstance(published_at_val, str):
            try:
                published_at_dt = datetime.fromisoformat(published_at_val)
            except ValueError:
                pass
        return Paper(
            id=paper["id"],
            title=paper["title"],
            source=paper["source"],
            doi=paper.get("doi"),
            published_at=published_at_dt,
            citation_count=paper.get("citationCount") or 0,
        )

    async with postgres_manager.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT id::text, title, source, doi, published_at, citation_count
            FROM literature_papers
            WHERE id = $1
            """,
            paper_id,
        )

    if row is None:
        raise HTTPException(status_code=404, detail="paper not found")

    return Paper(**dict(row))

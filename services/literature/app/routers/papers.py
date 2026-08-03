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

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.db.pool import get_pool_dependency

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "llm-wiki"}


@router.get("/readyz")
async def readyz(response: Response) -> dict[str, str]:
    try:
        pool = get_pool_dependency()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "ready", "service": "llm-wiki"}
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "service": "llm-wiki"}

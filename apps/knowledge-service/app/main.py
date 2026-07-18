from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from neo4j import AsyncDriver, AsyncGraphDatabase
from pydantic import BaseModel

from app.core.config import get_settings

settings = get_settings()
_driver: AsyncDriver | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _driver
    _driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    yield
    if _driver:
        await _driver.close()


app = FastAPI(
    title="AI-RxOS Knowledge Service",
    description="Frontend-facing aggregation over the Knowledge Graph context "
    "(Graph, Entity Resolution, Ontology services).",
    version="0.1.0",
    lifespan=lifespan,
)


class GraphEntity(BaseModel):
    id: str
    label: str
    type: str
    properties: dict[str, Any] = {}


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "knowledge-service"}


@app.get("/api/v1/knowledge/entities/{entity_id}", response_model=GraphEntity)
async def get_entity(entity_id: str) -> GraphEntity:
    assert _driver is not None
    async with _driver.session() as session:
        record = await session.run(
            "MATCH (n {id: $id}) RETURN n.id AS id, labels(n)[0] AS type, n AS props LIMIT 1",
            id=entity_id,
        )
        row = await record.single()
        if row is None:
            raise HTTPException(status_code=404, detail="entity not found")
        return GraphEntity(
            id=row["id"],
            label=row["props"].get("name", row["id"]),
            type=row["type"] or "unknown",
            properties=dict(row["props"]),
        )


@app.get("/api/v1/knowledge/entities/{entity_id}/neighbors")
async def get_neighbors(entity_id: str, limit: int = 25) -> dict[str, list[dict[str, Any]]]:
    assert _driver is not None
    async with _driver.session() as session:
        result = await session.run(
            "MATCH (n {id: $id})--(m) RETURN DISTINCT m.id AS id, labels(m)[0] AS type "
            "LIMIT $limit",
            id=entity_id,
            limit=limit,
        )
        rows = [dict(r) async for r in result]
        return {"neighbors": rows}

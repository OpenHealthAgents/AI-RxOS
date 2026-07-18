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
    title="AI-RxOS Graph Service",
    description="Core graph CRUD, Cypher execution, and traversal — the "
    "Knowledge Graph context's system of record (backs the Graph, Entity "
    "Resolution, and Ontology services).",
    version="0.1.0",
    lifespan=lifespan,
)


class UpsertNodeRequest(BaseModel):
    id: str
    label: str
    properties: dict[str, Any] = {}


class CypherQuery(BaseModel):
    query: str
    parameters: dict[str, Any] = {}


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "kg"}


@app.post("/api/v1/graph/nodes", status_code=201)
async def upsert_node(req: UpsertNodeRequest) -> dict[str, Any]:
    assert _driver is not None
    async with _driver.session() as session:
        await session.run(
            f"MERGE (n:{req.label} {{id: $id}}) SET n += $props",
            id=req.id,
            props=req.properties,
        )
    return {"id": req.id, "label": req.label, "status": "upserted"}


@app.post("/api/v1/graph/query")
async def run_cypher(req: CypherQuery) -> dict[str, list[dict[str, Any]]]:
    """Executes read-only Cypher. Production deployments should validate
    against a read-only Neo4j role rather than trusting caller intent."""
    assert _driver is not None
    if any(kw in req.query.upper() for kw in ("CREATE", "DELETE", "MERGE", "SET", "REMOVE")):
        raise HTTPException(status_code=400, detail="only read queries are permitted here")
    async with _driver.session() as session:
        result = await session.run(req.query, req.parameters)
        rows = [record.data() async for record in result]
    return {"results": rows}

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

from app.core.config import get_settings
from app.database.neo4j import neo4j_manager
from app.cypher import queries
from app.routers import nodes, relationships, graph, imports, versions
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

@asynccontextmanager
async def lifespan(_: FastAPI):
    # Initialize the Neo4j connection pool
    logger.info("Initializing Neo4j connection pool...")
    neo4j_manager.init_driver(settings)
    
    # Automatically create uniqueness constraints and range indexes
    logger.info("Creating uniqueness constraints and indexes...")
    try:
        async with neo4j_manager.get_session() as session:
            await session.execute_write(queries.create_constraints_and_indexes)
        logger.info("Database constraints and indexes initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database constraints and indexes: {str(e)}", exc_info=True)
        
    yield
    
    # Close the Neo4j connection pool
    logger.info("Closing Neo4j connection pool...")
    await neo4j_manager.close()
    logger.info("Neo4j connection pool closed.")

app = FastAPI(
    title="AI-RxOS Graph Service",
    description="Core graph CRUD, Cypher execution, and traversal — the "
    "Knowledge Graph context's system of record (backs the Graph, Entity "
    "Resolution, and Ontology services).",
    version="0.1.0",
    lifespan=lifespan,
)

# Wire modern API routers under /api/v1/graph path prefix
app.include_router(nodes.router, prefix="/api/v1/graph")
app.include_router(relationships.router, prefix="/api/v1/graph")
app.include_router(graph.router, prefix="/api/v1/graph")
app.include_router(imports.router, prefix="/api/v1/graph")
app.include_router(versions.router, prefix="/api/v1/graph")

# Legacy compatibility schemas & routes
class CypherQuery(BaseModel):
    query: str
    parameters: dict[str, Any] = {}

@app.post("/api/v1/graph/query", tags=["Legacy Compatibility"])
async def run_cypher(req: CypherQuery) -> dict[str, list[dict[str, Any]]]:
    """Executes read-only Cypher. Production deployments should validate
    against a read-only Neo4j role rather than trusting caller intent."""
    if any(kw in req.query.upper() for kw in ("CREATE", "DELETE", "MERGE", "SET", "REMOVE")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="only read queries are permitted here"
        )
    try:
        async with neo4j_manager.get_session() as session:
            result = await session.run(req.query, req.parameters)
            rows = [record.data() async for record in result]
        return {"results": rows}
    except Exception as e:
        logger.error(f"Legacy Cypher execution failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cypher execution failed: {str(e)}"
        )

# Health routes
@app.get("/healthz", tags=["Health"])
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "kg"}

@app.get("/health", tags=["Health"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "kg"}

@app.get("/api/v1/graph/health", tags=["Health"])
def api_health() -> dict[str, str]:
    return {"status": "ok", "service": "kg"}

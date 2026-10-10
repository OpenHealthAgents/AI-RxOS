import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

from app.core.config import get_settings
from app.database.neo4j import neo4j_manager
from app.database.canonical_store import canonical_store
from app.services.canonical_projection import CanonicalProjectionWorker
from app.cypher import queries
from app.routers import nodes, relationships, graph, imports, versions, canonical
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()
projection_worker = CanonicalProjectionWorker(canonical_store, neo4j_manager, settings)


async def _canonical_projection_loop() -> None:
    while True:
        try:
            if canonical_store.pool is not None:
                await projection_worker.run_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Canonical projection poll failed")
        await asyncio.sleep(5)

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

    try:
        await canonical_store.initialize(settings.database_url)
    except Exception:
        logger.exception("Canonical PostgreSQL store is unavailable; canonical routes will return 503")

    projection_task = asyncio.create_task(_canonical_projection_loop())
    try:
        yield
    finally:
        projection_task.cancel()
        try:
            await projection_task
        except asyncio.CancelledError:
            pass

        logger.info("Closing KG database connections...")
        await neo4j_manager.close()
        await canonical_store.close()

app = FastAPI(
    title="AI-RxOS Graph Service",
    description="Core graph CRUD, Cypher execution, and traversal — the Knowledge Graph context's system of record (backs the Graph, Entity Resolution, and Ontology services).",
    version="0.1.0",
    lifespan=lifespan,
    state=app_state,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Wire modern API routers under /api/v1/graph path prefix
app.include_router(nodes.router, prefix="/api/v1/graph")
app.include_router(relationships.router, prefix="/api/v1/graph")
app.include_router(graph.router, prefix="/api/v1/graph")
app.include_router(imports.router, prefix="/api/v1/graph")
app.include_router(versions.router, prefix="/api/v1/graph")
app.include_router(canonical.router)

# Legacy compatibility schemas & routes
class CypherQuery(BaseModel):
    query: str
    parameters: dict[str, Any] = {}

@app.post("/api/v1/graph/query", tags=["Legacy Compatibility"])
async def run_cypher(_: CypherQuery) -> dict[str, list[dict[str, Any]]]:
    """The legacy arbitrary-Cypher surface is disabled to prevent scope bypass."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="arbitrary Cypher execution is disabled; use scoped graph APIs",
    )

# Health routes with rate limiting
@app.get("/healthz", tags=["Health"])
@limiter.limit("100/minute")
def healthz(request: Request) -> dict[str, str]:
    return {"status": "ok", "service": "kg"}

@app.get("/health", tags=["Health"])
@limiter.limit("100/minute")
def health(request: Request) -> dict[str, str]:
    return {"status": "ok", "service": "kg"}

@app.get("/api/v1/graph/health", tags=["Health"])
@limiter.limit("100/minute")
def api_health(request: Request) -> dict[str, str]:
    return {"status": "ok", "service": "kg"}
@app.get("/api/v1/graph/health", tags=["Health"])
def api_health() -> dict[str, str]:
    return {"status": "ok", "service": "kg"}

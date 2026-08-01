from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.database.postgres import postgres_manager
from app.orchestrator.manager import orchestrator
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.environment == "test":
        logger.info("Skipping PostgreSQL lifecycle in test environment")
        yield
        return

    logger.info("Literature service starting")
    logger.info("Initializing PostgreSQL connection pool...")
    try:
        await postgres_manager.init_pool(settings)
        logger.info("Ensuring literature schema is available...")
        await postgres_manager.ensure_schema()
        logger.info("Literature database schema is ready.")
    except Exception as exc:
        postgres_manager.last_error = exc
        logger.exception(
            "PostgreSQL startup initialization failed; service will continue in degraded mode"
        )

    try:
        await orchestrator.start()
        yield
    finally:
        logger.info("Stopping ingestion orchestrator...")
        await orchestrator.stop()
        logger.info("Closing PostgreSQL connection pool...")
        await postgres_manager.close()
        logger.info("PostgreSQL connection pool closed.")

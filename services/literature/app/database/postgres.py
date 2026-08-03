from contextlib import asynccontextmanager

import asyncpg

from app.core.config import Settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class PostgresManager:
    def __init__(self) -> None:
        self.pool: asyncpg.Pool | None = None
        self.last_error: Exception | None = None

    async def init_pool(self, settings: Settings) -> None:
        self.last_error = None
        try:
            self.pool = await asyncpg.create_pool(
                dsn=settings.database_url,
                min_size=1,
                max_size=10,
            )
            logger.info("PostgreSQL pool initialized")
        except Exception as exc:
            self.pool = None
            self.last_error = exc
            logger.exception("PostgreSQL pool initialization failed")
            raise

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("PostgreSQL pool closed")

    def _ensure_pool(self) -> asyncpg.Pool:
        if self.pool is None:
            raise RuntimeError("PostgreSQL pool is not initialized")
        return self.pool

    @asynccontextmanager
    async def acquire(self):
        pool = self._ensure_pool()
        async with pool.acquire() as connection:
            yield connection

    async def ensure_schema(self) -> bool:
        try:
            async with self.acquire() as connection:
                await connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS literature_papers (
                        id UUID PRIMARY KEY,
                        title TEXT NOT NULL,
                        source TEXT NOT NULL,
                        doi TEXT,
                        published_at TIMESTAMPTZ,
                        citation_count INT NOT NULL DEFAULT 0,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                await connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS literature_ingestion_jobs (
                        id UUID PRIMARY KEY,
                        source TEXT NOT NULL,
                        query TEXT NOT NULL,
                        status TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        started_at TIMESTAMPTZ,
                        completed_at TIMESTAMPTZ,
                        schedule TEXT,
                        next_run_at TIMESTAMPTZ,
                        documents_total INT NOT NULL DEFAULT 0,
                        documents_processed INT NOT NULL DEFAULT 0,
                        documents_failed INT NOT NULL DEFAULT 0,
                        retry_count INT NOT NULL DEFAULT 0,
                        backoff_until TIMESTAMPTZ,
                        error_message TEXT,
                        dead_letter_count INT NOT NULL DEFAULT 0,
                        dead_letter_items TEXT
                    )
                    """
                )
                logger.info("Literature schema ensured")
                self.last_error = None
                return True
        except Exception as exc:
            self.last_error = exc
            logger.exception("Failed to initialize literature database schema")
            return False


postgres_manager = PostgresManager()

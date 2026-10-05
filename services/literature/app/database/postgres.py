from contextlib import asynccontextmanager
import json
import hashlib
from datetime import datetime
from typing import AsyncIterator
from uuid import UUID, uuid4

import asyncpg

from app.core.config import Settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class PostgresManager:
    def __init__(self) -> None:
        self.pool: asyncpg.Pool | None = None
        self.migration_pool: asyncpg.Pool | None = None
        self.last_error: Exception | None = None

    async def init_pool(self, settings: Settings) -> None:
        self.last_error = None
        try:
            self.pool = await asyncpg.create_pool(
                dsn=settings.database_url,
                min_size=1,
                max_size=10,
            )
            if (
                settings.literature_migration_database_url
                and settings.literature_migration_database_url != settings.database_url
            ):
                self.migration_pool = await asyncpg.create_pool(
                    dsn=settings.literature_migration_database_url,
                    min_size=1,
                    max_size=2,
                )
            logger.info("PostgreSQL pool initialized")
        except Exception as exc:
            if self.pool:
                await self.pool.close()
            self.pool = None
            self.migration_pool = None
            self.last_error = exc
            logger.exception("PostgreSQL pool initialization failed")
            raise

    async def close(self) -> None:
        if self.migration_pool:
            await self.migration_pool.close()
            self.migration_pool = None
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("PostgreSQL pool closed")

    def _ensure_pool(self) -> asyncpg.Pool:
        if self.pool is None:
            raise RuntimeError("PostgreSQL pool is not initialized")
        return self.pool

    @asynccontextmanager
    async def _acquire_pool(
        self,
        pool: asyncpg.Pool,
        organization_id: str | None = None,
        *,
        system_scope: bool = False,
    ) -> AsyncIterator[asyncpg.Connection]:
        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "SELECT set_config('app.literature_organization_id', $1, true)",
                    str(organization_id) if organization_id else "",
                )
                await connection.execute(
                    "SELECT set_config('app.literature_system_scope', $1, true)",
                    "true" if system_scope else "false",
                )
                yield connection

    @asynccontextmanager
    async def acquire(
        self,
        organization_id: str | None = None,
        *,
        system_scope: bool = False,
    ) -> AsyncIterator[asyncpg.Connection]:
        async with self._acquire_pool(
            self._ensure_pool(), organization_id, system_scope=system_scope
        ) as connection:
            yield connection

    async def ensure_schema(self) -> bool:
        try:
            schema_pool = self.migration_pool or self._ensure_pool()
            async with self._acquire_pool(schema_pool, system_scope=True) as connection:
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
                for statement in (
                    "ALTER TABLE literature_papers ADD COLUMN IF NOT EXISTS abstract TEXT",
                    "ALTER TABLE literature_papers ADD COLUMN IF NOT EXISTS authors JSONB NOT NULL DEFAULT '[]'::jsonb",
                    "ALTER TABLE literature_papers ADD COLUMN IF NOT EXISTS pmid TEXT",
                    "ALTER TABLE literature_papers ADD COLUMN IF NOT EXISTS pmcid TEXT",
                    "ALTER TABLE literature_papers ADD COLUMN IF NOT EXISTS journal TEXT",
                    "ALTER TABLE literature_papers ADD COLUMN IF NOT EXISTS source_metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
                    "ALTER TABLE literature_papers ADD COLUMN IF NOT EXISTS extracted_entities JSONB NOT NULL DEFAULT '[]'::jsonb",
                    "ALTER TABLE literature_papers ADD COLUMN IF NOT EXISTS extracted_relationships JSONB NOT NULL DEFAULT '[]'::jsonb",
                    "ALTER TABLE literature_papers ADD COLUMN IF NOT EXISTS tenant_id UUID",
                    "ALTER TABLE literature_papers ADD COLUMN IF NOT EXISTS source_id TEXT",
                    "ALTER TABLE literature_papers ADD COLUMN IF NOT EXISTS publication_date_source TEXT",
                    "ALTER TABLE literature_papers ADD COLUMN IF NOT EXISTS retrieved_at TIMESTAMPTZ",
                    "ALTER TABLE literature_papers ADD COLUMN IF NOT EXISTS ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
                    "ALTER TABLE literature_papers ADD COLUMN IF NOT EXISTS canonical_entity_id UUID",
                    "ALTER TABLE literature_papers ADD COLUMN IF NOT EXISTS reconciliation_status TEXT",
                ):
                    await connection.execute(statement)
                await connection.execute(
                    """CREATE UNIQUE INDEX IF NOT EXISTS literature_papers_pubmed_pmid_scope_unique
                    ON literature_papers (source, pmid,
                        (COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid)))
                    WHERE source = 'pubmed' AND pmid IS NOT NULL"""
                )
                await connection.execute(
                    """CREATE UNIQUE INDEX IF NOT EXISTS literature_papers_clinicaltrials_id_scope_unique
                    ON literature_papers (source, source_id,
                        (COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid)))
                    WHERE source = 'clinicaltrials' AND source_id IS NOT NULL"""
                )
                await connection.execute(
                    """CREATE UNIQUE INDEX IF NOT EXISTS literature_papers_regulatory_id_scope_unique
                    ON literature_papers (source, source_id,
                        (COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid)))
                    WHERE source = 'regulatory' AND source_id IS NOT NULL"""
                )
                await connection.execute(
                    """CREATE UNIQUE INDEX IF NOT EXISTS literature_papers_patent_id_scope_unique
                    ON literature_papers (source, source_id,
                        (COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid)))
                    WHERE source = 'patent' AND source_id IS NOT NULL"""
                )
                await connection.execute(
                    """CREATE TABLE IF NOT EXISTS literature_source_snapshots (
                        id UUID PRIMARY KEY,
                        source TEXT NOT NULL,
                        source_id TEXT NOT NULL,
                        content_hash TEXT NOT NULL,
                        raw_payload JSONB NOT NULL,
                        tenant_id UUID,
                        retrieved_at TIMESTAMPTZ NOT NULL,
                        ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )"""
                )
                await connection.execute(
                    """CREATE UNIQUE INDEX IF NOT EXISTS literature_source_snapshots_identity_unique
                    ON literature_source_snapshots (source, source_id, content_hash,
                        (COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid)))"""
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
                await connection.execute(
                    "ALTER TABLE literature_ingestion_jobs ADD COLUMN IF NOT EXISTS organization_id UUID"
                )
                await connection.execute(
                    "ALTER TABLE literature_ingestion_jobs ADD COLUMN IF NOT EXISTS checkpoint JSONB NOT NULL DEFAULT '{}'::jsonb"
                )
                await connection.execute(
                    "ALTER TABLE literature_ingestion_jobs ADD COLUMN IF NOT EXISTS auth_context JSONB NOT NULL DEFAULT '{}'::jsonb"
                )
                await connection.execute(
                    """CREATE OR REPLACE FUNCTION public.literature_current_organization_id() RETURNS uuid
                    LANGUAGE sql STABLE AS $$
                        SELECT NULLIF(current_setting('app.literature_organization_id', true), '')::uuid
                    $$"""
                )
                await connection.execute(
                    """CREATE OR REPLACE FUNCTION public.literature_system_scope() RETURNS boolean
                    LANGUAGE sql STABLE AS $$
                        SELECT current_setting('app.literature_system_scope', true) = 'true'
                    $$"""
                )
                for table, ownership_column in (
                    ("literature_papers", "tenant_id"),
                    ("literature_source_snapshots", "tenant_id"),
                    ("literature_ingestion_jobs", "organization_id"),
                ):
                    await connection.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
                    await connection.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
                    await connection.execute(f"DROP POLICY IF EXISTS {table}_tenant_scope ON {table}")
                    await connection.execute(
                        f"""CREATE POLICY {table}_tenant_scope ON {table}
                        FOR ALL USING (
                            public.literature_system_scope()
                            OR {ownership_column} IS NULL
                            OR {ownership_column} = public.literature_current_organization_id()
                        ) WITH CHECK (
                            public.literature_system_scope()
                            OR {ownership_column} IS NULL
                            OR {ownership_column} = public.literature_current_organization_id()
                        )"""
                    )
                    await connection.execute(
                        f"CREATE INDEX IF NOT EXISTS {table}_organization_idx ON {table} ({ownership_column})"
                    )
                logger.info("Literature schema ensured")
                self.last_error = None
                return True
        except Exception as exc:
            self.last_error = exc
            logger.exception("Failed to initialize literature database schema")
            return False

    async def upsert_pubmed_paper(
        self,
        record: dict[str, object],
        *,
        organization_id: UUID | None,
        retrieved_at,
        extracted_entities: list[dict[str, object]],
        extracted_relationships: list[dict[str, object]],
    ) -> UUID:
        pmid = str(record.get("pmid") or "").strip()
        if not pmid:
            raise ValueError("normalized PubMed record is missing PMID")
        authors = record.get("authors") or []
        metadata = record.get("metadata") or {}
        content_hash = str(metadata.get("content_hash") or "")
        if not content_hash:
            raw_payload = metadata.get("raw_xml") or metadata
            content_hash = hashlib.sha256(
                json.dumps(raw_payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
            ).hexdigest()
        async with self.acquire(str(organization_id) if organization_id else None) as connection:
            await connection.execute(
                """INSERT INTO literature_source_snapshots (
                    id, source, source_id, content_hash, raw_payload, tenant_id, retrieved_at
                ) VALUES ($1, 'pubmed', $2, $3, $4::jsonb, $5, $6)
                ON CONFLICT (source, source_id, content_hash,
                    (COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid)))
                DO NOTHING""",
                uuid4(),
                str(record.get("source_id") or f"PMID:{pmid}"),
                content_hash,
                json.dumps(metadata),
                organization_id,
                retrieved_at,
            )
            row = await connection.fetchrow(
                """INSERT INTO literature_papers (
                    id, title, source, doi, published_at, abstract, authors, pmid, pmcid,
                    journal, source_metadata, extracted_entities, extracted_relationships,
                    tenant_id, source_id, publication_date_source, retrieved_at
                ) VALUES (
                    $1, $2, 'pubmed', $3, NULL, $4, $5::jsonb, $6, $7, $8, $9::jsonb,
                    $10::jsonb, $11::jsonb, $12, $13, $14, $15
                )
                ON CONFLICT (source, pmid,
                    (COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid)))
                    WHERE source = 'pubmed' AND pmid IS NOT NULL
                DO UPDATE SET
                    title = EXCLUDED.title,
                    doi = COALESCE(EXCLUDED.doi, literature_papers.doi),
                    abstract = EXCLUDED.abstract,
                    authors = EXCLUDED.authors,
                    pmcid = COALESCE(EXCLUDED.pmcid, literature_papers.pmcid),
                    journal = EXCLUDED.journal,
                    source_metadata = EXCLUDED.source_metadata,
                    extracted_entities = EXCLUDED.extracted_entities,
                    extracted_relationships = EXCLUDED.extracted_relationships,
                    publication_date_source = EXCLUDED.publication_date_source,
                    retrieved_at = EXCLUDED.retrieved_at
                RETURNING id""",
                uuid4(),
                str(record.get("title") or "Untitled PubMed record"),
                str(record["doi"]) if record.get("doi") else None,
                str(record["abstract"]) if record.get("abstract") else None,
                json.dumps(authors),
                pmid,
                str(record["pmcid"]) if record.get("pmcid") else None,
                str(record["journal"]) if record.get("journal") else None,
                json.dumps(metadata),
                json.dumps(extracted_entities),
                json.dumps(extracted_relationships),
                organization_id,
                str(record.get("source_id") or f"PMID:{pmid}"),
                str(record["publication_date"]) if record.get("publication_date") else None,
                retrieved_at,
            )
        return row["id"]

    async def set_pubmed_reconciliation(
        self,
        pmid: str,
        *,
        organization_id: UUID | None,
        canonical_entity_id: UUID | None,
        status: str,
    ) -> None:
        async with self.acquire(str(organization_id) if organization_id else None) as connection:
            await connection.execute(
                """UPDATE literature_papers
                SET canonical_entity_id = $1, reconciliation_status = $2
                WHERE source = 'pubmed' AND pmid = $3
                  AND tenant_id IS NOT DISTINCT FROM $4::uuid""",
                canonical_entity_id,
                status,
                pmid,
                organization_id,
            )

    async def upsert_clinicaltrial_record(
        self,
        record: dict[str, object],
        *,
        organization_id: UUID | None,
        retrieved_at: datetime,
    ) -> UUID:
        nct_id = str(record.get("nct_id") or record.get("source_id") or "").strip().upper()
        if not nct_id:
            raise ValueError("normalized ClinicalTrials record is missing NCT ID")
        metadata = record.get("metadata") or {}
        content_hash = str(record.get("content_hash") or "")
        if not content_hash:
            raise ValueError("normalized ClinicalTrials record is missing content hash")
        snapshot = {
            "source_response": record.get("raw_payload"),
            "request_metadata": metadata,
            "endpoint": str(metadata.get("source_metadata", {}).get("api_endpoint") or ""),
        }
        async with self.acquire(str(organization_id) if organization_id else None) as connection:
            await connection.execute(
                """INSERT INTO literature_source_snapshots (
                    id, source, source_id, content_hash, raw_payload, tenant_id, retrieved_at
                ) VALUES ($1, 'clinicaltrials', $2, $3, $4::jsonb, $5, $6)
                ON CONFLICT (source, source_id, content_hash,
                    (COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid)))
                DO NOTHING""",
                uuid4(),
                nct_id,
                content_hash,
                json.dumps(snapshot),
                organization_id,
                retrieved_at,
            )
            row = await connection.fetchrow(
                """INSERT INTO literature_papers (
                    id, title, source, abstract, authors, journal, source_metadata,
                    tenant_id, source_id, retrieved_at
                ) VALUES ($1, $2, 'clinicaltrials', $3, '[]'::jsonb, 'ClinicalTrials.gov',
                    $4::jsonb, $5, $6, $7)
                ON CONFLICT (source, source_id,
                    (COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid)))
                    WHERE source = 'clinicaltrials' AND source_id IS NOT NULL
                DO UPDATE SET
                    title = EXCLUDED.title,
                    abstract = EXCLUDED.abstract,
                    source_metadata = EXCLUDED.source_metadata,
                    retrieved_at = EXCLUDED.retrieved_at
                RETURNING id""",
                uuid4(),
                str(record.get("title") or nct_id),
                str(record["abstract"]) if record.get("abstract") else None,
                json.dumps(metadata),
                organization_id,
                nct_id,
                retrieved_at,
            )
        return row["id"]

    async def set_clinicaltrial_reconciliation(
        self,
        nct_id: str,
        *,
        organization_id: UUID | None,
        canonical_entity_id: UUID | None,
        status: str,
    ) -> None:
        async with self.acquire(str(organization_id) if organization_id else None) as connection:
            await connection.execute(
                """UPDATE literature_papers
                SET canonical_entity_id = $1, reconciliation_status = $2
                WHERE source = 'clinicaltrials' AND source_id = $3
                  AND tenant_id IS NOT DISTINCT FROM $4::uuid""",
                canonical_entity_id,
                status,
                nct_id.strip().upper(),
                organization_id,
            )

    async def upsert_regulatory_record(
        self,
        record: dict[str, object],
        *,
        organization_id: UUID | None,
        retrieved_at: datetime,
    ) -> UUID:
        source_id = str(record.get("source_id") or "").strip()
        content_hash = str(record.get("content_hash") or "")
        if not source_id or not content_hash:
            raise ValueError("normalized regulatory record requires source ID and content hash")
        metadata = record.get("metadata") or {}
        snapshot = {
            "source_response": record.get("raw_payload"),
            "request_metadata": metadata,
        }
        async with self.acquire(str(organization_id) if organization_id else None) as connection:
            await connection.execute(
                """INSERT INTO literature_source_snapshots (
                    id, source, source_id, content_hash, raw_payload, tenant_id, retrieved_at
                ) VALUES ($1, 'regulatory', $2, $3, $4::jsonb, $5, $6)
                ON CONFLICT (source, source_id, content_hash,
                    (COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid)))
                DO NOTHING""",
                uuid4(),
                source_id,
                content_hash,
                json.dumps(snapshot),
                organization_id,
                retrieved_at,
            )
            row = await connection.fetchrow(
                """INSERT INTO literature_papers (
                    id, title, source, abstract, authors, journal, source_metadata,
                    tenant_id, source_id, retrieved_at
                ) VALUES ($1, $2, 'regulatory', $3, '[]'::jsonb, $4, $5::jsonb, $6, $7, $8)
                ON CONFLICT (source, source_id,
                    (COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid)))
                    WHERE source = 'regulatory' AND source_id IS NOT NULL
                DO UPDATE SET
                    title = EXCLUDED.title,
                    abstract = EXCLUDED.abstract,
                    journal = EXCLUDED.journal,
                    source_metadata = EXCLUDED.source_metadata,
                    retrieved_at = EXCLUDED.retrieved_at
                RETURNING id""",
                uuid4(),
                str(record.get("title") or source_id),
                str(record["abstract"]) if record.get("abstract") else None,
                "U.S. Food and Drug Administration",
                json.dumps(metadata),
                organization_id,
                source_id,
                retrieved_at,
            )
        return row["id"]

    async def set_regulatory_reconciliation(
        self,
        source_id: str,
        *,
        organization_id: UUID | None,
        canonical_entity_id: UUID | None,
        status: str,
    ) -> None:
        async with self.acquire(str(organization_id) if organization_id else None) as connection:
            await connection.execute(
                """UPDATE literature_papers
                SET canonical_entity_id = $1, reconciliation_status = $2
                WHERE source = 'regulatory' AND source_id = $3
                  AND tenant_id IS NOT DISTINCT FROM $4::uuid""",
                canonical_entity_id,
                status,
                source_id,
                organization_id,
            )

    async def upsert_patent_record(
        self,
        record: dict[str, object],
        *,
        organization_id: UUID | None,
        retrieved_at: datetime,
    ) -> UUID:
        source_id = str(record.get("source_id") or "").strip().upper()
        content_hash = str(record.get("content_hash") or "")
        if not source_id or not content_hash:
            raise ValueError("normalized patent record requires source ID and content hash")
        metadata = record.get("metadata") or {}
        snapshot = {
            "source_response": record.get("raw_payload"),
            "normalized_record": {
                key: value for key, value in record.items() if key != "raw_payload"
            },
            "source_metadata": metadata,
        }
        async with self.acquire(str(organization_id) if organization_id else None) as connection:
            await connection.execute(
                """INSERT INTO literature_source_snapshots (
                    id, source, source_id, content_hash, raw_payload, tenant_id, retrieved_at
                ) VALUES ($1, 'patent', $2, $3, $4::jsonb, $5, $6)
                ON CONFLICT (source, source_id, content_hash,
                    (COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid)))
                DO NOTHING""",
                uuid4(), source_id, content_hash, json.dumps(snapshot, default=str),
                organization_id, retrieved_at,
            )
            row = await connection.fetchrow(
                """INSERT INTO literature_papers (
                    id, title, source, abstract, authors, journal, source_metadata,
                    tenant_id, source_id, publication_date_source, retrieved_at
                ) VALUES ($1, $2, 'patent', $3, $4::jsonb, $5, $6::jsonb, $7, $8, $9, $10)
                ON CONFLICT (source, source_id,
                    (COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid)))
                    WHERE source = 'patent' AND source_id IS NOT NULL
                DO UPDATE SET
                    title = EXCLUDED.title,
                    abstract = EXCLUDED.abstract,
                    authors = EXCLUDED.authors,
                    journal = EXCLUDED.journal,
                    source_metadata = EXCLUDED.source_metadata,
                    publication_date_source = EXCLUDED.publication_date_source,
                    retrieved_at = EXCLUDED.retrieved_at
                RETURNING id""",
                uuid4(),
                str(record.get("title") or source_id),
                str(record["abstract"]) if record.get("abstract") else None,
                json.dumps(record.get("authors") or []),
                str(record.get("journal") or "Google Patents"),
                json.dumps(metadata, default=str),
                organization_id,
                source_id,
                str(record["published_date"]) if record.get("published_date") else None,
                retrieved_at,
            )
        return row["id"]

    async def set_patent_reconciliation(
        self,
        source_id: str,
        *,
        organization_id: UUID | None,
        canonical_entity_id: UUID | None,
        status: str,
    ) -> None:
        async with self.acquire(str(organization_id) if organization_id else None) as connection:
            await connection.execute(
                """UPDATE literature_papers
                SET canonical_entity_id = $1, reconciliation_status = $2
                WHERE source = 'patent' AND source_id = $3
                  AND tenant_id IS NOT DISTINCT FROM $4::uuid""",
                canonical_entity_id, status, source_id.strip().upper(), organization_id,
            )

postgres_manager = PostgresManager()

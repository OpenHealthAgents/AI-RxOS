from __future__ import annotations

from contextlib import asynccontextmanager
import hashlib
import json
from pathlib import Path
from typing import AsyncIterator
from uuid import UUID

import asyncpg

from app.utils.logging import get_logger

logger = get_logger(__name__)
_MIGRATION_LOCK = "ai_rxos_kg_canonical_migrations"


class CanonicalStore:
    def __init__(self) -> None:
        self.pool: asyncpg.Pool | None = None

    async def initialize(self, database_url: str) -> None:
        if self.pool is not None:
            return
        self.pool = await asyncpg.create_pool(database_url, min_size=1, max_size=10)
        try:
            await self.apply_migrations()
        except Exception:
            await self.close()
            raise
        logger.info("Canonical PostgreSQL store initialized")

    async def apply_migrations(self) -> None:
        pool = self._require_pool()
        migration_dir = Path(__file__).resolve().parents[2] / "migrations"
        async with pool.acquire() as connection:
            await connection.execute("CREATE SCHEMA IF NOT EXISTS canonical")
            await connection.execute("SET search_path TO canonical, public")
            await connection.execute(
                """CREATE TABLE IF NOT EXISTS canonical.schema_migrations (
                    migration_id TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    checksum TEXT
                )"""
            )
            await connection.execute(
                "ALTER TABLE canonical.schema_migrations ADD COLUMN IF NOT EXISTS checksum TEXT"
            )
            await connection.execute("SELECT pg_advisory_lock(hashtext($1))", _MIGRATION_LOCK)
            try:
                for migration_path in sorted(migration_dir.glob("[0-9][0-9][0-9]_*.sql")):
                    migration_id = migration_path.name
                    applied = await connection.fetchval(
                        "SELECT 1 FROM canonical.schema_migrations WHERE migration_id = $1",
                        migration_id,
                    )
                    if applied:
                        migration_sql = migration_path.read_text(encoding="utf-8")
                        checksum = hashlib.sha256(migration_sql.encode("utf-8")).hexdigest()
                        recorded_checksum = await connection.fetchval(
                            "SELECT checksum FROM canonical.schema_migrations WHERE migration_id = $1",
                            migration_id,
                        )
                        if recorded_checksum and recorded_checksum != checksum:
                            raise RuntimeError(
                                f"migration checksum mismatch for already-applied {migration_id}"
                            )
                        if recorded_checksum is None:
                            await connection.execute(
                                "UPDATE canonical.schema_migrations SET checksum = $2 WHERE migration_id = $1",
                                migration_id,
                                checksum,
                            )
                        continue
                    migration_sql = migration_path.read_text(encoding="utf-8")
                    checksum = hashlib.sha256(migration_sql.encode("utf-8")).hexdigest()
                    async with connection.transaction():
                        await connection.execute(migration_sql)
                        await connection.execute(
                            "INSERT INTO canonical.schema_migrations (migration_id, checksum) VALUES ($1, $2)",
                            migration_id, checksum,
                        )
                    logger.info("Applied canonical database migration", extra={"migration_id": migration_id})
            finally:
                await connection.execute("SELECT pg_advisory_unlock(hashtext($1))", _MIGRATION_LOCK)

    @asynccontextmanager
    async def connection(self, organization_id: UUID | None) -> AsyncIterator[asyncpg.Connection]:
        pool = self._require_pool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "SELECT set_config('app.canonical_organization_id', $1, true)",
                    str(organization_id) if organization_id else "",
                )
                yield connection

    async def claim_projection_events(self, organization_id: UUID | None, limit: int = 25) -> list[asyncpg.Record]:
        pool = self._require_pool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "SELECT set_config('app.canonical_organization_id', $1, true)",
                    str(organization_id) if organization_id else "",
                )
                rows = await connection.fetch(
                    """SELECT id, event_type, aggregate_id, payload, attempts
                    FROM canonical.projection_outbox
                    WHERE delivered_at IS NULL AND available_at <= NOW()
                                            AND dead_lettered_at IS NULL
                      AND (organization_id IS NULL OR organization_id = $1::uuid)
                    ORDER BY id
                    FOR UPDATE SKIP LOCKED
                    LIMIT $2""",
                    organization_id,
                    limit,
                )
                if rows:
                    updated_rows = await connection.fetch(
                        """UPDATE canonical.projection_outbox
                        SET attempts = attempts + 1, available_at = NOW() + INTERVAL '2 minutes'
                        WHERE id = ANY($1::bigint[])
                        RETURNING id, event_type, aggregate_id, payload, attempts""",
                        [row["id"] for row in rows],
                    )
                    updated_by_id = {row["id"]: row for row in updated_rows}
                    rows = [updated_by_id[row["id"]] for row in rows]
                return rows

    async def load_search_projection_metadata(
        self, entity_id: UUID, organization_id: UUID | None, available_at: str | None
    ) -> dict[str, object]:
        """Read provenance and evidence visible when this projection became available."""
        cutoff = None
        if available_at:
            from datetime import datetime

            cutoff = datetime.fromisoformat(available_at.replace("Z", "+00:00"))
        async with self.connection(organization_id) as connection:
            row = await connection.fetchrow(
                """SELECT jsonb_build_object(
                    'source_record', (
                        SELECT to_jsonb(s) FROM canonical.entities e
                        JOIN canonical.source_records s ON s.id = e.created_source_record_id
                        WHERE e.id = $1 AND (e.organization_id IS NULL OR e.organization_id = $2)
                          AND ($3::timestamptz IS NULL OR (e.created_at <= $3 AND s.ingested_at <= $3))
                    ),
                    'identifiers', COALESCE((
                        SELECT jsonb_agg(jsonb_build_object(
                            'namespace', i.namespace, 'identifier_type', i.identifier_type,
                            'value', i.value, 'source_record_id', i.source_record_id,
                            'created_at', i.created_at
                        ) ORDER BY i.namespace, i.identifier_type, i.value)
                        FROM canonical.identifiers i
                        JOIN canonical.source_records s ON s.id = i.source_record_id
                        WHERE i.entity_id = $1 AND (i.organization_id IS NULL OR i.organization_id = $2)
                          AND ($3::timestamptz IS NULL OR (i.created_at <= $3 AND s.ingested_at <= $3))
                    ), '[]'::jsonb),
                    'aliases', COALESCE((
                        SELECT jsonb_agg(jsonb_build_object(
                            'value', a.value, 'alias_type', a.alias_type,
                            'verification_state', a.verification_state,
                            'source_record_id', a.source_record_id, 'created_at', a.created_at
                        ) ORDER BY a.normalized_value, a.value)
                        FROM canonical.aliases a
                        JOIN canonical.source_records s ON s.id = a.source_record_id
                        WHERE a.entity_id = $1 AND (a.organization_id IS NULL OR a.organization_id = $2)
                          AND ($3::timestamptz IS NULL OR (a.created_at <= $3 AND s.ingested_at <= $3))
                    ), '[]'::jsonb),
                    'observations', COALESCE((
                        SELECT jsonb_agg(jsonb_build_object(
                            'id', o.id, 'property_name', o.property_name, 'observation_kind', o.observation_kind,
                            'value', o.value, 'verification_state', o.verification_state,
                            'confidence', o.confidence, 'valid_from', o.valid_from, 'valid_to', o.valid_to,
                            'published_at', o.published_at, 'observed_at', o.observed_at,
                            'ingested_at', o.ingested_at, 'source_record', to_jsonb(s)
                        ) ORDER BY o.created_at, o.id)
                        FROM canonical.observations o
                        JOIN canonical.source_records s ON s.id = o.source_record_id
                        WHERE o.entity_id = $1 AND (o.organization_id IS NULL OR o.organization_id = $2)
                          AND ($3::timestamptz IS NULL OR (
                              o.created_at <= $3 AND o.ingested_at <= $3 AND s.ingested_at <= $3
                              AND (o.valid_from IS NULL OR o.valid_from <= $3)
                              AND (o.valid_to IS NULL OR o.valid_to >= $3)
                          ))
                    ), '[]'::jsonb),
                    'claims', COALESCE((
                        SELECT jsonb_agg(
                            to_jsonb(c) || jsonb_build_object(
                                'source_record', to_jsonb(cs),
                                'evidence', COALESCE((
                                    SELECT jsonb_agg(
                                        to_jsonb(el) || jsonb_build_object(
                                            'source_record', CASE WHEN es.id IS NULL THEN NULL ELSE to_jsonb(es) END,
                                            'observation', CASE WHEN eo.id IS NULL THEN NULL ELSE to_jsonb(eo) END
                                        ) ORDER BY el.relation_type, el.created_at
                                    )
                                    FROM canonical.evidence_links el
                                    LEFT JOIN canonical.source_records es ON es.id = el.source_record_id
                                    LEFT JOIN canonical.observations eo ON eo.id = el.observation_id
                                    WHERE el.claim_id = c.id
                                      AND (el.organization_id IS NULL OR el.organization_id = $2)
                                      AND ($3::timestamptz IS NULL OR (
                                          el.created_at <= $3
                                          AND (el.valid_from IS NULL OR el.valid_from <= $3)
                                          AND (el.valid_to IS NULL OR el.valid_to >= $3)
                                          AND (el.source_record_id IS NULL OR es.ingested_at <= $3)
                                          AND (el.observation_id IS NULL OR (
                                              eo.ingested_at <= $3
                                              AND (eo.valid_from IS NULL OR eo.valid_from <= $3)
                                              AND (eo.valid_to IS NULL OR eo.valid_to >= $3)
                                          ))
                                      ))
                                ), '[]'::jsonb)
                            ) ORDER BY c.created_at, c.id
                        )
                        FROM canonical.claims c
                        JOIN canonical.source_records cs ON cs.id = c.source_record_id
                        WHERE c.entity_id = $1 AND (c.organization_id IS NULL OR c.organization_id = $2)
                          AND ($3::timestamptz IS NULL OR (
                              c.created_at <= $3 AND cs.ingested_at <= $3
                              AND (c.valid_from IS NULL OR c.valid_from <= $3)
                              AND (c.valid_to IS NULL OR c.valid_to >= $3)
                          ))
                    ), '[]'::jsonb),
                    'available_at', $3::timestamptz
                ) AS context""",
                entity_id, organization_id, cutoff,
            )
            value = row["context"]
            if isinstance(value, str):
                value = json.loads(value)
            return value

    async def claim_global_projection_events(self, limit: int = 25) -> list[asyncpg.Record]:
        """Backward-compatible wrapper for existing global-only callers."""
        pool = self._require_pool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute("SELECT set_config('app.canonical_organization_id', '', true)")
                rows = await connection.fetch(
                    """SELECT id, event_type, aggregate_id, payload, attempts
                    FROM canonical.projection_outbox
                                        WHERE visibility = 'global' AND delivered_at IS NULL AND dead_lettered_at IS NULL
                                            AND available_at <= NOW()
                    ORDER BY id FOR UPDATE SKIP LOCKED LIMIT $1""",
                    limit,
                )
                if rows:
                    updated_rows = await connection.fetch(
                        """UPDATE canonical.projection_outbox
                        SET attempts = attempts + 1, available_at = NOW() + INTERVAL '2 minutes'
                        WHERE id = ANY($1::bigint[])
                        RETURNING id, event_type, aggregate_id, payload, attempts""",
                        [row["id"] for row in rows],
                    )
                    updated_by_id = {row["id"]: row for row in updated_rows}
                    rows = [updated_by_id[row["id"]] for row in rows]
                return rows

    async def mark_projection_delivered(self, event_id: int) -> None:
        pool = self._require_pool()
        async with pool.acquire() as connection:
            await connection.execute(
                "UPDATE canonical.projection_outbox SET delivered_at = NOW(), last_error = NULL WHERE id = $1",
                event_id,
            )

    async def mark_projection_failed(self, event_id: int, attempts: int, error: str) -> None:
        pool = self._require_pool()
        delay_seconds = min(300, 2 ** min(attempts + 1, 8))
        async with pool.acquire() as connection:
            await connection.execute(
                """UPDATE canonical.projection_outbox
                SET available_at = CASE WHEN attempts >= max_attempts
                                        THEN available_at
                                        ELSE NOW() + ($2 * INTERVAL '1 second') END,
                    last_error = $3,
                    dead_lettered_at = CASE WHEN attempts >= max_attempts THEN NOW() ELSE dead_lettered_at END
                WHERE id = $1""",
                event_id,
                delay_seconds,
                error[:1000],
            )

    async def enqueue_reindex_events(
        self, organization_id: UUID | None = None, entity_type: str | None = None
    ) -> int:
        """Queue deterministic projections from canonical PostgreSQL state.

        This deliberately creates new outbox work instead of reading either
        derived store, so replay remains safe and PostgreSQL remains the source
        of truth.
        """
        pool = self._require_pool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "SELECT set_config('app.canonical_organization_id', $1, true)",
                    str(organization_id) if organization_id else "",
                )
                entity_count = await connection.fetchval(
                    """WITH inserted AS (
                    INSERT INTO canonical.projection_outbox (
                        event_type, aggregate_id, visibility, organization_id, payload
                    )
                    SELECT 'entity.upserted', e.id, e.visibility, e.organization_id,
                        jsonb_build_object(
                            'id', e.id::text,
                            'entity_type', e.entity_type,
                            'preferred_name', e.preferred_name,
                            'description', e.description,
                            'modality', e.modality,
                            'lifecycle_status', e.lifecycle_status,
                            'visibility', e.visibility,
                            'organization_id', e.organization_id::text,
                            'attributes', e.attributes,
                            'projection_version', extract(epoch FROM e.updated_at)::bigint,
                            'created_at', e.created_at::text,
                            'updated_at', e.updated_at::text,
                            'identifiers', COALESCE((SELECT jsonb_agg(jsonb_build_object(
                                'namespace', i.namespace, 'identifier_type', i.identifier_type,
                                'value', i.value)) FROM canonical.identifiers i WHERE i.entity_id = e.id), '[]'::jsonb),
                            'aliases', COALESCE((SELECT jsonb_agg(jsonb_build_object(
                                'value', a.value, 'alias_type', a.alias_type,
                                'verification_state', a.verification_state)) FROM canonical.aliases a WHERE a.entity_id = e.id), '[]'::jsonb)
                        )
                    FROM canonical.entities e
                    WHERE ($1::uuid IS NULL OR e.organization_id IS NULL OR e.organization_id = $1)
                      AND ($2::text IS NULL OR e.entity_type = $2)
                    RETURNING id
                    ) SELECT count(*) FROM inserted""",
                    organization_id,
                    entity_type,
                )
                relationship_count = await connection.fetchval(
                    """WITH inserted AS (
                        INSERT INTO canonical.projection_outbox (
                            event_type, aggregate_id, visibility, organization_id, payload
                        )
                        SELECT 'relationship.upserted', r.id, r.visibility, r.organization_id,
                            jsonb_build_object(
                                'id', r.id::text,
                                'subject_entity_id', r.subject_entity_id::text,
                                'predicate', r.predicate,
                                'object_entity_id', r.object_entity_id::text,
                                'visibility', r.visibility,
                                'organization_id', r.organization_id::text,
                                'attributes', r.attributes,
                                'projection_version', extract(epoch FROM r.created_at)::bigint,
                                'created_at', r.created_at::text,
                                'updated_at', r.created_at::text
                            )
                        FROM canonical.relationships r
                        WHERE ($1::uuid IS NULL OR r.organization_id IS NULL OR r.organization_id = $1)
                        RETURNING id
                    ) SELECT count(*) FROM inserted""",
                    organization_id,
                )
                return int(entity_count or 0) + int(relationship_count or 0)

    def _require_pool(self) -> asyncpg.Pool:
        if self.pool is None:
            raise RuntimeError("Canonical PostgreSQL store is unavailable")
        return self.pool

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None


canonical_store = CanonicalStore()

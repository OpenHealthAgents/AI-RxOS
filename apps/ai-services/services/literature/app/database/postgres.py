from contextlib import asynccontextmanager
import json
import hashlib
import sys
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Mapping
from uuid import UUID, uuid4

import asyncpg

from app.core.config import Settings
from app.monitoring.change_detection import (
    changed_material_fields,
    material_hash,
    material_payload,
    monitoring_event_id,
    source_category,
)
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
                    "ALTER TABLE literature_source_snapshots ADD COLUMN IF NOT EXISTS material_hash TEXT"
                )
                await connection.execute(
                    "ALTER TABLE literature_source_snapshots ADD COLUMN IF NOT EXISTS material_payload JSONB"
                )
                await connection.execute(
                    "DROP INDEX IF EXISTS literature_source_snapshots_identity_unique"
                )
                await connection.execute(
                    """CREATE INDEX IF NOT EXISTS literature_source_snapshots_identity_idx
                    ON literature_source_snapshots (
                        source, source_id, tenant_id, retrieved_at DESC, ingested_at DESC
                    )"""
                )
                await connection.execute(
                    """CREATE TABLE IF NOT EXISTS literature_monitoring_events (
                        id UUID PRIMARY KEY,
                        source TEXT NOT NULL,
                        source_category TEXT NOT NULL,
                        source_id TEXT NOT NULL,
                        change_type TEXT NOT NULL CHECK (
                            change_type IN ('new_source_record', 'material_change')
                        ),
                        previous_content_hash TEXT,
                        current_content_hash TEXT NOT NULL,
                        previous_material_hash TEXT,
                        current_material_hash TEXT NOT NULL,
                        previous_snapshot_id UUID REFERENCES literature_source_snapshots(id) ON DELETE SET NULL,
                        current_snapshot_id UUID NOT NULL REFERENCES literature_source_snapshots(id) ON DELETE RESTRICT,
                        source_event_at TIMESTAMPTZ,
                        detected_at TIMESTAMPTZ NOT NULL,
                        changed_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
                        evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
                        materiality_rationale TEXT NOT NULL,
                        canonical_entity_id UUID,
                        canonical_resolution_status TEXT NOT NULL DEFAULT 'unresolved',
                        recalculation_status TEXT NOT NULL DEFAULT 'not_supported',
                        decision_change_state TEXT NOT NULL DEFAULT 'unavailable',
                        previous_decision_version JSONB,
                        current_decision_version JSONB,
                        previous_decision_state TEXT,
                        current_decision_state TEXT,
                        evidence_caused_change JSONB NOT NULL DEFAULT '[]'::jsonb,
                        tenant_id UUID,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )"""
                )
                await connection.execute(
                    """CREATE TABLE IF NOT EXISTS literature_decision_recalculations (
                        id UUID PRIMARY KEY,
                        monitoring_event_id UUID NOT NULL REFERENCES literature_monitoring_events(id) ON DELETE CASCADE,
                        source TEXT NOT NULL,
                        source_category TEXT NOT NULL,
                        source_id TEXT NOT NULL,
                        asset_id TEXT,
                        tenant_id UUID,
                        previous_decision_version JSONB,
                        current_decision_version JSONB NOT NULL,
                        previous_decision_state TEXT,
                        current_decision_state TEXT NOT NULL,
                        score_delta NUMERIC,
                        evidence_caused_change JSONB NOT NULL DEFAULT '[]'::jsonb,
                        recalculation_status TEXT NOT NULL DEFAULT 'queued',
                        error_message TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        completed_at TIMESTAMPTZ
                    )"""
                )
                await connection.execute(
                    "ALTER TABLE literature_monitoring_events ADD COLUMN IF NOT EXISTS previous_decision_version JSONB"
                )
                await connection.execute(
                    "ALTER TABLE literature_monitoring_events ADD COLUMN IF NOT EXISTS current_decision_version JSONB"
                )
                await connection.execute(
                    "ALTER TABLE literature_monitoring_events ADD COLUMN IF NOT EXISTS previous_decision_state TEXT"
                )
                await connection.execute(
                    "ALTER TABLE literature_monitoring_events ADD COLUMN IF NOT EXISTS current_decision_state TEXT"
                )
                await connection.execute(
                    "ALTER TABLE literature_monitoring_events ADD COLUMN IF NOT EXISTS evidence_caused_change JSONB"
                )
                await connection.execute(
                    "DROP INDEX IF EXISTS literature_monitoring_event_identity_unique"
                )
                await connection.execute(
                    """CREATE INDEX IF NOT EXISTS literature_monitoring_events_detected_idx
                    ON literature_monitoring_events (detected_at DESC, id DESC)"""
                )
                await connection.execute(
                    """CREATE INDEX IF NOT EXISTS literature_monitoring_events_source_idx
                    ON literature_monitoring_events (source, source_id, detected_at DESC)"""
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
                    ("literature_monitoring_events", "tenant_id"),
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

    async def _persist_monitoring_snapshot(
        self,
        connection: asyncpg.Connection,
        *,
        source: str,
        source_id: str,
        content_hash: str,
        raw_payload: Mapping[str, Any],
        material: Mapping[str, Any],
        organization_id: UUID | None,
        retrieved_at: datetime,
        source_event_at: datetime | None = None,
    ) -> UUID:
        category = source_category(source)
        material_digest = material_hash(material)
        await connection.execute(
            "SELECT pg_advisory_xact_lock(hashtext($1), hashtext($2))",
            f"{source}:{source_id}",
            str(organization_id) if organization_id else "global",
        )
        previous = await connection.fetchrow(
            """SELECT id, content_hash, material_hash, material_payload
            FROM literature_source_snapshots
            WHERE source = $1 AND source_id = $2
              AND tenant_id IS NOT DISTINCT FROM $3::uuid
            ORDER BY ingested_at DESC, id DESC LIMIT 1""",
            source,
            source_id,
            organization_id,
        )
        if previous is None:
            change_type = "new_source_record"
            changed_fields = sorted(material)
            rationale = "First observed version for this source identity."
        else:
            previous_material = previous["material_payload"]
            if isinstance(previous_material, str):
                previous_material = json.loads(previous_material)
            if isinstance(previous_material, Mapping):
                changed_fields = changed_material_fields(previous_material, material)
            elif previous["content_hash"] != content_hash:
                changed_fields = ["source_content"]
            else:
                changed_fields = []
            if (
                not changed_fields
                and previous["material_hash"] == material_digest
                and previous["content_hash"] == content_hash
            ):
                return previous["id"]
            change_type = "material_change"
            rationale = (
                "Material source fields changed: " + ", ".join(changed_fields)
                if changed_fields
                else "Material baseline recorded for a legacy source snapshot."
            )

        current = await connection.fetchrow(
            """INSERT INTO literature_source_snapshots (
            id, source, source_id, content_hash, raw_payload, tenant_id,
            retrieved_at, material_hash, material_payload
            ) VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9::jsonb)
            RETURNING id""",
            uuid4(),
            source,
            source_id,
            content_hash,
            json.dumps(raw_payload, default=str),
            organization_id,
            retrieved_at,
            material_digest,
            json.dumps(material, default=str),
        )
        if current is None:
            raise RuntimeError("monitoring source snapshot was not persisted")

        if previous is not None and not changed_fields:
            return current["id"]

        event_id = monitoring_event_id(
            source,
            source_id,
            previous["id"] if previous else None,
            current["id"],
            organization_id,
        )
        evidence_refs = [
            {
                "kind": "literature_source_snapshot",
                "snapshot_id": str(current["id"]),
                "source": source,
                "source_id": source_id,
                "content_hash": content_hash,
            }
        ]
        if previous is not None:
            evidence_refs.insert(
                0,
                {
                    "kind": "literature_source_snapshot",
                    "snapshot_id": str(previous["id"]),
                    "source": source,
                    "source_id": source_id,
                    "content_hash": previous["content_hash"],
                },
            )
        await connection.execute(
            """INSERT INTO literature_monitoring_events (
                id, source, source_category, source_id, change_type,
                previous_content_hash, current_content_hash,
                previous_material_hash, current_material_hash,
                previous_snapshot_id, current_snapshot_id, source_event_at,
                detected_at, changed_fields, evidence_refs, materiality_rationale,
                tenant_id
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                clock_timestamp(), $13::jsonb, $14::jsonb, $15, $16
            ) ON CONFLICT (id) DO NOTHING""",
            event_id,
            source,
            category,
            source_id,
            change_type,
            previous["content_hash"] if previous else None,
            content_hash,
            previous["material_hash"] if previous else None,
            material_digest,
            previous["id"] if previous else None,
            current["id"],
            source_event_at,
            json.dumps(changed_fields),
            json.dumps(evidence_refs),
            rationale,
            organization_id,
        )
        event_row = await connection.fetchrow(
            """SELECT id, source, source_id, change_type, current_snapshot_id, tenant_id,
                evidence_refs
            FROM literature_monitoring_events WHERE id = $1""",
            event_id,
        )
        if event_row is not None:
            await self._process_event_recalculation(connection, dict(event_row))
        return current["id"]

    @staticmethod
    def _source_event_time(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            if value.tzinfo is None or value.utcoffset() is None:
                return value.replace(tzinfo=timezone.utc)
            return value
        if isinstance(value, date):
            return datetime.combine(value, time.min, tzinfo=timezone.utc)
        if isinstance(value, str) and value.strip():
            normalized = value.strip()
            try:
                parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
            except ValueError:
                try:
                    parsed_date = date.fromisoformat(normalized[:10])
                except ValueError:
                    return None
                return datetime.combine(parsed_date, time.min, tzinfo=timezone.utc)
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        return None

    async def _attach_monitoring_resolution(
        self,
        connection: asyncpg.Connection,
        *,
        source: str,
        source_id: str,
        organization_id: UUID | None,
        canonical_entity_id: UUID | None,
        status: str,
    ) -> None:
        await connection.execute(
            """UPDATE literature_monitoring_events
            SET canonical_entity_id = $1, canonical_resolution_status = $2
            WHERE id = (
                SELECT id FROM literature_monitoring_events
                WHERE source = $3 AND source_id = $4
                  AND tenant_id IS NOT DISTINCT FROM $5::uuid
                ORDER BY detected_at DESC, id DESC LIMIT 1
            )""",
            canonical_entity_id,
            status.strip().lower() or "unresolved",
            source,
            source_id,
            organization_id,
        )

    @staticmethod
    def _load_decision_engine() -> tuple[Any | None, type[Any] | None]:
        repo_root = Path(__file__).resolve().parents[4]
        ai_services_root = repo_root / "apps" / "ai-services"
        if str(ai_services_root) not in sys.path:
            sys.path.insert(0, str(ai_services_root))
        try:
            from app.opportunity_engine.decision.engine import MasterDecisionEngine
            from app.opportunity_engine.decision.models import DecisionPolicy

            return MasterDecisionEngine, DecisionPolicy
        except Exception:
            return None, None

    @staticmethod
    def _derive_signal_payload(source: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        normalized = payload.get("source_record") or payload.get("raw_payload") or payload
        evidence_refs = []
        if isinstance(normalized, Mapping):
            evidence_refs = [
                str(reference)
                for reference in (
                    normalized.get("source_reference") or normalized.get("citation") or normalized.get("url") or []
                )
                if reference is not None
            ]
        evidence_refs = evidence_refs or [str(payload.get("source_id") or source)]

        source_name = source.lower().strip()
        if source_name in {"company_websites", "company_events", "company"}:
            score = 0.0
            for key in ("score", "value", "market_share", "confidence"):
                value = normalized.get(key) if isinstance(normalized, Mapping) else None
                if isinstance(value, (int, float)):
                    score = float(value)
                    break
            if not score:
                score = 70.0
            return {
                "commercial": {"value": score, "status": "AVAILABLE", "supporting_evidence": evidence_refs},
                "competition": {"value": max(35.0, min(90.0, score * 0.9)), "status": "AVAILABLE", "supporting_evidence": evidence_refs},
                "evidence_quality": {"value": 0.8, "status": "AVAILABLE", "supporting_evidence": evidence_refs},
            }
        if source_name in {"licensing", "licensing_events"}:
            score = 55.0
            status = str(payload.get("status") or normalized.get("status") or "unknown").lower()
            if status in {"licensed", "approved", "active", "signed"}:
                score = 80.0
            elif status in {"terminated", "blocked", "disputed", "unknown"}:
                score = 35.0
            return {
                "licensing": {"value": score, "status": "AVAILABLE", "supporting_evidence": evidence_refs},
                "commercial": {"value": score, "status": "AVAILABLE", "supporting_evidence": evidence_refs},
                "evidence_quality": {"value": 0.75, "status": "AVAILABLE", "supporting_evidence": evidence_refs},
            }
        if source_name in {"competitors", "competition", "competitive"}:
            score = 60.0
            for key in ("differentiation_score", "score", "value", "market_share"):
                value = payload.get(key) or normalized.get(key) if isinstance(normalized, Mapping) else None
                if isinstance(value, (int, float)):
                    score = float(value)
                    break
            return {
                "competition": {"value": score, "status": "AVAILABLE", "supporting_evidence": evidence_refs},
                "commercial": {"value": max(20.0, min(90.0, score)), "status": "AVAILABLE", "supporting_evidence": evidence_refs},
                "evidence_quality": {"value": 0.7, "status": "AVAILABLE", "supporting_evidence": evidence_refs},
            }
        if source_name in {"resistance", "resistance_evidence"}:
            score = 45.0
            for key in ("risk_level", "score", "value", "confidence"):
                value = payload.get(key) or normalized.get(key) if isinstance(normalized, Mapping) else None
                if isinstance(value, (int, float)):
                    score = float(value)
                    break
            return {
                "resistance": {"value": score, "status": "AVAILABLE", "supporting_evidence": evidence_refs},
                "safety": {"value": max(10.0, 100.0 - score), "status": "AVAILABLE", "supporting_evidence": evidence_refs},
                "evidence_quality": {"value": 0.75, "status": "AVAILABLE", "supporting_evidence": evidence_refs},
            }
        if source_name in {"cns", "cns_evidence"}:
            score = 55.0
            for key in ("cns_activity_score", "brain_penetration", "score", "value"):
                value = payload.get(key) or normalized.get(key) if isinstance(normalized, Mapping) else None
                if isinstance(value, (int, float)):
                    score = float(value)
                    break
            return {
                "cns": {"value": score, "status": "AVAILABLE", "supporting_evidence": evidence_refs},
                "clinical": {"value": max(35.0, min(95.0, score)), "status": "AVAILABLE", "supporting_evidence": evidence_refs},
                "patient": {"value": max(30.0, min(90.0, score)), "status": "AVAILABLE", "supporting_evidence": evidence_refs},
                "evidence_quality": {"value": 0.8, "status": "AVAILABLE", "supporting_evidence": evidence_refs},
            }
        return {"evidence_quality": {"value": 0.6, "status": "AVAILABLE", "supporting_evidence": evidence_refs}}

    @staticmethod
    def _event_asset_id(
        event: Mapping[str, Any],
        snapshot_payload: Mapping[str, Any],
        source_name: str,
    ) -> str:
        for candidate in (
            event.get("asset_id"),
            event.get("canonical_asset_id"),
            snapshot_payload.get("asset_id"),
            snapshot_payload.get("asset"),
            snapshot_payload.get("canonical_entity_id"),
            snapshot_payload.get("source_record", {}).get("asset_id") if isinstance(snapshot_payload.get("source_record"), Mapping) else None,
            snapshot_payload.get("source_record", {}).get("asset") if isinstance(snapshot_payload.get("source_record"), Mapping) else None,
            snapshot_payload.get("metadata", {}).get("asset_id") if isinstance(snapshot_payload.get("metadata"), Mapping) else None,
            snapshot_payload.get("metadata", {}).get("asset") if isinstance(snapshot_payload.get("metadata"), Mapping) else None,
            snapshot_payload.get("competitor_asset_id"),
        ):
            if candidate is None:
                continue
            value = str(candidate).strip()
            if value:
                return value
        source_id = str(event.get("source_id") or snapshot_payload.get("source_id") or source_name).strip()
        return source_id or "monitoring-event"

    @staticmethod
    def _recalculation_reason(event: Mapping[str, Any]) -> str:
        if event.get("materiality_rationale"):
            return str(event["materiality_rationale"])
        changed_fields = event.get("changed_fields") or []
        if changed_fields:
            return "Material source fields changed: " + ", ".join(str(field) for field in changed_fields)
        return "Material source evidence changed and triggered a decision recalculation."

    async def _process_event_recalculation(
        self,
        connection: asyncpg.Connection,
        event: Mapping[str, Any],
    ) -> None:
        supported_source = source_category(event.get("source", "")) if str(event.get("source", "")).strip() else None
        if supported_source is None:
            return
        if event.get("change_type") != "material_change":
            return

        event_id = event.get("id")
        if event_id is None:
            return

        organization_id = event.get("tenant_id")
        existing_recalculation = await connection.fetchrow(
            """SELECT id, recalculation_status, current_decision_version, current_decision_state
            FROM literature_decision_recalculations
            WHERE monitoring_event_id = $1 AND tenant_id IS NOT DISTINCT FROM $2::uuid
            ORDER BY created_at DESC, id DESC LIMIT 1""",
            event_id,
            organization_id,
        )
        if existing_recalculation is not None and existing_recalculation["recalculation_status"] in {"completed", "queued"}:
            return

        engine_factory, policy_factory = self._load_decision_engine()
        if engine_factory is None or policy_factory is None:
            await connection.execute(
                """UPDATE literature_monitoring_events
                SET recalculation_status = 'skipped',
                    decision_change_state = 'unavailable'
                WHERE id = $1""",
                event_id,
            )
            return

        snapshot_row = await connection.fetchrow(
            """SELECT id, raw_payload, material_payload, source, source_id, tenant_id
            FROM literature_source_snapshots WHERE id = $1""",
            event["current_snapshot_id"],
        )
        if snapshot_row is None:
            return

        snapshot_payload = snapshot_row["material_payload"]
        if isinstance(snapshot_payload, str):
            snapshot_payload = json.loads(snapshot_payload)
        if not isinstance(snapshot_payload, Mapping):
            snapshot_payload = {}

        source_name = str(event.get("source") or snapshot_row["source"] or "")
        decision_inputs = self._derive_signal_payload(source_name, snapshot_payload)
        asset_id = self._event_asset_id(event, snapshot_payload, source_name)
        organization_id = event.get("tenant_id") if event.get("tenant_id") is not None else snapshot_row["tenant_id"]

        calc_id = existing_recalculation["id"] if existing_recalculation is not None else uuid4()
        try:
            engine = engine_factory()
            decision_policy = policy_factory()
            result = engine.evaluate(
                asset_id,
                tenant_id=str(organization_id) if organization_id else None,
                policy=decision_policy,
                **decision_inputs,
            )
        except Exception as exc:
            await connection.execute(
                """INSERT INTO literature_decision_recalculations (
                    id, monitoring_event_id, source, source_category, source_id,
                    asset_id, tenant_id, previous_decision_version, current_decision_version,
                    previous_decision_state, current_decision_state, score_delta,
                    evidence_caused_change, recalculation_status, error_message, completed_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, NULL, NULL, NULL, NULL, NULL,
                    $8::jsonb, 'failed', $9, NOW())
                ON CONFLICT (id) DO UPDATE SET
                    recalculation_status = EXCLUDED.recalculation_status,
                    error_message = EXCLUDED.error_message,
                    completed_at = NOW()""",
                calc_id,
                event_id,
                source_name,
                supported_source,
                str(event.get("source_id") or snapshot_row["source_id"]),
                asset_id,
                organization_id,
                json.dumps([
                    {"field": field, "reason": self._recalculation_reason(event)}
                    for field in (event.get("changed_fields") or [])
                ], default=str),
                str(exc),
            )
            await connection.execute(
                """UPDATE literature_monitoring_events
                SET recalculation_status = 'failed',
                    decision_change_state = 'failed',
                    evidence_caused_change = $1::jsonb
                WHERE id = $2""",
                json.dumps([
                    {"field": field, "reason": self._recalculation_reason(event)}
                    for field in (event.get("changed_fields") or [])
                ], default=str),
                event_id,
            )
            return

        previous_row = await connection.fetchrow(
            """SELECT current_decision_version, current_decision_state
            FROM literature_decision_recalculations
            WHERE source = $1 AND source_id = $2 AND tenant_id IS NOT DISTINCT FROM $3::uuid
              AND recalculation_status = 'completed'
            ORDER BY created_at DESC, id DESC LIMIT 1""",
            source_name,
            str(event.get("source_id") or snapshot_row["source_id"]),
            organization_id,
        )

        prev_version = previous_row["current_decision_version"] if previous_row else None
        previous_state = previous_row["current_decision_state"] if previous_row else None
        current_payload = {
            "decision": result.decision.value,
            "score": result.score,
            "confidence": result.confidence,
            "recommended_action": result.recommended_action,
            "supporting_evidence": result.supporting_evidence,
            "negative_drivers": result.negative_drivers,
            "positive_drivers": result.positive_drivers,
            "upstream_signal_availability": result.upstream_signal_availability,
        }
        evidence_caused_change = []
        for item in event.get("evidence_refs") or []:
            if isinstance(item, Mapping):
                evidence_caused_change.append(dict(item))
            else:
                evidence_caused_change.append({"reference": str(item)})
        for field_name in event.get("changed_fields") or []:
            evidence_caused_change.append({
                "field": str(field_name),
                "reason": self._recalculation_reason(event),
            })
        evidence_caused_change = evidence_caused_change[:20]

        changed_state = "unchanged"
        if previous_state is None or previous_state != current_payload["decision"] or prev_version != current_payload:
            changed_state = "changed"

        score_delta = None
        if previous_state is not None and prev_version is not None and isinstance(prev_version, Mapping):
            previous_score = prev_version.get("score")
            if previous_score is not None:
                try:
                    score_delta = float(result.score) - float(previous_score)
                except (TypeError, ValueError):
                    score_delta = None

        await connection.execute(
            """INSERT INTO literature_decision_recalculations (
                id, monitoring_event_id, source, source_category, source_id,
                asset_id, tenant_id, previous_decision_version,
                current_decision_version, previous_decision_state,
                current_decision_state, score_delta, evidence_caused_change,
                recalculation_status, error_message, completed_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10, $11,
                $12, $13::jsonb, 'completed', NULL, NOW())
            ON CONFLICT (id) DO NOTHING""",
            calc_id,
            event_id,
            source_name,
            supported_source,
            str(event.get("source_id") or snapshot_row["source_id"]),
            asset_id,
            organization_id,
            json.dumps(prev_version, default=str) if prev_version is not None else None,
            json.dumps(current_payload, default=str),
            previous_state,
            current_payload["decision"],
            score_delta,
            json.dumps(evidence_caused_change, default=str),
        )
        await connection.execute(
            """UPDATE literature_monitoring_events
            SET recalculation_status = 'completed',
                decision_change_state = $1,
                previous_decision_version = $2::jsonb,
                current_decision_version = $3::jsonb,
                previous_decision_state = $4,
                current_decision_state = $5,
                evidence_caused_change = $6::jsonb
            WHERE id = $7""",
            changed_state,
            json.dumps(prev_version, default=str) if prev_version is not None else None,
            json.dumps(current_payload, default=str),
            previous_state,
            current_payload["decision"],
            json.dumps(evidence_caused_change, default=str),
            event_id,
        )

    async def list_monitoring_events(
        self,
        *,
        organization_id: UUID | None,
        limit: int = 50,
        source_category: str | None = None,
    ) -> list[asyncpg.Record]:
        async with self.acquire(str(organization_id) if organization_id else None) as connection:
            return await connection.fetch(
                """SELECT id, source, source_category, source_id, change_type,
                    previous_content_hash, current_content_hash,
                    previous_material_hash, current_material_hash,
                    previous_snapshot_id, current_snapshot_id, source_event_at,
                    detected_at, changed_fields, evidence_refs, materiality_rationale,
                    canonical_entity_id, canonical_resolution_status,
                    recalculation_status, decision_change_state,
                    previous_decision_version, current_decision_version,
                    previous_decision_state, current_decision_state,
                    evidence_caused_change, created_at
                FROM literature_monitoring_events
                WHERE tenant_id IS NOT DISTINCT FROM $1::uuid
                  AND ($2::text IS NULL OR source_category = $2)
                ORDER BY detected_at DESC, id DESC LIMIT $3""",
                organization_id,
                source_category,
                limit,
            )

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
        source_id = str(record.get("source_id") or f"PMID:{pmid}")
        async with self.acquire(str(organization_id) if organization_id else None) as connection:
            await self._persist_monitoring_snapshot(
                connection,
                source="pubmed",
                source_id=source_id,
                content_hash=content_hash,
                raw_payload={"metadata": metadata},
                material=material_payload(
                    "pubmed",
                    record,
                    extracted_entities=extracted_entities,
                    extracted_relationships=extracted_relationships,
                ),
                organization_id=organization_id,
                retrieved_at=retrieved_at,
                source_event_at=self._source_event_time(record.get("publication_date")),
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
                source_id,
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
            await self._attach_monitoring_resolution(
                connection,
                source="pubmed",
                source_id=f"PMID:{pmid}",
                organization_id=organization_id,
                canonical_entity_id=canonical_entity_id,
                status=status,
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
            await self._persist_monitoring_snapshot(
                connection,
                source="clinicaltrials",
                source_id=nct_id,
                content_hash=content_hash,
                raw_payload=snapshot,
                material=material_payload("clinicaltrials", record),
                organization_id=organization_id,
                retrieved_at=retrieved_at,
                source_event_at=self._source_event_time(
                    (record.get("metadata") or {}).get("status_verified_date")
                    or (record.get("metadata") or {}).get("last_update_posted_date")
                ),
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
            await self._attach_monitoring_resolution(
                connection,
                source="clinicaltrials",
                source_id=nct_id.strip().upper(),
                organization_id=organization_id,
                canonical_entity_id=canonical_entity_id,
                status=status,
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
            await self._persist_monitoring_snapshot(
                connection,
                source="regulatory",
                source_id=source_id,
                content_hash=content_hash,
                raw_payload=snapshot,
                material=material_payload("regulatory", record),
                organization_id=organization_id,
                retrieved_at=retrieved_at,
                source_event_at=self._source_event_time(
                    (record.get("metadata") or {}).get("submission_status_date_source")
                    or (record.get("metadata") or {}).get("effective_date")
                ),
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
            await self._attach_monitoring_resolution(
                connection,
                source="regulatory",
                source_id=source_id,
                organization_id=organization_id,
                canonical_entity_id=canonical_entity_id,
                status=status,
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
            await self._persist_monitoring_snapshot(
                connection,
                source="patent",
                source_id=source_id,
                content_hash=content_hash,
                raw_payload=snapshot,
                material=material_payload("patent", record),
                organization_id=organization_id,
                retrieved_at=retrieved_at,
                source_event_at=self._source_event_time(
                    (record.get("metadata") or {}).get("publication_date_source")
                    or record.get("published_date")
                ),
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
            await self._attach_monitoring_resolution(
                connection,
                source="patent",
                source_id=source_id.strip().upper(),
                organization_id=organization_id,
                canonical_entity_id=canonical_entity_id,
                status=status,
            )

postgres_manager = PostgresManager()

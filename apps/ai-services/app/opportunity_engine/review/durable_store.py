from __future__ import annotations

import asyncio
import hashlib
import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import asyncpg

from app.core.config import get_settings


class DurableReviewStore:
    """PostgreSQL-backed durable storage for human scientific reviews using KG canonical decision_governance tables."""

    def __init__(self) -> None:
        self.pool: asyncpg.Pool | None = None
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        settings = get_settings()
        if not settings.kg_canonical_database_url:
            raise RuntimeError("kg_canonical_database_url is not configured")
        try:
            self.pool = await asyncpg.create_pool(
                settings.kg_canonical_database_url,
                min_size=1,
                max_size=10,
            )
            self._initialized = True
        except Exception as e:
            raise RuntimeError(f"Failed to connect to KG canonical database: {e}") from e

    async def initialize(self) -> None:
        await self._ensure_initialized()

    @asynccontextmanager
    async def connection(self, organization_id: UUID | None) -> Any:
        await self._ensure_initialized()
        if self.pool is None:
            raise RuntimeError("DurableReviewStore not initialized")
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "SELECT set_config('app.canonical_organization_id', $1, true)",
                    str(organization_id) if organization_id else "",
                )
                yield connection

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None
            self._initialized = False

    @staticmethod
    def _review_hash(
        *,
        reviewed_object_type: str,
        reviewed_object_id: str,
        review_action: str,
        review_status: str,
        reviewer_user_id: str,
        rationale: str,
        tenant_id: str | None,
        original_ai_value: Any,
        human_decision: Any,
        original_value: Any,
        corrected_value: Any,
        model_version: str | None,
        evidence_version: str | None,
        decision_version: str | None,
        source_provenance: dict[str, Any] | None,
        previous_review_id: str | None,
    ) -> str:
        payload = json.dumps(
            {
                "reviewed_object_type": reviewed_object_type,
                "reviewed_object_id": reviewed_object_id,
                "review_action": review_action,
                "review_status": review_status,
                "reviewer_user_id": reviewer_user_id,
                "rationale": rationale,
                "tenant_id": tenant_id or "",
                "original_ai_value": original_ai_value,
                "human_decision": human_decision,
                "original_value": original_value,
                "corrected_value": corrected_value,
                "model_version": model_version,
                "evidence_version": evidence_version,
                "decision_version": decision_version,
                "source_provenance": source_provenance or {},
                "previous_review_id": previous_review_id,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def create_review(
        self,
        *,
        reviewed_object_type: str,
        reviewed_object_id: str,
        review_action: str,
        review_status: str,
        rationale: str,
        original_ai_value: Any,
        human_decision: Any,
        original_value: Any,
        corrected_value: Any,
        reviewer_user_id: str,
        tenant_id: str | None,
        model_version: str | None = None,
        evidence_version: str | None = None,
        decision_version: str | None = None,
        source_provenance: dict[str, Any] | None = None,
        previous_review_id: str | None = None,
    ) -> dict[str, Any]:
        if not tenant_id:
            raise ValueError("tenant_id is required for durable review storage")

        try:
            org_id = UUID(tenant_id)
            reviewer_id = UUID(reviewer_user_id)
        except ValueError as e:
            raise ValueError("tenant_id and reviewer_user_id must be valid UUIDs") from e

        review_hash = self._review_hash(
            reviewed_object_type=reviewed_object_type,
            reviewed_object_id=reviewed_object_id,
            review_action=review_action,
            review_status=review_status,
            reviewer_user_id=reviewer_user_id,
            rationale=rationale,
            tenant_id=tenant_id,
            original_ai_value=original_ai_value,
            human_decision=human_decision,
            original_value=original_value,
            corrected_value=corrected_value,
            model_version=model_version,
            evidence_version=evidence_version,
            decision_version=decision_version,
            source_provenance=source_provenance,
            previous_review_id=previous_review_id,
        )

        idempotency_key = f"review:{review_hash}"

        async with self.connection(org_id) as connection:
            row = await connection.fetchrow(
                """INSERT INTO canonical.human_scientific_reviews (
                    organization_id, reviewer_id, reviewed_object_type, reviewed_object_id,
                    idempotency_key, review_action, review_status, rationale,
                    original_ai_value, human_decision, original_value, corrected_value,
                    model_version, evidence_version, decision_version, provenance,
                    previous_review_id, review_hash
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10::jsonb,
                    $11::jsonb, $12::jsonb, $13, $14, $15, $16::jsonb, $17, $18)
                ON CONFLICT (organization_id, idempotency_key) DO NOTHING
                RETURNING *""",
                org_id,
                reviewer_id,
                reviewed_object_type,
                reviewed_object_id,
                idempotency_key,
                review_action,
                review_status,
                rationale,
                json.dumps(original_ai_value, default=str),
                json.dumps(human_decision, default=str),
                json.dumps(original_value, default=str),
                json.dumps(corrected_value, default=str),
                model_version,
                evidence_version,
                decision_version,
                json.dumps(source_provenance or {}),
                UUID(previous_review_id) if previous_review_id else None,
                review_hash,
            )

            if row is None:
                row = await connection.fetchrow(
                    """SELECT * FROM canonical.human_scientific_reviews
                    WHERE organization_id = $1 AND idempotency_key = $2""",
                    org_id,
                    idempotency_key,
                )
                if row is None:
                    raise RuntimeError("Failed to retrieve review after insert")
                if row["review_hash"] != review_hash:
                    raise RuntimeError("Review idempotency key conflicts with different content")
            else:
                await connection.execute(
                    """INSERT INTO canonical.human_scientific_review_audit_events (
                        organization_id, review_id, actor_id, action, review_hash
                    ) VALUES ($1, $2, $3, 'human_review_recorded', $4)""",
                    org_id,
                    row["id"],
                    reviewer_id,
                    review_hash,
                )

            return dict(row)

    async def list_reviews(
        self,
        *,
        tenant_id: str | None = None,
        reviewed_object_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if not tenant_id:
            return []

        try:
            org_id = UUID(tenant_id)
        except ValueError:
            return []

        async with self.connection(org_id) as connection:
            query = """SELECT * FROM canonical.human_scientific_reviews
                       WHERE organization_id = $1"""
            params = [org_id]

            if reviewed_object_type:
                query += " AND reviewed_object_type = $2"
                params.append(reviewed_object_type)

            limit_position = len(params) + 1
            query += f" ORDER BY created_at DESC LIMIT ${limit_position}"
            params.append(limit)

            rows = await connection.fetch(query, *params)
            return [dict(row) for row in rows]

    def create_review_sync(
        self,
        *,
        reviewed_object_type: str,
        reviewed_object_id: str,
        review_action: str,
        review_status: str,
        rationale: str,
        original_ai_value: Any,
        human_decision: Any,
        original_value: Any,
        corrected_value: Any,
        reviewer_user_id: str,
        tenant_id: str | None,
        model_version: str | None = None,
        evidence_version: str | None = None,
        decision_version: str | None = None,
        source_provenance: dict[str, Any] | None = None,
        previous_review_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Synchronous wrapper for create_review. Returns None on failure to allow fallback."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're in an async context, create a task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.create_review(
                            reviewed_object_type=reviewed_object_type,
                            reviewed_object_id=reviewed_object_id,
                            review_action=review_action,
                            review_status=review_status,
                            rationale=rationale,
                            original_ai_value=original_ai_value,
                            human_decision=human_decision,
                            original_value=original_value,
                            corrected_value=corrected_value,
                            reviewer_user_id=reviewer_user_id,
                            tenant_id=tenant_id,
                            model_version=model_version,
                            evidence_version=evidence_version,
                            decision_version=decision_version,
                            source_provenance=source_provenance,
                            previous_review_id=previous_review_id,
                        )
                    )
                    return future.result(timeout=5.0)
            else:
                return asyncio.run(self.create_review(
                    reviewed_object_type=reviewed_object_type,
                    reviewed_object_id=reviewed_object_id,
                    review_action=review_action,
                    review_status=review_status,
                    rationale=rationale,
                    original_ai_value=original_ai_value,
                    human_decision=human_decision,
                    original_value=original_value,
                    corrected_value=corrected_value,
                    reviewer_user_id=reviewer_user_id,
                    tenant_id=tenant_id,
                    model_version=model_version,
                    evidence_version=evidence_version,
                    decision_version=decision_version,
                    source_provenance=source_provenance,
                    previous_review_id=previous_review_id,
                ))
        except Exception:
            return None


durable_review_store = DurableReviewStore()

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

from app.core.canonical_security import CanonicalPrincipal
from app.database.canonical_store import CanonicalStore
from app.schemas.decision_governance import DecisionReviewCreate, DecisionSnapshotCreate
from app.services.canonical_repository import (
    CanonicalAuthorizationError,
    CanonicalConflictError,
    CanonicalNotFoundError,
    CanonicalRepository,
)


class DecisionGovernanceRepository:
    def __init__(self, store: CanonicalStore):
        self.store = store

    @staticmethod
    def _require_tenant_writer(principal: CanonicalPrincipal) -> tuple[UUID, UUID]:
        if principal.organization_id is None or principal.user_id is None:
            raise CanonicalAuthorizationError(
                "decision governance writes require verified user and organization claims"
            )
        return principal.organization_id, principal.user_id

    @staticmethod
    def _json_value(value: Any) -> Any:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value

    @staticmethod
    def _snapshot_hash(payload: DecisionSnapshotCreate) -> str:
        encoded = json.dumps(
            payload.model_dump(mode="json", exclude={"idempotency_key"}),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            default=str,
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _review_hash(payload: DecisionReviewCreate) -> str:
        encoded = json.dumps(
            payload.model_dump(mode="json", exclude={"idempotency_key"}),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            default=str,
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _row_dict(row: asyncpg.Record) -> dict[str, Any]:
        result = dict(row)
        for key, value in tuple(result.items()):
            if isinstance(value, str) and key in {
                "model_versions", "feature_versions", "signal_payload",
                "evidence_refs", "explanation", "original_ai_value",
                "human_decision", "provenance", "payload",
            }:
                result[key] = DecisionGovernanceRepository._json_value(value)
        return result

    async def create_snapshot(
        self, payload: DecisionSnapshotCreate, principal: CanonicalPrincipal
    ) -> tuple[dict[str, Any], bool]:
        organization_id, user_id = self._require_tenant_writer(principal)
        snapshot_hash = self._snapshot_hash(payload)
        async with self.store.connection(organization_id) as connection:
            asset = await connection.fetchrow(
                """SELECT id FROM canonical.entities
                WHERE id = $1 AND entity_type = 'therapeutic_asset'
                  AND (organization_id IS NULL OR organization_id = $2::uuid)""",
                payload.asset_id,
                organization_id,
            )
            if asset is None:
                raise CanonicalNotFoundError("canonical asset not found")
            row = await connection.fetchrow(
                """INSERT INTO canonical.decision_snapshots (
                    asset_id, organization_id, user_id, idempotency_key, action,
                    score, confidence, evaluation_cutoff, policy_name, policy_version,
                    prompt_version, model_versions, feature_versions, signal_payload, evidence_refs,
                    explanation, snapshot_hash
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                    $11, $12::jsonb, $13::jsonb, $14::jsonb, $15::jsonb, $16::jsonb, $17)
                ON CONFLICT (organization_id, idempotency_key) DO NOTHING
                RETURNING *""",
                payload.asset_id,
                organization_id,
                user_id,
                payload.idempotency_key,
                payload.action,
                payload.score,
                payload.confidence,
                payload.evaluation_cutoff,
                payload.policy_name,
                payload.policy_version,
                payload.prompt_version,
                json.dumps(payload.model_versions),
                json.dumps(payload.feature_versions),
                json.dumps(payload.signal_payload),
                json.dumps(payload.evidence_refs),
                json.dumps(payload.explanation),
                snapshot_hash,
            )
            created = row is not None
            if row is None:
                row = await connection.fetchrow(
                    """SELECT * FROM canonical.decision_snapshots
                    WHERE organization_id = $1 AND idempotency_key = $2""",
                    organization_id,
                    payload.idempotency_key,
                )
                if row is None:
                    raise CanonicalConflictError("decision idempotency key conflict")
                if row["snapshot_hash"] != snapshot_hash:
                    raise CanonicalConflictError(
                        "decision idempotency key was already used for different content"
                    )
            else:
                await connection.execute(
                    """INSERT INTO canonical.decision_governance_events (
                        organization_id, asset_id, decision_snapshot_id, actor_id,
                        event_type, payload
                    ) VALUES ($1, $2, $3, $4, 'decision_snapshotted', $5::jsonb)""",
                    organization_id,
                    payload.asset_id,
                    row["id"],
                    user_id,
                    json.dumps({"snapshot_hash": snapshot_hash, "action": payload.action}),
                )
            return self._row_dict(row), created

    async def create_review(
        self,
        snapshot_id: UUID,
        payload: DecisionReviewCreate,
        principal: CanonicalPrincipal,
    ) -> tuple[dict[str, Any], bool]:
        if not principal.can_review:
            raise CanonicalAuthorizationError("review permission is required")
        organization_id, reviewer_id = self._require_tenant_writer(principal)
        review_hash = self._review_hash(payload)
        async with self.store.connection(organization_id) as connection:
            snapshot = await connection.fetchrow(
                """SELECT id, asset_id FROM canonical.decision_snapshots
                WHERE id = $1 AND organization_id = $2::uuid""",
                snapshot_id,
                organization_id,
            )
            if snapshot is None:
                raise CanonicalNotFoundError("decision snapshot not found")
            row = await connection.fetchrow(
                """INSERT INTO canonical.decision_reviews (
                    decision_snapshot_id, organization_id, reviewer_id, idempotency_key,
                    review_action, review_status, rationale, original_ai_value,
                    human_decision, model_version, evidence_version, provenance,
                    review_hash
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb,
                    $10, $11, $12::jsonb, $13)
                ON CONFLICT (organization_id, idempotency_key) DO NOTHING
                RETURNING *""",
                snapshot_id,
                organization_id,
                reviewer_id,
                payload.idempotency_key,
                payload.review_action,
                payload.review_status,
                payload.rationale,
                json.dumps(payload.original_ai_value, default=str),
                json.dumps(payload.human_decision, default=str),
                payload.model_version,
                payload.evidence_version,
                json.dumps(payload.provenance),
                review_hash,
            )
            created = row is not None
            if row is None:
                row = await connection.fetchrow(
                    """SELECT * FROM canonical.decision_reviews
                    WHERE organization_id = $1 AND idempotency_key = $2""",
                    organization_id,
                    payload.idempotency_key,
                )
                if row is None:
                    raise CanonicalConflictError("review idempotency key conflict")
                if row["review_hash"] != review_hash:
                    raise CanonicalConflictError(
                        "review idempotency key was already used for different content"
                    )
            else:
                await connection.execute(
                    """INSERT INTO canonical.decision_governance_events (
                        organization_id, asset_id, decision_snapshot_id,
                        decision_review_id, actor_id, event_type, payload
                    ) VALUES ($1, $2, $3, $4, $5, 'decision_reviewed', $6::jsonb)""",
                    organization_id,
                    snapshot["asset_id"],
                    snapshot_id,
                    row["id"],
                    reviewer_id,
                    json.dumps({
                        "review_action": payload.review_action,
                        "review_status": payload.review_status,
                        "rationale": payload.rationale,
                    }),
                )
            return self._row_dict(row), created

    async def list_history(
        self,
        asset_id: UUID,
        principal: CanonicalPrincipal,
        *,
        as_of: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        if principal.organization_id is None:
            raise CanonicalAuthorizationError("decision history requires a verified organization")
        CanonicalRepository._require_aware_as_of(as_of)
        offset = (page - 1) * page_size
        async with self.store.connection(principal.organization_id) as connection:
            asset = await connection.fetchrow(
                """SELECT id FROM canonical.entities
                WHERE id = $1 AND entity_type = 'therapeutic_asset'
                  AND (organization_id IS NULL OR organization_id = $2::uuid)""",
                asset_id,
                principal.organization_id,
            )
            if asset is None:
                raise CanonicalNotFoundError("canonical asset not found")
            rows = await connection.fetch(
                """SELECT d.*,
                    COALESCE((
                        SELECT jsonb_agg(to_jsonb(r) ORDER BY r.created_at, r.id)
                        FROM canonical.decision_reviews r
                        WHERE r.decision_snapshot_id = d.id
                          AND r.organization_id = d.organization_id
                          AND ($2::timestamptz IS NULL OR r.created_at <= $2)
                    ), '[]'::jsonb) AS reviews,
                    COALESCE((
                        SELECT jsonb_agg(to_jsonb(e) ORDER BY e.created_at, e.id)
                        FROM canonical.decision_governance_events e
                        WHERE e.decision_snapshot_id = d.id
                          AND e.organization_id = d.organization_id
                          AND ($2::timestamptz IS NULL OR e.created_at <= $2)
                    ), '[]'::jsonb) AS audit_events
                FROM canonical.decision_snapshots d
                WHERE d.asset_id = $1 AND d.organization_id = $3::uuid
                  AND ($2::timestamptz IS NULL OR d.created_at <= $2)
                ORDER BY d.created_at DESC, d.id DESC
                OFFSET $4 LIMIT $5""",
                asset_id,
                as_of,
                principal.organization_id,
                offset,
                page_size,
            )
            total = await connection.fetchval(
                """SELECT count(*) FROM canonical.decision_snapshots
                WHERE asset_id = $1 AND organization_id = $2::uuid
                  AND ($3::timestamptz IS NULL OR created_at <= $3)""",
                asset_id,
                principal.organization_id,
                as_of,
            )
            result = []
            for row in rows:
                item = self._row_dict(row)
                item["reviews"] = self._json_value(item.get("reviews")) or []
                item["audit_events"] = self._json_value(item.get("audit_events")) or []
                result.append(item)
            return result, int(total or 0)

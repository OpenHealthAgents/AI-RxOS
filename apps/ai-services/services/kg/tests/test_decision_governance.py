from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import asyncpg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.canonical_security import CanonicalPrincipal, get_canonical_principal
from app.database.canonical_store import canonical_store
from app.routers import canonical as canonical_router
from app.schemas.canonical import (
    CanonicalEntityCreate,
    EntityType,
    Modality,
    SourceRecordInput,
    Visibility,
)
from app.schemas.decision_governance import DecisionReviewCreate, DecisionSnapshotCreate
from app.services.canonical_repository import (
    CanonicalAuthorizationError,
    CanonicalConflictError,
    CanonicalNotFoundError,
)
from app.services.decision_governance import DecisionGovernanceRepository

TENANT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
USER_ID = UUID("11111111-1111-1111-1111-111111111111")
OTHER_TENANT_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def _principal(
    tenant_id: UUID = TENANT_ID,
    *,
    roles: frozenset[str] = frozenset({"reviewer"}),
    user_id: UUID | None = USER_ID,
) -> CanonicalPrincipal:
    return CanonicalPrincipal(user_id, tenant_id, roles, frozenset())


def _decision_payload(asset_id: UUID, idempotency_key: str = "decision-v1") -> DecisionSnapshotCreate:
    return DecisionSnapshotCreate(
        asset_id=asset_id,
        idempotency_key=idempotency_key,
        action="PURSUE",
        score=81.5,
        confidence=0.88,
        evaluation_cutoff=datetime(2026, 10, 1, tzinfo=UTC),
        policy_name="test-policy",
        policy_version="v1",
        model_versions={"decision": "m1"},
        feature_versions={"clinical": "f3"},
        signal_payload={"clinical": {"value": 77, "status": "AVAILABLE"}},
        evidence_refs=[{"source_record_id": "synthetic-evidence-1", "polarity": "supporting"}],
        explanation={"unknowns": ["commercial evidence unavailable"]},
    )


def _review_payload(idempotency_key: str = "review-v1") -> DecisionReviewCreate:
    return DecisionReviewCreate(
        idempotency_key=idempotency_key,
        review_action="override",
        review_status="overridden",
        rationale="Synthetic test review: preserve the original AI output.",
        original_ai_value={"action": "PURSUE"},
        human_decision={"action": "MONITOR"},
        model_version="m1",
        evidence_version="e3",
        provenance={"test_fixture": True},
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"action": "UNKNOWN"},
        {"score": 101},
        {"confidence": -0.1},
        {"evaluation_cutoff": "2026-10-01T00:00:00"},
        {"policy_version": " "},
    ],
)
def test_decision_snapshot_rejects_invalid_values(overrides):
    values = _decision_payload(uuid4()).model_dump(mode="python")
    values.update(overrides)
    with pytest.raises(ValidationError):
        DecisionSnapshotCreate.model_validate(values)


def test_review_rejects_missing_rationale_or_invalid_action():
    values = _review_payload().model_dump()
    values["rationale"] = " "
    with pytest.raises(ValidationError):
        DecisionReviewCreate.model_validate(values)
    values["rationale"] = "reason"
    values["review_action"] = "delete"
    with pytest.raises(ValidationError):
        DecisionReviewCreate.model_validate(values)


def test_decision_governance_api_requires_review_permission_and_timezone():
    api = FastAPI()
    api.include_router(canonical_router.router)
    api.dependency_overrides[get_canonical_principal] = lambda: _principal(roles=frozenset())
    previous_pool = canonical_store.pool
    canonical_store.pool = object()
    try:
        client = TestClient(api)
        response = client.post(
            f"/api/v1/canonical/decision-snapshots/{uuid4()}/reviews",
            json=_review_payload().model_dump(mode="json"),
        )
        assert response.status_code == 403

        response = client.get(
            "/api/v1/canonical/decision-snapshots/history",
            params={"asset_id": str(uuid4()), "as_of": "2026-10-01T00:00:00"},
        )
        assert response.status_code == 422
    finally:
        canonical_store.pool = previous_pool
        api.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_decision_snapshot_review_and_as_of_history_are_persisted(canonical_repo):
    store, repository = canonical_repo
    principal = _principal()
    suffix = str(uuid4())
    asset = await repository.create_entity(
        CanonicalEntityCreate(
            entity_type=EntityType.THERAPEUTIC_ASSET,
            preferred_name=f"Governance test asset {suffix}",
            modality=Modality.OTHER,
            visibility=Visibility.TENANT,
            source_record=SourceRecordInput(
                namespace="decision-governance-test",
                external_id=f"asset:{suffix}",
                source_type="demo",
                provenance={"synthetic": True},
            ),
        ),
        principal,
    )
    asset_id = UUID(str(asset["id"]))
    service = DecisionGovernanceRepository(store)

    snapshot_payload = _decision_payload(asset_id, f"decision:{suffix}")
    snapshot, created = await service.create_snapshot(snapshot_payload, principal)
    assert created
    assert snapshot["action"] == "PURSUE"
    assert snapshot["snapshot_hash"]
    assert snapshot["evidence_refs"][0]["source_record_id"] == "synthetic-evidence-1"

    duplicate, duplicate_created = await service.create_snapshot(snapshot_payload, principal)
    assert not duplicate_created
    assert duplicate["id"] == snapshot["id"]
    with pytest.raises(CanonicalConflictError, match="different content"):
        await service.create_snapshot(
            snapshot_payload.model_copy(update={"score": 82.0}), principal
        )

    review_payload = _review_payload(f"review:{suffix}")
    review, review_created = await service.create_review(
        UUID(str(snapshot["id"])), review_payload, principal
    )
    assert review_created
    assert review["original_ai_value"] == {"action": "PURSUE"}
    assert review["human_decision"] == {"action": "MONITOR"}
    duplicate_review, duplicate_review_created = await service.create_review(
        UUID(str(snapshot["id"])), review_payload, principal
    )
    assert not duplicate_review_created
    assert duplicate_review["id"] == review["id"]

    cutoff = snapshot["created_at"] + timedelta(seconds=1)
    history, total = await service.list_history(
        asset_id, principal, as_of=cutoff, page=1, page_size=10
    )
    assert total == 1
    assert history[0]["id"] == snapshot["id"]
    assert len(history[0]["reviews"]) == 1
    assert len(history[0]["audit_events"]) == 2

    before_write, before_total = await service.list_history(
        asset_id,
        principal,
        as_of=snapshot["created_at"] - timedelta(seconds=1),
        page=1,
        page_size=10,
    )
    assert before_write == []
    assert before_total == 0

    with pytest.raises(asyncpg.PostgresError, match="append-only"):
        async with store.connection(TENANT_ID) as connection:
            await connection.execute(
                "UPDATE canonical.decision_snapshots SET score = 0 WHERE id = $1",
                snapshot["id"],
            )


@pytest.mark.asyncio
async def test_decision_governance_rejects_missing_scope_and_cross_tenant_access(canonical_repo):
    store, repository = canonical_repo
    principal = _principal()
    suffix = str(uuid4())
    asset = await repository.create_entity(
        CanonicalEntityCreate(
            entity_type=EntityType.THERAPEUTIC_ASSET,
            preferred_name=f"Private governance asset {suffix}",
            modality=Modality.OTHER,
            visibility=Visibility.TENANT,
            source_record=SourceRecordInput(
                namespace="decision-governance-test",
                external_id=f"private-asset:{suffix}",
                source_type="demo",
                provenance={"synthetic": True},
            ),
        ),
        principal,
    )
    service = DecisionGovernanceRepository(store)
    asset_id = UUID(str(asset["id"]))

    with pytest.raises(CanonicalAuthorizationError, match="verified user and organization"):
        await service.create_snapshot(
            _decision_payload(asset_id),
            CanonicalPrincipal(None, None, frozenset(), frozenset()),
        )
    with pytest.raises(CanonicalAuthorizationError, match="review permission"):
        await service.create_review(
            uuid4(), _review_payload(), _principal(roles=frozenset())
        )
    snapshot, _ = await service.create_snapshot(_decision_payload(asset_id, f"private-snap:{suffix}"), principal)
    with pytest.raises(CanonicalNotFoundError):
        await service.create_review(
            UUID(str(snapshot["id"])),
            _review_payload(f"cross-review:{suffix}"),
            _principal(OTHER_TENANT_ID),
        )

    with pytest.raises(CanonicalNotFoundError):
        await service.list_history(
            asset_id,
            _principal(OTHER_TENANT_ID),
            as_of=None,
            page=1,
            page_size=10,
        )
    with pytest.raises(CanonicalAuthorizationError, match="verified organization"):
        await service.list_history(
            asset_id,
            CanonicalPrincipal(USER_ID, None, frozenset({"operator"}), frozenset()),
            as_of=None,
            page=1,
            page_size=10,
        )

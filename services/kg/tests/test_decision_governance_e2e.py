from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.core.canonical_security import CanonicalPrincipal, get_canonical_principal
from app.schemas.canonical import (
    CanonicalEntityCreate,
    EntityType,
    Modality,
    SourceRecordInput,
    Visibility,
)
from app.schemas.decision_governance import DecisionReviewCreate, DecisionSnapshotCreate
from app.services.canonical_repository import CanonicalRepository
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
        rationale="E2E test review: preserve original AI output.",
        original_ai_value={"action": "PURSUE"},
        human_decision={"action": "MONITOR"},
        model_version="m1",
        evidence_version="e3",
        provenance={"e2e_test": True},
    )


@pytest.mark.asyncio
async def test_e2e_decision_snapshot_review_and_history_lifecycle(canonical_repo):
    """End-to-end test: create snapshot, add review, retrieve history with as-of."""
    store, repository = canonical_repo
    principal = _principal()
    suffix = str(uuid4())

    # Step 1: Create a therapeutic asset
    asset = await repository.create_entity(
        CanonicalEntityCreate(
            entity_type=EntityType.THERAPEUTIC_ASSET,
            preferred_name=f"E2E test asset {suffix}",
            modality=Modality.OTHER,
            visibility=Visibility.TENANT,
            source_record=SourceRecordInput(
                namespace="e2e-test",
                external_id=f"asset:{suffix}",
                source_type="demo",
                provenance={"e2e": True},
            ),
        ),
        principal,
    )
    asset_id = UUID(str(asset["id"]))

    # Step 2: Create decision snapshot
    decision_service = DecisionGovernanceRepository(store)
    snapshot, created = await decision_service.create_snapshot(
        _decision_payload(asset_id, f"e2e-decision:{suffix}"),
        principal,
    )
    assert created
    assert snapshot["action"] == "PURSUE"
    snapshot_id = UUID(str(snapshot["id"]))
    snapshot_created_at = snapshot["created_at"]

    # Step 3: Add human review to the snapshot
    review, review_created = await decision_service.create_review(
        snapshot_id,
        _review_payload(f"e2e-review:{suffix}"),
        principal,
    )
    assert review_created
    assert review["original_ai_value"] == {"action": "PURSUE"}
    assert review["human_decision"] == {"action": "MONITOR"}

    # Step 4: Retrieve decision history with as-of cutoff
    cutoff = snapshot_created_at + timedelta(seconds=1)
    history, total = await decision_service.list_history(
        asset_id,
        principal,
        as_of=cutoff,
        page=1,
        page_size=10,
    )
    assert total == 1
    assert len(history) == 1
    assert history[0]["id"] == snapshot_id
    assert len(history[0]["reviews"]) == 1
    assert history[0]["reviews"][0]["human_decision"] == {"action": "MONITOR"}
    assert len(history[0]["audit_events"]) == 2  # snapshot + review events

    # Step 5: Verify as-of before snapshot returns empty
    before_history, before_total = await decision_service.list_history(
        asset_id,
        principal,
        as_of=snapshot_created_at - timedelta(seconds=1),
        page=1,
        page_size=10,
    )
    assert before_total == 0
    assert before_history == []

    # Step 6: Verify idempotency - duplicate snapshot returns same record
    duplicate_snapshot, duplicate_created = await decision_service.create_snapshot(
        _decision_payload(asset_id, f"e2e-decision:{suffix}"),
        principal,
    )
    assert not duplicate_created
    assert duplicate_snapshot["id"] == snapshot_id

    # Step 7: Verify idempotency - duplicate review returns same record
    duplicate_review, duplicate_review_created = await decision_service.create_review(
        snapshot_id,
        _review_payload(f"e2e-review:{suffix}"),
        principal,
    )
    assert not duplicate_review_created
    assert duplicate_review["id"] == review["id"]


@pytest.mark.asyncio
async def test_e2e_cross_tenant_isolation_enforced(canonical_repo):
    """End-to-end test: verify tenant isolation across the entire lifecycle."""
    store, repository = canonical_repo
    principal_a = _principal(TENANT_ID)
    principal_b = _principal(OTHER_TENANT_ID)
    suffix = str(uuid4())

    # Create asset in tenant A
    asset_a = await repository.create_entity(
        CanonicalEntityCreate(
            entity_type=EntityType.THERAPEUTIC_ASSET,
            preferred_name=f"Tenant A asset {suffix}",
            modality=Modality.OTHER,
            visibility=Visibility.TENANT,
            source_record=SourceRecordInput(
                namespace="e2e-tenant-test",
                external_id=f"asset-a:{suffix}",
                source_type="demo",
                provenance={"tenant": "A"},
            ),
        ),
        principal_a,
    )
    asset_id_a = UUID(str(asset_a["id"]))

    # Create snapshot in tenant A
    decision_service = DecisionGovernanceRepository(store)
    snapshot_a, _ = await decision_service.create_snapshot(
        _decision_payload(asset_id_a, f"tenant-a-decision:{suffix}"),
        principal_a,
    )

    # Tenant B cannot access tenant A's snapshot
    from app.services.canonical_repository import CanonicalNotFoundError
    with pytest.raises(CanonicalNotFoundError):
        await decision_service.create_review(
            UUID(str(snapshot_a["id"])),
            _review_payload(f"tenant-b-review:{suffix}"),
            principal_b,
        )

    # Tenant B cannot retrieve tenant A's history
    with pytest.raises(CanonicalNotFoundError):
        await decision_service.list_history(
            asset_id_a,
            principal_b,
            as_of=None,
            page=1,
            page_size=10,
        )

    # Tenant A can retrieve their own history
    history_a, total_a = await decision_service.list_history(
        asset_id_a,
        principal_a,
        as_of=None,
        page=1,
        page_size=10,
    )
    assert total_a == 1
    assert len(history_a) == 1


@pytest.mark.asyncio
async def test_e2e_append_only_history_preserves_versions(canonical_repo):
    """End-to-end test: verify append-only behavior preserves historical versions."""
    store, repository = canonical_repo
    principal = _principal()
    suffix = str(uuid4())

    asset = await repository.create_entity(
        CanonicalEntityCreate(
            entity_type=EntityType.THERAPEUTIC_ASSET,
            preferred_name=f"Version test asset {suffix}",
            modality=Modality.OTHER,
            visibility=Visibility.TENANT,
            source_record=SourceRecordInput(
                namespace="e2e-version-test",
                external_id=f"asset:{suffix}",
                source_type="demo",
                provenance={"version_test": True},
            ),
        ),
        principal,
    )
    asset_id = UUID(str(asset["id"]))

    decision_service = DecisionGovernanceRepository(store)

    # Create first snapshot with PURSUE action
    snapshot1, _ = await decision_service.create_snapshot(
        _decision_payload(asset_id, f"version-1:{suffix}"),
        principal,
    )

    # Create second snapshot with different action (MONITOR)
    payload2 = _decision_payload(asset_id, f"version-2:{suffix}")
    payload2.action = "MONITOR"
    payload2.score = 65.0
    snapshot2, _ = await decision_service.create_snapshot(payload2, principal)

    # Retrieve full history - should have both versions
    history, total = await decision_service.list_history(
        asset_id,
        principal,
        as_of=None,
        page=1,
        page_size=10,
    )
    assert total == 2
    assert len(history) == 2

    # Verify both versions are preserved (not overwritten)
    actions = {h["action"] for h in history}
    assert actions == {"PURSUE", "MONITOR"}

    # Verify ordering is stable (most recent first)
    assert history[0]["created_at"] >= history[1]["created_at"]

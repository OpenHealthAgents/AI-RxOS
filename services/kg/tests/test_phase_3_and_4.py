from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from httpx import ASGITransport, AsyncClient

from app.core.canonical_security import CanonicalPrincipal
from app.main import app
from app.routers import canonical as canonical_router
from app.schemas.canonical import (
    CanonicalEntityCreate,
    ClaimCreate,
    EntityType,
    EvidenceLinkCreate,
    IdentifierInput,
    ObservationCreate,
    ObservationKind,
    SourceRecordInput,
    Visibility,
)


@pytest.mark.asyncio
async def test_phase_3_evidence_lineage_supports_and_contradictions(canonical_repo):
    store, repository = canonical_repo
    tenant = UUID("33333333-3333-3333-3333-333333333333")
    principal = CanonicalPrincipal(
        UUID("55555555-5555-5555-5555-555555555555"), tenant,
        frozenset({"operator"}),
        frozenset(),
    )

    source = SourceRecordInput(
        namespace="phase-3",
        external_id=f"entity-{uuid4()}",
        source_type="demo",
        provenance={"scenario": "phase-3"},
    )
    entity = await repository.create_entity(
        CanonicalEntityCreate(
            entity_type=EntityType.TARGET,
            preferred_name="Phase 3 target",
            visibility=Visibility.TENANT,
            source_record=source,
            identifiers=[
                IdentifierInput(
                    namespace="phase-3",
                    identifier_type="target",
                    value=f"phase-3-target-{uuid4()}",
                    source_record=source,
                )
            ],
        ),
        principal,
    )
    entity_id = UUID(str(entity["id"]))

    supporting_observation = await repository.create_observation(
        ObservationCreate(
            entity_id=entity_id,
            property_name="validation_signal",
            observation_kind=ObservationKind.SOURCE_FACT,
            value={"status": "evidence-supported"},
            visibility=Visibility.TENANT,
            source_record=SourceRecordInput(
                namespace="phase-3",
                external_id=f"support-{uuid4()}",
                source_type="demo",
                provenance={"scenario": "supporting"},
            ),
        ),
        principal,
    )
    contradicting_observation = await repository.create_observation(
        ObservationCreate(
            entity_id=entity_id,
            property_name="validation_signal",
            observation_kind=ObservationKind.SOURCE_FACT,
            value={"status": "contradicting"},
            visibility=Visibility.TENANT,
            source_record=SourceRecordInput(
                namespace="phase-3",
                external_id=f"contradict-{uuid4()}",
                source_type="demo",
                provenance={"scenario": "contradicting"},
            ),
        ),
        principal,
    )

    claim = await repository.create_claim(
        ClaimCreate(
            entity_id=entity_id,
            claim_type="derived_claim",
            statement="The target has a validated signal",
            visibility=Visibility.TENANT,
            confidence=0.83,
            source_record=SourceRecordInput(
                namespace="phase-3",
                external_id=f"claim-{uuid4()}",
                source_type="demo",
                provenance={"scenario": "claim"},
            ),
            observation_id=supporting_observation["id"],
        ),
        principal,
    )

    await repository.link_evidence(
        claim["id"],
        EvidenceLinkCreate(
            observation_id=supporting_observation["id"],
            relation_type="supporting",
            metadata={"reason": "corroborated evidence"},
            visibility=Visibility.TENANT,
        ),
        principal,
    )
    await repository.link_evidence(
        claim["id"],
        EvidenceLinkCreate(
            observation_id=contradicting_observation["id"],
            relation_type="contradicting",
            metadata={"reason": "conflicting evidence"},
            visibility=Visibility.TENANT,
        ),
        principal,
    )

    lineage = await repository.get_claim_lineage(UUID(str(claim["id"])), principal)
    assert lineage["statement"] == "The target has a validated signal"
    assert {row["relation_type"] for row in lineage["evidence"]} == {"supporting", "contradicting"}
    assert any(row["observation_id"] == supporting_observation["id"] for row in lineage["evidence"])
    assert any(row["observation_id"] == contradicting_observation["id"] for row in lineage["evidence"])


@pytest.mark.asyncio
async def test_phase_4_as_of_temporal_filtering_excludes_future_evidence(canonical_repo):
    store, repository = canonical_repo
    tenant = UUID("44444444-4444-4444-4444-444444444444")
    principal = CanonicalPrincipal(
        UUID("66666666-6666-6666-6666-666666666666"), tenant,
        frozenset({"operator"}),
        frozenset(),
    )

    source = SourceRecordInput(
        namespace="phase-4",
        external_id=f"entity-{uuid4()}",
        source_type="demo",
        provenance={"scenario": "phase-4"},
    )
    entity = await repository.create_entity(
        CanonicalEntityCreate(
            entity_type=EntityType.TARGET,
            preferred_name="Phase 4 target",
            visibility=Visibility.TENANT,
            source_record=source,
            identifiers=[IdentifierInput(
                namespace="phase-4",
                identifier_type="target",
                value=f"phase-4-target-{uuid4()}",
                source_record=source,
            )],
        ),
        principal,
    )
    entity_id = UUID(str(entity["id"]))

    known_from = datetime(2019, 1, 1, tzinfo=timezone.utc)
    valid_start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    first_valid_end = datetime(2021, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    late_arrival = datetime(2021, 2, 1, tzinfo=timezone.utc)
    contradiction_start = datetime(2022, 1, 1, tzinfo=timezone.utc)
    contradiction_end = datetime(2022, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    correction_start = datetime(2023, 1, 1, tzinfo=timezone.utc)

    async with store.connection(tenant) as connection:
        await connection.execute(
            "UPDATE canonical.entities SET created_at = $2 WHERE id = $1",
            entity_id, known_from,
        )
        await connection.execute(
            "UPDATE canonical.source_records SET ingested_at = $2 WHERE id = $1",
            entity["created_source_record_id"], known_from,
        )

    async def persist_observation(
        label: str,
        published_at: datetime | None,
        observed_at: datetime | None,
        ingested_at: datetime,
        valid_from: datetime | None,
        valid_to: datetime | None,
    ) -> UUID:
        source_id = uuid4()
        observation_id = uuid4()
        async with store.connection(tenant) as connection:
            await connection.execute(
                """INSERT INTO canonical.source_records (
                    id, visibility, organization_id, namespace, external_id, source_type,
                    published_at, observed_at, ingested_at, provenance
                ) VALUES ($1, 'tenant', $2, 'phase-4-timeline', $3, 'publication',
                    $4, $5, $6, $7::jsonb)""",
                source_id, tenant, f"source-{label}-{uuid4()}", published_at, observed_at,
                ingested_at, json.dumps({"timeline": label}),
            )
            await connection.execute(
                """INSERT INTO canonical.observations (
                    id, entity_id, property_name, observation_kind, value, verification_state,
                    source_record_id, valid_from, valid_to, published_at, observed_at,
                    ingested_at, visibility, organization_id, created_at
                ) VALUES ($1, $2, 'activity_state', 'source_fact', $3::jsonb, 'unreviewed',
                    $4, $5, $6, $7, $8, $9, 'tenant', $10, $9)""",
                observation_id, entity_id, json.dumps({"evidence": label}), source_id,
                valid_from, valid_to, published_at, observed_at, ingested_at, tenant,
            )
        return observation_id

    early_observation = await persist_observation(
        "early-support", datetime(2019, 6, 1, tzinfo=timezone.utc),
        datetime(2019, 5, 20, tzinfo=timezone.utc), datetime(2019, 6, 2, tzinfo=timezone.utc),
        valid_start, first_valid_end,
    )
    late_observation = await persist_observation(
        "late-arrival", datetime(2019, 6, 1, tzinfo=timezone.utc),
        datetime(2019, 5, 20, tzinfo=timezone.utc), late_arrival,
        valid_start, contradiction_end,
    )
    contradicting_observation = await persist_observation(
        "later-contradiction", datetime(2021, 12, 15, tzinfo=timezone.utc),
        datetime(2021, 12, 10, tzinfo=timezone.utc), datetime(2021, 12, 16, tzinfo=timezone.utc),
        contradiction_start, contradiction_end,
    )
    correction_observation = await persist_observation(
        "correction", datetime(2022, 12, 15, tzinfo=timezone.utc),
        datetime(2022, 12, 10, tzinfo=timezone.utc), datetime(2022, 12, 16, tzinfo=timezone.utc),
        correction_start, None,
    )
    unbounded_observation = await persist_observation(
        "unknown-time", None, None, known_from, None, None,
    )

    claim = await repository.create_claim(
        ClaimCreate(
            entity_id=entity_id,
            claim_type="derived_claim",
            statement="Asset activity changes as evidence is updated",
            visibility=Visibility.TENANT,
            valid_from=known_from,
            confidence=0.7,
            source_record=SourceRecordInput(
                namespace="phase-4",
                external_id=f"claim-{uuid4()}",
                source_type="demo",
                published_at=known_from,
                provenance={"scenario": "temporal-state"},
            ),
        ),
        principal,
    )
    async with store.connection(tenant) as connection:
        await connection.execute(
            "UPDATE canonical.claims SET created_at = $2 WHERE id = $1",
            claim["id"], known_from,
        )
        await connection.execute(
            "UPDATE canonical.source_records SET ingested_at = $2 WHERE id = $1",
            claim["source_record_id"], known_from,
        )

    async def add_evidence(
        observation_id: UUID,
        relation_type: str,
        valid_from: datetime | None,
        valid_to: datetime | None,
        available_at: datetime,
        label: str,
    ) -> None:
        evidence = await repository.link_evidence(
            UUID(str(claim["id"])),
            EvidenceLinkCreate(
                observation_id=observation_id,
                relation_type=relation_type,
                metadata={"timeline": label},
                visibility=Visibility.TENANT,
                valid_from=valid_from,
                valid_to=valid_to,
            ),
            principal,
        )
        async with store.connection(tenant) as connection:
            await connection.execute(
                "UPDATE canonical.evidence_links SET created_at = $2 WHERE id = $1",
                evidence["id"], available_at,
            )

    await add_evidence(early_observation, "supporting", valid_start, first_valid_end,
                       datetime(2019, 6, 2, tzinfo=timezone.utc), "early-support")
    await add_evidence(late_observation, "supporting", valid_start, contradiction_end,
                       late_arrival, "late-arrival")
    await add_evidence(contradicting_observation, "contradicting", contradiction_start,
                       contradiction_end, datetime(2021, 12, 16, tzinfo=timezone.utc), "later-contradiction")
    await add_evidence(correction_observation, "supporting", correction_start, None,
                       datetime(2022, 12, 16, tzinfo=timezone.utc), "correction")
    await add_evidence(unbounded_observation, "context", None, None, known_from, "unknown-time")

    async def lineage_at(timestamp: datetime) -> dict:
        return await repository.get_claim_lineage(UUID(str(claim["id"])), principal, as_of=timestamp)

    before_validity = await repository.list_claims(
        entity_id, principal, as_of=datetime(2018, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    )
    assert before_validity["items"] == []

    before_evidence_validity = await lineage_at(datetime(2019, 12, 31, 23, 59, 59, tzinfo=timezone.utc))
    assert {row["metadata"]["timeline"] for row in before_evidence_validity["evidence"]} == {
        "unknown-time"
    }

    at_valid_from = await lineage_at(valid_start)
    assert {row["metadata"]["timeline"] for row in at_valid_from["evidence"]} == {
        "early-support", "unknown-time"
    }
    unknown_time = next(row for row in at_valid_from["evidence"] if row["metadata"]["timeline"] == "unknown-time")
    assert unknown_time["observation"]["published_at"] is None
    assert unknown_time["observation"]["observed_at"] is None

    before_late_ingestion = await lineage_at(datetime(2021, 1, 31, 23, 59, 59, tzinfo=timezone.utc))
    assert {row["metadata"]["timeline"] for row in before_late_ingestion["evidence"]} == {
        "early-support", "unknown-time"
    }

    at_late_ingestion = await lineage_at(late_arrival)
    assert {row["metadata"]["timeline"] for row in at_late_ingestion["evidence"]} == {
        "early-support", "late-arrival", "unknown-time"
    }
    timezone_equivalent = await lineage_at(
        datetime(2021, 1, 31, 19, tzinfo=timezone(timedelta(hours=-5)))
    )
    assert {row["id"] for row in timezone_equivalent["evidence"]} == {
        row["id"] for row in at_late_ingestion["evidence"]
    }
    late_lineage = next(
        row for row in at_late_ingestion["evidence"]
        if row["metadata"]["timeline"] == "late-arrival"
    )
    assert late_lineage["observation"]["source_record"]["provenance"]
    assert late_lineage["observation"]["published_at"] == "2019-06-01T00:00:00+00:00"

    at_contradiction_start = await lineage_at(contradiction_start)
    assert "later-contradiction" in {
        row["metadata"]["timeline"] for row in at_contradiction_start["evidence"]
    }
    at_contradiction_end = await lineage_at(contradiction_end)
    assert "later-contradiction" in {
        row["metadata"]["timeline"] for row in at_contradiction_end["evidence"]
    }
    after_contradiction = await lineage_at(datetime(2023, 1, 1, tzinfo=timezone.utc))
    assert {row["metadata"]["timeline"] for row in after_contradiction["evidence"]} == {
        "correction", "unknown-time"
    }
    assert {row["relation_type"] for row in after_contradiction["evidence"]} == {"supporting", "context"}
    assert after_contradiction["statement"] == "Asset activity changes as evidence is updated"
    assert after_contradiction["source_record"]["provenance"]["scenario"] == "temporal-state"
    async with store.connection(tenant) as connection:
        persisted_evidence_count = await connection.fetchval(
            "SELECT count(*) FROM canonical.evidence_links WHERE claim_id = $1",
            claim["id"],
        )
    assert persisted_evidence_count == 5
    with pytest.raises(ValueError, match="timezone"):
        await repository.list_claims(entity_id, principal, as_of=datetime(2023, 1, 1))


@pytest.mark.asyncio
async def test_phase_3_cross_tenant_evidence_access_is_rejected(canonical_repo):
    _, repository = canonical_repo
    tenant_a = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    tenant_b = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    principal_a = CanonicalPrincipal(
        UUID("11111111-1111-1111-1111-111111111111"), tenant_a,
        frozenset({"operator"}),
        frozenset(),
    )
    principal_b = CanonicalPrincipal(
        UUID("22222222-2222-2222-2222-222222222222"), tenant_b,
        frozenset({"operator"}),
        frozenset(),
    )

    source_a = SourceRecordInput(
        namespace="phase-3-tenant-a",
        external_id=f"entity-{uuid4()}",
        source_type="demo",
        provenance={"scenario": "tenant-a"},
    )
    source_b = SourceRecordInput(
        namespace="phase-3-tenant-b",
        external_id=f"entity-{uuid4()}",
        source_type="demo",
        provenance={"scenario": "tenant-b"},
    )

    entity_a = await repository.create_entity(
        CanonicalEntityCreate(
            entity_type=EntityType.TARGET,
            preferred_name="Tenant A asset",
            visibility=Visibility.TENANT,
            source_record=source_a,
            identifiers=[IdentifierInput(
                namespace="phase-3-tenant-a",
                identifier_type="target",
                value=f"tenant-a-target-{uuid4()}",
                source_record=source_a,
            )],
        ),
        principal_a,
    )
    entity_b = await repository.create_entity(
        CanonicalEntityCreate(
            entity_type=EntityType.TARGET,
            preferred_name="Tenant B asset",
            visibility=Visibility.TENANT,
            source_record=source_b,
            identifiers=[IdentifierInput(
                namespace="phase-3-tenant-b",
                identifier_type="target",
                value=f"tenant-b-target-{uuid4()}",
                source_record=source_b,
            )],
        ),
        principal_b,
    )

    observation_b = await repository.create_observation(
        ObservationCreate(
            entity_id=UUID(str(entity_b["id"])),
            property_name="status",
            observation_kind=ObservationKind.SOURCE_FACT,
            value={"status": "private-b"},
            visibility=Visibility.TENANT,
            source_record=SourceRecordInput(
                namespace="phase-3-tenant-b",
                external_id=f"observation-{uuid4()}",
                source_type="demo",
                provenance={"scenario": "tenant-b-observation"},
            ),
        ),
        principal_b,
    )
    claim_b = await repository.create_claim(
        ClaimCreate(
            entity_id=UUID(str(entity_b["id"])),
            claim_type="derived_claim",
            statement="Tenant B private claim",
            visibility=Visibility.TENANT,
            source_record=SourceRecordInput(
                namespace="phase-3-tenant-b",
                external_id=f"claim-{uuid4()}",
                source_type="demo",
                provenance={"scenario": "tenant-b-claim"},
            ),
            observation_id=observation_b["id"],
        ),
        principal_b,
    )

    with pytest.raises(Exception):
        await repository.get_claim_lineage(UUID(str(claim_b["id"])), principal_a)

    with pytest.raises(Exception):
        await repository.link_evidence(
            UUID(str(claim_b["id"])),
            EvidenceLinkCreate(
                observation_id=observation_b["id"],
                relation_type="supporting",
                metadata={"unauthorized": True},
                visibility=Visibility.TENANT,
            ),
            principal_a,
        )

    tenant_b_claims = await repository.list_claims(UUID(str(entity_b["id"])), principal_b)
    assert any(item["id"] == claim_b["id"] for item in tenant_b_claims["items"])

    tenant_a_claims = await repository.list_claims(UUID(str(entity_b["id"])), principal_a)
    assert tenant_a_claims["items"] == []

    tenant_a_entity = await repository.get_entity(UUID(str(entity_a["id"])), principal_a)
    assert tenant_a_entity["id"] == entity_a["id"]

    with pytest.raises(Exception):
        await repository.get_entity(UUID(str(entity_b["id"])), principal_a)

    global_source = SourceRecordInput(
        namespace="phase-4-visibility",
        external_id=f"shared-entity-{uuid4()}",
        source_type="demo",
        provenance={"scenario": "temporal-tenant-isolation"},
    )
    shared_entity = await repository.create_entity(
        CanonicalEntityCreate(
            entity_type=EntityType.TARGET,
            preferred_name=f"Shared temporal target {uuid4()}",
            visibility=Visibility.GLOBAL,
            source_record=global_source,
        ),
        principal_a,
    )

    async def create_scoped_claim(principal, visibility: Visibility, scope: str) -> dict:
        return await repository.create_claim(
            ClaimCreate(
                entity_id=UUID(str(shared_entity["id"])),
                claim_type="source_fact",
                statement=f"{scope} temporal claim",
                visibility=visibility,
                valid_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
                source_record=SourceRecordInput(
                    namespace="phase-4-visibility",
                    external_id=f"{scope}-{uuid4()}",
                    source_type="demo",
                    published_at=datetime(2019, 6, 1, tzinfo=timezone.utc),
                    provenance={"scope": scope},
                ),
            ),
            principal,
        )

    public_claim = await create_scoped_claim(principal_a, Visibility.GLOBAL, "public")
    private_claim_a = await create_scoped_claim(principal_a, Visibility.TENANT, "tenant-a")
    private_claim_b = await create_scoped_claim(principal_b, Visibility.TENANT, "tenant-b")
    future_cutoff = datetime(2100, 1, 1, tzinfo=timezone.utc)
    claims_as_a = await repository.list_claims(UUID(str(shared_entity["id"])), principal_a, as_of=future_cutoff)
    claims_as_b = await repository.list_claims(UUID(str(shared_entity["id"])), principal_b, as_of=future_cutoff)
    unscoped = CanonicalPrincipal(None, None, frozenset(), frozenset())
    claims_unscoped = await repository.list_claims(
        UUID(str(shared_entity["id"])), unscoped, as_of=future_cutoff
    )

    assert {row["id"] for row in claims_as_a["items"]} == {
        public_claim["id"], private_claim_a["id"]
    }
    assert {row["id"] for row in claims_as_b["items"]} == {
        public_claim["id"], private_claim_b["id"]
    }
    assert {row["id"] for row in claims_unscoped["items"]} == {public_claim["id"]}


def test_temporal_source_timestamps_require_timezone():
    with pytest.raises(ValidationError):
        SourceRecordInput(
            namespace="phase-4-naive-time",
            external_id="naive-publication",
            source_type="publication",
            published_at=datetime(2019, 6, 1),
        )


@pytest.mark.asyncio
async def test_as_of_api_requires_timezone_and_accepts_rfc3339(monkeypatch):
    received = []
    monkeypatch.setattr(canonical_router, "_require_store", lambda: None)

    async def list_claims(entity_id, principal, page=1, page_size=20, as_of=None):
        received.append(as_of)
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    monkeypatch.setattr(canonical_router.repository, "list_claims", list_claims)
    entity_id = uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://kg.test") as client:
        missing = await client.get(f"/api/v1/canonical/entities/{entity_id}/claims")
        offset = await client.get(
            f"/api/v1/canonical/entities/{entity_id}/claims",
            params={"as_of": "2021-02-01T02:00:00+02:00"},
        )
        malformed = await client.get(
            f"/api/v1/canonical/entities/{entity_id}/claims",
            params={"as_of": "not-a-timestamp"},
        )
        naive = await client.get(
            f"/api/v1/canonical/entities/{entity_id}/claims",
            params={"as_of": "2021-02-01T00:00:00"},
        )

    assert missing.status_code == 200
    assert received[0] is None
    assert offset.status_code == 200
    assert received[1].utcoffset() == timedelta(hours=2)
    assert malformed.status_code == 422
    assert naive.status_code == 422

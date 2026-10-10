from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

import asyncpg
import pytest
import pytest_asyncio

from app.core.canonical_security import CanonicalPrincipal
from app.database.canonical_store import CanonicalStore
from app.schemas.canonical import (
    CanonicalEntityCreate,
    EntityType,
    ExclusivityState,
    IdentifierInput,
    IPEntityIdentifierRef,
    IPReferenceRole,
    LicensingEventIngest,
    LicensingEventType,
    Modality,
    PatentRecordIngest,
    SourceRecordInput,
    Visibility,
)
from app.services.canonical_repository import CanonicalRepository

TEST_DATABASE_URL = os.getenv("KG_TEST_DATABASE_URL")


def _admin_url(database_url: str) -> str:
    parts = urlsplit(database_url)
    return urlunsplit((parts.scheme, parts.netloc, "/postgres", parts.query, parts.fragment))


@pytest_asyncio.fixture
async def ip_repository():
    if not TEST_DATABASE_URL:
        pytest.skip("set KG_TEST_DATABASE_URL to run IP PostgreSQL integration tests")
    database_name = f"ai_rxos_ip_{uuid4().hex}"
    admin = await asyncpg.connect(_admin_url(TEST_DATABASE_URL), statement_cache_size=0)
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
    finally:
        await admin.close()
    parts = urlsplit(TEST_DATABASE_URL)
    database_url = urlunsplit((parts.scheme, parts.netloc, f"/{database_name}", parts.query, parts.fragment))
    store = CanonicalStore()
    try:
        await store.initialize(database_url)
        yield store, CanonicalRepository(store)
    finally:
        await store.close()
        admin = await asyncpg.connect(_admin_url(TEST_DATABASE_URL), statement_cache_size=0)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
        finally:
            await admin.close()


def _source(namespace: str = "ip-test") -> SourceRecordInput:
    return SourceRecordInput(
        namespace=namespace,
        external_id=str(uuid4()),
        source_type="database",
        provenance={"test": True},
    )


def _patent_payload(
    *,
    source_id: str,
    content_hash: str,
    status: str,
    title: str = "Patent title",
) -> PatentRecordIngest:
    return PatentRecordIngest(
        source_id=source_id,
        jurisdiction="us",
        title=title,
        abstract="Patent abstract text",
        publication_number=source_id,
        family_identifier="FAM-12345",
        publication_date_source="2019",
        status=status,
        applicants=["Applicant A"],
        assignees=["Assignee A"],
        inventors=["Inventor A"],
        source_url=f"https://patents.google.com/patent/{source_id}/en",
        retrieved_at=datetime.now(timezone.utc),
        content_hash=content_hash,
        raw_payload_ref=f"literature_source_snapshots:patent:{source_id}:{content_hash}",
        source_metadata={"parser_version": "test-v1"},
        query=source_id,
    )


def test_ip_models_preserve_partial_dates_and_unknown_exclusivity():
    patent = _patent_payload(
        source_id="US20240123456A1",
        content_hash="a" * 64,
        status="pending",
    )
    event = LicensingEventIngest(
        event_id="event-1",
        event_type=LicensingEventType.LICENSE_GRANTED,
        title="License announcement",
        source_name="Company IR",
        source_url="https://example.org/ir/license",
        event_date_source="2024-02",
        exclusivity=ExclusivityState.UNKNOWN,
        retrieved_at=datetime.now(timezone.utc),
        content_hash="b" * 64,
        raw_payload_ref="snapshot:licensing:event-1",
        query="event-1",
    )

    assert patent.publication_date_source == "2019"
    assert event.exclusivity == ExclusivityState.UNKNOWN
    assert event.event_date_source == "2024-02"


@pytest.mark.asyncio
async def test_ip_ingestion_identity_evidence_time_and_tenant_boundaries(ip_repository):
    store, repository = ip_repository
    organization_a = uuid4()
    organization_b = uuid4()
    principal_a = CanonicalPrincipal(uuid4(), organization_a, frozenset(), frozenset())
    principal_b = CanonicalPrincipal(uuid4(), organization_b, frozenset(), frozenset())
    patent_id = "US20240123456A1"
    first_payload = _patent_payload(
        source_id=patent_id, content_hash="a" * 64, status="filed"
    )

    first = await repository.ingest_patent_record(first_payload, principal_a)
    repeated = await repository.ingest_patent_record(first_payload, principal_a)
    assert first["canonical_entity_id"] == repeated["canonical_entity_id"]
    assert first["source_record_id"] == repeated["source_record_id"]
    assert first["family_entity_id"] == repeated["family_entity_id"]

    async with store.connection(organization_a) as connection:
        first_available = await connection.fetchval(
            "SELECT ingested_at FROM canonical.source_records WHERE id = $1",
            UUID(first["source_record_id"]),
        )
        first_observation_available = await connection.fetchval(
            """SELECT max(created_at) FROM canonical.observations
            WHERE entity_id = $1 AND source_record_id = $2""",
            UUID(first["canonical_entity_id"]), UUID(first["source_record_id"]),
        )
        entity_counts = await connection.fetchrow(
            """SELECT
                (SELECT count(*) FROM canonical.entities
                 WHERE entity_type = 'patent' AND organization_id = $1) AS patents,
                (SELECT count(*) FROM canonical.entities
                 WHERE entity_type = 'patent_family' AND organization_id = $1) AS families,
                (SELECT count(*) FROM canonical.identifiers i
                 JOIN canonical.entities e ON e.id = i.entity_id
                 WHERE e.id = $2 AND i.namespace = 'patent:us'
                   AND i.identifier_type = 'publication_number') AS patent_ids,
                (SELECT count(*) FROM canonical.claims
                 WHERE entity_id = $2 AND claim_type = 'source_fact') AS claims,
                (SELECT count(*) FROM canonical.evidence_links el
                 JOIN canonical.claims c ON c.id = el.claim_id
                 WHERE c.entity_id = $2 AND el.relation_type = 'supporting') AS evidence""",
            organization_a, UUID(first["canonical_entity_id"]),
        )
    assert entity_counts["patents"] == entity_counts["families"] == 1
    assert entity_counts["patent_ids"] == 1
    assert entity_counts["claims"] == entity_counts["evidence"] == len(first["claim_ids"])

    changed = await repository.ingest_patent_record(
        _patent_payload(
            source_id=patent_id,
            content_hash="c" * 64,
            status="granted",
            title="Updated patent title",
        ),
        principal_a,
    )
    assert changed["canonical_entity_id"] == first["canonical_entity_id"]
    async with store.connection(organization_a) as connection:
        changed_available = await connection.fetchval(
            "SELECT ingested_at FROM canonical.source_records WHERE id = $1",
            UUID(changed["source_record_id"]),
        )
    historical, _ = await repository.list_ip_entities(
        principal_a,
        entity_type=EntityType.PATENT,
        source_identifier=patent_id,
        as_of=max(first_available, first_observation_available) + timedelta(microseconds=1),
    )
    current, _ = await repository.list_ip_entities(
        principal_a,
        entity_type=EntityType.PATENT,
        source_identifier=patent_id,
        as_of=changed_available + timedelta(seconds=1),
    )
    assert [item["value"] for item in historical[0]["facts"]["status"]] == ["filed"]
    assert [item["value"] for item in current[0]["facts"]["status"]] == ["filed", "granted"]
    assert current[0]["facts"]["publication_date_source"][-1]["value"] == "2019"

    company_source = _source("ip-company")
    company = await repository.create_entity(
        CanonicalEntityCreate(
            entity_type=EntityType.COMPANY,
            preferred_name="Acme Therapeutics",
            visibility=Visibility.TENANT,
            source_record=company_source,
            identifiers=[IdentifierInput(
                namespace="company_registry",
                identifier_type="company_id",
                value="ACME-001",
                source_record=company_source,
            )],
        ),
        principal_a,
    )
    asset_source = _source("ip-asset")
    asset = await repository.create_entity(
        CanonicalEntityCreate(
            entity_type=EntityType.THERAPEUTIC_ASSET,
            preferred_name="Example Drug",
            modality=Modality.SMALL_MOLECULE,
            visibility=Visibility.TENANT,
            source_record=asset_source,
            identifiers=[IdentifierInput(
                namespace="asset_registry",
                identifier_type="asset_id",
                value="ASSET-001",
                source_record=asset_source,
            )],
        ),
        principal_a,
    )
    event_payload = LicensingEventIngest(
        event_id="deal-123",
        event_type=LicensingEventType.LICENSE_GRANTED,
        title="Acme license announcement",
        source_name="Company IR",
        source_url="https://example.org/ir/deal-123",
        event_date_source="2024-02",
        effective_date_source="2024",
        licensor_names=["Acme Therapeutics"],
        licensee_names=["Partner Ltd"],
        asset_names=["Example Drug"],
        patent_identifiers=[patent_id],
        territory=["EU"],
        exclusivity=ExclusivityState.UNKNOWN,
        entity_references=[
            IPEntityIdentifierRef(
                role=IPReferenceRole.LICENSOR,
                entity_type=EntityType.COMPANY,
                namespace="company_registry",
                identifier_type="company_id",
                value="ACME-001",
            ),
            IPEntityIdentifierRef(
                role=IPReferenceRole.ASSET,
                entity_type=EntityType.THERAPEUTIC_ASSET,
                namespace="asset_registry",
                identifier_type="asset_id",
                value="ASSET-001",
            ),
        ],
        retrieved_at=datetime.now(timezone.utc),
        content_hash="d" * 64,
        raw_payload_ref="literature_source_snapshots:licensing:deal-123",
        source_metadata={"release_type": "company_disclosure"},
        query="deal-123",
    )
    event = await repository.ingest_licensing_event(event_payload, principal_a)
    repeated_event = await repository.ingest_licensing_event(event_payload, principal_a)
    assert event["canonical_entity_id"] == repeated_event["canonical_entity_id"]
    assert {item["status"] for item in event["entity_reconciliation"]} == {"EXACT_MATCH"}
    assert event["claim_ids"] == repeated_event["claim_ids"]
    event_history, _ = await repository.list_ip_entities(
        principal_a, entity_type=EntityType.LICENSING_EVENT, source_identifier="deal-123"
    )
    assert event_history[0]["attributes"]["exclusivity"] == "unknown"
    assert event_history[0]["facts"]["event_date_source"][-1]["value"] == "2024-02"

    status_claim = UUID(changed["claim_ids"]["status"])
    lineage = await repository.get_claim_lineage(status_claim, principal_a)
    assert lineage["claim_type"] == "source_fact"
    assert lineage["supporting_evidence"]

    hidden_from_b, _ = await repository.list_ip_entities(
        principal_b, entity_type=EntityType.PATENT, source_identifier=patent_id
    )
    assert hidden_from_b == []
    assert str(company["organization_id"]) == str(organization_a)
    assert str(asset["organization_id"]) == str(organization_a)

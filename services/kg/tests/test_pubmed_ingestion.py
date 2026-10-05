from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.canonical_security import CanonicalPrincipal, get_canonical_principal
from app.main import app
from app.routers import canonical as canonical_router
from app.schemas.canonical import (
    CanonicalEntityCreate,
    ClinicalTrialIngest,
    EntityType,
    IdentifierInput,
    Modality,
    PubMedArticleIngest,
    RegulatoryEventIngest,
    SourceRecordInput,
    Visibility,
)
from app.services.canonical_repository import CanonicalNotFoundError


def _article(pmid: str, title: str = "PubMed canonical test", **overrides):
    values = {
        "pmid": pmid,
        "pmcid": "PMC123456",
        "doi": "10.1000/pubmed-test",
        "title": title,
        "abstract": "A source-backed abstract.",
        "authors": [{"fore_name": "Ada", "last_name": "Lovelace"}],
        "journal": "Journal of Canonical Tests",
        "publication_date_source": "2019 Jun",
        "retrieved_at": datetime(2024, 2, 1, tzinfo=timezone.utc),
        "source_metadata": {
            "parser": "pubmed-efetch-xml-v1",
            "content_hash": "a" * 64,
            "raw_payload_ref": f"literature_papers:pubmed:{pmid}",
            "publication_types": ["Journal Article"],
        },
        "extracted_entities": [{"text": "HER2", "type": "gene", "confidence_score": 0.5}],
        "extracted_relationships": [{"predicate": "targets", "confidence": 0.4}],
        "query": "HER2",
    }
    values.update(overrides)
    return PubMedArticleIngest(**values)


def _clinical_trial(nct_id: str | None = None, status: str = "RECRUITING", **overrides):
    nct_id = nct_id or f"NCT{uuid4().int % 100_000_000:08d}"
    values = {
        "nct_id": nct_id,
        "title": f"Clinical Trial Canonical Test {nct_id.upper()}",
        "abstract": "A source-backed trial summary.",
        "study_data": {
            "overall_status": status,
            "status_verified_date": "2025-02",
            "start_date": "2022-01",
            "completion_date": "2027",
            "phases": ["PHASE2"],
            "study_type": "INTERVENTIONAL",
            "lead_sponsor": {"name": "Example Sponsor", "class": "INDUSTRY"},
            "conditions": ["Condition A"],
            "interventions": [{"type": "DRUG", "name": "Example Drug"}],
            "primary_outcomes": [{"measure": "Outcome", "timeFrame": "12 months"}],
            "eligibility": {"eligibilityCriteria": "Adults."},
            "locations": [{"facility": "Site One"}],
        },
        "retrieved_at": datetime(2026, 1, 2, tzinfo=timezone.utc),
        "content_hash": "a" * 64,
        "source_metadata": {
            "parser": "clinicaltrials-api-v2-v1",
            "source_url": f"https://clinicaltrials.gov/study/{nct_id.upper()}",
            "api_endpoint": "https://clinicaltrials.gov/api/v2/studies",
        },
        "query": nct_id.upper(),
    }
    values.update(overrides)
    return ClinicalTrialIngest(**values)


def _regulatory_event(event_id: str | None = None, status: str = "AP", **overrides):
    event_id = event_id or f"FDA:NDA{uuid4().int % 1_000_000:06d}:1"
    values = {
        "event_id": event_id,
        "regulator": "U.S. Food and Drug Administration",
        "jurisdiction": "US",
        "event_type": "approval" if status == "AP" else "complete_response",
        "event_status": status,
        "application_number": "NDA021248",
        "application_type": "NDA",
        "submission_number": "1",
        "submission_type": "ORIG",
        "submission_class_code": "TYPE 1",
        "event_date_source": "20240115",
        "product_names": ["Example Drug"],
        "product_identifiers": [{"product_number": "001", "brand_name": "Example Drug"}],
        "active_ingredients": [{"name": "examplemab", "strength": "100MG"}],
        "sponsor_name": "Example Sponsor",
        "title": f"FDA approval {event_id}",
        "retrieved_at": datetime(2026, 1, 2, tzinfo=timezone.utc),
        "content_hash": "a" * 64,
        "source_url": "https://www.accessdata.fda.gov/",
        "source_metadata": {
            "source": "openFDA Drugs@FDA",
            "parser": "openfda-drugsfda-v1",
            "raw_source_status": status,
        },
        "raw_payload_ref": f"literature_source_snapshots:regulatory:{event_id}",
        "query": "application_number:021248",
    }
    values.update(overrides)
    return RegulatoryEventIngest(**values)


def test_clinicaltrial_ingest_normalizes_nct_case_and_rejects_invalid_identity():
    payload = _clinical_trial("nct12345678")
    assert payload.nct_id == "NCT12345678"
    with pytest.raises(ValueError, match="NCT followed by eight digits"):
        _clinical_trial("NCT1234567X")


@pytest.mark.asyncio
async def test_pubmed_ingestion_is_idempotent_and_creates_canonical_evidence(canonical_repo):
    store, repository = canonical_repo
    principal = CanonicalPrincipal(None, None, frozenset({"operator"}), frozenset())
    pmid = str(uuid4().int)[:10]
    payload = _article(pmid, title=f"PubMed canonical test {pmid}")

    first = await repository.ingest_pubmed_article(payload, principal)
    replay = await repository.ingest_pubmed_article(payload, principal)

    assert first["canonical_entity_id"] == replay["canonical_entity_id"]
    assert first["source_record_id"] == replay["source_record_id"]
    assert first["claim_id"] == replay["claim_id"]
    assert first["evidence_id"] == replay["evidence_id"]
    entity_id = UUID(first["canonical_entity_id"])
    async with store.connection(None) as connection:
        assert await connection.fetchval(
            "SELECT count(*) FROM canonical.entities WHERE id = $1", entity_id
        ) == 1
        assert await connection.fetchval(
            """SELECT count(*) FROM canonical.identifiers
            WHERE entity_id = $1 AND (
                (namespace = 'pubmed' AND identifier_type = 'pmid' AND value = $2)
                OR (namespace = 'pmc' AND identifier_type = 'pmcid' AND value = $3)
                OR (namespace = 'doi' AND identifier_type = 'doi' AND value = $4)
            )""",
            entity_id,
            pmid,
            payload.pmcid,
            payload.doi,
        ) == 3
        assert await connection.fetchval(
            "SELECT count(*) FROM canonical.observations WHERE entity_id = $1 AND source_record_id = $2",
            entity_id,
            UUID(first["source_record_id"]),
        ) == 11
        assert await connection.fetchval(
            "SELECT count(*) FROM canonical.claims WHERE id = $1 AND source_record_id = $2",
            UUID(first["claim_id"]),
            UUID(first["source_record_id"]),
        ) == 1
        assert await connection.fetchval(
            "SELECT count(*) FROM canonical.evidence_links WHERE id = $1", UUID(first["evidence_id"])
        ) == 1
        projection = await connection.fetchrow(
            """SELECT payload FROM canonical.projection_outbox
            WHERE aggregate_id = $1 AND event_type = 'entity.upserted'
            ORDER BY created_at DESC, id DESC LIMIT 1""",
            entity_id,
            )
        assert projection is not None
        projected_entity = repository._json_value(projection["payload"])
        assert projected_entity["id"] == str(entity_id)
        assert projected_entity["preferred_name"] == payload.title
        assert any(
            identifier["namespace"] == "pubmed"
            and identifier["identifier_type"] == "pmid"
            and identifier["value"] == pmid
            for identifier in projected_entity["identifiers"]
        )
    lineage = await repository.get_claim_lineage(UUID(first["claim_id"]), principal)
    assert lineage["claim_type"] == "source_fact"
    assert lineage["supporting_evidence"][0]["source_record_id"] == UUID(first["source_record_id"])
    assert lineage["observation"]["value"] == f"PubMed canonical test {pmid}"
    assert lineage["source_record"]["published_at"] is None
    assert "raw_xml" not in lineage["source_record"]["provenance"]["source_metadata"]


@pytest.mark.asyncio
async def test_pubmed_identity_and_evidence_preserve_tenant_and_public_scope(canonical_repo):
    _, repository = canonical_repo
    organization_a = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    organization_b = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    principal_a = CanonicalPrincipal(UUID("11111111-1111-1111-1111-111111111111"), organization_a, frozenset(), frozenset())
    principal_b = CanonicalPrincipal(UUID("22222222-2222-2222-2222-222222222222"), organization_b, frozenset(), frozenset())
    global_operator = CanonicalPrincipal(None, None, frozenset({"operator"}), frozenset())
    pmid = str(uuid4().int)[:10]
    tenant_payload_a = _article(pmid, title=f"Tenant A PubMed {pmid}", source_metadata={
        "parser": "pubmed-efetch-xml-v1",
        "content_hash": "b" * 64,
        "publication_types": ["Journal Article"],
    }, doi=f"10.1000/tenant-{pmid}", pmcid=f"PMC{pmid}")
    tenant_payload_b = tenant_payload_a.model_copy(update={"title": f"Tenant B PubMed {pmid}"})
    public_payload = _article(
        str(uuid4().int)[:10],
        title=f"Public PubMed {uuid4()}",
        source_metadata={
            "parser": "pubmed-efetch-xml-v1",
            "content_hash": "c" * 64,
            "publication_types": ["Journal Article"],
        },
    )

    result_a = await repository.ingest_pubmed_article(tenant_payload_a, principal_a)
    result_b = await repository.ingest_pubmed_article(tenant_payload_b, principal_b)
    public_result = await repository.ingest_pubmed_article(public_payload, global_operator)

    assert result_a["canonical_entity_id"] != result_b["canonical_entity_id"]
    assert result_a["visibility"] == result_b["visibility"] == "tenant"
    assert public_result["visibility"] == "global"
    assert (await repository.get_entity(UUID(public_result["canonical_entity_id"]), principal_a))["id"] == UUID(public_result["canonical_entity_id"])
    with pytest.raises(CanonicalNotFoundError):
        await repository.get_entity(UUID(result_b["canonical_entity_id"]), principal_a)
    with pytest.raises(CanonicalNotFoundError):
        await repository.get_entity(UUID(result_a["canonical_entity_id"]), principal_b)
    with pytest.raises(CanonicalNotFoundError):
        await repository.get_entity(UUID(result_a["canonical_entity_id"]), CanonicalPrincipal(None, None, frozenset(), frozenset()))


@pytest.mark.asyncio
async def test_pubmed_source_correction_appends_revision_and_obeys_as_of(canonical_repo):
    _, repository = canonical_repo
    principal = CanonicalPrincipal(None, None, frozenset({"operator"}), frozenset())
    pmid = str(uuid4().int)[:10]
    first_payload = _article(
        pmid,
        title=f"Source revision one {pmid}",
        source_metadata={"parser": "fixture-v1", "content_hash": "1" * 64},
    )
    corrected_payload = first_payload.model_copy(update={
        "title": f"Source revision two {pmid}",
        "source_metadata": {"parser": "fixture-v1", "content_hash": "2" * 64},
    })

    first = await repository.ingest_pubmed_article(first_payload, principal)
    corrected = await repository.ingest_pubmed_article(corrected_payload, principal)

    assert first["canonical_entity_id"] == corrected["canonical_entity_id"]
    assert first["source_record_id"] != corrected["source_record_id"]
    assert first["claim_id"] != corrected["claim_id"]
    with pytest.raises(CanonicalNotFoundError):
        await repository.get_claim_lineage(
            UUID(corrected["claim_id"]),
            principal,
            as_of=corrected_payload.retrieved_at,
        )
    historical = await repository.get_claim_lineage(
        UUID(corrected["claim_id"]),
        principal,
        as_of=datetime(2100, 1, 1, tzinfo=timezone.utc),
    )
    assert historical["observation"]["value"] == f"Source revision two {pmid}"


@pytest.mark.asyncio
async def test_clinicaltrial_ingestion_preserves_nct_identity_provenance_and_temporal_revisions(canonical_repo):
    store, repository = canonical_repo
    principal = CanonicalPrincipal(None, None, frozenset({"operator"}), frozenset())
    payload = _clinical_trial()

    first = await repository.ingest_clinical_trial(payload, principal)
    replay = await repository.ingest_clinical_trial(
        _clinical_trial(payload.nct_id.lower()), principal
    )

    assert first["canonical_entity_id"] == replay["canonical_entity_id"]
    assert first["source_record_id"] == replay["source_record_id"]
    assert first["claim_ids"] == replay["claim_ids"]
    assert first["evidence_ids"] == replay["evidence_ids"]
    entity_id = UUID(first["canonical_entity_id"])
    async with store.connection(None) as connection:
        assert await connection.fetchval(
            "SELECT count(*) FROM canonical.entities WHERE id = $1", entity_id
        ) == 1
        assert await connection.fetchval(
            """SELECT count(*) FROM canonical.identifiers
            WHERE entity_id = $1 AND namespace = 'clinicaltrials'
              AND identifier_type = 'nct_id' AND normalized_value = $2""",
            entity_id,
            payload.nct_id.lower(),
        ) == 1
        assert await connection.fetchval(
            "SELECT count(*) FROM canonical.observations WHERE entity_id = $1 AND source_record_id = $2",
            entity_id,
            UUID(first["source_record_id"]),
        ) == len(first["observation_ids"])
        assert await connection.fetchval(
            "SELECT count(*) FROM canonical.claims WHERE source_record_id = $1",
            UUID(first["source_record_id"]),
        ) == len(first["claim_ids"])
        assert await connection.fetchval(
            "SELECT count(*) FROM canonical.evidence_links WHERE claim_id = ANY($1::uuid[])",
            [UUID(value) for value in first["claim_ids"].values()],
        ) == len(first["evidence_ids"])
        projection = await connection.fetchrow(
            """SELECT payload FROM canonical.projection_outbox
            WHERE aggregate_id = $1 AND event_type = 'entity.upserted'
            ORDER BY created_at DESC, id DESC LIMIT 1""",
            entity_id,
            )
        assert projection is not None
        projected_entity = repository._json_value(projection["payload"])
        assert projected_entity["id"] == str(entity_id)
        assert projected_entity["preferred_name"] == payload.title
        assert projected_entity["attributes"]["nct_id"] == payload.nct_id

    lineage = await repository.get_claim_lineage(UUID(first["claim_ids"]["overall_status"]), principal)
    assert lineage["claim_type"] == "source_fact"
    assert lineage["observation"]["value"] == "RECRUITING"
    assert lineage["source_record"]["namespace"] == "clinicaltrials"
    assert lineage["source_record"]["content_hash"] == payload.content_hash
    assert lineage["supporting_evidence"][0]["observation_id"] == UUID(first["observation_ids"]["overall_status"])
    with pytest.raises(CanonicalNotFoundError):
        await repository.get_claim_lineage(
            UUID(first["claim_ids"]["overall_status"]),
            principal,
            as_of=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )

    updated_payload = payload.model_copy(update={
        "study_data": {**payload.study_data, "overall_status": "COMPLETED"},
        "content_hash": "b" * 64,
        "retrieved_at": datetime(2026, 2, 2, tzinfo=timezone.utc),
    })
    updated = await repository.ingest_clinical_trial(updated_payload, principal)
    assert updated["canonical_entity_id"] == first["canonical_entity_id"]
    assert updated["source_record_id"] != first["source_record_id"]
    assert updated["claim_ids"]["overall_status"] != first["claim_ids"]["overall_status"]
    current_lineage = await repository.get_claim_lineage(
        UUID(updated["claim_ids"]["overall_status"]),
        principal,
        as_of=datetime(2100, 1, 1, tzinfo=timezone.utc),
    )
    assert current_lineage["observation"]["value"] == "COMPLETED"
    current_entity = await repository.get_entity(entity_id, principal)
    assert current_entity["attributes"]["status"] == "COMPLETED"
    async with store.connection(None) as connection:
        projection_rows = await connection.fetch(
            """SELECT payload FROM canonical.projection_outbox
            WHERE aggregate_id = $1 AND event_type = 'entity.upserted'
            ORDER BY created_at DESC, id DESC LIMIT 1""",
            entity_id,
        )
        assert projection_rows
        latest_projection = repository._json_value(projection_rows[0]["payload"])
        assert latest_projection["id"] == str(entity_id)
        assert latest_projection["attributes"]["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_clinicaltrial_tenant_scope_is_preserved(canonical_repo):
    _, repository = canonical_repo
    organization_a = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    organization_b = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    principal_a = CanonicalPrincipal(UUID("11111111-1111-1111-1111-111111111111"), organization_a, frozenset(), frozenset())
    principal_b = CanonicalPrincipal(UUID("22222222-2222-2222-2222-222222222222"), organization_b, frozenset(), frozenset())
    result = await repository.ingest_clinical_trial(_clinical_trial(), principal_a)
    assert result["visibility"] == "tenant"
    entity_a = await repository.get_entity(UUID(result["canonical_entity_id"]), principal_a)
    assert entity_a["id"] == UUID(result["canonical_entity_id"])
    assert entity_a["organization_id"] == organization_a, (
        result["reconciliation"].get("status"),
        result["reconciliation"].get("tenant_id"),
        result["reconciliation"].get("match_method"),
    )
    with pytest.raises(CanonicalNotFoundError):
        await repository.get_entity(UUID(result["canonical_entity_id"]), principal_b)


@pytest.mark.asyncio
async def test_regulatory_ingestion_is_idempotent_and_preserves_temporal_revisions(canonical_repo):
    store, repository = canonical_repo
    principal = CanonicalPrincipal(None, None, frozenset({"operator"}), frozenset())
    payload = _regulatory_event(source_metadata={
        "source": "untrusted override",
        "event_id": "forged",
        "retrieved_at": "1900-01-01T00:00:00+00:00",
        "parser": "openfda-drugsfda-v1",
    })

    first = await repository.ingest_regulatory_event(payload, principal)
    replay = await repository.ingest_regulatory_event(payload, principal)
    assert first["canonical_entity_id"] == replay["canonical_entity_id"]
    assert first["source_record_id"] == replay["source_record_id"]
    assert first["observation_ids"] == replay["observation_ids"]
    assert first["claim_ids"] == replay["claim_ids"]
    assert first["evidence_ids"] == replay["evidence_ids"]
    assert first["asset_reconciliation"][0]["status"] == "UNRESOLVED"

    entity_id = UUID(first["canonical_entity_id"])
    source_record_id = UUID(first["source_record_id"])
    async with store.connection(None) as connection:
        assert await connection.fetchval(
            "SELECT count(*) FROM canonical.entities WHERE id = $1", entity_id
        ) == 1
        assert await connection.fetchval(
            """SELECT count(*) FROM canonical.identifiers
            WHERE entity_id = $1 AND namespace = 'fda'
              AND identifier_type = 'submission_event' AND value = $2""",
            entity_id,
            payload.event_id,
        ) == 1
        assert await connection.fetchval(
            "SELECT count(*) FROM canonical.observations WHERE entity_id = $1 AND source_record_id = $2",
            entity_id,
            source_record_id,
        ) == len(first["observation_ids"])
        assert await connection.fetchval(
            "SELECT count(*) FROM canonical.claims WHERE source_record_id = $1",
            source_record_id,
        ) == len(first["claim_ids"])
        assert await connection.fetchval(
            "SELECT count(*) FROM canonical.evidence_links WHERE claim_id = ANY($1::uuid[])",
            [UUID(value) for value in first["claim_ids"].values()],
        ) == len(first["evidence_ids"])
        first_available_at = await connection.fetchval(
            """SELECT created_at FROM canonical.observations
            WHERE id = $1""",
            UUID(first["observation_ids"]["event_status"]),
        )
        projection = await connection.fetchrow(
            """SELECT payload FROM canonical.projection_outbox
            WHERE aggregate_id = $1 AND event_type = 'entity.upserted'
            ORDER BY created_at DESC, id DESC LIMIT 1""",
            entity_id,
            )
        assert projection is not None
        projected_entity = repository._json_value(projection["payload"])
        assert projected_entity["id"] == str(entity_id)
        assert projected_entity["preferred_name"] == payload.title
        assert projected_entity["attributes"]["event_status"] == payload.event_status

    lineage = await repository.get_claim_lineage(
        UUID(first["claim_ids"]["event_status"]), principal
    )
    assert lineage["claim_type"] == "source_fact"
    assert lineage["observation"]["value"] == "AP"
    assert lineage["source_record"]["namespace"] == "fda_drugsfda"
    assert lineage["source_record"]["content_hash"] == payload.content_hash
    assert lineage["source_record"]["provenance"]["source"] == payload.regulator
    assert lineage["source_record"]["provenance"]["event_id"] == payload.event_id
    assert lineage["source_record"]["provenance"]["retrieved_at"] == payload.retrieved_at.isoformat()
    assert lineage["supporting_evidence"][0]["observation_id"] == UUID(
        first["observation_ids"]["event_status"]
    )

    before_availability = await repository.list_regulatory_events(
        principal,
        event_id=payload.event_id,
        jurisdiction="US",
        event_status="AP",
        as_of=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    assert before_availability[1] == 0
    historically_known = await repository.list_regulatory_events(
        principal,
        event_id=payload.event_id,
        jurisdiction="US",
        event_status="AP",
        as_of=first_available_at + timedelta(microseconds=1),
    )
    assert historically_known[1] == 1
    assert historically_known[0][0]["facts"]["event_status"]["value"] == "AP"

    updated_payload = payload.model_copy(update={
        "event_type": "complete_response",
        "event_status": "CR",
        "event_date_source": "20260601",
        "content_hash": "b" * 64,
        "retrieved_at": datetime(2026, 6, 2, tzinfo=timezone.utc),
    })
    updated = await repository.ingest_regulatory_event(updated_payload, principal)
    assert updated["canonical_entity_id"] == first["canonical_entity_id"]
    assert updated["source_record_id"] != first["source_record_id"]
    old_snapshot = await repository.list_regulatory_events(
        principal,
        event_id=payload.event_id,
        event_status="AP",
        as_of=first_available_at + timedelta(microseconds=1),
    )
    latest_snapshot = await repository.list_regulatory_events(
        principal,
        event_id=payload.event_id,
        event_status="CR",
        as_of=datetime(2100, 1, 1, tzinfo=timezone.utc),
    )
    assert old_snapshot[1] == 1
    assert latest_snapshot[1] == 1
    assert latest_snapshot[0][0]["facts"]["event_date_source"]["value"] == "20260601"
    async with store.connection(None) as connection:
        projection = await connection.fetchrow(
            """SELECT payload FROM canonical.projection_outbox
            WHERE aggregate_id = $1 AND event_type = 'entity.upserted'
            ORDER BY created_at DESC, id DESC LIMIT 1""",
            entity_id,
        )
        assert projection is not None
        latest_projection = repository._json_value(projection["payload"])
        assert latest_projection["id"] == str(entity_id)
        assert latest_projection["attributes"]["event_status"] == "CR"


@pytest.mark.asyncio
async def test_regulatory_event_links_asset_only_by_exact_fda_product_identifier(canonical_repo):
    store, repository = canonical_repo
    principal = CanonicalPrincipal(None, None, frozenset({"operator"}), frozenset())
    asset_source = SourceRecordInput(
        namespace="test-fixture",
        external_id=f"asset:{uuid4()}",
        source_type="manual",
        provenance={"test_fixture": True},
    )
    product_number = f"{uuid4().int % 1_000_000:06d}"
    asset = await repository.create_entity(
        CanonicalEntityCreate(
            entity_type=EntityType.THERAPEUTIC_ASSET,
            preferred_name=f"Exact FDA asset {product_number}",
            modality=Modality.SMALL_MOLECULE,
            visibility=Visibility.GLOBAL,
            identifiers=[IdentifierInput(
                namespace="fda",
                identifier_type="product_number",
                value=product_number,
                source_record=asset_source,
            )],
            source_record=asset_source,
        ),
        principal,
    )
    payload = _regulatory_event(
        product_identifiers=[{"product_number": product_number, "brand_name": "Example Drug"}],
    )
    result = await repository.ingest_regulatory_event(payload, principal)
    assert result["asset_reconciliation"][0]["status"] == "EXACT_MATCH"
    assert result["asset_reconciliation"][0]["canonical_entity_id"] == str(asset["id"])
    async with store.connection(None) as connection:
        relation = await connection.fetchrow(
            """SELECT predicate, subject_entity_id, object_entity_id
            FROM canonical.relationships WHERE id = $1""",
            UUID(result["asset_reconciliation"][0]["relationship_id"]),
        )
    assert relation["predicate"] == "REGULATORY_EVENT_FOR_ASSET"
    assert relation["subject_entity_id"] == UUID(result["canonical_entity_id"])
    assert relation["object_entity_id"] == asset["id"]


@pytest.mark.asyncio
async def test_regulatory_event_tenant_scope_is_preserved(canonical_repo):
    _, repository = canonical_repo
    organization_a = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    organization_b = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    principal_a = CanonicalPrincipal(
        UUID("11111111-1111-1111-1111-111111111111"), organization_a, frozenset(), frozenset()
    )
    principal_b = CanonicalPrincipal(
        UUID("22222222-2222-2222-2222-222222222222"), organization_b, frozenset(), frozenset()
    )
    public_operator = CanonicalPrincipal(None, None, frozenset({"operator"}), frozenset())
    tenant_event = _regulatory_event()
    public_event = _regulatory_event()
    tenant_result = await repository.ingest_regulatory_event(tenant_event, principal_a)
    public_result = await repository.ingest_regulatory_event(public_event, public_operator)
    assert tenant_result["visibility"] == "tenant"
    assert public_result["visibility"] == "global"
    assert (await repository.get_entity(UUID(public_result["canonical_entity_id"]), principal_a))["id"] == UUID(
        public_result["canonical_entity_id"]
    )
    with pytest.raises(CanonicalNotFoundError):
        await repository.get_entity(UUID(tenant_result["canonical_entity_id"]), principal_b)
    visible_to_b, _ = await repository.list_regulatory_events(principal_b)
    visible_ids = {item["id"] for item in visible_to_b}
    assert UUID(tenant_result["canonical_entity_id"]) not in visible_ids
    assert UUID(public_result["canonical_entity_id"]) in visible_ids


@pytest.mark.asyncio
async def test_regulatory_history_api_filters_temporally_and_validates_pagination(
    canonical_repo,
    monkeypatch,
):
    _, repository = canonical_repo
    principal = CanonicalPrincipal(None, None, frozenset({"operator"}), frozenset())
    payload = _regulatory_event(event_id=f"FDA:NDA021248:{uuid4().hex[:8]}")
    previous_principal = app.dependency_overrides.get(get_canonical_principal)
    monkeypatch.setattr(canonical_router, "repository", repository)
    monkeypatch.setattr(canonical_router, "_require_store", lambda: None)
    app.dependency_overrides[get_canonical_principal] = lambda: principal
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            created = await client.post(
                "/api/v1/canonical/regulatory-events/ingest",
                json=payload.model_dump(mode="json"),
            )
            assert created.status_code == 200, created.text

            history = await client.get(
                "/api/v1/canonical/regulatory-events/history",
                params={
                    "event_id": payload.event_id,
                    "regulator": payload.regulator,
                    "jurisdiction": payload.jurisdiction,
                    "event_type": "approval",
                    "event_status": "AP",
                    "as_of": "2100-01-01T00:00:00Z",
                    "page": 1,
                    "page_size": 5,
                },
            )
            invalid_page_size = await client.get(
                "/api/v1/canonical/regulatory-events/history",
                params={"page_size": 101},
            )
        assert history.status_code == 200, history.text
        assert history.json()["total"] == 1
        assert history.json()["items"][0]["id"] == created.json()["canonical_entity_id"]
        assert invalid_page_size.status_code == 422
    finally:
        if previous_principal is None:
            app.dependency_overrides.pop(get_canonical_principal, None)
        else:
            app.dependency_overrides[get_canonical_principal] = previous_principal

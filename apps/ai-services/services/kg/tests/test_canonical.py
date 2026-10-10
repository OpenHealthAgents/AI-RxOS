from __future__ import annotations

import os
import json
import asyncio
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

import asyncpg
import jwt
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.core.canonical_security import CanonicalPrincipal, get_canonical_principal
from app.core.config import get_settings
from app.database.canonical_store import CanonicalStore, canonical_store
from app.routers import canonical as canonical_router
from app.schemas.canonical import (
    AliasInput,
    CanonicalEntityCreate,
    CanonicalRelationshipCreate,
    EntityType,
    IdentifierInput,
    Modality,
    ObservationCreate,
    ObservationCreate,
    ObservationKind,
    SourceRecordInput,
    Visibility,
)
from app.services.canonical_identity import normalize_identifier, normalize_name
from app.services.canonical_repository import (
    CanonicalAuthorizationError,
    CanonicalNotFoundError,
    CanonicalRepository,
)

TEST_DATABASE_URL = os.getenv("KG_TEST_DATABASE_URL")


def _admin_url(database_url: str) -> str:
    parts = urlsplit(database_url)
    return urlunsplit((parts.scheme, parts.netloc, "/postgres", parts.query, parts.fragment))


def _source(external_id: str | None = None) -> SourceRecordInput:
    return SourceRecordInput(
        namespace="ai-rxos-test",
        external_id=external_id or str(uuid4()),
        source_type="demo",
        provenance={"synthetic": True, "not_scientific_evidence": True},
    )


@pytest_asyncio.fixture
async def canonical_repo():
    if not TEST_DATABASE_URL:
        pytest.skip("set KG_TEST_DATABASE_URL to run canonical PostgreSQL integration tests")

    database_name = f"ai_rxos_canonical_{uuid4().hex}"
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


def test_name_and_identifier_normalization_are_exact_only():
    assert normalize_name("  HER2\u00a0Program ") == "her2 program"
    assert normalize_identifier(" PMID: 123 ") == "pmid: 123"
    assert normalize_identifier("doi:10.1000/Example") == "10.1000/example"
    assert normalize_identifier("https://doi.org/10.1000/Example") == "10.1000/example"
    assert normalize_name("ABC-123") != normalize_name("ABC123")


def test_asset_requires_supported_modality():
    with pytest.raises(ValidationError):
        CanonicalEntityCreate(
            entity_type=EntityType.THERAPEUTIC_ASSET,
            preferred_name="Demo asset",
            source_record=_source(),
        )
    payload = CanonicalEntityCreate(
        entity_type=EntityType.THERAPEUTIC_ASSET,
        preferred_name="Demo asset",
        modality=Modality.CELL_THERAPY,
        source_record=_source(),
    )
    assert payload.modality == Modality.CELL_THERAPY


def test_hypotheses_cannot_be_marked_verified():
    with pytest.raises(ValidationError):
        ObservationCreate(
            entity_id=uuid4(),
            property_name="target_relationship",
            observation_kind=ObservationKind.HYPOTHESIS,
            value={"synthetic": True},
            verification_state="verified",
            source_record=_source(),
        )


def test_canonical_principal_uses_verified_jwt_claims(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("JWT_SECRET", "canonical-test-secret")
    get_settings.cache_clear()
    claims = {
        "sub": "11111111-1111-1111-1111-111111111111",
        "organizationId": "22222222-2222-2222-2222-222222222222",
        "roles": ["reviewer"],
    }
    token = jwt.encode(claims, "canonical-test-secret", algorithm="HS256")
    principal = get_canonical_principal(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))
    assert principal.organization_id == UUID(claims["organizationId"])
    assert principal.can_review

    with pytest.raises(HTTPException) as invalid:
        get_canonical_principal(HTTPAuthorizationCredentials(scheme="Bearer", credentials=f"{token}x"))
    assert invalid.value.status_code == 401
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_postgres_migration_provenance_identity_and_tenant_scope(canonical_repo):
    store, repository = canonical_repo
    global_operator = CanonicalPrincipal(
        UUID("11111111-1111-1111-1111-111111111111"), None,
        frozenset({"operator", "reviewer"}), frozenset(),
    )
    migration_ids = {
        "001_canonical_data_model.sql",
        "002_decouple_auth_ownership.sql",
        "003_allow_ambiguous_names.sql",
        "004_record_verification_actor.sql",
        "005_entity_source_provenance.sql",
    }
    async with store.connection(None) as connection:
        applied = await connection.fetch(
            "SELECT migration_id FROM canonical.schema_migrations WHERE migration_id = ANY($1::text[])",
            list(migration_ids),
        )
        assert {row["migration_id"] for row in applied} == migration_ids

    suffix = str(uuid4())
    target = await repository.create_entity(
        CanonicalEntityCreate(
            entity_type=EntityType.TARGET,
            preferred_name=f"Synthetic target {suffix}",
            visibility=Visibility.GLOBAL,
            source_record=_source(f"target:{suffix}"),
            identifiers=[IdentifierInput(
                namespace="demo", identifier_type="local", value=f"T-{suffix}",
                source_record=_source(f"target-id:{suffix}"),
            )],
            aliases=[AliasInput(
                value=f"Synthetic alias {suffix}", alias_type="alias",
                source_record=_source(f"target-alias:{suffix}"),
                ), AliasInput(
                    value=f"Verified alias {suffix}", alias_type="alias",
                    verification_state="verified",
                    source_record=_source(f"verified-target-alias:{suffix}"),
                )],
        ),
        global_operator,
    )
    assert target["identifiers"][0]["value"] == f"T-{suffix}"
    assert target["created_source_record_id"]
    verified_alias = next(alias for alias in target["aliases"] if alias["value"] == f"Verified alias {suffix}")
    assert verified_alias["verified_by"] == global_operator.user_id
    assert verified_alias["verified_at"] is not None

    by_id = await repository.resolve_identifier("demo", "local", f"T-{suffix}", global_operator)
    assert by_id["status"] == "resolved"
    by_unreviewed_alias = await repository.resolve_identifier(
        "unrelated", "alias", f"Synthetic alias {suffix}", global_operator
    )
    assert by_unreviewed_alias["status"] == "unresolved"
    assert len(by_unreviewed_alias["candidates"]) == 1
    by_verified_alias = await repository.resolve_identifier(
        "unrelated", "alias", f"Verified alias {suffix}", global_operator
    )
    assert by_verified_alias["status"] == "resolved"

    asset = await repository.create_entity(
        CanonicalEntityCreate(
            entity_type=EntityType.THERAPEUTIC_ASSET,
            preferred_name=f"Synthetic asset {suffix}",
            modality=Modality.OTHER,
            lifecycle_status="preclinical-demo-only",
            visibility=Visibility.GLOBAL,
            source_record=_source(f"asset:{suffix}"),
        ),
        global_operator,
    )
    relationship = await repository.create_relationship(
        CanonicalRelationshipCreate(
            subject_entity_id=UUID(str(asset["id"])),
            predicate="TARGETS",
            object_entity_id=UUID(str(target["id"])),
            source_record=_source(f"relationship:{suffix}"),
            observation_value={"synthetic": True},
            observation_kind=ObservationKind.HYPOTHESIS,
        ),
        global_operator,
    )
    observations, total = await repository.list_observations(UUID(str(asset["id"])), global_operator)
    assert total == 2
    assert f"relationship:{suffix}" in {item["source_external_id"] for item in observations}
    assert relationship["observation_id"]
    verified_observation = await repository.create_observation(
        ObservationCreate(
            entity_id=UUID(str(asset["id"])),
            property_name="demo_review_fixture",
            observation_kind=ObservationKind.SOURCE_FACT,
            value={"synthetic": True, "scientific_claim": False},
            verification_state="verified",
            source_record=_source(f"verified-observation:{suffix}"),
        ),
        global_operator,
    )
    assert verified_observation["manually_verified_by"] == global_operator.user_id
    assert verified_observation["manually_verified_at"] is not None
    lifecycle_observations, lifecycle_count = await repository.list_observations(UUID(str(asset["id"])), global_operator)
    assert lifecycle_count == 3
    assert any(item["property_name"] == "lifecycle_status" for item in lifecycle_observations)
    async with store.pool.acquire() as connection:
        with pytest.raises(asyncpg.PostgresError, match="append-only"):
            await connection.execute(
                "UPDATE canonical.observations SET property_name = 'tampered' WHERE id = $1",
                UUID(relationship["observation_id"]),
            )

    duplicate_name = await repository.create_entity(
        CanonicalEntityCreate(
            entity_type=EntityType.TARGET,
            preferred_name=f" synthetic   target {suffix.upper()} ",
            visibility=Visibility.GLOBAL,
            source_record=_source(f"duplicate-name:{suffix}"),
        ),
        global_operator,
    )
    by_name = await repository.resolve_name(EntityType.TARGET.value, f"Synthetic target {suffix}", global_operator)
    assert by_name["status"] == "ambiguous"
    assert {str(item["id"]) for item in by_name["candidates"]} == {str(target["id"]), str(duplicate_name["id"])}

    organization_a = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    organization_b = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    tenant_a = CanonicalPrincipal(UUID("aaaaaaaa-0000-0000-0000-000000000001"), organization_a, frozenset(), frozenset())
    tenant_b = CanonicalPrincipal(UUID("bbbbbbbb-0000-0000-0000-000000000001"), organization_b, frozenset(), frozenset())
    private_relationship = await repository.create_relationship(
        CanonicalRelationshipCreate(
            subject_entity_id=UUID(str(asset["id"])),
            predicate="INTERNAL_REVIEW_NOTE",
            object_entity_id=UUID(str(target["id"])),
            visibility=Visibility.TENANT,
            source_record=_source(f"private-relationship:{suffix}"),
            observation_value={"synthetic": True, "private": True},
            observation_kind=ObservationKind.HYPOTHESIS,
        ),
        tenant_a,
    )
    private_observation = await repository.create_observation(
        ObservationCreate(
            entity_id=UUID(str(asset["id"])),
            relationship_id=UUID(private_relationship["id"]),
            visibility=Visibility.TENANT,
            property_name="private_annotation",
            observation_kind=ObservationKind.HYPOTHESIS,
            value={"synthetic": True, "private": True},
            source_record=_source(f"private-observation:{suffix}"),
        ),
        tenant_a,
    )
    private_links_a, _ = await repository.list_relationships(UUID(str(asset["id"])), tenant_a)
    private_links_b, _ = await repository.list_relationships(UUID(str(asset["id"])), tenant_b)
    assert any(item["predicate"] == "INTERNAL_REVIEW_NOTE" for item in private_links_a)
    assert not any(item["predicate"] == "INTERNAL_REVIEW_NOTE" for item in private_links_b)
    private_observations_a, _ = await repository.list_observations(UUID(str(asset["id"])), tenant_a)
    private_observations_b, _ = await repository.list_observations(UUID(str(asset["id"])), tenant_b)
    assert any(item["property_name"] == "private_annotation" for item in private_observations_a)
    assert not any(item["property_name"] == "private_annotation" for item in private_observations_b)
    assert private_observation["organization_id"] == organization_a

    private_entity = await repository.create_entity(
        CanonicalEntityCreate(
            entity_type=EntityType.THERAPEUTIC_ASSET,
            preferred_name=f"Private synthetic asset {suffix}",
            modality=Modality.OTHER,
            visibility=Visibility.TENANT,
            source_record=_source(f"private:{suffix}"),
        ),
        tenant_a,
    )
    assert private_entity["organization_id"] == organization_a
    with pytest.raises(CanonicalNotFoundError):
        await repository.get_entity(UUID(str(private_entity["id"])), tenant_b)

    claims = await asyncio.gather(
        store.claim_global_projection_events(100),
        store.claim_global_projection_events(100),
    )
    pending = [event for batch in claims for event in batch]
    assert len({event["id"] for event in pending}) == len(pending)
    assert pending
    assert all(json.loads(event["payload"])["organization_id"] is None for event in pending)
    async with store.connection(organization_a) as connection:
        private_event = await connection.fetchrow(
            """SELECT delivered_at FROM canonical.projection_outbox
            WHERE aggregate_id = $1 AND event_type = 'entity.upserted'""",
            UUID(str(private_entity["id"])),
        )
        assert private_event["delivered_at"] is None
    for event in pending:
        await store.mark_projection_delivered(event["id"])


@pytest.mark.asyncio
async def test_canonical_asset_api_create_list_and_detail(canonical_repo):
    store, repository = canonical_repo
    previous_store = canonical_router.repository.store
    previous_pool = canonical_store.pool
    canonical_router.repository.store = store
    canonical_store.pool = store.pool
    principal = CanonicalPrincipal(
        UUID("11111111-1111-1111-1111-111111111111"), None,
        frozenset({"operator"}), frozenset(),
    )
    api = FastAPI()
    api.include_router(canonical_router.router)
    api.dependency_overrides[get_canonical_principal] = lambda: principal
    suffix = str(uuid4())
    payload = {
        "entity_type": "therapeutic_asset",
        "preferred_name": f"Synthetic API asset {suffix}",
        "modality": "ADC",
        "visibility": "global",
        "source_record": {
            "namespace": "ai-rxos-test",
            "external_id": f"api-asset:{suffix}",
            "source_type": "demo",
            "provenance": {"synthetic": True},
        },
    }
    try:
        async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
            created = await client.post("/api/v1/canonical/assets", json=payload)
            assert created.status_code == 201, created.text
            entity_id = created.json()["id"]
            assert created.json()["modality"] == "ADC"

            fetched = await client.get(f"/api/v1/canonical/assets/{entity_id}")
            assert fetched.status_code == 200
            assert fetched.json()["id"] == entity_id

            page = await client.get("/api/v1/canonical/assets", params={"page": 1, "page_size": 20})
            assert page.status_code == 200
            assert any(item["id"] == entity_id for item in page.json()["items"])

            invalid_type = await client.post("/api/v1/canonical/targets", json=payload)
            assert invalid_type.status_code == 422
    finally:
        canonical_router.repository.store = previous_store
        canonical_store.pool = previous_pool


@pytest.mark.asyncio
async def test_reconciliation_engine_matches_and_safely_handles_ambiguity(canonical_repo):
    store, repository = canonical_repo
    global_operator = CanonicalPrincipal(
        UUID("11111111-1111-1111-1111-111111111111"), None,
        frozenset({"operator"}), frozenset(),
    )
    org_a = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    org_b = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    tenant_a = CanonicalPrincipal(
        UUID("11111111-1111-1111-1111-222222222222"), org_a,
        frozenset({"operator"}), frozenset(),
    )
    tenant_b = CanonicalPrincipal(
        UUID("11111111-1111-1111-1111-333333333333"), org_b,
        frozenset({"operator"}), frozenset(),
    )

    exact_target = await repository.create_entity(
        CanonicalEntityCreate(
            entity_type=EntityType.TARGET,
            preferred_name="Exact Reconciliation Target",
            visibility=Visibility.GLOBAL,
            source_record=_source("exact-target"),
            identifiers=[IdentifierInput(
                namespace="pubmed",
                identifier_type="pmid",
                value="12345678",
                source_record=_source("exact-target-id"),
            )],
        ),
        global_operator,
    )

    result = await repository.reconcile_legacy_record(
        {
            "source_type": "literature",
            "source_record_id": "legacy-1",
            "entity_type": "target",
            "tenant_id": None,
            "identifiers": [{"namespace": "pubmed", "identifier_type": "pmid", "value": "12345678"}],
            "names": ["Exact Reconciliation Target"],
            "aliases": [],
            "metadata": {},
            "source_record": _source("legacy-1"),
        },
        global_operator,
    )
    assert result["status"] == "EXACT_MATCH"
    assert str(result["canonical_entity_id"]) == str(exact_target["id"])

    second = await repository.create_entity(
        CanonicalEntityCreate(
            entity_type=EntityType.TARGET,
            preferred_name="Common Name Alias Target",
            visibility=Visibility.GLOBAL,
            source_record=_source("common-name-alias"),
            aliases=[AliasInput(value="common-name-alias", alias_type="alias", source_record=_source("alias-source"))],
        ),
        global_operator,
    )
    alias_result = await repository.reconcile_legacy_record(
        {
            "source_type": "literature",
            "source_record_id": "legacy-alias",
            "entity_type": "target",
            "tenant_id": None,
            "identifiers": [],
            "names": ["Legacy Name"],
            "aliases": ["common-name-alias"],
            "metadata": {},
            "source_record": _source("legacy-alias"),
        },
        global_operator,
    )
    assert alias_result["status"] == "POSSIBLE_MATCH"
    assert str(second["id"]) in {str(item) for item in alias_result["candidate_ids"]}

    ambiguous_a = await repository.create_entity(
        CanonicalEntityCreate(
            entity_type=EntityType.TARGET,
            preferred_name="Ambiguous Candidate One",
            visibility=Visibility.GLOBAL,
            source_record=_source("ambiguous-one"),
        ),
        global_operator,
    )
    ambiguous_b = await repository.create_entity(
        CanonicalEntityCreate(
            entity_type=EntityType.TARGET,
            preferred_name="Ambiguous Candidate Two",
            visibility=Visibility.GLOBAL,
            source_record=_source("ambiguous-two"),
        ),
        global_operator,
    )
    await repository.create_entity(
        CanonicalEntityCreate(
            entity_type=EntityType.TARGET,
            preferred_name="Ambiguous Candidate One",
            visibility=Visibility.GLOBAL,
            source_record=_source("ambiguous-three"),
        ),
        global_operator,
    )
    ambiguous_result = await repository.reconcile_legacy_record(
        {
            "source_type": "literature",
            "source_record_id": "legacy-ambiguous",
            "entity_type": "target",
            "tenant_id": None,
            "identifiers": [],
            "names": ["Ambiguous Candidate One"],
            "aliases": [],
            "metadata": {},
            "source_record": _source("legacy-ambiguous"),
        },
        global_operator,
    )
    assert ambiguous_result["status"] == "AMBIGUOUS"
    assert len(ambiguous_result["candidate_ids"]) >= 2

    unresolved = await repository.reconcile_legacy_record(
        {
            "source_type": "literature",
            "source_record_id": "legacy-unresolved",
            "entity_type": "target",
            "tenant_id": None,
            "identifiers": [],
            "names": ["Does Not Exist Anywhere In Canonical Data"],
            "aliases": [],
            "metadata": {},
            "source_record": _source("legacy-unresolved"),
        },
        global_operator,
    )
    assert unresolved["status"] == "UNRESOLVED"

    created = await repository.reconcile_legacy_record(
        {
            "source_type": "literature",
            "source_record_id": "legacy-created",
            "entity_type": "target",
            "tenant_id": None,
            "identifiers": [],
            "names": ["New Created Target"],
            "aliases": [],
            "metadata": {},
            "source_record": _source("legacy-created"),
        },
        global_operator,
        create_if_unresolved=True,
    )
    assert created["status"] == "NEW_ENTITY"
    assert created["canonical_entity_id"] is not None

    repeated = await repository.reconcile_legacy_record(
        {
            "source_type": "literature",
            "source_record_id": "legacy-created",
            "entity_type": "target",
            "tenant_id": None,
            "identifiers": [],
            "names": ["New Created Target"],
            "aliases": [],
            "metadata": {},
            "source_record": _source("legacy-created"),
        },
        global_operator,
        create_if_unresolved=True,
    )
    assert repeated["status"] == "NEW_ENTITY"
    assert str(repeated["canonical_entity_id"]) == str(created["canonical_entity_id"])

    private_entity = await repository.create_entity(
        CanonicalEntityCreate(
            entity_type=EntityType.TARGET,
            preferred_name="Private Tenant Entity",
            visibility=Visibility.TENANT,
            source_record=_source("private-entity"),
        ),
        tenant_a,
    )

    tenant_match = await repository.reconcile_legacy_record(
        {
            "source_type": "literature",
            "source_record_id": "tenant-legacy-match",
            "entity_type": "target",
            "tenant_id": str(org_a),
            "identifiers": [],
            "names": ["Private Tenant Entity"],
            "aliases": [],
            "metadata": {},
            "source_record": _source("tenant-legacy-match"),
        },
        tenant_a,
    )
    assert tenant_match["status"] == "POSSIBLE_MATCH"

    cross_tenant = await repository.reconcile_legacy_record(
        {
            "source_type": "literature",
            "source_record_id": "tenant-b-cross-check",
            "entity_type": "target",
            "tenant_id": str(org_b),
            "identifiers": [],
            "names": ["Private Tenant Entity"],
            "aliases": [],
            "metadata": {},
            "source_record": _source("tenant-b-cross-check"),
        },
        tenant_b,
    )
    assert cross_tenant["status"] == "UNRESOLVED"

    with pytest.raises(CanonicalAuthorizationError):
        await repository.reconcile_legacy_record(
            {
                "source_type": "literature",
                "source_record_id": "missing-tenant",
                "entity_type": "target",
                "tenant_id": str(org_a),
                "identifiers": [],
                "names": ["Private Tenant Entity"],
                "aliases": [],
                "metadata": {},
                "source_record": _source("missing-tenant"),
            },
            global_operator,
        )

    dry_run = await repository.reconcile_legacy_record(
        {
            "source_type": "literature",
            "source_record_id": "dry-run-legacy",
            "entity_type": "target",
            "tenant_id": None,
            "identifiers": [],
            "names": ["Dry Run Candidate"],
            "aliases": [],
            "metadata": {},
            "source_record": _source("dry-run-legacy"),
        },
        global_operator,
        dry_run=True,
    )
    assert dry_run["status"] == "UNRESOLVED"
    assert dry_run["canonical_entity_id"] is None

    stored = await repository.get_reconciliation_result("literature", "legacy-1", None, "target")
    assert stored["status"] == "EXACT_MATCH"
    assert stored["match_reason"]
    assert stored["source_record_id"] == "legacy-1"



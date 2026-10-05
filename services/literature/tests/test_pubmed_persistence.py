from __future__ import annotations

import os
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from app.core.config import Settings
from app.database.postgres import PostgresManager
from app.orchestrator.manager import IngestionOrchestrator

TEST_DATABASE_URL = os.getenv(
    "LITERATURE_TEST_DATABASE_URL", os.getenv("KG_TEST_DATABASE_URL")
)
MIGRATION_DATABASE_URL = os.getenv(
    "LITERATURE_TEST_MIGRATION_DATABASE_URL",
    os.getenv("KG_TEST_MIGRATION_DATABASE_URL"),
)


@pytest_asyncio.fixture
async def literature_db():
    if not TEST_DATABASE_URL or not MIGRATION_DATABASE_URL:
        pytest.skip(
            "set LITERATURE_TEST_DATABASE_URL (restricted runtime role) and "
            "LITERATURE_TEST_MIGRATION_DATABASE_URL (schema owner) for "
            "Literature PostgreSQL tests; KG test URL variables are fallbacks"
        )
    manager = PostgresManager()
    await manager.init_pool(Settings(
        LITERATURE_DATABASE_URL=TEST_DATABASE_URL,
        LITERATURE_MIGRATION_DATABASE_URL=MIGRATION_DATABASE_URL,
    ))
    assert await manager.ensure_schema()
    try:
        yield manager
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_pubmed_upsert_is_idempotent_and_preserves_temporal_precision(literature_db):
    tenant_id = UUID("c1111111-1111-1111-1111-111111111111")
    pmid = f"991{datetime.now(timezone.utc).strftime('%M%S%f')}"
    async with literature_db.acquire(system_scope=True) as connection:
        database_now = await connection.fetchval("SELECT transaction_timestamp()")
    first_retrieved = database_now - timedelta(seconds=1)
    second_retrieved = database_now + timedelta(seconds=1)
    initial = {
        "pmid": pmid,
        "pmcid": "PMC123456",
        "doi": "10.1000/example",
        "source_id": f"PMID:{pmid}",
        "title": "A PubMed test article",
        "abstract": "Structured abstract text",
        "authors": [{"fore_name": "Ada", "last_name": "Lovelace"}],
        "journal": "Journal of Tests",
        "publication_date": "2019 Jun",
        "metadata": {"raw_xml": "<PubmedArticle>test</PubmedArticle>", "parser": "fixture-v1"},
    }
    entities = [{"text": "HER2", "type": "gene", "confidence_score": 0.5}]
    relationships = [{"predicate": "targets", "confidence": 0.4}]
    paper_id = await literature_db.upsert_pubmed_paper(
        initial,
        organization_id=tenant_id,
        retrieved_at=first_retrieved,
        extracted_entities=entities,
        extracted_relationships=relationships,
    )
    updated = {**initial, "title": "A corrected PubMed title"}
    repeated_id = await literature_db.upsert_pubmed_paper(
        updated,
        organization_id=tenant_id,
        retrieved_at=second_retrieved,
        extracted_entities=entities,
        extracted_relationships=relationships,
    )

    try:
        async with literature_db.acquire(str(tenant_id)) as connection:
            role = await connection.fetchrow(
                "SELECT r.rolsuper, r.rolbypassrls FROM pg_roles r WHERE r.rolname = current_user"
            )
            assert role["rolsuper"] is False
            assert role["rolbypassrls"] is False
            row = await connection.fetchrow(
                """SELECT id, title, published_at, publication_date_source, retrieved_at,
                    ingested_at, source_metadata, extracted_entities
                FROM literature_papers WHERE source = 'pubmed' AND pmid = $1 AND tenant_id = $2""",
                pmid,
                tenant_id,
            )
            snapshot = await connection.fetchrow(
                """SELECT content_hash, raw_payload, retrieved_at FROM literature_source_snapshots
                WHERE source = 'pubmed' AND source_id = $1 AND tenant_id = $2""",
                f"PMID:{pmid}",
                tenant_id,
            )
            count = await connection.fetchval(
                "SELECT count(*) FROM literature_papers WHERE source = 'pubmed' AND pmid = $1 AND tenant_id = $2",
                pmid,
                tenant_id,
            )
            snapshot_count = await connection.fetchval(
                "SELECT count(*) FROM literature_source_snapshots WHERE source = 'pubmed' AND source_id = $1 AND tenant_id = $2",
                f"PMID:{pmid}",
                tenant_id,
            )
        assert paper_id == repeated_id == row["id"]
        assert count == 1
        assert row["title"] == "A corrected PubMed title"
        assert row["published_at"] is None
        assert row["publication_date_source"] == "2019 Jun"
        assert row["retrieved_at"] == second_retrieved
        assert row["ingested_at"] < row["retrieved_at"]
        source_metadata = json.loads(row["source_metadata"])
        assert "raw_xml" in source_metadata
        assert json.loads(row["extracted_entities"]) == entities
        assert snapshot_count == 1
        assert snapshot["content_hash"]
        assert "<PubmedArticle>test</PubmedArticle>" in snapshot["raw_payload"]
    finally:
        async with literature_db.acquire(str(tenant_id)) as connection:
            await connection.execute("DELETE FROM literature_papers WHERE id = $1", paper_id)
            await connection.execute(
                "DELETE FROM literature_source_snapshots WHERE source_id = $1 AND tenant_id = $2",
                f"PMID:{pmid}",
                tenant_id,
            )


@pytest.mark.asyncio
async def test_literature_job_checkpoints_survive_restart(literature_db, monkeypatch):
    from app.orchestrator import manager as manager_module

    organization_id = UUID("c2222222-2222-2222-2222-222222222222")
    job_id = UUID(int=123456789)
    regulatory_job_id = UUID(int=123456790)
    patent_job_id = UUID(int=123456791)
    checkpoint = {"page_token": "50", "completed_pmids": ["100", "101"]}
    regulatory_checkpoint = {
        "page_size": 17,
        "offset": 4,
        "completed_record_keys": ["FDA:NDA021248:1"],
        "seen_offsets": ["0"],
        "complete": False,
    }
    patent_checkpoint = {
        "page_size": 20,
        "page_token": "3:10",
        "completed_record_keys": ["US20240123456A1"],
        "seen_page_tokens": ["0:0", "1:0"],
    }
    auth_context = {
        "sub": "11111111-1111-1111-1111-111111111111",
        "organizationId": str(organization_id),
        "roles": ["researcher"],
    }
    async with literature_db.acquire(system_scope=True) as connection:
        await connection.execute(
            """INSERT INTO literature_ingestion_jobs (
                id, source, query, status, organization_id, checkpoint, auth_context
            ) VALUES ($1, 'pubmed', 'HER2', 'running', $2, $3::jsonb, $4::jsonb)""",
            job_id,
            organization_id,
            json.dumps(checkpoint),
            json.dumps(auth_context),
        )
        await connection.execute(
            """INSERT INTO literature_ingestion_jobs (
                id, source, query, status, organization_id, checkpoint, auth_context
            ) VALUES ($1, 'patent', 'US20240123456A1', 'running', $2, $3::jsonb, $4::jsonb)""",
            patent_job_id,
            organization_id,
            json.dumps(patent_checkpoint),
            json.dumps(auth_context),
        )
        await connection.execute(
            """INSERT INTO literature_ingestion_jobs (
                id, source, query, status, organization_id, checkpoint, auth_context
            ) VALUES ($1, 'regulatory', 'application_number:NDA021248', 'running', $2, $3::jsonb, $4::jsonb)""",
            regulatory_job_id,
            organization_id,
            json.dumps(regulatory_checkpoint),
            json.dumps(auth_context),
        )

    monkeypatch.setattr(manager_module, "postgres_manager", literature_db)
    restarted_orchestrator = IngestionOrchestrator()
    try:
        recovered = await restarted_orchestrator._load_job_from_db(str(job_id), str(organization_id))
        assert recovered is not None
        assert recovered.checkpoint == checkpoint
        assert recovered.auth_context == auth_context
        assert "bearer_token" not in recovered.auth_context
        assert recovered.status.value == "running"
        recovered_regulatory = await restarted_orchestrator._load_job_from_db(
            str(regulatory_job_id),
            str(organization_id),
        )
        assert recovered_regulatory is not None
        assert recovered_regulatory.checkpoint == regulatory_checkpoint
        assert recovered_regulatory.auth_context == auth_context
        assert "bearer_token" not in recovered_regulatory.auth_context
        recovered_patent = await restarted_orchestrator._load_job_from_db(
            str(patent_job_id), str(organization_id)
        )
        assert recovered_patent is not None
        assert recovered_patent.checkpoint == patent_checkpoint
        assert recovered_patent.auth_context == auth_context
    finally:
        async with literature_db.acquire(system_scope=True) as connection:
            await connection.execute(
                "DELETE FROM literature_ingestion_jobs WHERE id = ANY($1::uuid[])",
                [job_id, regulatory_job_id, patent_job_id],
            )


@pytest.mark.asyncio
async def test_clinicaltrial_source_snapshot_and_nct_row_are_idempotent(literature_db):
    tenant_id = UUID("c3333333-3333-3333-3333-333333333333")
    retrieved_at = datetime.now(timezone.utc)
    first = {
        "source_id": "NCT01234567",
        "nct_id": "NCT01234567",
        "title": "A Clinical Trial",
        "abstract": "Study summary.",
        "url": "https://clinicaltrials.gov/study/NCT01234567",
        "metadata": {
            "overall_status": "RECRUITING",
            "start_date": "2022-01",
            "source_metadata": {
                "parser": "clinicaltrials-api-v2-v1",
                "query": "NCT01234567",
                "api_endpoint": "https://clinicaltrials.gov/api/v2/studies",
            },
        },
        "raw_payload": {"protocolSection": {"statusModule": {"overallStatus": "RECRUITING"}}},
        "content_hash": "a" * 64,
    }
    replayed_id = await literature_db.upsert_clinicaltrial_record(
        first,
        organization_id=tenant_id,
        retrieved_at=retrieved_at,
    )
    repeated_id = await literature_db.upsert_clinicaltrial_record(
        first,
        organization_id=tenant_id,
        retrieved_at=retrieved_at,
    )
    corrected = {
        **first,
        "metadata": {
            **first["metadata"],
            "overall_status": "COMPLETED",
        },
        "raw_payload": {"protocolSection": {"statusModule": {"overallStatus": "COMPLETED"}}},
        "content_hash": "b" * 64,
    }
    corrected_id = await literature_db.upsert_clinicaltrial_record(
        corrected,
        organization_id=tenant_id,
        retrieved_at=retrieved_at,
    )

    try:
        async with literature_db.acquire(str(tenant_id)) as connection:
            paper_rows = await connection.fetch(
                """SELECT id, title, source_metadata, retrieved_at
                FROM literature_papers
                WHERE source = 'clinicaltrials' AND source_id = $1 AND tenant_id = $2""",
                "NCT01234567",
                tenant_id,
            )
            snapshots = await connection.fetch(
                """SELECT content_hash, raw_payload, retrieved_at
                FROM literature_source_snapshots
                WHERE source = 'clinicaltrials' AND source_id = $1 AND tenant_id = $2
                ORDER BY content_hash""",
                "NCT01234567",
                tenant_id,
            )
        assert replayed_id == repeated_id == corrected_id
        assert len(paper_rows) == 1
        assert json.loads(paper_rows[0]["source_metadata"])["overall_status"] == "COMPLETED"
        assert len(snapshots) == 2
        assert {row["content_hash"] for row in snapshots} == {"a" * 64, "b" * 64}
        assert json.loads(snapshots[0]["raw_payload"])["source_response"]["protocolSection"]
    finally:
        async with literature_db.acquire(str(tenant_id)) as connection:
            await connection.execute(
                "DELETE FROM literature_papers WHERE source = 'clinicaltrials' AND source_id = $1 AND tenant_id = $2",
                "NCT01234567",
                tenant_id,
            )
            await connection.execute(
                "DELETE FROM literature_source_snapshots WHERE source = 'clinicaltrials' AND source_id = $1 AND tenant_id = $2",
                "NCT01234567",
                tenant_id,
            )


@pytest.mark.asyncio
async def test_regulatory_source_snapshot_and_event_identity_are_idempotent(literature_db):
    tenant_id = uuid4()
    source_id = f"FDA:NDA021248:{uuid4().hex[:8]}"
    retrieved_at = datetime.now(timezone.utc)
    initial = {
        "source_id": source_id,
        "title": f"FDA submission {source_id}",
        "url": "https://www.accessdata.fda.gov/",
        "metadata": {
            "regulator": "U.S. Food and Drug Administration",
            "jurisdiction": "US",
            "event_status": "AP",
            "submission_status_date_source": "20240115",
            "source_metadata": {"parser": "openfda-drugsfda-v1"},
        },
        "raw_payload": {"application": {"application_number": "NDA021248"}, "submission": {"submission_status": "AP"}},
        "content_hash": "c" * 64,
    }
    first_id = await literature_db.upsert_regulatory_record(
        initial,
        organization_id=tenant_id,
        retrieved_at=retrieved_at,
    )
    repeated_id = await literature_db.upsert_regulatory_record(
        initial,
        organization_id=tenant_id,
        retrieved_at=retrieved_at,
    )
    corrected = {
        **initial,
        "metadata": {
            **initial["metadata"],
            "event_status": "CR",
            "submission_status_date_source": "20260601",
        },
        "raw_payload": {
            "application": {"application_number": "NDA021248"},
            "submission": {"submission_status": "CR"},
        },
        "content_hash": "d" * 64,
    }
    corrected_id = await literature_db.upsert_regulatory_record(
        corrected,
        organization_id=tenant_id,
        retrieved_at=retrieved_at,
    )

    try:
        async with literature_db.acquire(str(tenant_id)) as connection:
            records = await connection.fetch(
                """SELECT id, source_metadata, retrieved_at
                FROM literature_papers
                WHERE source = 'regulatory' AND source_id = $1 AND tenant_id = $2""",
                source_id,
                tenant_id,
            )
            snapshots = await connection.fetch(
                """SELECT content_hash, raw_payload, retrieved_at
                FROM literature_source_snapshots
                WHERE source = 'regulatory' AND source_id = $1 AND tenant_id = $2
                ORDER BY content_hash""",
                source_id,
                tenant_id,
            )
        assert first_id == repeated_id == corrected_id
        assert len(records) == 1
        assert json.loads(records[0]["source_metadata"])["event_status"] == "CR"
        assert len(snapshots) == 2
        assert {row["content_hash"] for row in snapshots} == {"c" * 64, "d" * 64}
        assert json.loads(snapshots[0]["raw_payload"])["source_response"]["submission"]
    finally:
        async with literature_db.acquire(str(tenant_id)) as connection:
            await connection.execute(
                "DELETE FROM literature_papers WHERE source = 'regulatory' AND source_id = $1 AND tenant_id = $2",
                source_id,
                tenant_id,
            )
            await connection.execute(
                "DELETE FROM literature_source_snapshots WHERE source = 'regulatory' AND source_id = $1 AND tenant_id = $2",
                source_id,
                tenant_id,
            )


@pytest.mark.asyncio
async def test_patent_source_snapshot_and_identity_are_idempotent(literature_db):
    tenant_id = uuid4()
    source_id = f"US{uuid4().hex[:12].upper()}A1"
    retrieved_at = datetime.now(timezone.utc) + timedelta(seconds=2)
    initial = {
        "source_id": source_id,
        "title": "A patent record",
        "abstract": "Structured patent abstract.",
        "authors": ["Inventor A"],
        "journal": "Google Patents",
        "published_date": "2019",
        "url": f"https://patents.google.com/patent/{source_id}/en",
        "content_hash": "e" * 64,
        "raw_payload": {"id": f"patent/{source_id}/en", "patent": {"title": "A patent record"}},
        "metadata": {
            "jurisdiction": "US",
            "publication_number": source_id,
            "publication_date_source": "2019",
            "parser_version": "google-patents-html-v1",
        },
    }
    first_id = await literature_db.upsert_patent_record(
        initial, organization_id=tenant_id, retrieved_at=retrieved_at
    )
    repeated_id = await literature_db.upsert_patent_record(
        initial, organization_id=tenant_id, retrieved_at=retrieved_at
    )
    corrected = {
        **initial,
        "metadata": {
            **initial["metadata"],
            "status": "granted",
        },
        "content_hash": "f" * 64,
    }
    corrected_id = await literature_db.upsert_patent_record(
        corrected, organization_id=tenant_id, retrieved_at=retrieved_at
    )

    try:
        async with literature_db.acquire(str(tenant_id)) as connection:
            rows = await connection.fetch(
                """SELECT id, published_at, publication_date_source, retrieved_at,
                    ingested_at, source_metadata
                FROM literature_papers
                WHERE source = 'patent' AND source_id = $1 AND tenant_id = $2""",
                source_id,
                tenant_id,
            )
            snapshots = await connection.fetch(
                """SELECT content_hash, raw_payload
                FROM literature_source_snapshots
                WHERE source = 'patent' AND source_id = $1 AND tenant_id = $2
                ORDER BY content_hash""",
                source_id,
                tenant_id,
            )
        assert first_id == repeated_id == corrected_id
        assert len(rows) == 1
        assert rows[0]["published_at"] is None
        assert rows[0]["publication_date_source"] == "2019"
        assert rows[0]["retrieved_at"] == retrieved_at
        assert rows[0]["ingested_at"] < rows[0]["retrieved_at"]
        assert json.loads(rows[0]["source_metadata"])["status"] == "granted"
        assert len(snapshots) == 2
        assert {row["content_hash"] for row in snapshots} == {"e" * 64, "f" * 64}
        snapshot = json.loads(snapshots[0]["raw_payload"])
        assert snapshot["normalized_record"]["title"] == "A patent record"
        assert snapshot["source_response"]["patent"]["title"] == "A patent record"
    finally:
        async with literature_db.acquire(str(tenant_id)) as connection:
            await connection.execute(
                "DELETE FROM literature_papers WHERE source = 'patent' AND source_id = $1 AND tenant_id = $2",
                source_id,
                tenant_id,
            )
            await connection.execute(
                "DELETE FROM literature_source_snapshots WHERE source = 'patent' AND source_id = $1 AND tenant_id = $2",
                source_id,
                tenant_id,
            )

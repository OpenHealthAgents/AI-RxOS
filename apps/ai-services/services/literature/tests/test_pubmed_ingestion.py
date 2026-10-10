from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import jwt
import pytest

from app.core.config import Settings
from app.orchestrator.manager import IngestionJob
from app.services.pubmed_ingestion import PubMedIngestionProcessor


class FakeConnector:
    def __init__(self, records, malformed_records=None):
        self.records = records
        self.malformed_records = list(malformed_records or [])
        self.last_malformed_records = []
        self.calls = []

    def fetch_page(self, query, *, page_token=None, page_size=50):
        self.calls.append(page_token)
        if page_token is None:
            self.last_malformed_records = self.malformed_records
            return self.records, "2"
        self.last_malformed_records = []
        return [], None


class FakeDatabase:
    def __init__(self):
        self.papers = {}
        self.upsert_calls = []
        self.reconciliation = []

    async def upsert_pubmed_paper(self, record, **kwargs):
        pmid = record.get("pmid")
        self.upsert_calls.append(pmid)
        self.papers.setdefault(pmid, f"paper-{pmid}")
        return self.papers[pmid]

    async def set_pubmed_reconciliation(self, pmid, **kwargs):
        self.reconciliation.append((pmid, kwargs["status"]))


class FakeNLP:
    class NER:
        def extract_entities(self, text):
            return [{"text": "HER2", "type": "gene", "confidence": 0.5}] if text else []

    ner = NER()

    def extract_relationships(self, document):
        return []


class FakeKGClient:
    def __init__(self, fail_pmid=None):
        self.fail_pmid = fail_pmid
        self.calls = []

    async def ingest_pubmed_article(self, article, *, bearer_token):
        self.calls.append((article["pmid"], bearer_token))
        if article["pmid"] == self.fail_pmid:
            self.fail_pmid = None
            raise RuntimeError("temporary canonical outage")
        return {
            "canonical_entity_id": f"entity-{article['pmid']}",
            "reconciliation": {"status": "NEW_ENTITY"},
        }


@pytest.mark.asyncio
async def test_pubmed_job_resumes_mid_page_after_restart_without_duplicate_rows():
    records = [
        {
            "pmid": "1",
            "source_id": "PMID:1",
            "title": "First article",
            "abstract": "HER2 study",
            "authors": [],
            "metadata": {"parser": "fixture", "raw_xml": "<article/>"},
        },
        {
            "pmid": "2",
            "source_id": "PMID:2",
            "title": "Second article",
            "abstract": "HER2 study",
            "authors": [],
            "metadata": {"parser": "fixture", "raw_xml": "<article/>"},
        },
    ]
    database = FakeDatabase()
    connector = FakeConnector(records)
    kg_client = FakeKGClient(fail_pmid="2")
    settings = Settings(environment="test", jwt_secret="test-secret", kg_service_url="http://kg.test")
    processor = PubMedIngestionProcessor(
        settings=settings, database=database, kg_client=kg_client, nlp=FakeNLP()
    )
    processor._connector = lambda: connector
    job = IngestionJob(
        job_id="job-1",
        source="pubmed",
        query="HER2",
        organization_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        auth_context={
            "sub": "11111111-1111-1111-1111-111111111111",
            "organizationId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "roles": ["operator"],
        },
    )
    persisted_checkpoints: list[dict[str, Any]] = []

    async def persist(current_job):
        persisted_checkpoints.append(dict(current_job.checkpoint))

    with pytest.raises(RuntimeError, match="temporary canonical outage"):
        await processor.run(job, persist)

    assert persisted_checkpoints[-1]["completed_pmids"] == ["1"]
    assert "Bearer" not in job.auth_context
    assert jwt.decode(kg_client.calls[0][1], options={"verify_signature": False})["organizationId"] == job.organization_id

    from app.orchestrator.manager import JobProgress

    restarted_job = IngestionJob(
        job_id=job.job_id,
        source=job.source,
        query=job.query,
        organization_id=job.organization_id,
        status=job.status,
        created_at=job.created_at,
        started_at=job.started_at,
        progress=JobProgress(
            total_documents=job.progress.total_documents,
            processed_documents=job.progress.processed_documents,
            failed_documents=job.progress.failed_documents,
            dead_lettered_documents=job.progress.dead_lettered_documents,
        ),
        dead_letter_count=job.dead_letter_count,
        dead_letter_items=list(job.dead_letter_items),
        checkpoint=dict(persisted_checkpoints[-1]),
        auth_context=dict(job.auth_context),
    )
    restarted_connector = FakeConnector(records)
    restarted_kg = FakeKGClient()
    restarted = PubMedIngestionProcessor(
        settings=settings, database=database, kg_client=restarted_kg, nlp=FakeNLP()
    )
    restarted._connector = lambda: restarted_connector
    await restarted.run(restarted_job, persist)

    assert restarted_connector.calls == [None, "2"]
    assert database.upsert_calls == ["1", "2", "2"]
    assert database.papers == {"1": "paper-1", "2": "paper-2"}
    assert restarted_job.progress.processed_documents == 2
    assert restarted_job.checkpoint == {"page_token": None, "completed_pmids": []}
    assert [pmid for pmid, _ in restarted_kg.calls] == ["2"]
    assert database.reconciliation == [("1", "NEW_ENTITY"), ("2", "NEW_ENTITY")]


@pytest.mark.asyncio
async def test_pubmed_malformed_records_are_dead_lettered_once_and_checkpointed():
    malformed = {
        "pmid": "broken-article",
        "raw_xml": "<PubmedArticle><PMID>broken-article</PMID></PubmedArticle>",
    }
    connector = FakeConnector([], malformed_records=[malformed])
    database = FakeDatabase()
    processor = PubMedIngestionProcessor(
        settings=Settings(environment="test", jwt_secret="test-secret"),
        database=database,
        kg_client=FakeKGClient(),
        nlp=FakeNLP(),
    )
    processor._connector = lambda: connector
    job = IngestionJob(job_id="job-malformed", source="pubmed", query="broken-article[PMID]")
    checkpoints = []

    async def interrupt_after_checkpoint(current_job):
        checkpoints.append(dict(current_job.checkpoint))
        raise RuntimeError("simulated process interruption")

    with pytest.raises(RuntimeError, match="simulated process interruption"):
        await processor.run(job, interrupt_after_checkpoint)
    assert job.progress.failed_documents == 1
    assert job.dead_letter_count == 1
    assert job.dead_letter_items[0]["source_id"] == "broken-article"
    assert checkpoints[0]["completed_pmids"] == ["broken-article"]

    retry_job = IngestionJob(
        job_id=job.job_id,
        source=job.source,
        query=job.query,
        checkpoint=dict(checkpoints[0]),
        dead_letter_count=job.dead_letter_count,
        dead_letter_items=list(job.dead_letter_items),
        progress=job.progress,
    )
    await processor.run(retry_job, lambda current_job: persist_checkpoint(current_job, checkpoints))
    assert retry_job.progress.failed_documents == 1
    assert retry_job.dead_letter_count == 1
    assert len(retry_job.dead_letter_items) == 1


async def persist_checkpoint(current_job, checkpoints):
    checkpoints.append(dict(current_job.checkpoint))

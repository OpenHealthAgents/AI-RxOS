from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib

import pytest

from app.core.config import Settings
from app.orchestrator.manager import IngestionJob
from app.services.patent_ingestion import PatentIngestionProcessor


class _FakeDatabase:
    def __init__(self):
        self.upserts: list[str] = []
        self.reconciliations: list[str] = []

    async def upsert_patent_record(self, record, **kwargs):
        self.upserts.append(record["source_id"])

    async def set_patent_reconciliation(self, source_id, **kwargs):
        self.reconciliations.append(source_id)


class _FakeKGClient:
    def __init__(self):
        self.calls: list[str] = []

    async def ingest_patent_record(self, record, **kwargs):
        self.calls.append(record["source_id"])
        return {
            "canonical_entity_id": f"canonical-{record['source_id']}",
            "reconciliation": {"status": "EXACT_MATCH"},
        }


class _FakeConnector:
    last_malformed_records: list[dict] = []

    def __init__(self, records):
        self.records = records

    def fetch_page(self, query, *, page_token=None, page_size=50):
        return self.records, None


def _record(source_id: str) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "source_id": source_id,
        "title": f"Patent {source_id}",
        "abstract": "source text",
        "url": f"https://patents.google.com/patent/{source_id}/en",
        "published_date": "2019",
        "content_hash": hashlib.sha256(source_id.encode("utf-8")).hexdigest(),
        "retrieved_at": now,
        "metadata": {
            "source_name": "Google Patents",
            "jurisdiction": source_id[:2],
            "publication_number": source_id,
            "publication_date_source": "2019",
            "parser_version": "fake-v1",
        },
    }


@pytest.mark.asyncio
async def test_patent_job_resumes_from_durable_record_checkpoint(monkeypatch):
    records = [_record("US20240123456A1"), _record("US20240123457A1")]
    database = _FakeDatabase()
    kg_client = _FakeKGClient()
    connector = _FakeConnector(records)
    processor = PatentIngestionProcessor(
        settings=Settings(jwt_secret="test-secret"),
        database=database,
        kg_client=kg_client,
    )
    monkeypatch.setattr(processor, "_connector", lambda: connector)
    job = IngestionJob(
        job_id="ip-test",
        source="patent",
        query="oncology",
        organization_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        auth_context={
            "sub": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "organization_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        },
        checkpoint={"page_size": 2},
    )
    persisted = []
    fail_after_first_save = True

    async def persist_job(current_job):
        nonlocal fail_after_first_save
        persisted.append(deepcopy(current_job))
        if current_job.progress.processed_documents == 1 and fail_after_first_save:
            fail_after_first_save = False
            raise RuntimeError("simulated worker interruption")

    with pytest.raises(RuntimeError, match="simulated worker interruption"):
        await processor.run(job, persist_job)

    resumed_job = persisted[-1]
    assert resumed_job.checkpoint["completed_record_keys"] == ["US20240123456A1"]
    assert database.upserts == ["US20240123456A1"]

    await processor.run(resumed_job, persist_job)

    assert database.upserts == ["US20240123456A1", "US20240123457A1"]
    assert database.reconciliations == ["US20240123456A1", "US20240123457A1"]
    assert kg_client.calls == ["US20240123456A1", "US20240123457A1"]
    assert resumed_job.progress.processed_documents == 2
    assert resumed_job.checkpoint["complete"] is True


@pytest.mark.asyncio
async def test_patent_job_isolates_malformed_source_record(monkeypatch):
    database = _FakeDatabase()
    kg_client = _FakeKGClient()
    connector = _FakeConnector([_record("US20240123456A1")])
    connector.last_malformed_records = [{
        "source_id": "US00000000000A1",
        "error_message": "malformed source metadata",
        "source_url": "https://patents.google.com/patent/US00000000000A1/en",
    }]
    processor = PatentIngestionProcessor(
        settings=Settings(jwt_secret="test-secret"),
        database=database,
        kg_client=kg_client,
    )
    monkeypatch.setattr(processor, "_connector", lambda: connector)
    job = IngestionJob(
        job_id="ip-malformed",
        source="patent",
        query="oncology",
        checkpoint={"page_size": 10},
    )

    async def persist_job(_):
        return None

    await processor.run(job, persist_job)

    assert job.progress.processed_documents == 1
    assert job.progress.failed_documents == 1
    assert job.progress.dead_lettered_documents == 1
    assert job.dead_letter_items[0]["source_id"] == "US00000000000A1"

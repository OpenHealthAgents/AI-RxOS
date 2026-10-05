from __future__ import annotations

import copy
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest

from app.connectors.sources import FDARegulatoryConnector
from app.core.config import Settings
from app.orchestrator.manager import IngestionJob, JobProgress
from app.services.regulatory_ingestion import RegulatoryIngestionProcessor


def _application(
    application_number: str = "NDA021248",
    submissions: list[dict] | None = None,
) -> dict:
    return {
        "application_number": application_number,
        "sponsor_name": "Example Sponsor",
        "products": [{
            "product_number": "001",
            "brand_name": "EXAMPLE DRUG",
            "reference_drug": "Yes",
            "marketing_status": "Prescription",
            "active_ingredients": [{"name": "examplemab", "strength": "100MG"}],
        }],
        "submissions": submissions if submissions is not None else [{
            "submission_type": "ORIG",
            "submission_number": "1",
            "submission_status": "AP",
            "submission_status_date": "20240115",
            "submission_class_code": "TYPE 1",
            "submission_class_code_description": "New molecular entity",
        }],
    }


def _response(payload: dict, status: int = 200) -> httpx.Response:
    request = httpx.Request("GET", "https://api.fda.gov/drug/drugsfda.json")
    return httpx.Response(status, json=payload, request=request)


def _page(applications: list[dict], total: int) -> dict:
    return {
        "meta": {"results": {"skip": 0, "limit": 2, "total": total}},
        "results": applications,
    }


def test_fda_adapter_normalizes_authoritative_submission_and_preserves_snapshot():
    connector = FDARegulatoryConnector({"requests_per_second": 0})
    application = _application()
    with patch.object(connector, "_request_page", return_value=_response(_page([application], 1))) as request:
        records, next_offset = connector.fetch_page("application_number:NDA021248", page_size=2)
    assert next_offset is None
    assert request.call_args.args[0] == {
        "limit": 2,
        "skip": 0,
        "search": "application_number:NDA021248",
    }
    record = records[0]
    metadata = record["metadata"]
    assert record["source_id"] == "FDA:NDA021248:1"
    assert metadata["event_type"] == "approval"
    assert metadata["event_status"] == "AP"
    assert metadata["jurisdiction"] == "US"
    assert metadata["submission_status_date_source"] == "20240115"
    assert metadata["products"][0]["product_number"] == "001"
    assert metadata["source_metadata"]["source"] == "openFDA Drugs@FDA"
    assert record["raw_payload"] == {
        "application": {key: value for key, value in application.items() if key != "submissions"},
        "submission": application["submissions"][0],
    }
    assert len(record["content_hash"]) == 64


def test_fda_adapter_paginates_and_isolates_malformed_submissions():
    connector = FDARegulatoryConnector({"requests_per_second": 0})
    application = _application(submissions=[
        {"submission_type": "ORIG", "submission_number": "1", "submission_status": "TA"},
        {"submission_type": "SUPPL", "submission_status": "AP"},
    ])
    with patch.object(connector, "_request_page", return_value=_response(_page([application], 4))) as request:
        records, next_offset = connector.fetch_page("sponsor_name:Example", offset=2, page_size=1)
    assert request.call_args.args[0]["skip"] == 2
    assert len(records) == 1
    assert records[0]["metadata"]["event_type"] == "tentative_approval"
    assert connector.last_malformed_records[0]["submission_index"] == 1
    assert next_offset == 3


def test_fda_adapter_rejects_empty_query_and_resumes_after_timeout():
    connector = FDARegulatoryConnector({
        "requests_per_second": 0,
        "max_retries": 1,
        "backoff_seconds": 0,
    })
    with patch.object(connector, "_request_page") as request:
        with pytest.raises(ValueError, match="query must not be empty"):
            connector.fetch_page("  ")
    request.assert_not_called()

    with patch("app.connectors.sources.httpx.Client.get", side_effect=[
        httpx.ReadTimeout("timed out"),
        _response(_page([_application()], 1)),
    ]) as request, patch("app.connectors.sources.time.sleep"):
        records, _ = connector.fetch_page("application_number:NDA021248")
    assert len(records) == 1
    assert request.call_count == 2


def test_fda_adapter_returns_final_accessible_page_and_marks_offset_limit():
    connector = FDARegulatoryConnector({"requests_per_second": 0})
    with patch.object(
        connector,
        "_request_page",
        return_value=_response(_page([_application()], 26_000)),
    ):
        records, next_offset = connector.fetch_page(
            "application_number:NDA021248", offset=25_000, page_size=100
        )
    assert len(records) == 1
    assert next_offset is None
    assert connector.last_offset_limit_reached is True


def test_fda_rate_limit_is_shared_across_connector_instances(monkeypatch):
    import app.connectors.sources as sources

    first = FDARegulatoryConnector({"requests_per_second": 1})
    second = FDARegulatoryConnector({"requests_per_second": 1})
    monkeypatch.setattr(sources, "_FDA_LAST_REQUEST", 0.0)
    with patch("app.connectors.sources.time.monotonic", return_value=100.0), patch(
        "app.connectors.sources.time.sleep"
    ) as sleep, patch(
        "app.connectors.sources.httpx.Client.get",
        return_value=_response(_page([], 0)),
    ):
        first._request_page({"search": "first"})
        second._request_page({"search": "second"})
    sleep.assert_called_once_with(1.0)


def test_fda_adapter_handles_no_matches_retries_transient_and_rejects_permanent_failure():
    connector = FDARegulatoryConnector({
        "requests_per_second": 0,
        "max_retries": 2,
        "backoff_seconds": 0,
    })
    with patch("app.connectors.sources.httpx.Client.get", return_value=_response(
        {"error": {"code": "NOT_FOUND", "message": "No matches found!"}}, status=404
    )):
        assert connector.fetch_page("brand_name:no-match") == ([], None)

    with patch("app.connectors.sources.httpx.Client.get", side_effect=[
        _response({}, status=429),
        _response({}, status=503),
        _response(_page([_application()], 1)),
    ]) as request, patch("app.connectors.sources.time.sleep"):
        records, _ = connector.fetch_page("application_number:NDA021248")
    assert records[0]["metadata"]["event_type"] == "approval"
    assert request.call_count == 3

    with patch("app.connectors.sources.httpx.Client.get", return_value=_response({}, status=403)) as request:
        with pytest.raises(httpx.HTTPStatusError):
            connector.fetch_page("application_number:NDA021248")
    assert request.call_count == 1


class _Database:
    def __init__(self) -> None:
        self.records: dict[str, dict] = {}
        self.reconciliations: dict[str, tuple[str | None, str]] = {}
        self.fail_once: str | None = None

    async def upsert_regulatory_record(self, record, *, organization_id, retrieved_at):
        if record["source_id"] == self.fail_once:
            self.fail_once = None
            raise RuntimeError("simulated database interruption")
        self.records[record["source_id"]] = record
        return uuid4()

    async def set_regulatory_reconciliation(self, source_id, **kwargs):
        self.reconciliations[source_id] = (
            kwargs["canonical_entity_id"],
            kwargs["status"],
        )


class _KGClient:
    async def ingest_regulatory_event(self, event, *, bearer_token):
        return {
            "canonical_entity_id": str(uuid4()),
            "reconciliation": {"status": "NEW_ENTITY"},
        }


def _normalized_event(event_id: str) -> dict:
    return {
        "source": "regulatory",
        "source_id": event_id,
        "title": f"FDA decision {event_id}",
        "url": "https://www.accessdata.fda.gov/",
        "content_hash": "a" * 64,
        "raw_payload": {"application": {}, "submission": {"submission_number": "1"}},
        "metadata": {
            "regulator": "U.S. Food and Drug Administration",
            "jurisdiction": "US",
            "event_id": event_id,
            "event_type": "approval",
            "event_status": "AP",
            "application_number": "NDA021248",
            "submission_number": "1",
            "products": [{"product_number": "001", "brand_name": "Example"}],
            "source_metadata": {"source": "openFDA Drugs@FDA", "parser": "test"},
        },
    }


class _PagedConnector:
    def __init__(self) -> None:
        self.last_malformed_records: list[dict] = []
        self.last_total_count = 2
        self.calls: list[int] = []

    def fetch_page(self, query, *, offset, page_size):
        self.calls.append(offset)
        if offset == 0:
            self.last_malformed_records = [
                {
                    "source_id": "malformed-app",
                    "record_index": 0,
                    "submission_index": index,
                    "error_message": "missing submission",
                    "raw_payload": {"application_number": "malformed-app"},
                }
                for index in range(2)
            ]
            return [_normalized_event("FDA:NDA021248:1")], 1
        self.last_malformed_records = []
        return [_normalized_event("FDA:NDA021248:2")], None


class _OffsetLimitedConnector(_PagedConnector):
    def __init__(self) -> None:
        super().__init__()
        self.last_total_count = 26_000
        self.last_offset_limit_reached = True
        self.last_malformed_records = []

    def fetch_page(self, query, *, offset, page_size):
        self.calls.append(offset)
        return [_normalized_event("FDA:NDA021248:LAST")], None


@pytest.mark.asyncio
async def test_regulatory_processor_checkpoints_and_resumes_after_database_failure():
    database = _Database()
    database.fail_once = "FDA:NDA021248:2"
    connector = _PagedConnector()
    processor = RegulatoryIngestionProcessor(
        settings=Settings(jwt_secret="test-secret", fda_regulatory_requests_per_second=0),
        database=database,
        kg_client=_KGClient(),
    )
    processor._connector = lambda: connector
    job = IngestionJob(
        job_id=str(uuid4()),
        source="regulatory",
        query="application_number:NDA021248",
        checkpoint={"page_size": 1},
        auth_context={"sub": "user", "roles": ["operator"]},
    )
    persisted: list[dict] = []

    async def persist(current):
        persisted.append(copy.deepcopy(current.checkpoint))

    with pytest.raises(RuntimeError, match="simulated database interruption"):
        await processor.run(job, persist)
    assert job.checkpoint["completed_record_keys"] == []
    assert job.progress.processed_documents == 1
    assert job.dead_letter_count == 2
    assert job.checkpoint["offset"] == 1
    assert set(database.records) == {"FDA:NDA021248:1"}
    assert job.dead_letter_count == 2

    resumed = IngestionJob(
        job_id=job.job_id,
        source=job.source,
        query=job.query,
        auth_context=job.auth_context,
        checkpoint=copy.deepcopy(job.checkpoint),
        progress=JobProgress(
            total_documents=job.progress.total_documents,
            processed_documents=job.progress.processed_documents,
            failed_documents=job.progress.failed_documents,
            dead_lettered_documents=job.progress.dead_lettered_documents,
        ),
        dead_letter_items=copy.deepcopy(job.dead_letter_items),
        dead_letter_count=job.dead_letter_count,
    )
    await processor.run(resumed, persist)
    assert connector.calls == [0, 1, 1]
    assert resumed.progress.processed_documents == 2
    assert resumed.dead_letter_count == 2
    assert set(database.records) == {"FDA:NDA021248:1", "FDA:NDA021248:2"}
    assert resumed.checkpoint["offset"] == 0
    assert resumed.checkpoint["complete"] is True
    assert resumed.progress.total_documents == 4
    calls_after_completion = list(connector.calls)
    await processor.run(resumed, persist)
    assert connector.calls == calls_after_completion


@pytest.mark.asyncio
async def test_regulatory_processor_fails_explicitly_after_final_accessible_offset_page():
    database = _Database()
    connector = _OffsetLimitedConnector()
    processor = RegulatoryIngestionProcessor(
        settings=Settings(jwt_secret="test-secret", fda_regulatory_requests_per_second=0),
        database=database,
        kg_client=_KGClient(),
    )
    processor._connector = lambda: connector
    job = IngestionJob(
        job_id=str(uuid4()),
        source="regulatory",
        query="application_number:NDA021248",
        checkpoint={"page_size": 100},
        auth_context={"sub": "user", "roles": ["operator"]},
    )

    async def persist(_current):
        return None

    with pytest.raises(ValueError, match="25000-record offset window"):
        await processor.run(job, persist)
    assert "FDA:NDA021248:LAST" in database.records
    assert job.checkpoint["offset"] == 0
    assert job.checkpoint["completed_record_keys"] == ["FDA:NDA021248:LAST"]
    assert job.checkpoint.get("complete") is not True

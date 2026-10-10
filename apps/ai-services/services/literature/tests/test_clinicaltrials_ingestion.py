from __future__ import annotations

import copy
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import httpx
import pytest

from app.connectors.sources import ClinicalTrialsConnector
from app.core.config import Settings
from app.orchestrator.manager import IngestionJob, JobProgress
from app.services.clinicaltrials_ingestion import ClinicalTrialsIngestionProcessor


def _study(nct_id: str = "NCT01234567", status: str = "RECRUITING") -> dict:
    return {
        "protocolSection": {
            "identificationModule": {
                "nctId": nct_id,
                "briefTitle": "A Trial",
                "officialTitle": "A Study of Therapy",
                "acronym": "AST",
                "orgStudyIdInfo": {"id": "SPONSOR-42"},
                "secondaryIdInfos": [{"id": "EUDRA-9", "type": "REGISTRY"}],
                "organization": {"fullName": "Research Network", "class": "NETWORK"},
            },
            "statusModule": {
                "overallStatus": status,
                "statusVerifiedDateStruct": {"date": "2025-02"},
                "startDateStruct": {"date": "2022-01", "type": "ACTUAL"},
                "primaryCompletionDateStruct": {"date": "2026", "type": "ESTIMATED"},
                "completionDateStruct": {"date": "2027-03-01", "type": "ESTIMATED"},
                "lastUpdateSubmitDate": "2025-03-11",
                "lastUpdatePostDateStruct": {"date": "2025-03-12"},
            },
            "descriptionModule": {
                "briefSummary": "Brief summary.",
                "detailedDescription": "Extended protocol text.",
            },
            "designModule": {
                "studyType": "INTERVENTIONAL",
                "phases": ["PHASE2"],
                "enrollmentInfo": {"count": 84, "type": "ACTUAL"},
                "designInfo": {"allocation": "RANDOMIZED"},
            },
            "sponsorCollaboratorsModule": {
                "leadSponsor": {"name": "Example Sponsor", "class": "INDUSTRY"},
                "collaborators": [{"name": "Academic Center", "class": "OTHER"}],
            },
            "conditionsModule": {"conditions": ["Condition A"], "keywords": ["marker A"]},
            "armsInterventionsModule": {
                "armGroups": [{"label": "Arm A", "type": "EXPERIMENTAL"}],
                "interventions": [{"type": "DRUG", "name": "Example Drug", "armGroupLabels": ["Arm A"]}],
            },
            "outcomesModule": {
                "primaryOutcomes": [{"measure": "Outcome", "timeFrame": "12 months"}],
                "secondaryOutcomes": [{"measure": "Safety"}],
            },
            "eligibilityModule": {
                "eligibilityCriteria": "Include adults.",
                "minimumAge": "18 Years",
                "sex": "ALL",
                "healthyVolunteers": False,
            },
            "contactsLocationsModule": {
                "locations": [{"facility": "Site One", "city": "Boston", "country": "United States"}],
            },
            "referencesModule": {
                "references": [{"pmid": "12345678", "type": "RESULT"}],
            },
        },
        "resultsSection": {"outcomeMeasuresModule": {"outcomeMeasures": [{"title": "Outcome"}]}},
    }


def _response(payload: dict, status: int = 200) -> httpx.Response:
    request = httpx.Request("GET", "https://clinicaltrials.gov/api/v2/studies")
    return httpx.Response(status, json=payload, request=request)


def test_clinicaltrials_v2_normalizes_nct_dates_and_study_metadata():
    connector = ClinicalTrialsConnector({
        "base_url": "https://example.test/api/v2/studies",
        "requests_per_second": 0,
    })
    with patch.object(connector, "_request", return_value=_response({
        "totalCount": 1,
        "studies": [_study("nct01234567")],
    })) as request:
        records, next_token = connector.fetch_page("NCT01234567", page_size=20)

    assert next_token is None
    assert request.call_args.kwargs["params"] == {
        "pageSize": 20,
        "format": "json",
        "query.id": "NCT01234567",
    }
    record = records[0]
    assert record["source_id"] == record["nct_id"] == "NCT01234567"
    assert record["title"] == "A Study of Therapy"
    assert record["metadata"]["start_date"] == "2022-01"
    assert record["metadata"]["primary_completion_date"] == "2026"
    assert record["metadata"]["completion_date"] == "2027-03-01"
    assert record["metadata"]["overall_status"] == "RECRUITING"
    assert record["metadata"]["lead_sponsor"]["name"] == "Example Sponsor"
    assert record["metadata"]["interventions"][0]["armGroupLabels"] == ["Arm A"]
    assert record["metadata"]["eligibility"]["eligibilityCriteria"] == "Include adults."
    assert record["metadata"]["locations"][0]["facility"] == "Site One"
    assert record["metadata"]["references"][0]["pmid"] == "12345678"
    assert record["metadata"]["results"]["outcomeMeasuresModule"]
    assert record["raw_payload"] == _study("nct01234567")
    assert len(record["content_hash"]) == 64


def test_clinicaltrials_pages_with_opaque_token_and_isolates_malformed_study():
    connector = ClinicalTrialsConnector({"requests_per_second": 0})
    with patch.object(connector, "_request", return_value=_response({
        "studies": [_study(), {"protocolSection": {}}],
        "nextPageToken": "opaque-next",
    })) as request:
        records, token = connector.fetch_page("oncology", page_size=2)
    assert len(records) == 1
    assert token == "opaque-next"
    assert request.call_args.kwargs["params"]["query.term"] == "oncology"
    assert connector.last_malformed_records[0]["error_message"] == "study is missing a valid NCT identifier"
    assert connector.last_malformed_records[0]["raw_payload"] == {"protocolSection": {}}

    with patch.object(connector, "_request", return_value=_response({"studies": []})) as request:
        connector.fetch_page("oncology", page_token="opaque-next", page_size=2)
    assert request.call_args.kwargs["params"]["pageToken"] == "opaque-next"


def test_clinicaltrials_retries_429_but_does_not_retry_permanent_4xx():
    connector = ClinicalTrialsConnector({
        "requests_per_second": 0,
        "max_retries": 2,
        "backoff_seconds": 0,
    })
    with patch("app.connectors.sources.httpx.Client.request", side_effect=[
        _response({}, status=429),
        _response({"studies": [_study()]}),
    ]) as request, patch("app.connectors.sources.time.sleep"):
        records, _ = connector.fetch_page("oncology")
    assert records[0]["nct_id"] == "NCT01234567"
    assert request.call_count == 2

    with patch("app.connectors.sources.httpx.Client.request", return_value=_response({}, status=404)) as request:
        with pytest.raises(httpx.HTTPStatusError):
            connector.fetch_page("oncology")
    assert request.call_count == 1

    with patch("app.connectors.sources.httpx.Client.request", return_value=_response({}, status=503)) as request, patch(
        "app.connectors.sources.time.sleep"
    ):
        with pytest.raises(httpx.HTTPStatusError):
            connector.fetch_page("oncology")
    assert request.call_count == 3

    with patch("app.connectors.sources.httpx.Client.request", side_effect=[
        httpx.ReadTimeout("request timed out"),
        _response({"studies": [_study()]}),
    ]) as request, patch("app.connectors.sources.time.sleep"):
        records, _ = connector.fetch_page("oncology")
    assert records[0]["nct_id"] == "NCT01234567"
    assert request.call_count == 2


def test_clinicaltrials_request_pacing_waits_between_calls():
    connector = ClinicalTrialsConnector({"requests_per_second": 2, "max_retries": 0})
    monotonic = iter((0.0, 0.0, 0.1, 0.5))
    fake_time = SimpleNamespace(monotonic=lambda: next(monotonic), sleep=Mock())
    with patch("app.connectors.sources.time", fake_time), patch(
        "app.connectors.sources.httpx.Client.request",
        return_value=_response({"studies": []}),
    ):
        connector._request("GET", connector.base_url)
        connector._request("GET", connector.base_url)
    fake_time.sleep.assert_called_once_with(pytest.approx(0.4))


class _Database:
    def __init__(self) -> None:
        self.upserts: dict[str, object] = {}
        self.paper_ids: dict[str, object] = {}
        self.fail_once_for: str | None = None
        self.failed = False
        self.reconciliation: dict[str, tuple[object, str]] = {}

    async def upsert_clinicaltrial_record(self, record, *, organization_id, retrieved_at):
        nct_id = record["nct_id"]
        if nct_id == self.fail_once_for and not self.failed:
            self.failed = True
            raise RuntimeError("simulated database interruption")
        self.upserts[nct_id] = record
        return self.paper_ids.setdefault(nct_id, uuid4())

    async def set_clinicaltrial_reconciliation(self, nct_id, **kwargs):
        self.reconciliation[nct_id] = (kwargs["canonical_entity_id"], kwargs["status"])


class _KGClient:
    async def ingest_clinical_trial(self, trial, *, bearer_token):
        return {
            "canonical_entity_id": str(uuid4()),
            "reconciliation": {"status": "NEW_ENTITY"},
        }


class _PagedConnector:
    def __init__(self) -> None:
        self.calls: list[str | None] = []
        self.last_total_count = 2
        self.last_malformed_records = [{
            "source_id": None,
            "error_message": "missing protocol section",
            "raw_payload": {"unexpected": True},
        }]

    def fetch_page(self, query, *, page_token, page_size):
        self.calls.append(page_token)
        self.last_malformed_records = [{
            "source_id": None,
            "error_message": "missing protocol section",
            "raw_payload": {"unexpected": True},
        }] if page_token is None else []
        if page_token is None:
            return [
                {
                    "nct_id": "NCT00000001",
                    "source_id": "NCT00000001",
                    "title": "First trial",
                    "abstract": None,
                    "url": "https://clinicaltrials.gov/study/NCT00000001",
                    "metadata": {"source_metadata": {"parser": "test"}},
                    "raw_payload": _study("NCT00000001"),
                    "content_hash": "1" * 64,
                },
                {
                    "nct_id": "NCT00000002",
                    "source_id": "NCT00000002",
                    "title": "Second trial",
                    "abstract": None,
                    "url": "https://clinicaltrials.gov/study/NCT00000002",
                    "metadata": {"source_metadata": {"parser": "test"}},
                    "raw_payload": _study("NCT00000002"),
                    "content_hash": "2" * 64,
                },
            ], "next-token"
        return [], None


@pytest.mark.asyncio
async def test_clinicaltrials_processor_resumes_checkpoint_and_deduplicates_dead_letters():
    database = _Database()
    database.fail_once_for = "NCT00000002"
    connector = _PagedConnector()
    settings = Settings(
        clinicaltrials_requests_per_second=0,
        clinicaltrials_page_size=2,
        jwt_secret="test-secret",
    )
    processor = ClinicalTrialsIngestionProcessor(settings=settings, database=database, kg_client=_KGClient())
    processor._connector = lambda: connector
    job = IngestionJob(
        job_id=str(uuid4()),
        source="clinicaltrials",
        query="oncology",
        auth_context={"sub": "user", "roles": ["operator"]},
    )
    persisted: list[dict] = []

    async def persist(current):
        persisted.append(copy.deepcopy(current.checkpoint))

    with pytest.raises(RuntimeError, match="simulated database interruption"):
        await processor.run(job, persist)
    assert set(job.checkpoint["completed_record_keys"]) == {
        job.dead_letter_items[0]["checkpoint_key"],
        "NCT00000001",
    }
    assert job.progress.processed_documents == 1
    assert job.dead_letter_count == 1

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

    assert connector.calls == [None, None, "next-token"]
    assert resumed.progress.processed_documents == 2
    assert resumed.progress.failed_documents == 1
    assert resumed.dead_letter_count == 1
    assert set(database.upserts) == {"NCT00000001", "NCT00000002"}
    assert resumed.checkpoint["page_token"] is None
    assert "__first_page__" in resumed.checkpoint["seen_page_tokens"]


@pytest.mark.asyncio
async def test_clinicaltrials_processor_fails_on_repeated_pagination_token():
    class RepeatingConnector:
        last_total_count = 0
        last_malformed_records: list[dict] = []

        def fetch_page(self, query, *, page_token, page_size):
            return [], "repeat-token"

    processor = ClinicalTrialsIngestionProcessor(
        settings=Settings(jwt_secret="test-secret", clinicaltrials_requests_per_second=0),
        database=_Database(),
        kg_client=_KGClient(),
    )
    processor._connector = RepeatingConnector
    job = IngestionJob(job_id=str(uuid4()), source="clinicaltrials", query="oncology")

    async def persist(_):
        return None

    with pytest.raises(RuntimeError, match="repeated a pagination token"):
        await processor.run(job, persist)

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport

from app.core.security import get_current_user
from app.main import app
from app.orchestrator.manager import IngestionJob, IngestionOrchestrator, JobStatus


@pytest.mark.asyncio
async def test_compute_next_run_valid_schedule():
    orch = IngestionOrchestrator()
    reference = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)

    next_run = orch._compute_next_run("*/5 * * * *", reference)

    assert next_run > reference
    assert next_run.minute % 5 == 0


@pytest.mark.asyncio
async def test_compute_next_run_invalid_schedule_raises():
    orch = IngestionOrchestrator()

    with pytest.raises(ValueError):
        orch._compute_next_run("invalid-cron")


@pytest.mark.asyncio
async def test_schedule_persists_and_starts(monkeypatch):
    orch = IngestionOrchestrator()
    job = IngestionJob(job_id="11111111-1111-1111-1111-111111111111", source="pubmed", query="cancer")

    persist = AsyncMock()
    start = AsyncMock()
    monkeypatch.setattr(orch, "_persist_job_state", persist)
    monkeypatch.setattr(orch, "start", start)

    await orch.schedule(job, "*/15 * * * *")

    assert job.status == JobStatus.SCHEDULED
    assert job.next_run_at is not None
    persist.assert_awaited_once_with(job)
    start.assert_awaited_once()
    assert orch.get_metrics()["ingestion.jobs_scheduled"] == 1


@pytest.mark.asyncio
async def test_trigger_retry_loads_db_and_enqueues_job(monkeypatch):
    orch = IngestionOrchestrator()
    job = IngestionJob(
        job_id="22222222-2222-2222-2222-222222222222",
        source="biorxiv",
        query="immunotherapy",
        status=JobStatus.FAILED,
    )

    load = AsyncMock(return_value=job)
    monkeypatch.setattr(orch, "_load_job_from_db", load)
    enqueue = Mock()
    monkeypatch.setattr(orch, "enqueue", enqueue)
    start = AsyncMock()
    monkeypatch.setattr(orch, "start", start)

    await orch.trigger_retry(job.job_id)

    assert job.status == JobStatus.QUEUED
    assert job.backoff_until is not None
    assert job.retry_count == 1
    enqueue.assert_called_once_with(job)
    start.assert_awaited_once()
    assert orch.get_metrics()["ingestion.job_retries"] == 1


@pytest.mark.asyncio
async def test_scheduler_triggers_scheduled_job_to_completion(monkeypatch):
    scheduled_orchestrator = IngestionOrchestrator()
    transitions: list[str] = []
    completed_event = asyncio.Event()
    now = datetime.now(timezone.utc)

    job_data: dict[str, Any] = {
        "id": "44444444-4444-4444-4444-444444444444",
        "source": "pubmed",
        "query": "cancer",
        "status": "scheduled",
        "created_at": now,
        "started_at": None,
        "completed_at": None,
        "schedule": "*/1 * * * *",
        "next_run_at": now,
        "documents_total": 0,
        "documents_processed": 0,
        "documents_failed": 0,
        "retry_count": 0,
        "backoff_until": None,
        "error_message": None,
        "dead_letter_count": 0,
        "dead_letter_items": json.dumps([]),
    }

    class FakeConnection:
        async def execute(self, query: str, *args: Any) -> None:
            if "INSERT INTO literature_ingestion_jobs" in query:
                job_data.update(
                    id=str(args[0]),
                    source=args[1],
                    query=args[2],
                    status=args[3],
                    created_at=args[4],
                    schedule=args[5],
                    next_run_at=args[6],
                )
                return

            if query.strip().startswith("UPDATE literature_ingestion_jobs"):
                previous_status = job_data["status"]
                job_data.update(
                    status=args[0],
                    started_at=args[1],
                    completed_at=args[2],
                    schedule=args[3],
                    next_run_at=args[4],
                    documents_total=args[5],
                    documents_processed=args[6],
                    documents_failed=args[7],
                    error_message=args[8],
                    retry_count=args[9],
                    backoff_until=args[10],
                    dead_letter_count=args[11],
                    dead_letter_items=args[12] or json.dumps([]),
                )
                if job_data["status"] != previous_status:
                    transitions.append(job_data["status"])
                if job_data["status"] == "completed":
                    completed_event.set()
                return

        async def fetchrow(self, query: str, *args: Any) -> Any:
            if "WHERE id = $1" in query:
                return job_data.copy()
            return None

        async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
            if "WHERE status = $1" in query:
                scheduled_status, cutoff = args[0], args[1]
                if (
                    job_data["status"] == scheduled_status
                    and job_data["next_run_at"] is not None
                    and job_data["next_run_at"] <= cutoff
                ):
                    return [job_data.copy()]
            return []

    @asynccontextmanager
    async def fake_acquire() -> Any:
        yield FakeConnection()

    monkeypatch.setattr("app.routers.ingestion.postgres_manager.acquire", fake_acquire)
    monkeypatch.setattr("app.orchestrator.manager.postgres_manager.acquire", fake_acquire)
    monkeypatch.setattr("app.routers.ingestion.orchestrator", scheduled_orchestrator)
    original_compute_next_run = IngestionOrchestrator._compute_next_run

    def fake_compute_next_run(self, schedule, reference=None):
        if reference is None:
            return now
        return original_compute_next_run(self, schedule, reference)

    monkeypatch.setattr(
        "app.orchestrator.manager.IngestionOrchestrator._compute_next_run",
        fake_compute_next_run,
    )
    monkeypatch.setattr(
        "app.orchestrator.manager.IngestionOrchestrator._simulate_ingestion",
        AsyncMock(return_value=None),
    )

    original_sleep = asyncio.sleep

    async def fast_sleep(duration: float, *args: Any, **kwargs: Any) -> None:
        await original_sleep(min(duration, 0.01))

    monkeypatch.setattr("app.orchestrator.manager.asyncio.sleep", fast_sleep)

    await scheduled_orchestrator.start()

    try:
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/ingestion",
                json={"source": "pubmed", "query": "cancer", "schedule": "*/1 * * * *"},
                headers={"Authorization": "Bearer fake-token"},
            )

        assert response.status_code == 202

        await asyncio.wait_for(completed_event.wait(), timeout=5)

        assert "completed" in transitions
        assert job_data["started_at"] is not None
        assert job_data["completed_at"] is not None
        assert job_data["status"] == "scheduled"
    finally:
        await scheduled_orchestrator.stop()


@asynccontextmanager
def dummy_acquire(connection):
    yield connection


class DummyConnection:
    def __init__(self, response):
        self.response = response

    async def execute(self, *args, **kwargs):
        return None

    async def fetchrow(self, *args, **kwargs):
        return self.response


@pytest.fixture(autouse=True)
def app_auth_override(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: {"sub": "test-user"}
    yield
    app.dependency_overrides.clear()


def test_start_ingestion_enqueue_route(monkeypatch):
    client = TestClient(app)
    created_at = datetime.now(timezone.utc)
    row = {
        "id": "32027b04-56f7-4d28-82c5-8cbd0177c4f4",
        "source": "pubmed",
        "query": "cancer",
        "status": "queued",
        "created_at": created_at,
        "started_at": None,
        "completed_at": None,
        "schedule": None,
        "next_run_at": None,
        "documents_total": 0,
        "documents_processed": 0,
        "documents_failed": 0,
        "retry_count": 0,
        "backoff_until": None,
        "error_message": None,
        "dead_letter_count": 0,
        "dead_letter_items": json.dumps([]),
    }

    @asynccontextmanager
    async def fake_acquire():
        yield DummyConnection(row)

    monkeypatch.setattr("app.routers.ingestion.postgres_manager.acquire", fake_acquire)
    monkeypatch.setattr("app.routers.ingestion.orchestrator.enqueue", Mock())
    monkeypatch.setattr("app.routers.ingestion.orchestrator.start", AsyncMock())

    response = client.post(
        "/api/v1/ingestion",
        json={"source": "pubmed", "query": "cancer"},
        headers={"Authorization": "Bearer fake-token"},
    )

    assert response.status_code == 202
    data = response.json()
    assert data["source"] == "pubmed"
    assert data["query"] == "cancer"
    assert data["status"] == "queued"


def test_dead_letter_items_route(monkeypatch):
    client = TestClient(app)
    dead_letter_items = [{"job_id": "33333333-3333-3333-3333-333333333333", "error_message": "failed"}]
    row = {
        "id": "33333333-3333-3333-3333-333333333333",
        "dead_letter_items": json.dumps(dead_letter_items),
    }

    @asynccontextmanager
    async def fake_acquire():
        yield DummyConnection(row)

    monkeypatch.setattr("app.routers.ingestion.postgres_manager.acquire", fake_acquire)

    response = client.get(
        "/api/v1/ingestion/33333333-3333-3333-3333-333333333333/dead-letter",
        headers={"Authorization": "Bearer fake-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"items": dead_letter_items, "total": 1}

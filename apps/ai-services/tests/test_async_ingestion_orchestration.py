from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.opportunity_engine.ingestion.orchestrator import (
    AsyncIngestionOrchestrator,
    DeadLetterQueueService,
    DeadLetterRecord,
    DeadLetterStatus,
    IngestionDataQualityValidator,
    IngestionDeduplicator,
    IngestionItem,
    IngestionPipeline,
    IngestionRetryExecutor,
    IngestionRunRecord,
    IngestionRunStatus,
    NonRetryableIngestionError,
    PipelineSchedule,
    PipelineStatus,
    QualityValidationStatus,
    RetryPolicy,
    Watermark,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def dlq_service() -> DeadLetterQueueService:
    return DeadLetterQueueService()


@pytest.fixture
def deduplicator() -> IngestionDeduplicator:
    return IngestionDeduplicator()


@pytest.fixture
def orchestrator(dlq_service: DeadLetterQueueService, deduplicator: IngestionDeduplicator) -> AsyncIngestionOrchestrator:
    return AsyncIngestionOrchestrator(dlq_service=dlq_service, deduplicator=deduplicator)


# ==============================================================================
# 1. Scheduled Ingestion Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_scheduled_ingestion_registration_and_trigger(orchestrator: AsyncIngestionOrchestrator) -> None:
    """
    Verifies that pipelines can be registered with interval schedules
    and triggered when due.
    """
    pipeline_id = "test-scheduled-pipeline"
    now = datetime.now(timezone.utc)
    due_time = now - timedelta(seconds=10)  # past due

    pipe = IngestionPipeline(
        id=pipeline_id,
        name="Scheduled Test Pipeline",
        source_name="TestSource",
        schedule=PipelineSchedule(
            interval_seconds=300,
            is_enabled=True,
            next_run_at=due_time,
        ),
        watermark=Watermark(pipeline_id=pipeline_id, updated_at=now),
    )

    items_fetched: list[str] = []

    async def mock_fetcher(watermark: datetime | None, limit: int) -> list[IngestionItem]:
        items_fetched.append("fetched")
        return [
            IngestionItem(
                item_id="SCHED-001",
                source="TestSource",
                payload={"title": "Scheduled Item Alpha", "value": 42},
                timestamp=datetime.now(timezone.utc),
            )
        ]

    orchestrator.register_pipeline(pipe, fetcher=mock_fetcher)

    # Run scheduled due
    due_runs = await orchestrator.run_scheduled_due()
    assert len(due_runs) == 1
    run = due_runs[0]
    assert run.pipeline_id == pipeline_id
    assert run.triggered_by == "SCHEDULED"
    assert run.status == IngestionRunStatus.COMPLETED
    assert run.telemetry.items_fetched == 1
    assert run.telemetry.items_succeeded == 1

    # Verify next_run_at advanced into the future
    updated_pipe = orchestrator.get_pipeline(pipeline_id)
    assert updated_pipe is not None
    assert updated_pipe.schedule.next_run_at is not None
    assert updated_pipe.schedule.next_run_at > now


# ==============================================================================
# 2. Incremental Updates & High-Watermark Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_incremental_updates_and_high_watermark_advancement(orchestrator: AsyncIngestionOrchestrator) -> None:
    """
    Verifies incremental updates:
    - High-watermark tracks last processed timestamp.
    - Subsequent runs only receive items newer than watermark.
    - Watermark only advances when items succeed.
    """
    pipeline_id = "test-incremental-pipe"
    now = datetime.now(timezone.utc)
    t0 = now - timedelta(days=2)
    t1 = now - timedelta(days=1)
    t2 = now

    pipe = IngestionPipeline(
        id=pipeline_id,
        name="Incremental Pipeline",
        source_name="IncrementalSource",
        watermark=Watermark(pipeline_id=pipeline_id, last_processed_timestamp=t0, updated_at=t0),
    )

    fetch_watermarks_passed: list[datetime | None] = []

    all_data = [
        IngestionItem(item_id="INC-1", source="IncrementalSource", payload={"title": "Historic Item 1"}, timestamp=t0),
        IngestionItem(item_id="INC-2", source="IncrementalSource", payload={"title": "New Item 2"}, timestamp=t1),
        IngestionItem(item_id="INC-3", source="IncrementalSource", payload={"title": "Newest Item 3"}, timestamp=t2),
    ]

    async def incremental_fetcher(watermark: datetime | None, limit: int) -> list[IngestionItem]:
        fetch_watermarks_passed.append(watermark)
        if watermark is None:
            return all_data
        return [item for item in all_data if item.timestamp and item.timestamp > watermark]

    orchestrator.register_pipeline(pipe, fetcher=incremental_fetcher)

    # First incremental run: watermark is t0, should fetch INC-2 and INC-3
    run1 = await orchestrator.trigger_pipeline_run(pipeline_id=pipeline_id, incremental=True)
    assert run1.status == IngestionRunStatus.COMPLETED
    assert run1.telemetry.items_fetched == 2
    assert run1.telemetry.items_succeeded == 2
    assert fetch_watermarks_passed[0] == t0

    # Verify pipeline watermark updated to t2
    updated_pipe = orchestrator.get_pipeline(pipeline_id)
    assert updated_pipe is not None
    assert updated_pipe.watermark.last_processed_timestamp == t2

    # Second incremental run: watermark is t2, no newer items
    run2 = await orchestrator.trigger_pipeline_run(pipeline_id=pipeline_id, incremental=True)
    assert run2.status == IngestionRunStatus.COMPLETED
    assert run2.telemetry.items_fetched == 0
    assert fetch_watermarks_passed[1] == t2


# ==============================================================================
# 3. Retry Policy & Exponential Backoff Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_retry_with_exponential_backoff_and_jitter() -> None:
    """
    Verifies that transient errors trigger exponential backoff retries
    and that retries succeed when service recovers.
    """
    policy = RetryPolicy(
        max_retries=3,
        initial_backoff_seconds=0.05,
        backoff_multiplier=2.0,
        max_backoff_seconds=1.0,
        jitter=False,
    )

    attempts = 0
    retry_delays: list[float] = []

    async def flaky_operation(x: int) -> int:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionResetError(f"Transient connection glitch on attempt {attempts}")
        return x * 10

    def on_retry(att: int, exc: Exception, delay: float) -> None:
        retry_delays.append(delay)

    result, retries_used = await IngestionRetryExecutor.execute_with_retry(
        flaky_operation,
        5,
        policy=policy,
        on_retry_callback=on_retry,
    )

    assert result == 50
    assert retries_used == 2
    assert attempts == 3
    assert len(retry_delays) == 2
    assert retry_delays[0] == 0.05
    assert retry_delays[1] == pytest.approx(0.10)


@pytest.mark.asyncio
async def test_non_retryable_error_aborts_immediately() -> None:
    """Verifies that NonRetryableIngestionError terminates without retrying."""
    policy = RetryPolicy(max_retries=5, initial_backoff_seconds=0.05)
    attempts = 0

    async def fatal_operation() -> None:
        nonlocal attempts
        attempts += 1
        raise NonRetryableIngestionError("Fatal unrecoverable schema corruption")

    with pytest.raises(NonRetryableIngestionError):
        await IngestionRetryExecutor.execute_with_retry(fatal_operation, policy=policy)

    assert attempts == 1  # Aborted immediately on first attempt


# ==============================================================================
# 4. Dead-Letter Handling & Replay Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_dead_letter_routing_on_retry_exhaustion_and_replay(
    orchestrator: AsyncIngestionOrchestrator,
) -> None:
    """
    Verifies:
    1. Exhausted retries route failing items to the DLQ with full diagnostic context.
    2. Items in DLQ are queryable and can be replayed.
    3. Replaying a fixed item marks the DLQ entry as REPLAYED.
    """
    pipeline_id = "test-dlq-pipe"
    now = datetime.now(timezone.utc)

    pipe = IngestionPipeline(
        id=pipeline_id,
        name="DLQ Test Pipeline",
        source_name="DLQSource",
        retry_policy=RetryPolicy(max_retries=2, initial_backoff_seconds=0.01),
        watermark=Watermark(pipeline_id=pipeline_id, updated_at=now),
    )

    fail_counter = 0

    async def flaky_processor(item: IngestionItem) -> None:
        nonlocal fail_counter
        fail_counter += 1
        if fail_counter <= 3:  # Fails for initial run (attempts: 1 initial + 2 retries = 3)
            raise TimeoutError("Database transaction lock timeout")
        # Succeeds on 4th attempt (which happens during DLQ replay)

    test_item = IngestionItem(
        item_id="POISON-001",
        source="DLQSource",
        payload={"title": "Target Therapy Trial", "dose": "50mg"},
        timestamp=now,
    )

    orchestrator.register_pipeline(pipe, processor=flaky_processor)

    # Initial Run: Fails after 2 retries -> routed to DLQ
    run = await orchestrator.trigger_pipeline_run(
        pipeline_id=pipeline_id,
        items_override=[test_item],
    )

    assert run.status == IngestionRunStatus.FAILED
    assert run.telemetry.items_failed == 1
    assert run.telemetry.items_dead_lettered == 1
    assert run.telemetry.items_retried == 2

    # Verify DLQ contains the record
    dlq_records = orchestrator.dlq.list_records(pipeline_id=pipeline_id)
    assert len(dlq_records) == 1
    dlq_entry = dlq_records[0]
    assert dlq_entry.item_id == "POISON-001"
    assert dlq_entry.failure_category == "TimeoutError"
    assert dlq_entry.status == DeadLetterStatus.PENDING
    assert dlq_entry.retry_attempts == 2
    assert dlq_entry.payload["dose"] == "50mg"

    # Replay DLQ Item: Now the processor succeeds
    replay_run = await orchestrator.replay_dead_letter(dlq_entry.id)
    assert replay_run.status == IngestionRunStatus.COMPLETED
    assert replay_run.telemetry.items_succeeded == 1

    # Verify DLQ record marked REPLAYED
    updated_dlq = orchestrator.dlq.get(dlq_entry.id)
    assert updated_dlq is not None
    assert updated_dlq.status == DeadLetterStatus.REPLAYED


# ==============================================================================
# 5. Deduplication Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_deduplication_prevents_duplicate_processing(
    orchestrator: AsyncIngestionOrchestrator,
) -> None:
    """
    Verifies that identical items submitted repeatedly are deduplicated
    via content fingerprint and not redundantly processed.
    """
    pipeline_id = "test-dedup-pipe"
    now = datetime.now(timezone.utc)

    pipe = IngestionPipeline(
        id=pipeline_id,
        name="Dedup Test Pipeline",
        source_name="DedupSource",
        watermark=Watermark(pipeline_id=pipeline_id, updated_at=now),
    )

    processed_count = 0

    async def counting_processor(item: IngestionItem) -> None:
        nonlocal processed_count
        processed_count += 1

    orchestrator.register_pipeline(pipe, processor=counting_processor)

    item1 = IngestionItem(
        item_id="PUBMED-998877",
        source="PubMed",
        payload={"title": "HER2 exon 20 mutations in NSCLC", "pmid": "998877"},
        timestamp=now,
    )

    # Run 1: First time processed
    run1 = await orchestrator.trigger_pipeline_run(
        pipeline_id=pipeline_id,
        items_override=[item1],
    )
    assert run1.status == IngestionRunStatus.COMPLETED
    assert run1.telemetry.items_processed == 1
    assert run1.telemetry.items_succeeded == 1
    assert run1.telemetry.items_deduplicated == 0
    assert processed_count == 1

    # Run 2: Exact same item -> deduplicated
    run2 = await orchestrator.trigger_pipeline_run(
        pipeline_id=pipeline_id,
        items_override=[item1],
    )
    assert run2.status == IngestionRunStatus.COMPLETED
    assert run2.telemetry.items_processed == 1
    assert run2.telemetry.items_succeeded == 0
    assert run2.telemetry.items_deduplicated == 1
    assert processed_count == 1  # Processor was NOT called again!


# ==============================================================================
# 6. Data-Quality Validation Tests
# ==============================================================================

def test_data_quality_validator_rules() -> None:
    """
    Verifies data-quality validation rules:
    - Missing mandatory fields
    - Invalid identifier syntax
    - Non-informative placeholder content
    - Distant future timestamps
    """
    # 1. Valid Item
    valid_item = IngestionItem(
        item_id="NCT04455841",
        source="ClinicalTrials.gov",
        payload={
            "nct_id": "NCT04455841",
            "title": "Phase 3 Beamion Trial of Zongertinib in HER2-mutant NSCLC",
            "phase": "Phase 3",
        },
        timestamp=datetime.now(timezone.utc),
    )
    report_valid = IngestionDataQualityValidator.validate_item(valid_item)
    assert report_valid.status == QualityValidationStatus.PASSED
    assert report_valid.score == 1.0
    assert not report_valid.has_errors

    # 2. Invalid Item (Missing title & invalid NCT formatting)
    invalid_item = IngestionItem(
        item_id="INVALID_TRIAL_ID",
        source="ClinicalTrials.gov",
        payload={"nct_id": "INVALID_TRIAL_ID", "title": "   "},
        timestamp=datetime.now(timezone.utc),
    )
    report_invalid = IngestionDataQualityValidator.validate_item(invalid_item)
    assert report_invalid.status == QualityValidationStatus.FAILED
    assert report_invalid.has_errors
    assert any("NCT" in issue.message for issue in report_invalid.issues)
    assert any("title" in issue.field for issue in report_invalid.issues)

    # 3. Temporal Sanity Violation (Date 5 years into the future)
    future_item = IngestionItem(
        item_id="NCT09999999",
        source="ClinicalTrials.gov",
        payload={"nct_id": "NCT09999999", "title": "Valid Title"},
        timestamp=datetime.now(timezone.utc) + timedelta(days=365 * 5),
    )
    report_future = IngestionDataQualityValidator.validate_item(future_item)
    assert report_future.status == QualityValidationStatus.FAILED
    assert any("future" in issue.message for issue in report_future.issues)


@pytest.mark.asyncio
async def test_strict_quality_gate_routes_directly_to_dlq(
    orchestrator: AsyncIngestionOrchestrator,
) -> None:
    """
    Verifies that items failing the data quality gate are rejected directly into DLQ
    and never sent to downstream processors.
    """
    pipeline_id = "test-quality-gate"
    now = datetime.now(timezone.utc)

    pipe = IngestionPipeline(
        id=pipeline_id,
        name="Quality Gate Test Pipeline",
        source_name="PubMed",
        quality_gate_strict=True,
        watermark=Watermark(pipeline_id=pipeline_id, updated_at=now),
    )

    processor_called = False

    async def mock_processor(item: IngestionItem) -> None:
        nonlocal processor_called
        processor_called = True

    orchestrator.register_pipeline(pipe, processor=mock_processor)

    # Bad item with empty title
    bad_item = IngestionItem(
        item_id="12345",
        source="PubMed",
        payload={"pmid": "12345", "title": "N/A"},
        timestamp=now,
    )

    run = await orchestrator.trigger_pipeline_run(
        pipeline_id=pipeline_id,
        items_override=[bad_item],
    )

    assert run.status == IngestionRunStatus.FAILED
    assert run.telemetry.items_failed == 1
    assert run.telemetry.items_dead_lettered == 1
    assert not processor_called  # Never invoked downstream processor!

    # Verify DLQ entry has QUALITY_VALIDATION_ERROR category
    dlq_records = orchestrator.dlq.list_records(pipeline_id=pipeline_id)
    assert len(dlq_records) == 1
    assert dlq_records[0].failure_category == "QUALITY_VALIDATION_ERROR"
    assert "Quality Validation Failed" in dlq_records[0].failure_reason


# ==============================================================================
# 7. Observability & Zero Silent Failures Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_no_silent_failures_on_unhandled_pipeline_crash(
    orchestrator: AsyncIngestionOrchestrator,
) -> None:
    """
    STRICT INVARIANT: No ingestion pipeline should silently fail.
    Verifies that fatal unhandled exceptions during execution mark run as FAILED,
    populate error messages, mark pipeline as ERROR, and reflect in observability health.
    """
    pipeline_id = "test-fatal-crash"
    now = datetime.now(timezone.utc)

    pipe = IngestionPipeline(
        id=pipeline_id,
        name="Crash Test Pipeline",
        source_name="CrashSource",
        watermark=Watermark(pipeline_id=pipeline_id, updated_at=now),
    )

    async def crashing_fetcher(watermark: datetime | None, limit: int) -> list[IngestionItem]:
        raise RuntimeError("Critical storage backend unmapped failure")

    orchestrator.register_pipeline(pipe, fetcher=crashing_fetcher)

    run = await orchestrator.trigger_pipeline_run(pipeline_id=pipeline_id)
    assert run.status == IngestionRunStatus.FAILED
    assert "Critical storage backend unmapped failure" in (run.error_message or "")

    # Pipeline live state must be ERROR
    crashed_pipe = orchestrator.get_pipeline(pipeline_id)
    assert crashed_pipe is not None
    assert crashed_pipe.status == PipelineStatus.ERROR

    # Observability health must report DEGRADED
    health = orchestrator.get_health_status()
    assert health["status"] == "DEGRADED"
    assert pipeline_id in health["unhealthy_pipelines"]


# ==============================================================================
# 8. FastAPI Endpoints Tests
# ==============================================================================

def test_fastapi_orchestration_endpoints(client: TestClient) -> None:
    """
    Verifies FastAPI endpoints for:
    - GET /api/v1/orchestration/pipelines
    - POST /api/v1/orchestration/pipelines/{id}/trigger
    - GET /api/v1/orchestration/runs
    - GET /api/v1/orchestration/dlq
    - GET /api/v1/orchestration/observability/metrics
    - GET /api/v1/orchestration/observability/health
    """
    # 1. List pipelines
    resp_pipes = client.get("/api/v1/orchestration/pipelines")
    assert resp_pipes.status_code == 200
    pipes = resp_pipes.json()
    assert len(pipes) >= 5
    pipe_ids = [p["id"] for p in pipes]
    assert "pubmed" in pipe_ids
    assert "clinicaltrials" in pipe_ids
    assert "regulatory" in pipe_ids

    # 2. Trigger a pipeline with items
    trigger_payload = {
        "incremental": True,
        "items": [
            {
                "item_id": "API-ITEM-101",
                "source": "ClinicalTrials.gov",
                "payload": {
                    "nct_id": "NCT05001122",
                    "title": "Phase 2 Evaluation of Novel Kinase Inhibitor",
                },
            }
        ],
    }
    resp_trigger = client.post("/api/v1/orchestration/pipelines/clinicaltrials/trigger", json=trigger_payload)
    assert resp_trigger.status_code == 200
    run_data = resp_trigger.json()
    assert run_data["status"] == "COMPLETED"
    assert run_data["telemetry"]["items_succeeded"] == 1
    run_id = run_data["id"]

    # 3. Query run by ID
    resp_run = client.get(f"/api/v1/orchestration/runs/{run_id}")
    assert resp_run.status_code == 200
    assert resp_run.json()["id"] == run_id

    # 4. Observability metrics
    resp_metrics = client.get("/api/v1/orchestration/observability/metrics")
    assert resp_metrics.status_code == 200
    metrics = resp_metrics.json()
    assert metrics["orchestrator_status"] == "HEALTHY"
    assert metrics["item_metrics"]["succeeded"] >= 1

    # 5. Observability health
    resp_health = client.get("/api/v1/orchestration/observability/health")
    assert resp_health.status_code == 200
    assert resp_health.json()["status"] == "HEALTHY"


# ==============================================================================
# 9. Database Migration Verification
# ==============================================================================

def test_migration_039_async_ingestion_orchestration_exists() -> None:
    """
    Verifies that services/kg/migrations/039_async_ingestion_orchestration.sql
    defines all tables for orchestration, runs, DLQ, and deduplication.
    """
    repo_root = Path(__file__).resolve().parents[3]
    migration_path = repo_root / "services" / "kg" / "migrations" / "039_async_ingestion_orchestration.sql"

    assert migration_path.exists(), f"Migration file not found at {migration_path}"
    content = migration_path.read_text(encoding="utf-8")

    # Tables
    assert "CREATE TABLE IF NOT EXISTS ingestion_pipelines" in content
    assert "CREATE TABLE IF NOT EXISTS ingestion_runs" in content
    assert "CREATE TABLE IF NOT EXISTS ingestion_dead_letter_queue" in content
    assert "CREATE TABLE IF NOT EXISTS ingestion_deduplication_records" in content

    # Check constraints
    assert "'IDLE'" in content
    assert "'RUNNING'" in content
    assert "'COMPLETED'" in content
    assert "'PARTIAL_SUCCESS'" in content
    assert "'FAILED'" in content
    assert "'PENDING'" in content
    assert "'REPLAYED'" in content

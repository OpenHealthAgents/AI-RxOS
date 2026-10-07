from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


# ==============================================================================
# 1. Pipeline & Ingestion Enums
# ==============================================================================

class PipelineStatus(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    ERROR = "ERROR"


class IngestionRunStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"


class DeadLetterStatus(str, Enum):
    PENDING = "PENDING"
    REPLAYED = "REPLAYED"
    RESOLVED = "RESOLVED"
    DISCARDED = "DISCARDED"


class QualityValidationStatus(str, Enum):
    PASSED = "PASSED"
    WARNING = "WARNING"
    FAILED = "FAILED"


# ==============================================================================
# 2. Configuration & Policy Models
# ==============================================================================

class RetryPolicy(BaseModel):
    """Configurable exponential backoff retry policy."""
    model_config = ConfigDict(from_attributes=True)

    max_retries: int = Field(default=3, ge=0, le=10)
    initial_backoff_seconds: float = Field(default=0.5, ge=0.01)
    backoff_multiplier: float = Field(default=2.0, ge=1.0)
    max_backoff_seconds: float = Field(default=30.0, ge=1.0)
    jitter: bool = True


class PipelineSchedule(BaseModel):
    """Defines execution schedule for continuous / periodic ingestion."""
    model_config = ConfigDict(from_attributes=True)

    cron_expression: Optional[str] = None
    interval_seconds: Optional[int] = None
    is_enabled: bool = True
    next_run_at: Optional[datetime] = None


class Watermark(BaseModel):
    """
    Tracks high-watermark for incremental updates to ensure no data is skipped
    and no historic records are unnecessarily reprocessed.
    """
    model_config = ConfigDict(from_attributes=True)

    pipeline_id: str
    last_processed_timestamp: Optional[datetime] = None
    last_processed_id: Optional[str] = None
    high_watermark_value: Optional[str] = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class IngestionItem(BaseModel):
    """Single item submitted to an ingestion pipeline."""
    model_config = ConfigDict(from_attributes=True)

    item_id: str
    source: str
    payload: Dict[str, Any]
    timestamp: Optional[datetime] = None
    version_or_hash: Optional[str] = None


# ==============================================================================
# 3. Telemetry & Dead-Letter Models
# ==============================================================================

class IngestionTelemetry(BaseModel):
    """Real-time observability metrics for an ingestion run."""
    model_config = ConfigDict(from_attributes=True)

    items_fetched: int = 0
    items_processed: int = 0
    items_succeeded: int = 0
    items_failed: int = 0
    items_retried: int = 0
    items_deduplicated: int = 0
    items_dead_lettered: int = 0
    duration_seconds: float = 0.0
    error_summary: Dict[str, int] = Field(default_factory=dict)


class DeadLetterRecord(BaseModel):
    """
    Preserved record for items failing validation or exceeding max retries.
    Guarantees no ingestion failure is silently discarded.
    """
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    pipeline_id: str
    item_id: str
    source: str
    payload: Dict[str, Any]
    failure_reason: str
    failure_category: str
    stack_trace: Optional[str] = None
    retry_attempts: int = 0
    status: DeadLetterStatus = DeadLetterStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None
    resolution_note: Optional[str] = None


class IngestionRunRecord(BaseModel):
    """Execution audit trail for a single ingestion pipeline run."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    pipeline_id: str
    triggered_by: str = "MANUAL"
    status: IngestionRunStatus = IngestionRunStatus.QUEUED
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    watermark_start: Optional[datetime] = None
    watermark_end: Optional[datetime] = None
    telemetry: IngestionTelemetry = Field(default_factory=IngestionTelemetry)
    error_message: Optional[str] = None
    quality_reports: List[Dict[str, Any]] = Field(default_factory=list)


class IngestionPipeline(BaseModel):
    """Definition and live state of an ingestion pipeline."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    source_name: str
    schedule: PipelineSchedule = Field(default_factory=PipelineSchedule)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    watermark: Watermark
    status: PipelineStatus = PipelineStatus.IDLE
    concurrency_limit: int = 5
    quality_gate_strict: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

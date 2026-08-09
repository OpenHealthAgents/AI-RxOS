from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from pydantic import BaseModel, Field

JobStatus = Literal[
    "pending",
    "running",
    "parsing",
    "processing",
    "completed",
    "failed",
    "retrying",
    "dead_letter",
]


class IngestionJobState(BaseModel):
    id: str
    source: str
    query: str
    status: JobStatus = "pending"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    attempts: int = 0
    max_retries: int = 3
    error: str | None = None
    result: dict[str, Any] | None = None

    def transition(self, new_status: JobStatus, error: str | None = None, result: dict[str, Any] | None = None) -> None:
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc).isoformat()
        if error:
            self.error = error
        if result:
            self.result = result


class JobStore:
    """Thread-safe job state store with lightweight JSON persistence."""

    def __init__(self):
        self._lock = Lock()
        self._jobs: dict[str, IngestionJobState] = {}
        self._storage_path = Path(os.environ.get("LITERATURE_JOB_STORE_PATH", "data/ingestion_jobs.json"))
        self._load()

    def _load(self) -> None:
        if not self._storage_path.exists():
            return
        try:
            payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                return
            for item in payload:
                if isinstance(item, dict):
                    job = IngestionJobState.model_validate(item)
                    self._jobs[job.id] = job
        except (OSError, ValueError, TypeError):
            self._jobs = {}

    def _persist(self) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = [job.model_dump() for job in self._jobs.values()]
        self._storage_path.write_text(json.dumps(serialized, indent=2), encoding="utf-8")

    def save(self, job: IngestionJobState) -> IngestionJobState:
        with self._lock:
            self._jobs[job.id] = job
            self._persist()
        return job

    def get(self, job_id: str) -> IngestionJobState | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_all(self) -> list[IngestionJobState]:
        with self._lock:
            return list(self._jobs.values())


job_store = JobStore()

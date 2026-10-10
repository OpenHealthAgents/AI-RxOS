from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from app.database.models import IngestionJobState, job_store
from app.observability.metrics import metrics

logger = logging.getLogger(__name__)

PipelineStage = Callable[[dict[str, Any]], dict[str, Any]]


class PipelineRunner:
    """Reusable stage-based execution model supporting retries, explicit state transitions, and dead-letter queueing."""

    def __init__(self, stages: list[PipelineStage] | None = None, retries: int = 2, delay_seconds: float = 0.05):
        self.stages = stages or []
        self.retries = retries
        self.delay_seconds = delay_seconds

    def run_with_job(self, job: IngestionJobState, initial_payload: dict[str, Any]) -> dict[str, Any]:
        job.transition("running")
        job_store.save(job)
        current = dict(initial_payload)

        try:
            for idx, stage in enumerate(self.stages):
                stage_name = getattr(stage, "name", getattr(stage, "__name__", f"stage_{idx}"))
                if "parse" in stage_name.lower():
                    job.transition("parsing")
                else:
                    job.transition("processing")
                job_store.save(job)

                stage_success = False
                for attempt in range(self.retries + 1):
                    job.attempts += 1
                    try:
                        current = stage(current)
                        stage_success = True
                        break
                    except Exception as exc:
                        logger.warning("Pipeline stage %s failed attempt %d: %s", stage_name, attempt + 1, exc)
                        if attempt < self.retries:
                            job.transition("retrying", error=str(exc))
                            job_store.save(job)
                            metrics.increment("pipeline.retry")
                            time.sleep(self.delay_seconds * (2**attempt))
                        else:
                            raise

                if not stage_success:
                    raise RuntimeError(f"Stage {stage_name} failed after {self.retries + 1} attempts.")

            job.transition("completed", result=current)
            job_store.save(job)
            metrics.increment("pipeline.completed")
            return current

        except Exception as fatal_exc:  # noqa: BLE001
            logger.error("Pipeline fatal error for job %s: %s", job.id, fatal_exc)
            job.transition("dead_letter", error=str(fatal_exc))
            job_store.save(job)
            metrics.increment("pipeline.dead_letter")
            current["status"] = "dead_letter"
            current["error"] = str(fatal_exc)
            return current

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        current = dict(payload)
        for stage in self.stages:
            for attempt in range(self.retries + 1):
                try:
                    current = stage(current)
                    break
                except Exception:
                    if attempt >= self.retries:
                        raise
                    time.sleep(self.delay_seconds * (2**attempt))
        return current

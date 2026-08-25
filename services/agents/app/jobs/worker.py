from __future__ import annotations

import asyncio
import os
import signal
import time
import uuid
from datetime import datetime, timezone

import redis.asyncio as redis
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.observability import (
    extract_trace_context,
    metrics,
    new_context,
    set_context,
    span,
)
from app.jobs.queue import RedisJobQueue
from app.jobs.state import transition
from app.security.redaction import redact_event


async def _job_event(task, event_type: str, worker_id: str) -> None:
    from app.main import _persist_task

    task.progress.events = [
        *task.progress.events[-49:],
        redact_event(
            {
                "type": event_type,
                "task_id": task.id,
                "execution_id": task.execution_id,
                "worker_id": worker_id,
                "status": task.status,
                "retry_count": task.retry_count,
            }
        ),
    ]
    await _persist_task(task)


async def process_job(
    queue: RedisJobQueue,
    message_id: str,
    task_id: str,
    worker_id: str | None = None,
    recovered: bool = False,
) -> None:
    from app.main import TASK_KEY, _execute_task, _load_task, _persist_task

    raw = await queue.client.get(TASK_KEY.format(id=task_id))
    if raw is None:
        await queue.acknowledge(message_id)
        return
    task = await _load_task(raw)
    owner = worker_id or os.getenv("AGENT_WORKER_ID") or "worker"
    settings = get_settings()
    execution_key = f"agents:concurrent:{task.tenant.get('organization_id', '_none')}:{task.tenant.get('workspace_id', '_shared')}:{task.tenant.get('user_id', '_none')}"
    if not await queue.claim_lock(
        task.id,
        owner,
        ttl_ms=int(settings.agent_worker_lock_ttl_seconds * 1000),
    ):
        return
    extract_trace_context(task.trace_context)
    set_context(new_context(task.request_id, task.correlation_id))
    try:
        if task.status in {"succeeded", "cancelled"} or (
            task.status == "failed"
            and (
                not task.retry_allowed
                or task.retry_count >= settings.agent_max_retries
            )
        ):
            await queue.acknowledge(message_id)
            return
        if task.cancel_requested:
            transition(task, "cancelled")
            await _job_event(task, "job_cancelled", owner)
            await _persist_task(task)
            await queue.acknowledge(message_id)
            return

        if task.status == "failed":
            transition(task, "retrying")
            task.retry_count += 1
            transition(task, "queued")
        if task.status != "running":
            transition(task, "running")
        task.worker_id = owner
        await _persist_task(task)
        await _job_event(task, "job_claimed", owner)
        if recovered:
            await _job_event(task, "job_recovered", owner)
        started = time.perf_counter()
        with span("agent.job", job_id=task.id, agent_type=task.agentType):
            await asyncio.wait_for(
                _execute_task(task),
                timeout=settings.agent_worker_execution_timeout_seconds,
            )
        metrics.observe(
            "agent_job_duration_seconds",
            time.perf_counter() - started,
            agent_type=task.agentType,
        )
        metrics.inc("agent_jobs_total", agent_type=task.agentType, status=task.status)
        if task.idempotency_key:
            scope = f"{task.tenant.get('organization_id', '_none')}:{task.tenant.get('workspace_id', '_shared')}:{task.tenant.get('user_id', '_none')}"
            await queue.client.set(
                f"agents:idempotency:{scope}:{task.idempotency_key}",
                (await queue.client.get(TASK_KEY.format(id=task.id))),
                ex=settings.idempotency_ttl,
            )
        if (
            task.status == "failed"
            and task.retry_allowed
            and task.retry_count < settings.agent_max_retries
        ):
            task.retry_count += 1
            metrics.inc(
                "agent_jobs_retried_total", agent_type=task.agentType, status="retrying"
            )
            transition(task, "retrying")
            await _job_event(task, "job_retrying", owner)
            await _persist_task(task)
            transition(task, "queued")
            await _persist_task(task)
            await queue.enqueue(task.id)
            await queue.acknowledge(message_id)
        else:
            if task.status == "failed":
                transition(task, "dead_letter")
                await _persist_task(task)
                await queue.move_to_dead_letter(
                    task_id=task.id,
                    tenant_id=task.tenant.get("organization_id", "_none"),
                    workspace_id=task.tenant.get("workspace_id", "_shared"),
                    task_type=task.job_type,
                    failure_category="internal",
                    retry_count=task.retry_count,
                    payload_reference=task.id,
                    original_message_id=message_id,
                    dead_letter_stream=settings.agent_dlq_stream,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
                await _job_event(task, "job_failed", owner)
            else:
                await _job_event(task, "job_completed", owner)
            await queue.acknowledge(message_id)
    except asyncio.TimeoutError:
        if task.status not in {"succeeded", "failed", "cancelled"}:
            transition(task, "failed")
            task.error = "operation failed"
            await _persist_task(task)
            await _job_event(task, "job_timeout", owner)
        if task.retry_allowed and task.retry_count < settings.agent_max_retries:
            task.retry_count += 1
            transition(task, "retrying")
            await _persist_task(task)
            transition(task, "queued")
            await _persist_task(task)
            await queue.enqueue(task.id)
        else:
            transition(task, "dead_letter")
            await _persist_task(task)
            await queue.move_to_dead_letter(
                task_id=task.id,
                tenant_id=task.tenant.get("organization_id", "_none"),
                workspace_id=task.tenant.get("workspace_id", "_shared"),
                task_type=task.job_type,
                failure_category="timeout",
                retry_count=task.retry_count,
                payload_reference=task.id,
                original_message_id=message_id,
                dead_letter_stream=settings.agent_dlq_stream,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        await queue.acknowledge(message_id)
    except asyncio.CancelledError:
        if task.status not in {"succeeded", "failed", "cancelled"}:
            transition(task, "cancelled")
            await _persist_task(task)
            await _job_event(task, "job_cancelled", owner)
        await queue.acknowledge(message_id)
        raise
    finally:
        exists = getattr(queue.client, "exists", None)
        if exists is not None and await exists(execution_key):
            await queue.client.decr(execution_key)
        await queue.release_lock(task.id, owner)


async def run_worker() -> None:
    settings = get_settings()
    client = redis.from_url(
        settings.redis_url,
        password=settings.redis_password,
        decode_responses=True,
        socket_timeout=settings.redis_operation_timeout_seconds,
        socket_connect_timeout=settings.redis_operation_timeout_seconds,
    )
    queue = RedisJobQueue(
        client, stream=settings.agent_job_stream, group=settings.agent_job_group
    )
    consumer = os.getenv("AGENT_WORKER_ID", str(uuid.uuid4()))
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(signum, stop_event.set)
        except (NotImplementedError, RuntimeError):
            pass
    await queue.ensure_group()
    try:
        while not stop_event.is_set():
            try:
                recovered_messages = await queue.recover(
                    consumer,
                    min_idle_ms=int(settings.agent_worker_reclaim_idle_seconds * 1000),
                )
                recovered = bool(recovered_messages)
                messages = recovered_messages
                if not messages:
                    messages = await queue.read(consumer)
                for message_id, fields in messages:
                    task_id = fields.get("task_id")
                    if isinstance(task_id, str):
                        await process_job(
                            queue, message_id, task_id, consumer, recovered=recovered
                        )
                    else:
                        await queue.acknowledge(message_id)
                    if stop_event.is_set():
                        break
            except (RedisError, ConnectionError, OSError):
                await asyncio.sleep(min(settings.redis_operation_timeout_seconds, 30.0))
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(run_worker())

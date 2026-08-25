from __future__ import annotations

import os
import uuid

import pytest
import redis.asyncio as redis

from app.jobs.queue import RedisJobQueue


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("AI_RXOS_LIVE_WORKER_TESTS") != "1",
    reason="set AI_RXOS_LIVE_WORKER_TESTS=1 to enable",
)
async def test_real_redis_pending_message_can_be_reclaimed():
    url = os.getenv("AI_RXOS_REDIS_URL", "redis://localhost:6379/0")
    client = redis.from_url(url, decode_responses=True)
    suffix = uuid.uuid4().hex
    queue = RedisJobQueue(
        client,
        stream=f"agents:jobs:live:{suffix}",
        group=f"agents-workers:live:{suffix}",
    )
    try:
        message_id = await queue.enqueue(f"live-task-{suffix}")
        first = await queue.read("worker-a", block_ms=1000)
        assert first == [(message_id, {"task_id": f"live-task-{suffix}"})]

        recovered = await queue.recover("worker-b", min_idle_ms=0)
        assert recovered == first
        assert await queue.acknowledge(message_id) == 1
    finally:
        await client.delete(queue.stream)
        await client.aclose()

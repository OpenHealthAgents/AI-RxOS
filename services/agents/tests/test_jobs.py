from __future__ import annotations

import pytest
from redis.exceptions import ResponseError

from app.jobs.queue import RedisJobQueue


class FakeRedis:
    def __init__(self):
        self.group_created = False
        self.messages = []
        self.acknowledged = []

    async def xgroup_create(self, stream, group, id, mkstream):
        if self.group_created:
            raise ResponseError("BUSYGROUP Consumer Group name already exists")
        self.group_created = True

    async def xadd(self, stream, fields):
        message_id = f"{len(self.messages) + 1}-0"
        self.messages.append((message_id, fields))
        return message_id

    async def xreadgroup(self, group, consumer, streams, count, block):
        return [(next(iter(streams)), self.messages)]

    async def xautoclaim(self, stream, group, consumer, min_idle_time, start_id, count):
        return ("0-0", [], [])

    async def xack(self, stream, group, message_id):
        self.acknowledged.append(message_id)
        return 1


@pytest.mark.asyncio
async def test_redis_job_queue_persists_and_delivers_job_ids():
    client = FakeRedis()
    queue = RedisJobQueue(client)

    message_id = await queue.enqueue("task-1")
    messages = await queue.read("worker-1")
    await queue.acknowledge(message_id)

    assert messages == [(message_id, {"task_id": "task-1"})]
    assert client.acknowledged == [message_id]


@pytest.mark.asyncio
async def test_redis_job_queue_reuses_existing_consumer_group():
    client = FakeRedis()
    queue = RedisJobQueue(client)

    await queue.ensure_group()
    await queue.ensure_group()
    assert client.group_created is True


@pytest.mark.asyncio
async def test_redis_job_queue_dead_letter_contains_metadata_only():
    client = FakeRedis()
    queue = RedisJobQueue(client)

    message_id = await queue.move_to_dead_letter(
        task_id="task-1",
        tenant_id="org-1",
        workspace_id="ws-1",
        task_type="agent.invoke",
        failure_category="timeout",
        retry_count=3,
        payload_reference="task-1",
        original_message_id="7-0",
        dead_letter_stream="agents:jobs:dead-letter",
        timestamp="2026-08-25T00:00:00+00:00",
    )

    assert message_id == "1-0"
    assert client.messages[0][0] == message_id
    fields = client.messages[0][1]
    assert fields["payload_reference"] == "task-1"
    assert fields["failure_reason"] == "operation failed"
    assert "private live input" not in str(fields)

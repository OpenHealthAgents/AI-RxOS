from __future__ import annotations

import inspect
from collections.abc import Awaitable
from typing import Any, TypeVar, cast

import redis.asyncio as redis
from redis.exceptions import ResponseError

Result = TypeVar("Result")


async def _resolve(value: Awaitable[Result] | Result) -> Result:
    return await value if inspect.isawaitable(value) else value


class RedisJobQueue:
    """Durable Redis Streams queue with consumer-group delivery semantics."""

    def __init__(
        self,
        client: redis.Redis,
        *,
        stream: str = "agents:jobs",
        group: str = "agents-workers",
    ) -> None:
        self.client = client
        self.stream = stream
        self.group = group

    async def ensure_group(self) -> None:
        try:
            await self.client.xgroup_create(
                self.stream, self.group, id="0", mkstream=True
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def enqueue(
        self,
        task_id: str,
        *,
        request_id: str | None = None,
        correlation_id: str | None = None,
    ) -> str:
        await self.ensure_group()
        fields: dict[str, str] = {"task_id": task_id}
        if request_id:
            fields["request_id"] = request_id
        if correlation_id:
            fields["correlation_id"] = correlation_id
        return await self.client.xadd(self.stream, cast(Any, fields))

    async def read(
        self, consumer: str, *, count: int = 1, block_ms: int = 5000
    ) -> list[tuple[str, dict[str, Any]]]:
        await self.ensure_group()
        batches = await self.client.xreadgroup(
            self.group,
            consumer,
            {self.stream: ">"},
            count=count,
            block=block_ms,
        )
        return [message for _stream, messages in batches for message in messages]

    async def recover(
        self, consumer: str, *, min_idle_ms: int = 60000, count: int = 10
    ) -> list[tuple[str, dict[str, Any]]]:
        await self.ensure_group()
        _next_id, messages, _deleted = await self.client.xautoclaim(
            self.stream,
            self.group,
            consumer,
            min_idle_time=min_idle_ms,
            start_id="0-0",
            count=count,
        )
        return messages

    async def claim_lock(self, task_id: str, owner: str, *, ttl_ms: int) -> bool:
        result = await _resolve(
            self.client.set(f"agents:job-lock:{task_id}", owner, nx=True, px=ttl_ms)
        )
        return bool(result)

    async def release_lock(self, task_id: str, owner: str) -> None:
        key = f"agents:job-lock:{task_id}"
        await _resolve(self.client.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",
            1,
            key,
            owner,
        ))

    async def refresh_lock(self, task_id: str, owner: str, *, ttl_ms: int) -> bool:
        result = await _resolve(
            self.client.eval(
                "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('pexpire', KEYS[1], ARGV[2]) else return 0 end",
                1,
                f"agents:job-lock:{task_id}",
                owner,
                str(ttl_ms),
            )
        )
        return bool(result)

    async def acknowledge(self, message_id: str) -> int:
        return await self.client.xack(self.stream, self.group, message_id)

    async def move_to_dead_letter(
        self,
        *,
        task_id: str,
        tenant_id: str,
        workspace_id: str,
        task_type: str,
        failure_category: str,
        retry_count: int,
        payload_reference: str,
        original_message_id: str,
        dead_letter_stream: str,
        timestamp: str,
    ) -> str:
        return await self.client.xadd(
            dead_letter_stream,
            cast(Any, {
                "task_id": task_id,
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
                "task_type": task_type,
                "failure_category": failure_category,
                "failure_reason": "operation failed",
                "retry_count": str(retry_count),
                "payload_reference": payload_reference,
                "original_message_id": original_message_id,
                "timestamp": timestamp,
            }),
        )

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.jobs.queue import RedisJobQueue
from app.jobs.state import transition


class LockRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def set(self, key, value, nx=False, px=None):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def get(self, key):
        return self.values.get(key)

    async def delete(self, key):
        self.values.pop(key, None)
        return 1

    async def eval(self, _script, _count, key, owner, *args):
        if self.values.get(key) == owner:
            self.values.pop(key)
            return 1
        return 0


@pytest.mark.asyncio
async def test_task_lock_allows_only_one_worker_owner():
    redis = LockRedis()
    queue = RedisJobQueue(redis)

    assert await queue.claim_lock("task-1", "worker-a", ttl_ms=1000)
    assert not await queue.claim_lock("task-1", "worker-b", ttl_ms=1000)
    await queue.release_lock("task-1", "worker-a")
    assert await queue.claim_lock("task-1", "worker-b", ttl_ms=1000)


def test_task_state_machine_rejects_terminal_restart():
    class Task:
        status = "succeeded"

    with pytest.raises(ValueError, match="invalid task transition"):
        transition(Task(), "running")


def test_worker_lock_ttl_covers_execution_and_reclaim_windows():
    with pytest.raises(ValidationError, match="LOCK_TTL"):
        Settings(
            agent_worker_execution_timeout_seconds=30,
            agent_worker_reclaim_idle_seconds=10,
            agent_worker_lock_ttl_seconds=40,
        )

    settings = Settings(
        agent_worker_execution_timeout_seconds=30,
        agent_worker_reclaim_idle_seconds=10,
        agent_worker_lock_ttl_seconds=41,
    )
    assert settings.agent_worker_lock_ttl_seconds > (
        settings.agent_worker_execution_timeout_seconds
        + settings.agent_worker_reclaim_idle_seconds
    )

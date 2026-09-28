from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.security.payloads import RedisExecutionPayloadStore


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def set(self, key, value, ex=None):
        self.values[key] = value
        return True

    async def get(self, key):
        return self.values.get(key)

    async def delete(self, key):
        self.values.pop(key, None)
        return 1


@pytest.mark.asyncio
async def test_payloads_are_encrypted_and_tenant_scoped():
    client = FakeRedis()
    store = RedisExecutionPayloadStore(client, key=Fernet.generate_key().decode())
    payload = {"input": {"prompt": "private"}, "result": {"answer": "secret"}}

    await store.put(
        tenant_id="org-a", workspace_id="ws-a", payload_id="run-1", payload=payload
    )

    stored = client.values[next(iter(client.values))]
    assert b"private" not in stored
    assert await store.get(
        tenant_id="org-a", workspace_id="ws-a", payload_id="run-1"
    ) == payload
    assert await store.get(
        tenant_id="org-b", workspace_id="ws-a", payload_id="run-1"
    ) is None


@pytest.mark.asyncio
async def test_payload_delete_removes_ciphertext():
    client = FakeRedis()
    store = RedisExecutionPayloadStore(client, key=Fernet.generate_key().decode())

    await store.put(
        tenant_id="org-a", workspace_id="ws-a", payload_id="run-1", payload={"value": 1}
    )
    await store.delete(tenant_id="org-a", workspace_id="ws-a", payload_id="run-1")

    assert client.values == {}


def test_invalid_payload_key_fails_closed():
    with pytest.raises(ValueError, match="valid Fernet key"):
        RedisExecutionPayloadStore(FakeRedis(), key="invalid-key")

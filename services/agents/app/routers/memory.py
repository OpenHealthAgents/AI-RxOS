from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.security import TenantContext, get_tenant_context
from app.memory.llm_wiki import AgentMemory, create_agent_memory

router = APIRouter(prefix="/api/v1/agents/memory", tags=["Agent Memory"])

tenant_dependency = Depends(get_tenant_context)


class StoreMemoryRequest(BaseModel):
    agent_id: str
    key: str
    value: Any
    provenance: dict[str, Any] = {}
    persist_long_term: bool = False


def get_memory_store(tenant: TenantContext = tenant_dependency) -> AgentMemory:
    from app.main import _redis

    return create_agent_memory(str(uuid.uuid4()), tenant, redis_client=_redis)


memory_store_dependency = Depends(get_memory_store)


@router.post("", status_code=201)
async def store_memory(
    req: StoreMemoryRequest,
    tenant: TenantContext = tenant_dependency,
    store: AgentMemory = memory_store_dependency,
) -> dict[str, Any]:
    return await store.store(
        tenant=tenant,
        agent_id=req.agent_id,
        key=req.key,
        value=req.value,
        provenance=req.provenance,
        persist_long_term=req.persist_long_term,
    )


@router.get("/{agent_id}/{key}")
async def retrieve_memory(
    agent_id: str,
    key: str,
    tenant: TenantContext = tenant_dependency,
    store: AgentMemory = memory_store_dependency,
) -> dict[str, Any]:
    record = await store.retrieve(tenant=tenant, agent_id=agent_id, key=key)
    if record is None:
        raise HTTPException(status_code=404, detail="memory entry not found")
    return record


@router.get("/{agent_id}")
async def search_memory(
    agent_id: str,
    query: str | None = None,
    limit: int = 10,
    tenant: TenantContext = tenant_dependency,
    store: AgentMemory = memory_store_dependency,
) -> dict[str, Any]:
    records = await store.search(tenant=tenant, agent_id=agent_id, query=query, limit=limit)
    return {"items": records, "total": len(records)}

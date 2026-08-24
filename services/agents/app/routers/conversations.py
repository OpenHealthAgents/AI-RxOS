from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.security import TenantContext, get_tenant_context
from app.memory.conversation import ConversationMemoryStore

router = APIRouter(prefix="/api/v1/agents/conversations", tags=["Conversation Memory"])

tenant_dependency = Depends(get_tenant_context)


class AddMessageRequest(BaseModel):
    role: str
    content: str
    metadata: dict[str, Any] = {}


def get_conversation_store() -> ConversationMemoryStore:
    from app.main import conversation_memory_store

    return conversation_memory_store


conversation_store_dependency = Depends(get_conversation_store)


@router.post("/{conversation_id}/messages", status_code=201)
async def add_message(
    conversation_id: str,
    req: AddMessageRequest,
    tenant: TenantContext = tenant_dependency,
    store: ConversationMemoryStore = conversation_store_dependency,
) -> dict[str, Any]:
    record = await store.add_message(
        tenant=tenant,
        conversation_id=conversation_id,
        role=req.role,
        content=req.content,
        metadata=req.metadata,
    )
    if record is None:
        # Conversation exists but belongs to a different tenant — reported
        # as not-found rather than forbidden, so probing conversation ids
        # can't be used to distinguish "wrong tenant" from "doesn't exist".
        raise HTTPException(status_code=404, detail="conversation not found")
    return record


@router.get("/{conversation_id}/messages")
async def get_messages(
    conversation_id: str,
    limit: int | None = None,
    tenant: TenantContext = tenant_dependency,
    store: ConversationMemoryStore = conversation_store_dependency,
) -> dict[str, Any]:
    messages = await store.get_messages(tenant=tenant, conversation_id=conversation_id, limit=limit)
    if messages is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return {"conversation_id": conversation_id, "messages": messages, "total": len(messages)}

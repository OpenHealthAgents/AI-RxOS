import json
import uuid
from typing import Any, Literal

import redis.asyncio as redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.core.config import get_settings

settings = get_settings()
app = FastAPI(
    title="AI-RxOS Agent Orchestrator",
    description="Agent registration, invocation, tool routing, and "
    "conversation memory for the AI Orchestration context.",
    version="0.1.0",
)

_redis = redis.from_url(settings.redis_url, decode_responses=True)
TASK_KEY = "agents:task:{id}"


class ToolInvocation(BaseModel):
    tool: str
    arguments: dict[str, Any] = {}


class AgentInvokeRequest(BaseModel):
    agentType: str
    input: dict[str, Any]
    tools: list[str] = []


class AgentTask(BaseModel):
    id: str
    agentType: str
    status: Literal["pending", "running", "succeeded", "failed"]
    input: dict[str, Any]
    result: dict[str, Any] | None = None


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "agents"}


@app.post("/api/v1/agents/invoke", response_model=AgentTask, status_code=202)
async def invoke_agent(req: AgentInvokeRequest) -> AgentTask:
    task = AgentTask(id=str(uuid.uuid4()), agentType=req.agentType, status="pending", input=req.input)
    await _redis.set(TASK_KEY.format(id=task.id), task.model_dump_json(), ex=86400)
    return task


@app.get("/api/v1/agents/tasks/{task_id}", response_model=AgentTask)
async def get_task(task_id: str) -> AgentTask:
    raw = await _redis.get(TASK_KEY.format(id=task_id))
    if raw is None:
        raise HTTPException(status_code=404, detail="task not found")
    return AgentTask(**json.loads(raw))


@app.get("/api/v1/tools")
def list_tools() -> dict[str, list[str]]:
    return {"tools": ["literature.search", "kg.query", "docking.run", "reports.generate"]}

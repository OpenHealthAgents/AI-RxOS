import uuid
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="AI-RxOS AI Services",
    description="Agent orchestration, model registry, and inference facade "
    "for the AI Orchestration bounded context.",
    version="0.1.0",
)

# In-memory task store — the reference implementation for local dev / demos.
# A production deployment swaps this for the Agent Orchestrator Service's
# PostgreSQL-backed store (see architecture/02-microservices.md §4.1).
_TASKS: dict[str, dict[str, Any]] = {}


class AgentRunRequest(BaseModel):
    agentType: str
    input: dict[str, Any]


class AgentTask(BaseModel):
    id: str
    agentType: str
    input: dict[str, Any]
    status: Literal["pending", "running", "succeeded", "failed"]
    result: dict[str, Any] | None = None


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ai-services", "environment": settings.environment}


@app.post("/api/v1/agents/run", response_model=AgentTask, status_code=202)
def run_agent(req: AgentRunRequest) -> AgentTask:
    task_id = str(uuid.uuid4())
    task = AgentTask(id=task_id, agentType=req.agentType, input=req.input, status="pending")
    _TASKS[task_id] = task.model_dump()
    return task


@app.get("/api/v1/agents/tasks/{task_id}", response_model=AgentTask)
def get_task(task_id: str) -> AgentTask:
    task = _TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return AgentTask(**task)


@app.get("/api/v1/models")
def list_models() -> dict[str, list[dict[str, str]]]:
    return {"models": [{"id": "default-llm", "provider": "internal", "status": "active"}]}

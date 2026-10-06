import uuid
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.core.config import get_settings
from app.opportunity_engine.api import router as opportunity_router
from app.opportunity_engine.biology.router import router as biology_router
from app.opportunity_engine.clinical.router import router as clinical_router
from app.opportunity_engine.cns.router import router as cns_router
from app.opportunity_engine.discover.router import router as discover_router
from app.opportunity_engine.kg.router import router as kg_router
from app.opportunity_engine.licensing.router import router as licensing_router
from app.opportunity_engine.patient_match.router import router as patient_match_router
from app.opportunity_engine.regulatory.router import router as regulatory_router
from app.opportunity_engine.resistance.router import router as resistance_router
from app.opportunity_engine.combination.router import router as combination_router
from app.opportunity_engine.safety.router import router as safety_router
from app.opportunity_engine.competitive.router import router as competitive_router
from app.opportunity_engine.commercial.router import router as commercial_router

settings = get_settings()

app = FastAPI(
    title="AI-RxOS AI Services",
    description="Agent orchestration, model registry, and inference facade "
    "for the AI Orchestration bounded context.",
    version="0.1.0",
)

app.include_router(opportunity_router)
app.include_router(regulatory_router)
app.include_router(licensing_router)
app.include_router(kg_router)
app.include_router(discover_router)
app.include_router(biology_router)
app.include_router(cns_router)
app.include_router(clinical_router)
app.include_router(patient_match_router)
app.include_router(resistance_router)
app.include_router(combination_router)
app.include_router(safety_router)
app.include_router(competitive_router)
app.include_router(commercial_router)



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

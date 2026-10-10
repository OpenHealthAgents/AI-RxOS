import logging
import uuid
from typing import Any, Literal
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.security import trusted_identity_middleware
from app.ml.router import router as ml_router
from app.opportunity_engine.api import router as opportunity_router
from app.opportunity_engine.backtest_api import router as backtest_router
from app.opportunity_engine.biology.router import router as biology_router
from app.opportunity_engine.clinical.router import router as clinical_router
from app.opportunity_engine.cns.router import router as cns_router
from app.opportunity_engine.combination.router import router as combination_router
from app.opportunity_engine.compare_api import router as compare_router
from app.opportunity_engine.commercial.router import router as commercial_router
from app.opportunity_engine.competitive.router import router as competitive_router
from app.opportunity_engine.core_api import router as core_assets_router
from app.opportunity_engine.decision.router import router as decision_router
from app.opportunity_engine.discover.router import router as discover_router
from app.opportunity_engine.discover.api import router as discover_api_router
from app.opportunity_engine.ingestion.clinicaltrials.router import (
    router as clinicaltrials_router,
)
from app.opportunity_engine.ingestion.orchestrator.router import (
    router as orchestration_router,
)
from app.opportunity_engine.ingestion.pubmed.router import router as pubmed_router
from app.opportunity_engine.kg.router import router as kg_router
from app.opportunity_engine.licensing.router import router as licensing_router
from app.opportunity_engine.patient_match.router import router as patient_match_router
from app.opportunity_engine.regulatory.router import router as regulatory_router
from app.opportunity_engine.research_reports import router as research_reports_router
from app.opportunity_engine.resistance.router import router as resistance_router
from app.opportunity_engine.review.durable_store import durable_review_store
from app.opportunity_engine.review.router import router as review_router
from app.opportunity_engine.safety.router import router as safety_router
from app.opportunity_engine.search.router import router as search_router

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await durable_review_store.initialize()
    except Exception as exc:
        if settings.environment.lower() in {"production", "prod"}:
            raise
        logger.warning("Durable review store is unavailable; review writes will fail closed (%s)", type(exc).__name__)
    yield
    # Cleanup on shutdown
    await durable_review_store.close()


app = FastAPI(
    title="AI-RxOS AI Services",
    description="Agent orchestration, model registry, and inference facade "
    "for the AI Orchestration bounded context.",
    version="0.1.0",
    lifespan=lifespan,
)
app.state.security_settings = settings
app.middleware("http")(trusted_identity_middleware)

app.include_router(opportunity_router)
app.include_router(backtest_router)
app.include_router(core_assets_router)
app.include_router(compare_router)
app.include_router(regulatory_router)
app.include_router(research_reports_router)
app.include_router(licensing_router)
app.include_router(review_router)
app.include_router(kg_router)
app.include_router(discover_router)
app.include_router(discover_api_router)
app.include_router(search_router)
app.include_router(biology_router)
app.include_router(cns_router)
app.include_router(clinical_router)
app.include_router(patient_match_router)
app.include_router(resistance_router)
app.include_router(combination_router)
app.include_router(safety_router)
app.include_router(competitive_router)
app.include_router(commercial_router)
app.include_router(decision_router)
app.include_router(pubmed_router)
app.include_router(clinicaltrials_router)
app.include_router(orchestration_router)
app.include_router(ml_router)





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
    configured = bool(
        settings.research_llm_base_url and settings.research_llm_model
    )
    return {
        "models": [
            {
                "id": settings.research_llm_model or "default-llm",
                "provider": "openai-compatible",
                "status": "active" if configured else "unavailable",
            }
        ]
    }

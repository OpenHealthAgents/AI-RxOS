import uuid
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.core.config import get_settings

settings = get_settings()
app = FastAPI(
    title="AI-RxOS Workflow Service",
    description="Multi-step scientific workflow orchestration (e.g. "
    "literature-review -> knowledge-graph-enrich -> report-generate chains). "
    "Production deployments back this with Temporal; this reference "
    "implementation uses an in-memory step machine.",
    version="0.1.0",
)

_WORKFLOWS: dict[str, dict[str, Any]] = {}


class WorkflowStep(BaseModel):
    name: str
    service: str
    status: Literal["pending", "running", "completed", "failed"] = "pending"


class CreateWorkflowRequest(BaseModel):
    name: str
    steps: list[str]


class Workflow(BaseModel):
    id: str
    name: str
    status: Literal["pending", "running", "completed", "failed"]
    steps: list[WorkflowStep]


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "workflows"}


@app.post("/api/v1/workflows", response_model=Workflow, status_code=201)
def create_workflow(req: CreateWorkflowRequest) -> Workflow:
    wf = Workflow(
        id=str(uuid.uuid4()),
        name=req.name,
        status="pending",
        steps=[WorkflowStep(name=s, service=s.split(".")[0]) for s in req.steps],
    )
    _WORKFLOWS[wf.id] = wf.model_dump()
    return wf


@app.get("/api/v1/workflows/{workflow_id}", response_model=Workflow)
def get_workflow(workflow_id: str) -> Workflow:
    wf = _WORKFLOWS.get(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="workflow not found")
    return Workflow(**wf)


@app.post("/api/v1/workflows/{workflow_id}/advance", response_model=Workflow)
def advance_workflow(workflow_id: str) -> Workflow:
    wf = _WORKFLOWS.get(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="workflow not found")
    for step in wf["steps"]:
        if step["status"] in ("pending", "running"):
            step["status"] = "completed"
            break
    if all(s["status"] == "completed" for s in wf["steps"]):
        wf["status"] = "completed"
    else:
        wf["status"] = "running"
    return Workflow(**wf)

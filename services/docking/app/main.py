import uuid
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.core.config import get_settings

settings = get_settings()
app = FastAPI(
    title="AI-RxOS Docking Service",
    description="Protein-ligand docking and binding pose prediction for the "
    "Molecule Discovery context. Production deployments run this on "
    "GPU nodes against AutoDock Vina; this reference implementation "
    "exposes the same contract with a deterministic stub scorer.",
    version="0.1.0",
)

_JOBS: dict[str, dict] = {}


class DockingRequest(BaseModel):
    moleculeId: str
    targetId: str
    smiles: str | None = None


class DockingResult(BaseModel):
    id: str
    moleculeId: str
    targetId: str
    bindingAffinity: float | None = None
    status: Literal["queued", "running", "completed", "failed"]


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "docking"}


@app.post("/api/v1/docking", response_model=DockingResult, status_code=202)
def submit_docking(req: DockingRequest) -> DockingResult:
    job = DockingResult(
        id=str(uuid.uuid4()),
        moleculeId=req.moleculeId,
        targetId=req.targetId,
        status="queued",
    )
    _JOBS[job.id] = job.model_dump()
    return job


@app.get("/api/v1/docking/{job_id}", response_model=DockingResult)
def get_docking_result(job_id: str) -> DockingResult:
    job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="docking job not found")
    return DockingResult(**job)


@app.post("/api/v1/docking/{job_id}/complete", response_model=DockingResult)
def complete_docking(job_id: str, binding_affinity: float) -> DockingResult:
    """Test/demo hook — a real deployment marks jobs complete from the GPU worker."""
    job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="docking job not found")
    job["status"] = "completed"
    job["bindingAffinity"] = binding_affinity
    return DockingResult(**job)

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="AI-RxOS Literature Service",
    description="Ingestion, extraction, and citation services for the "
    "Literature Intelligence bounded context.",
    version="0.1.0",
)

_PAPERS: dict[str, dict] = {}
_INGESTION_JOBS: dict[str, dict] = {}


class Paper(BaseModel):
    id: str
    title: str
    source: Literal["pubmed", "biorxiv", "medrxiv", "patent", "conference"]
    doi: str | None = None
    publishedAt: str | None = None
    citationCount: int = 0


class IngestionRequest(BaseModel):
    source: Literal["pubmed", "biorxiv", "medrxiv", "patent", "conference"]
    query: str


class IngestionJob(BaseModel):
    id: str
    source: str
    query: str
    status: Literal["queued", "running", "completed", "failed"]
    createdAt: str


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "literature"}


@app.get("/api/v1/papers")
def list_papers(page: int = 1, page_size: int = 20) -> dict:
    items = list(_PAPERS.values())[(page - 1) * page_size : page * page_size]
    return {"items": items, "total": len(_PAPERS), "page": page, "pageSize": page_size}


@app.get("/api/v1/papers/{paper_id}")
def get_paper(paper_id: str) -> Paper | dict:
    paper = _PAPERS.get(paper_id)
    return paper or {"error": "not_found"}


@app.post("/api/v1/ingestion", response_model=IngestionJob, status_code=202)
def start_ingestion(req: IngestionRequest) -> IngestionJob:
    job_id = str(uuid.uuid4())
    job = IngestionJob(
        id=job_id,
        source=req.source,
        query=req.query,
        status="queued",
        createdAt=datetime.now(timezone.utc).isoformat(),
    )
    _INGESTION_JOBS[job_id] = job.model_dump()
    return job


@app.get("/api/v1/ingestion/{job_id}")
def get_ingestion_job(job_id: str) -> dict:
    return _INGESTION_JOBS.get(job_id, {"error": "not_found"})

import uuid
from typing import Literal

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.core.config import get_settings
from app.database.models import IngestionJobState, job_store
from app.observability.metrics import metrics
from app.services.literature_service import LiteratureService

settings = get_settings()
literature_service = LiteratureService(
    {
        "kg_service_url": settings.kg_service_url,
        "kg_timeout": settings.kg_timeout,
        "kg_max_retries": settings.kg_max_retries,
        "kg_backoff_seconds": settings.kg_backoff_seconds,
        "wiki_service_url": settings.okf_wiki_url,
        "wiki_api_key": settings.wiki_api_key,
        "wiki_dir": settings.okf_wiki_dir,
        "wiki_timeout": settings.wiki_timeout,
        "wiki_max_retries": settings.wiki_max_retries,
        "wiki_backoff_seconds": settings.wiki_backoff_seconds,
        "llm_provider": settings.llm_provider,
        "llm_api_key": settings.llm_api_key,
        "llm_api_url": settings.llm_api_url,
        "llm_model": settings.llm_model,
        "llm_timeout": settings.llm_timeout,
        "llm_max_retries": settings.llm_max_retries,
        "llm_backoff_seconds": settings.llm_backoff_seconds,
        "ner_provider": settings.ner_provider,
        "ner_model": settings.ner_model,
        "ner_timeout": settings.ner_timeout,
        "crawler_user_agent": settings.crawler_user_agent,
        "crawler_timeout": settings.crawler_timeout,
        "crawler_rate_limit": settings.crawler_rate_limit,
        "crawler_max_pages": settings.crawler_max_pages,
        "crawler_max_depth": settings.crawler_max_depth,
        "crawler_allowed_domains": settings.crawler_allowed_domains,
    }
)

app = FastAPI(
    title="AI-RxOS Literature Service",
    description="Ingestion, extraction, knowledge graph, and citation services for the Literature Intelligence bounded context.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-ID") or str(uuid.uuid4())
    response: Response = await call_next(request)
    response.headers["X-Trace-ID"] = trace_id
    return response


_PAPERS: dict[str, dict] = {}


class Paper(BaseModel):
    id: str
    title: str
    source: Literal[
        "pubmed",
        "pmc",
        "clinicaltrials",
        "aacr",
        "asco",
        "sabcs",
        "esmo",
        "biorxiv",
        "medrxiv",
        "patents",
        "company_websites",
    ]
    doi: str | None = None
    publishedAt: str | None = None
    citationCount: int = 0


class IngestionRequest(BaseModel):
    source: Literal[
        "pubmed",
        "pmc",
        "clinicaltrials",
        "aacr",
        "asco",
        "sabcs",
        "esmo",
        "biorxiv",
        "medrxiv",
        "patents",
        "company_websites",
    ]
    query: str


class IngestionJobResponse(BaseModel):
    id: str
    source: str
    query: str
    status: str
    createdAt: str


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "literature"}


@app.get("/metrics")
def get_metrics() -> dict[str, int]:
    return metrics.snapshot()


@app.get("/api/v1/papers")
def list_papers(page: int = 1, page_size: int = 20) -> dict:
    items = list(_PAPERS.values())[(page - 1) * page_size : page * page_size]
    return {"items": items, "total": len(_PAPERS), "page": page, "pageSize": page_size}


@app.get("/api/v1/papers/{paper_id}")
def get_paper(paper_id: str) -> Paper | dict:
    paper = _PAPERS.get(paper_id)
    return paper or {"error": "not_found"}


@app.post("/api/v1/ingestion", response_model=IngestionJobResponse, status_code=202)
def start_ingestion(req: IngestionRequest) -> IngestionJobResponse:
    job_id = str(uuid.uuid4())
    job = IngestionJobState(
        id=job_id,
        source=req.source,
        query=req.query,
        status="pending",
    )
    job_store.save(job)

    literature_service.ingest(req.source, req.query, job_id=job_id)

    updated_job = job_store.get(job_id) or job
    status_output = "completed" if updated_job.status == "completed" else updated_job.status
    return IngestionJobResponse(
        id=updated_job.id,
        source=updated_job.source,
        query=updated_job.query,
        status=status_output,
        createdAt=updated_job.created_at,
    )


@app.get("/api/v1/ingestion/{job_id}")
def get_ingestion_job(job_id: str) -> dict:
    job = job_store.get(job_id)
    if not job:
        return {"error": "not_found"}
    return job.model_dump()


@app.post("/api/v1/analyze")
def analyze_text(text: str) -> dict:
    return literature_service.analyze_text(text)

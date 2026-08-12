from __future__ import annotations

import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.lifespan import lifespan
from app.observability.metrics import (
    REQUEST_COUNT,
    REQUEST_ERRORS,
    REQUEST_IN_FLIGHT,
    REQUEST_LATENCY_SECONDS,
)
from app.routers.documents import router as documents_router
from app.routers.health import router as health_router
from app.routers.ingestion import router as ingestion_router
from app.routers.nlp import router as nlp_router
from app.routers.papers import router as papers_router
from app.services.literature_service import LiteratureService
from app.utils.logging import get_logger, set_request_context

settings = get_settings()
logger = get_logger(__name__)

# Literature Service instance to support fallback in-memory ingestion route
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

# In-memory papers cache to support fallback in-memory papers router
_PAPERS: dict[str, dict] = {}

app = FastAPI(
    title="AI-RxOS Literature Service",
    description="Ingestion, extraction, and citation services for the Literature Intelligence bounded context.",
    version="0.2.0",
    lifespan=lifespan,
)

cors_origins = getattr(settings, "cors_origins", ["*"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_context(request: Request, call_next):
    # Support both case-sensitive request ID/trace ID variations
    request_id = (
        request.headers.get("x-request-id")
        or request.headers.get("X-Request-ID")
        or request.headers.get("X-Trace-ID")
        or request.headers.get("x-trace-id")
        or str(uuid.uuid4())
    )
    trace_id = request_id
    request.state.request_id = request_id
    request.state.trace_id = trace_id
    set_request_context(request_id=request_id, trace_id=trace_id)

    method = request.method
    endpoint = request.url.path
    REQUEST_IN_FLIGHT.labels(method=method, endpoint=endpoint).inc()
    start_time = time.perf_counter()
    try:
        response = await call_next(request)
        status_code = str(response.status_code)
        REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status_code).inc()
        if response.status_code >= 400:
            REQUEST_ERRORS.labels(
                method=method, endpoint=endpoint, status=status_code
            ).inc()
        response.headers["x-request-id"] = request_id
        response.headers["x-trace-id"] = trace_id
        response.headers["X-Trace-ID"] = trace_id
        return response
    except Exception:
        REQUEST_COUNT.labels(method=method, endpoint=endpoint, status="500").inc()
        REQUEST_ERRORS.labels(method=method, endpoint=endpoint, status="500").inc()
        raise
    finally:
        elapsed = time.perf_counter() - start_time
        REQUEST_LATENCY_SECONDS.labels(method=method, endpoint=endpoint).observe(
            elapsed
        )
        REQUEST_IN_FLIGHT.labels(method=method, endpoint=endpoint).dec()


app.include_router(health_router)
app.include_router(papers_router, prefix="/api/v1")
app.include_router(ingestion_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(nlp_router, prefix="/api/v1")

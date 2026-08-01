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
from app.utils.logging import get_logger, set_request_context

settings = get_settings()
logger = get_logger(__name__)

app = FastAPI(
    title="AI-RxOS Literature Service",
    description="Ingestion, extraction, and citation services for the Literature Intelligence bounded context.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    trace_id = request.headers.get("x-trace-id") or str(uuid.uuid4())
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

from datetime import datetime, timezone
from typing import Any

import asyncpg
import httpx
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.core.config import get_settings
from app.database.postgres import postgres_manager
from app.observability.metrics import generate_prometheus_metrics
from app.orchestrator.manager import orchestrator
from app.parsing import parser_metrics

settings = get_settings()
router = APIRouter(tags=["Health"])
service_start_time = datetime.now(timezone.utc)


def _uptime_seconds() -> int:
    return int((datetime.now(timezone.utc) - service_start_time).total_seconds())


async def _db_ready() -> tuple[bool, str]:
    if settings.environment == "test":
        return True, "test environment"
    if postgres_manager.pool is None:
        if postgres_manager.last_error is not None:
            return False, f"connection pool unavailable: {postgres_manager.last_error}"
        return False, "connection pool uninitialized"
    try:
        async with postgres_manager.acquire() as connection:
            result = await connection.fetchval("SELECT 1")
            return True, f"db responded: {result}"
    except asyncpg.PostgresError as exc:
        return False, str(exc)


async def _service_available(url: str) -> tuple[bool, str]:
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                return True, "ok"
            return False, f"status={response.status_code}"
    except httpx.HTTPError as exc:
        return False, str(exc)


def _orchestrator_ready() -> tuple[bool, str]:
    try:
        metrics = orchestrator.get_metrics()
        if isinstance(metrics, dict):
            return True, "ok"
        return False, "invalid metrics payload"
    except (ValueError, RuntimeError, TypeError) as exc:
        return False, str(exc)


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "literature"}


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "literature"}


@router.get("/ready")
async def ready() -> dict[str, Any]:
    db_ready, db_details = await _db_ready()
    search_ready, search_details = await _service_available(
        f"{settings.search_service_url}/api/v1/health"
    )
    kg_ready, kg_details = await _service_available(
        f"{settings.kg_service_url}/api/v1/health"
    )
    orchestrator_ready, orchestrator_details = _orchestrator_ready()
    all_ready = db_ready and search_ready and kg_ready and orchestrator_ready
    return {
        "status": "ok" if all_ready else "fail",
        "service": "literature",
        "ready": all_ready,
        "dependencies": {
            "postgresql": {
                "status": "ok" if db_ready else "fail",
                "details": db_details,
            },
            "search_service": {
                "status": "ok" if search_ready else "fail",
                "details": search_details,
            },
            "kg_service": {
                "status": "ok" if kg_ready else "fail",
                "details": kg_details,
            },
            "orchestrator": {
                "status": "ok" if orchestrator_ready else "fail",
                "details": orchestrator_details,
            },
        },
        "metrics": {
            "uptime_seconds": _uptime_seconds(),
            "parser_metrics": parser_metrics.snapshot(),
            "orchestrator_metrics": orchestrator.get_metrics(),
        },
    }


@router.get("/live")
def live() -> dict[str, Any]:
    return {"status": "ok", "service": "literature", "live": True}


@router.get("/metrics")
def metrics() -> dict[str, Any]:
    return {
        "service": "literature",
        "environment": settings.environment,
        "uptime_seconds": _uptime_seconds(),
        "parser_metrics": parser_metrics.snapshot(),
        "orchestrator_metrics": orchestrator.get_metrics(),
    }


@router.get("/metrics/prometheus", response_class=PlainTextResponse)
def metrics_prometheus() -> bytes:
    return generate_prometheus_metrics()


@router.get("/api/v1/health")
def api_health() -> dict[str, str]:
    return {"status": "ok", "service": "literature"}

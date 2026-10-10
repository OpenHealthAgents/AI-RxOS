from __future__ import annotations

import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import get_tenant_context
from app.database.postgres import postgres_manager
from app.knowledge.models import TenantContext
from app.monitoring.models import MonitoringCategory, MonitoringEvent, MonitoringEventPage

router = APIRouter(prefix="/monitoring", tags=["Continuous Monitoring"])


@router.get("/events", response_model=MonitoringEventPage)
async def list_monitoring_events(
    source_category: Annotated[MonitoringCategory | None, Query()] = None,
    limit: int = Query(50, ge=1, le=200),
    tenant: TenantContext = Depends(get_tenant_context),
) -> MonitoringEventPage:
    if postgres_manager.pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="continuous monitoring events require the PostgreSQL-backed ingestion service",
        )
    organization_id = (
        UUID(tenant.organization_id) if tenant.organization_id is not None else None
    )
    rows = await postgres_manager.list_monitoring_events(
        organization_id=organization_id,
        limit=limit,
        source_category=source_category,
    )
    events = []
    for row in rows:
        payload = dict(row)
        for key in ("changed_fields", "evidence_refs"):
            if isinstance(payload.get(key), str):
                payload[key] = json.loads(payload[key])
        events.append(MonitoringEvent.model_validate(payload))
    return MonitoringEventPage(
        items=events,
        count=len(events),
        limit=limit,
        source_category=source_category,
    )

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.core.config import get_settings

settings = get_settings()
app = FastAPI(
    title="AI-RxOS Report Service",
    description="Scientific, competitive, due-diligence, and executive "
    "report generation for the Collaboration context.",
    version="0.1.0",
)

_REPORTS: dict[str, dict] = {}


class GenerateReportRequest(BaseModel):
    title: str
    type: Literal["scientific", "competitive", "due-diligence", "executive"]
    sourceIds: list[str] = []


class Report(BaseModel):
    id: str
    title: str
    type: Literal["scientific", "competitive", "due-diligence", "executive"]
    status: Literal["draft", "generating", "ready", "failed"]
    createdAt: str


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "reports"}


@app.get("/api/v1/reports")
def list_reports(page: int = 1, page_size: int = 20) -> dict:
    items = list(_REPORTS.values())[(page - 1) * page_size : page * page_size]
    return {"items": items, "total": len(_REPORTS), "page": page, "pageSize": page_size}


@app.post("/api/v1/reports", response_model=Report, status_code=202)
def generate_report(req: GenerateReportRequest) -> Report:
    report = Report(
        id=str(uuid.uuid4()),
        title=req.title,
        type=req.type,
        status="generating",
        createdAt=datetime.now(timezone.utc).isoformat(),
    )
    _REPORTS[report.id] = report.model_dump()
    return report


@app.get("/api/v1/reports/{report_id}", response_model=Report)
def get_report(report_id: str) -> Report:
    report = _REPORTS.get(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="report not found")
    return Report(**report)

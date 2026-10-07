from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .models import (
    ExtractedObservation,
    ExtractionCategory,
    IngestionResult,
    PubMedArticleRecord,
    PubMedQualityReport,
)
from .service import PubMedIngestionService

router = APIRouter(prefix="/api/v1/ingest/pubmed", tags=["PubMed Ingestion Engine"])
_service = PubMedIngestionService()


class BatchIngestRequest(BaseModel):
    articles: List[PubMedArticleRecord]
    force_reprocess: bool = False
    run_quality_checks: bool = True


@router.post("/article", response_model=IngestionResult)
async def ingest_pubmed_article_route(
    record: PubMedArticleRecord,
    force_reprocess: bool = Query(False, description="Bypass deduplication and reprocess"),
    run_quality_checks: bool = Query(True, description="Run automated quality and anti-hallucination checks"),
) -> IngestionResult:
    """
    Ingests a PubMed article: captures PMID, title, abstract, authors, journal,
    publication date, study type, MeSH, keywords; extracts asset, target, disease,
    biomarker, mutation, model, efficacy, toxicity, CNS, resistance, combination,
    clinical result; resolves canonical entities; runs quality checks; and stores raw
    evidence and immutable extraction lineage.
    """
    result = await _service.ingest_article(
        record=record,
        force_reprocess=force_reprocess,
        run_quality_checks=run_quality_checks,
    )
    return result


@router.post("/batch")
async def batch_ingest_pubmed_articles_route(
    req: BatchIngestRequest,
) -> dict:
    """
    Batch ingests multiple PubMed articles with idempotent deduplication,
    entity resolution, extraction lineage, and quality reporting.
    """
    results = await _service.batch_ingest_articles(
        records=req.articles,
        force_reprocess=req.force_reprocess,
        run_quality_checks=req.run_quality_checks,
    )
    return {
        "total_submitted": len(req.articles),
        "total_processed": len(results),
        "ingested_count": sum(1 for r in results if r.status.value in ("INGESTED", "RETRIED_AND_SUCCEEDED")),
        "duplicate_skipped_count": sum(1 for r in results if r.is_duplicate),
        "failed_count": sum(1 for r in results if r.status.value == "FAILED"),
        "results": [r.model_dump(mode="json") for r in results],
    }


@router.get("/{pmid}", response_model=PubMedArticleRecord)
def get_pubmed_article_route(pmid: str) -> PubMedArticleRecord:
    """Retrieves raw captured PubMed article record by PMID."""
    article = _service.get_article(pmid)
    if not article:
        raise HTTPException(status_code=404, detail=f"PubMed article '{pmid}' not found.")
    return article


@router.get("/{pmid}/observations", response_model=List[ExtractedObservation])
def get_pubmed_observations_route(
    pmid: str,
    category: Optional[str] = Query(None, description="Optional category filter (e.g. drug, target, cns, clinical_result)"),
) -> List[ExtractedObservation]:
    """Retrieves all extracted observations and extraction lineage for a PMID."""
    article = _service.get_article(pmid)
    if not article:
        raise HTTPException(status_code=404, detail=f"PubMed article '{pmid}' not found.")
    cat_enum = ExtractionCategory(category) if category else None
    return _service.get_observations(pmid, category=cat_enum)


@router.get("/{pmid}/quality", response_model=PubMedQualityReport)
def get_pubmed_quality_report_route(pmid: str) -> PubMedQualityReport:
    """Retrieves automated quality check and groundedness report for a PMID."""
    report = _service.get_quality_report(pmid)
    if not report:
        raise HTTPException(status_code=404, detail=f"Quality report for PMID '{pmid}' not found.")
    return report


@router.get("/{pmid}/lineage")
def get_pubmed_extraction_lineage_route(pmid: str) -> dict:
    """Retrieves complete extraction lineage for all observations under PMID."""
    observations = _service.get_observations(pmid)
    if not observations:
        raise HTTPException(status_code=404, detail=f"No observations found for PMID '{pmid}'.")
    return {
        "pmid": pmid,
        "total_observations": len(observations),
        "lineage_records": [
            {
                "observation_id": str(o.id),
                "category": o.extraction_category.value,
                "entity": o.entity_text,
                "confidence": o.confidence,
                "resolved_canonical_id": str(o.resolved_canonical_id) if o.resolved_canonical_id else None,
                "resolved_canonical_name": o.resolved_canonical_name,
                "resolution_method": o.resolution_method,
                "lineage": o.lineage.model_dump(mode="json") if o.lineage else None,
            }
            for o in observations
        ],
    }

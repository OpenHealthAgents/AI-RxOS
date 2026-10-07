from __future__ import annotations

from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from .models import (
    AssetOwnershipProfile,
    DealType,
    LicensingStatus,
    OwnershipAndDealEvent,
    PatentClaimType,
    PatentRecord,
    ProhibitedFTOAssertionError,
    UnverifiedLicensingAssertionError,
)
from .service import OwnershipAndLicensingService

router = APIRouter(prefix="/api/v1/licensing", tags=["Ownership & Licensing Intelligence"])

_service = OwnershipAndLicensingService()


def get_licensing_service() -> OwnershipAndLicensingService:
    return _service


class UpdateLicensingStatusRequest(BaseModel):
    status: LicensingStatus
    rationale: str
    verification_source: Optional[str] = None
    is_verified: bool = False
    strict: bool = True


@router.get("/assets/{asset_id}", response_model=AssetOwnershipProfile)
def get_asset_ownership_profile(
    asset_id: UUID,
    cutoff_date: Optional[date] = Query(None, description="Optional temporal cutoff date to prevent leakage"),
) -> AssetOwnershipProfile:
    """
    Returns the comprehensive ownership, corporate deal lineage, and patent intelligence
    profile for a therapeutic asset.
    """
    service = get_licensing_service()
    profile = service.get_ownership_profile(asset_id=asset_id, cutoff_date=cutoff_date)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ownership profile for asset '{asset_id}' not found.",
        )
    return profile


class BatchPatentIngestRequest(BaseModel):
    patents: List[PatentRecord]


class BatchPatentIngestResponse(BaseModel):
    total_submitted: int
    total_ingested: int
    patents: List[PatentRecord]


@router.get("/assets/{asset_id}/patents", response_model=List[PatentRecord])
def get_asset_patents(
    asset_id: UUID,
    cutoff_date: Optional[date] = Query(None, description="Optional temporal cutoff date"),
) -> List[PatentRecord]:
    """Returns the patent portfolio for the asset."""
    profile = get_asset_ownership_profile(asset_id=asset_id, cutoff_date=cutoff_date)
    return profile.patents


@router.post("/patents", response_model=PatentRecord, status_code=status.HTTP_201_CREATED)
def record_patent_route(
    patent: PatentRecord,
) -> PatentRecord:
    """
    Ingests and records a patent.
    Captures patent number, patent family, assignee, inventors, jurisdiction,
    priority date, filing date, expiration date, and claim types.
    Enforces invariant: Never claim freedom to operate (FTO).
    """
    service = get_licensing_service()
    try:
        return service.record_patent(patent)
    except ProhibitedFTOAssertionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/patents/batch", response_model=BatchPatentIngestResponse)
def batch_record_patents_route(
    req: BatchPatentIngestRequest,
) -> BatchPatentIngestResponse:
    """Batch ingests patent records."""
    service = get_licensing_service()
    try:
        ingested = service.batch_record_patents(req.patents)
        return BatchPatentIngestResponse(
            total_submitted=len(req.patents),
            total_ingested=len(ingested),
            patents=ingested,
        )
    except ProhibitedFTOAssertionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/patents/{patent_number}", response_model=PatentRecord)
def get_patent_route(patent_number: str) -> PatentRecord:
    """Retrieves a single patent record by its patent number."""
    service = get_licensing_service()
    patent = service.get_patent(patent_number)
    if not patent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patent '{patent_number}' not found.",
        )
    return patent


@router.get("/patents/family/{family_id}", response_model=List[PatentRecord])
def get_patents_by_family_route(family_id: str) -> List[PatentRecord]:
    """Retrieves all patents in a patent family."""
    service = get_licensing_service()
    return service.get_patents_by_family(family_id)


@router.get("/patents/claim-type/{claim_type}", response_model=List[PatentRecord])
def get_patents_by_claim_type_route(
    claim_type: PatentClaimType,
    cutoff_date: Optional[date] = Query(None, description="Optional temporal cutoff date to prevent leakage"),
) -> List[PatentRecord]:
    """
    Retrieves all patents classified with a given claim type
    (COMPOSITION_OF_MATTER, THERAPEUTIC_USE, FORMULATION, COMBINATION, BIOMARKER_CLAIMS).
    """
    service = get_licensing_service()
    return service.get_patents_by_claim_type(claim_type=claim_type, cutoff_date=cutoff_date)


@router.post("/assets", response_model=AssetOwnershipProfile, status_code=status.HTTP_201_CREATED)
def register_asset_profile(profile: AssetOwnershipProfile) -> AssetOwnershipProfile:
    """Registers or updates an asset ownership and IP intelligence profile."""
    service = get_licensing_service()
    return service.register_profile(profile)


class BatchDealIngestRequest(BaseModel):
    deals: List[OwnershipAndDealEvent]


class BatchDealIngestResponse(BaseModel):
    total_submitted: int
    total_ingested: int
    deals: List[OwnershipAndDealEvent]


@router.post("/deals", response_model=OwnershipAndDealEvent, status_code=status.HTTP_201_CREATED)
def record_deal_route(deal: OwnershipAndDealEvent) -> OwnershipAndDealEvent:
    """
    Ingests and records a public company event:
    funding, acquisition, licensing, partnership, asset transfer,
    co-development, option.
    """
    service = get_licensing_service()
    return service.record_deal_event(deal)


@router.post("/deals/batch", response_model=BatchDealIngestResponse)
def batch_record_deals_route(req: BatchDealIngestRequest) -> BatchDealIngestResponse:
    """Batch ingests corporate deal and company transaction events."""
    service = get_licensing_service()
    ingested = service.batch_record_deal_events(req.deals)
    return BatchDealIngestResponse(
        total_submitted=len(req.deals),
        total_ingested=len(ingested),
        deals=ingested,
    )


@router.get("/deals", response_model=List[OwnershipAndDealEvent])
def list_deals(
    cutoff_date: Optional[date] = Query(None, description="Optional temporal cutoff date to prevent leakage"),
) -> List[OwnershipAndDealEvent]:
    """Retrieves all recorded public company events up to an optional cutoff date."""
    service = get_licensing_service()
    return service.get_all_deals(cutoff_date=cutoff_date)


@router.get("/deals/by-type/{deal_type}", response_model=List[OwnershipAndDealEvent])
def get_deals_by_type_route(
    deal_type: DealType,
    cutoff_date: Optional[date] = Query(None, description="Optional temporal cutoff date to prevent leakage"),
) -> List[OwnershipAndDealEvent]:
    """
    Retrieves public company events filtered by deal type:
    FUNDING, ACQUISITION, LICENSING, PARTNERSHIP, ASSET_TRANSFER,
    CO_DEVELOPMENT, OPTION.
    """
    service = get_licensing_service()
    return service.get_deal_events_by_type(deal_type=deal_type, cutoff_date=cutoff_date)


@router.get("/assets/{asset_id}/deals", response_model=List[OwnershipAndDealEvent])
def get_asset_deals(
    asset_id: UUID,
    cutoff_date: Optional[date] = Query(None, description="Optional temporal cutoff date"),
) -> List[OwnershipAndDealEvent]:
    """Returns the corporate transaction and licensing alliance history for the asset."""
    profile = get_asset_ownership_profile(asset_id=asset_id, cutoff_date=cutoff_date)
    return profile.deal_history


@router.post("/assets/{asset_id}/status", response_model=AssetOwnershipProfile)
def update_licensing_status(
    asset_id: UUID,
    req: UpdateLicensingStatusRequest,
) -> AssetOwnershipProfile:
    """
    Updates the licensing status of an asset.
    Enforces anti-unverified guardrail and zero FTO assertion rules.
    """
    service = get_licensing_service()
    try:
        return service.update_licensing_status(
            asset_id=asset_id,
            status=req.status,
            rationale=req.rationale,
            verification_source=req.verification_source,
            is_verified=req.is_verified,
            strict=req.strict,
        )
    except UnverifiedLicensingAssertionError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except ProhibitedFTOAssertionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except KeyError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

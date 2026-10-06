from __future__ import annotations

from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from .models import (
    AssetOwnershipProfile,
    LicensingStatus,
    OwnershipAndDealEvent,
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


@router.get("/assets/{asset_id}/patents", response_model=List[PatentRecord])
def get_asset_patents(
    asset_id: UUID,
    cutoff_date: Optional[date] = Query(None, description="Optional temporal cutoff date"),
) -> List[PatentRecord]:
    """Returns the patent portfolio for the asset."""
    profile = get_asset_ownership_profile(asset_id=asset_id, cutoff_date=cutoff_date)
    return profile.patents


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

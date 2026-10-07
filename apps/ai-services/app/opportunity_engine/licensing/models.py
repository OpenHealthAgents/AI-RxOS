from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


MANDATORY_FTO_DISCLAIMER = (
    "DISCLAIMER: IP analysis provided is competitive and scientific decision intelligence, "
    "not legal advice. No Freedom to Operate (FTO) is claimed or warranted. "
    "Consult qualified patent counsel for formal legal opinions."
)


# ==============================================================================
# 1. Licensing Availability States & Deal Types
# ==============================================================================

class LicensingStatus(str, Enum):
    """
    Standardized licensing availability states.
    Strict invariant: Never state 'licensing available' unless verified.
    """
    VERIFIED_AVAILABLE = "VERIFIED_AVAILABLE"
    POTENTIALLY_AVAILABLE = "POTENTIALLY_AVAILABLE"
    PARTNERED = "PARTNERED"
    OWNERSHIP_UNCLEAR = "OWNERSHIP_UNCLEAR"
    NO_PUBLIC_SIGNAL = "NO_PUBLIC_SIGNAL"
    NO_PUBLIC_LICENSING_SIGNAL = "NO_PUBLIC_LICENSING_SIGNAL"
    UNKNOWN = "UNKNOWN"


class DealType(str, Enum):
    """
    Public company events and transaction types impacting asset ownership and partnering:
    - FUNDING
    - ACQUISITION
    - LICENSING (and LICENSING_ANNOUNCEMENT)
    - PARTNERSHIP
    - ASSET_TRANSFER
    - CO_DEVELOPMENT
    - OPTION (and OPTION_AGREEMENT)
    """
    FUNDING = "FUNDING"
    ACQUISITION = "ACQUISITION"
    LICENSING = "LICENSING"
    LICENSING_ANNOUNCEMENT = "LICENSING_ANNOUNCEMENT"
    PARTNERSHIP = "PARTNERSHIP"
    ASSET_TRANSFER = "ASSET_TRANSFER"
    CO_DEVELOPMENT = "CO_DEVELOPMENT"
    OPTION = "OPTION"
    OPTION_AGREEMENT = "OPTION_AGREEMENT"


# ==============================================================================
# 2. Patent Jurisdictions, Claim Types & Statuses
# ==============================================================================

class PatentJurisdiction(str, Enum):
    US = "US"
    EP = "EP"
    WO = "WO"
    JP = "JP"
    CN = "CN"
    CA = "CA"
    OTHER = "OTHER"


class PatentClaimType(str, Enum):
    COMPOSITION_OF_MATTER = "COMPOSITION_OF_MATTER"
    THERAPEUTIC_USE = "THERAPEUTIC_USE"
    FORMULATION = "FORMULATION"
    COMBINATION = "COMBINATION"
    BIOMARKER_CLAIMS = "BIOMARKER_CLAIMS"


class PatentStatus(str, Enum):
    GRANTED = "GRANTED"
    PENDING = "PENDING"
    EXPIRED = "EXPIRED"
    ABANDONED = "ABANDONED"
    REVOKED = "REVOKED"


# ==============================================================================
# 3. Patent Entities
# ==============================================================================

class PatentFamily(BaseModel):
    """Group of related patent applications sharing priority filings."""
    model_config = ConfigDict(from_attributes=True)
    family_id: str
    title: str
    earliest_priority_date: date
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PatentRecord(BaseModel):
    """
    Granular patent entity covering assignee, inventors, jurisdiction,
    filing, priority, expiration, and claim types.
    """
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    family_id: Optional[str] = None
    patent_number: str
    title: str
    assignee: str
    inventors: List[str] = Field(default_factory=list)
    jurisdiction: PatentJurisdiction
    filing_date: date
    priority_date: date
    expiration_date: date
    grant_date: Optional[date] = None
    status: PatentStatus = PatentStatus.GRANTED
    claim_types: List[PatentClaimType] = Field(default_factory=list)
    composition_of_matter_expiry: Optional[date] = None
    source_citation: str
    source_url: Optional[str] = None
    is_verified_evidence: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================================
# 4. Corporate Deal & Ownership Event
# ==============================================================================

class OwnershipAndDealEvent(BaseModel):
    """
    Corporate transaction or public event impacting asset ownership rights:
    funding, acquisition, licensing, partnership, asset transfer,
    co-development, option.
    """
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    deal_type: DealType
    licensor: Optional[str] = None
    licensee: Optional[str] = None
    partner: Optional[str] = None
    territory: str = "Global"
    effective_date: date
    disclosed_upfront_usd: Optional[int] = None
    disclosed_milestones_usd: Optional[int] = None
    royalty_rate_pct: Optional[str] = None
    funding_round: Optional[str] = None
    investors: List[str] = Field(default_factory=list)
    summary: str
    source_citation: str
    source_url: Optional[str] = None
    is_verified_evidence: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("deal_type", mode="before")
    @classmethod
    def normalize_deal_type(cls, v: Any) -> Any:
        if isinstance(v, str):
            clean = v.strip().upper().replace(" ", "_").replace("-", "_")
            if clean in ("LICENSE", "LICENSING_AGREEMENT"):
                return DealType.LICENSING
            if clean in DealType.__members__:
                return DealType[clean]
            for m in DealType:
                if m.value == clean:
                    return m
        return v


# ==============================================================================
# 5. Asset Ownership & Licensing Profile
# ==============================================================================

class AssetOwnershipProfile(BaseModel):
    """
    Comprehensive ownership, deal history, and IP profile for a therapeutic asset.
    Tracks developer, originator, current owner, former owner, academic origin,
    partner, licensee, licensor, and patents.
    """
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    developer: str
    originator: str
    current_owner: str
    former_owners: List[str] = Field(default_factory=list)
    academic_origin: Optional[str] = None
    partner: Optional[str] = None
    licensing_status: LicensingStatus = LicensingStatus.UNKNOWN
    licensing_status_rationale: str = ""
    licensing_status_verified: bool = False
    licensing_verification_source: Optional[str] = None
    deal_history: List[OwnershipAndDealEvent] = Field(default_factory=list)
    patents: List[PatentRecord] = Field(default_factory=list)
    fto_disclaimer: str = MANDATORY_FTO_DISCLAIMER
    content_hash: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("licensing_status", mode="before")
    @classmethod
    def normalize_licensing_status(cls, v: Any) -> Any:
        if isinstance(v, str):
            clean = v.strip().upper().replace(" ", "_").replace("-", "_")
            if clean in LicensingStatus.__members__:
                return LicensingStatus[clean]
            for m in LicensingStatus:
                if m.value == clean:
                    return m
        return v

    def compute_content_hash(self) -> str:
        hasher = hashlib.sha256()
        hasher.update(str(self.asset_id).encode("utf-8"))
        hasher.update(self.current_owner.strip().upper().encode("utf-8"))
        hasher.update(self.licensing_status.value.encode("utf-8"))
        hasher.update(str(self.licensing_status_verified).encode("utf-8"))
        return hasher.hexdigest()

    def model_post_init(self, __context: Any) -> None:
        if not self.content_hash:
            self.content_hash = self.compute_content_hash()
        # Guarantee mandatory disclaimer is never blanked out
        if not self.fto_disclaimer:
            self.fto_disclaimer = MANDATORY_FTO_DISCLAIMER


# ==============================================================================
# 6. Policy Exceptions
# ==============================================================================

class UnverifiedLicensingAssertionError(ValueError):
    """Raised when 'licensing available' is asserted without verified evidence."""
    pass


class ProhibitedFTOAssertionError(ValueError):
    """Raised when an attempt is made to claim Freedom to Operate (FTO)."""
    pass

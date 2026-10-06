from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ==============================================================================
# 1. Regulatory Jurisdictions & Authorities
# ==============================================================================

class RegulatoryJurisdiction(str, Enum):
    US = "US"
    EU = "EU"
    JP = "JP"
    CN = "CN"
    UK = "UK"
    CA = "CA"
    GLOBAL = "GLOBAL"


class RegulatoryAuthority(str, Enum):
    FDA = "FDA"
    EMA = "EMA"
    PMDA = "PMDA"
    NMPA = "NMPA"
    MHRA = "MHRA"
    HEALTH_CANADA = "HEALTH_CANADA"
    WHO = "WHO"
    OTHER = "OTHER"


# ==============================================================================
# 2. Canonical Regulatory Event Types (All 12 Required Categories)
# ==============================================================================

class RegulatoryEventType(str, Enum):
    IND_RELATED = "IND_RELATED"
    FAST_TRACK = "FAST_TRACK"
    BREAKTHROUGH_THERAPY = "BREAKTHROUGH_THERAPY"
    ORPHAN_DRUG = "ORPHAN_DRUG"
    ACCELERATED_APPROVAL = "ACCELERATED_APPROVAL"
    FULL_APPROVAL = "FULL_APPROVAL"
    SUPPLEMENTAL_APPROVAL = "SUPPLEMENTAL_APPROVAL"
    COMPLETE_RESPONSE_LETTER = "COMPLETE_RESPONSE_LETTER"
    WITHDRAWAL = "WITHDRAWAL"
    SAFETY_WARNING = "SAFETY_WARNING"
    LABEL_CHANGE = "LABEL_CHANGE"
    REGULATORY_MILESTONE = "REGULATORY_MILESTONE"


# ==============================================================================
# 3. Provenance Sources & Verification Status
# ==============================================================================

class RegulatorySourceType(str, Enum):
    FDA_DRUGS_AT_FDA = "FDA_DRUGS_AT_FDA"
    FDA_ACTION_LETTER = "FDA_ACTION_LETTER"
    FDA_ORANGE_BOOK = "FDA_ORANGE_BOOK"
    EMA_EPAR = "EMA_EPAR"
    PMDA_NOTICE = "PMDA_NOTICE"
    NMPA_NOTICE = "NMPA_NOTICE"
    SEC_8K_FILING = "SEC_8K_FILING"
    FEDERAL_REGISTER = "FEDERAL_REGISTER"
    SPONSOR_REGULATORY_DISCLOSURE = "SPONSOR_REGULATORY_DISCLOSURE"
    UNVERIFIED_MARKETING_CLAIM = "UNVERIFIED_MARKETING_CLAIM"
    OTHER = "OTHER"


class VerificationStatus(str, Enum):
    VERIFIED_OFFICIAL_RECORD = "VERIFIED_OFFICIAL_RECORD"
    PROVISIONAL_PENDING_CONFIRMATION = "PROVISIONAL_PENDING_CONFIRMATION"
    REJECTED_UNVERIFIED_MARKETING = "REJECTED_UNVERIFIED_MARKETING"


# ==============================================================================
# 4. Typed Components for the 7 Required Event Attributes
# ==============================================================================

class RegulatorySource(BaseModel):
    """Provenance and verification metadata for regulatory claims."""
    model_config = ConfigDict(from_attributes=True)
    source_type: RegulatorySourceType
    source_citation: str
    source_url: Optional[str] = None
    source_document_id: Optional[str] = None
    is_verified_evidence: bool = False
    publication_date: Optional[date] = None


class RegulatoryAssetRef(BaseModel):
    """Canonical drug asset entity reference."""
    model_config = ConfigDict(from_attributes=True)
    asset_id: UUID
    asset_name: str


class RegulatoryIndicationRef(BaseModel):
    """Canonical clinical disease indication reference."""
    model_config = ConfigDict(from_attributes=True)
    indication_id: Optional[UUID] = None
    indication_name: str
    cancer_subtype: Optional[str] = None


class RegulatoryEventPayload(BaseModel):
    """Specific event payload and milestone classification."""
    model_config = ConfigDict(from_attributes=True)
    event_type: RegulatoryEventType
    headline: str
    details: str
    milestone_type: Optional[str] = None  # e.g., PDUFA_GOAL, ADCOM_VOTE, RTOR, ROLLING_REVIEW
    dossier_data: Dict[str, Any] = Field(default_factory=dict)


# ==============================================================================
# 5. Core Regulatory Event Record
# ==============================================================================

class RegulatoryEventRecord(BaseModel):
    """
    Core Regulatory Event Record capturing the 7 mandatory attributes:
    1. source
    2. date
    3. jurisdiction
    4. asset
    5. indication
    6. event
    7. confidence

    Guarantees strict policy: Never infer regulatory approval from marketing claims
    without verified evidence.
    """
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)

    # 1. Source (provenance)
    source: RegulatorySource

    # 2. Date
    event_date: date

    # 3. Jurisdiction
    jurisdiction: RegulatoryJurisdiction
    authority: RegulatoryAuthority = RegulatoryAuthority.FDA

    # 4. Asset
    asset: RegulatoryAssetRef

    # 5. Indication
    indication: RegulatoryIndicationRef

    # 6. Event
    event: RegulatoryEventPayload

    # 7. Confidence (0.000 to 1.000)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    # System Status & Integrity
    verification_status: VerificationStatus = VerificationStatus.VERIFIED_OFFICIAL_RECORD
    policy_violation: Optional[str] = None
    content_hash: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def compute_content_hash(self) -> str:
        hasher = hashlib.sha256()
        hasher.update(str(self.asset.asset_id).encode("utf-8"))
        hasher.update(self.indication.indication_name.strip().upper().encode("utf-8"))
        hasher.update(self.event.event_type.value.encode("utf-8"))
        hasher.update(self.event_date.isoformat().encode("utf-8"))
        hasher.update(self.jurisdiction.value.encode("utf-8"))
        hasher.update(self.source.source_citation.strip().encode("utf-8"))
        return hasher.hexdigest()

    def model_post_init(self, __context: Any) -> None:
        if not self.content_hash:
            self.content_hash = self.compute_content_hash()


# ==============================================================================
# 6. Domain Exceptions
# ==============================================================================

class UnverifiedMarketingClaimError(ValueError):
    """Raised when marketing or promotional claims attempt to assert regulatory approval without official verified evidence."""
    pass


class RegulatoryVerificationPolicyError(ValueError):
    """Raised when an invalid regulatory record violates evidence standards."""
    pass

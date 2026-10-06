from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


# ==============================================================================
# 1. 14-Dimensional Structured Filters
# ==============================================================================

class StructuredDiscoverFilters(BaseModel):
    """
    Structured criteria parsed from natural language query covering all 14 dimensions:
    1. target
    2. disease
    3. indication
    4. stage
    5. modality
    6. biomarker
    7. mutation
    8. cns_requirement
    9. clinical_evidence
    10. safety
    11. competition
    12. ownership
    13. licensing
    14. commercial_opportunity
    """
    model_config = ConfigDict(from_attributes=True)

    # 1. Target
    target: Optional[str] = None

    # 2. Disease
    disease: Optional[str] = None

    # 3. Indication
    indication: Optional[str] = None

    # 4. Stage
    stage: Optional[List[str]] = Field(default_factory=list)

    # 5. Modality
    modality: Optional[str] = None

    # 6. Biomarker
    biomarker: Optional[str] = None

    # 7. Mutation
    mutation: Optional[str] = None

    # 8. CNS Requirement
    cns_requirement: Optional[bool] = None

    # 9. Clinical Evidence
    clinical_evidence: Optional[bool] = None

    # 10. Safety
    safety: Optional[str] = None

    # 11. Competition
    competition: Optional[str] = None

    # 12. Ownership
    ownership: Optional[str] = None

    # 13. Licensing
    licensing: Optional[str] = None

    # 14. Commercial Opportunity
    commercial_opportunity: Optional[str] = None


# ==============================================================================
# 2. Ranked Match & Result Models
# ==============================================================================

class RankedDiscoverMatch(BaseModel):
    """
    Every result in the Discover Engine must expose:
    - ranking
    - reason
    - evidence
    - confidence
    - unknowns
    """
    model_config = ConfigDict(from_attributes=True)

    ranking: int = Field(description="1-based integer ranking among matched candidates")
    asset_id: str
    asset_name: str
    code_name: Optional[str] = None
    match_score: float = Field(ge=0.0, le=100.0, description="Composite fit score (0-100)")
    reason: str = Field(description="Explanatory scientific rationale for recommendation")
    evidence: List[Dict[str, Any]] = Field(default_factory=list, description="Provenance-backed evidence items")
    confidence: float = Field(ge=0.0, le=1.0, description="AI inference certainty score")
    unknowns: List[str] = Field(default_factory=list, description="Explicit unknowns and evidence gaps")

    # Supporting metadata
    primary_indication: str = ""
    stage: str = ""
    modality: str = ""
    owner: str = ""


class DiscoverQueryRequest(BaseModel):
    query: str
    explicit_filters: Optional[StructuredDiscoverFilters] = None
    top_k: int = 10


class DiscoverQueryResult(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    query: str
    parsed_filters: StructuredDiscoverFilters
    results_count: int
    ranked_assets: List[RankedDiscoverMatch]
    queried_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

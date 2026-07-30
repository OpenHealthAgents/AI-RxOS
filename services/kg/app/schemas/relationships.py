from uuid import UUID
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

VALID_RELATIONSHIP_TYPES = {
    "TREATS", "TARGETS", "INTERACTS", "PRESENTED_AT",
    "PUBLISHED_IN", "OWNED_BY", "COMPETES_WITH"
}

class RelationshipCreate(BaseModel):
    from_node_id: UUID
    to_node_id: UUID
    type: str
    id: Optional[UUID] = None
    evidence: Optional[str] = None
    confidence: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description=(
            "Optional caller-supplied confidence override. If omitted, the "
            "server computes it from source trust + corroboration count + "
            "recency (see app.services.evidence_service.compute_confidence). "
            "A supplied value that diverges sharply from the computed score "
            "is accepted but logged for review, not silently trusted."
        ),
    )
    source: Optional[str] = None
    created_at: Optional[datetime] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in VALID_RELATIONSHIP_TYPES:
            raise ValueError(f"Invalid relationship type: '{v}'. Must be one of: {sorted(list(VALID_RELATIONSHIP_TYPES))}")
        return v

class RelationshipResponse(BaseModel):
    id: UUID
    from_node_id: UUID
    to_node_id: UUID
    type: str
    evidence: Optional[str] = None
    confidence: Optional[float] = None
    source: Optional[str] = None
    created_at: datetime
    version: Optional[int] = None

class RelationshipListResponse(BaseModel):
    relationships: list[RelationshipResponse]
    total: int
    page: int
    size: int

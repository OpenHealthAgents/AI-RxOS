from uuid import UUID
from typing import Any, Optional, Dict
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

VALID_LABELS = {
    "Gene", "Protein", "Disease", "Drug", "Target", "Mutation",
    "Publication", "Patent", "ClinicalTrial", "Company", "Conference"
}

class NodeCreate(BaseModel):
    label: str
    id: Optional[UUID] = None
    name: str
    description: Optional[str] = None
    source: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("label")
    @classmethod
    def validate_label(cls, v: str) -> str:
        if v not in VALID_LABELS:
            raise ValueError(f"Invalid node label: '{v}'. Must be one of: {sorted(list(VALID_LABELS))}")
        return v

class NodeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    updated_at: Optional[datetime] = None

class NodeResponse(BaseModel):
    id: UUID
    label: str
    name: str
    description: Optional[str] = None
    source: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    version: Optional[int] = None

class NodeListResponse(BaseModel):
    nodes: list[NodeResponse]
    total: int
    page: int
    size: int

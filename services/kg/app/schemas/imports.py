from typing import Optional
from pydantic import BaseModel, Field
from app.schemas.nodes import NodeCreate
from app.schemas.relationships import RelationshipCreate

class ImportJSONRequest(BaseModel):
    nodes: list[NodeCreate] = Field(default_factory=list)
    relationships: list[RelationshipCreate] = Field(default_factory=list)
    description: Optional[str] = None

class ImportResponse(BaseModel):
    version_number: int
    nodes_imported: int
    relationships_imported: int
    elapsed_seconds: float
    status: str

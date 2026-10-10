from uuid import UUID
from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class GraphVersionResponse(BaseModel):
    id: UUID
    version_number: int
    description: Optional[str] = None
    status: str
    created_at: datetime

class VersionListResponse(BaseModel):
    versions: list[GraphVersionResponse]

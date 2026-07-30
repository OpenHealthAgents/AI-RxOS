from pydantic import BaseModel
from app.schemas.nodes import NodeResponse
from app.schemas.relationships import RelationshipResponse

class NeighborItem(BaseModel):
    relationship: RelationshipResponse
    node: NodeResponse

class NeighborsResponse(BaseModel):
    node: NodeResponse
    neighbors: list[NeighborItem]

class PathResponse(BaseModel):
    nodes: list[NodeResponse]
    relationships: list[RelationshipResponse]

class SubgraphResponse(BaseModel):
    nodes: list[NodeResponse]
    relationships: list[RelationshipResponse]

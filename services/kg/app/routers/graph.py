from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from app.core.canonical_security import CanonicalPrincipal, get_canonical_principal
from app.schemas.nodes import NodeResponse, VALID_LABELS
from app.schemas.graph import NeighborsResponse, PathResponse, SubgraphResponse
from app.services.graph_service import GraphService
from app.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["Graph Operations"])


class GraphRelevanceRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    document_ids: List[str] = Field(min_length=1, max_length=100)

@router.get("/neighbors/{node_id}", response_model=NeighborsResponse)
async def get_neighbors(node_id: str, principal: CanonicalPrincipal = Depends(get_canonical_principal)):
    try:
        neighbors_data = await GraphService.get_neighbors(node_id, principal)
        if not neighbors_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Node with ID '{node_id}' not found in active graph version."
            )
        return neighbors_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching neighbors for node '{node_id}': {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching neighbors: {str(e)}"
        )

@router.get("/path", response_model=PathResponse)
async def get_path(
    start_node_id: str = Query(..., description="ID of the starting node"),
    end_node_id: str = Query(..., description="ID of the target node"),
    max_depth: int = Query(3, ge=1, le=5, description="Maximum path depth/length"),
    principal: CanonicalPrincipal = Depends(get_canonical_principal)
):
    try:
        path = await GraphService.get_path(
            start_node_id=start_node_id,
            end_node_id=end_node_id,
            max_depth=max_depth,
            principal=principal
        )
        if not path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No path found between node '{start_node_id}' and node '{end_node_id}' in active graph version."
            )
        return path
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error finding path: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error finding path: {str(e)}"
        )

@router.get("/subgraph", response_model=SubgraphResponse)
async def get_subgraph(
    node_ids: List[str] = Query(..., description="List of node IDs or comma-separated string of IDs"),
    relationship_types: Optional[List[str]] = Query(None, description="Optional relationship types to filter"),
    principal: CanonicalPrincipal = Depends(get_canonical_principal)
):
    try:
        parsed_ids = []
        for nid in node_ids:
            if "," in nid:
                parsed_ids.extend([x.strip() for x in nid.split(",") if x.strip()])
            else:
                parsed_ids.append(nid.strip())

        parsed_rel_types = []
        if relationship_types:
            for rt in relationship_types:
                if "," in rt:
                    parsed_rel_types.extend([x.strip().upper() for x in rt.split(",") if x.strip()])
                else:
                    parsed_rel_types.append(rt.strip().upper())
        else:
            parsed_rel_types = None

        return await GraphService.get_subgraph(
            node_ids=parsed_ids,
            relationship_types=parsed_rel_types,
            principal=principal
        )
    except Exception as e:
        logger.error(f"Failed to generate subgraph: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate subgraph: {str(e)}"
        )

@router.get("/search", response_model=List[NodeResponse])
async def search_nodes(
    q: str = Query(..., min_length=1, description="Search query string"),
    label: Optional[str] = Query(None, description="Optional label to filter results by"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of results"),
    principal: CanonicalPrincipal = Depends(get_canonical_principal)
):
    if label is not None and label not in VALID_LABELS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid node label: '{label}'. Must be one of: {sorted(VALID_LABELS)}"
        )
    try:
        return await GraphService.search_nodes(q=q, label=label, limit=limit, principal=principal)
    except Exception as e:
        logger.error(f"Search query failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@router.post("/relevance")
async def graph_relevance(
    payload: GraphRelevanceRequest,
    principal: CanonicalPrincipal = Depends(get_canonical_principal),
):
    try:
        relevance = await GraphService.search_relevance(
            payload.query, payload.document_ids, principal=principal
        )
        return {"relevance": relevance}
    except Exception as e:
        logger.error("Graph relevance query failed: %s", str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Graph relevance query failed",
        )

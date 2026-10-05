from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.core.canonical_security import CanonicalPrincipal, get_canonical_principal
from app.schemas.nodes import NodeCreate, NodeUpdate, NodeResponse, NodeListResponse, VALID_LABELS
from app.services.graph_service import GraphService
from app.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/nodes", tags=["Nodes"])

@router.post("", response_model=NodeResponse, status_code=status.HTTP_201_CREATED)
async def create_node(node_in: NodeCreate, principal: CanonicalPrincipal = Depends(get_canonical_principal)):
    try:
        return await GraphService.create_node(node_in, principal)
    except Exception as e:
        logger.error(f"Failed to create node: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create node: {str(e)}"
        )

@router.get("/{id}", response_model=NodeResponse)
async def get_node(id: str, principal: CanonicalPrincipal = Depends(get_canonical_principal)):
    try:
        node = await GraphService.get_node(id, principal)
        if not node:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Node with ID '{id}' not found in active graph version."
            )
        return node
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching node '{id}': {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching node: {str(e)}"
        )

@router.put("/{id}", response_model=NodeResponse)
async def update_node(id: str, node_in: NodeUpdate, principal: CanonicalPrincipal = Depends(get_canonical_principal)):
    try:
        node = await GraphService.update_node(id, node_in, principal)
        if not node:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Node with ID '{id}' not found in active graph version."
            )
        return node
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update node '{id}': {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update node: {str(e)}"
        )

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node(id: str, principal: CanonicalPrincipal = Depends(get_canonical_principal)):
    try:
        deleted = await GraphService.delete_node(id, principal)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Node with ID '{id}' not found in active graph version."
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete node '{id}': {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete node: {str(e)}"
        )

@router.get("", response_model=NodeListResponse)
async def list_nodes(
    label: Optional[str] = Query(None, description="Filter nodes by label type"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    principal: CanonicalPrincipal = Depends(get_canonical_principal)
):
    if label is not None and label not in VALID_LABELS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid node label: '{label}'. Must be one of: {sorted(VALID_LABELS)}"
        )
    try:
        nodes, total = await GraphService.list_nodes(label=label, page=page, size=size, principal=principal)
        return NodeListResponse(nodes=nodes, total=total, page=page, size=size)
    except Exception as e:
        logger.error(f"Failed to list nodes: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list nodes: {str(e)}"
        )

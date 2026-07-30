from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status
from app.schemas.relationships import (
    RelationshipCreate,
    RelationshipResponse,
    RelationshipListResponse,
    VALID_RELATIONSHIP_TYPES,
)
from app.services.graph_service import GraphService
from app.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/relationships", tags=["Relationships"])

@router.post("", response_model=RelationshipResponse, status_code=status.HTTP_201_CREATED)
async def create_relationship(rel_in: RelationshipCreate):
    try:
        rel = await GraphService.create_relationship(rel_in)
        if not rel:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Failed to create relationship: One or both of the specified nodes do not exist in the active graph version."
            )
        return rel
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create relationship: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create relationship: {str(e)}"
        )

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_relationship(id: str):
    try:
        deleted = await GraphService.delete_relationship(id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Relationship with ID '{id}' not found in active graph version."
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete relationship '{id}': {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete relationship: {str(e)}"
        )

@router.get("", response_model=RelationshipListResponse)
async def list_relationships(
    type: Optional[str] = Query(None, description="Filter relationships by type"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page")
):
    if type is not None and type not in VALID_RELATIONSHIP_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid relationship type: '{type}'. Must be one of: {sorted(VALID_RELATIONSHIP_TYPES)}"
        )
    try:
        relationships, total = await GraphService.list_relationships(rel_type=type, page=page, size=size)
        return RelationshipListResponse(relationships=relationships, total=total, page=page, size=size)
    except Exception as e:
        logger.error(f"Failed to list relationships: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list relationships: {str(e)}"
        )

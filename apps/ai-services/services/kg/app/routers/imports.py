from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from app.core.canonical_security import CanonicalPrincipal, get_canonical_principal
from app.schemas.imports import ImportJSONRequest, ImportResponse
from app.services.import_service import ImportService
from app.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/import", tags=["Bulk Import"])

@router.post("/json", response_model=ImportResponse, status_code=status.HTTP_201_CREATED)
async def import_json(req: ImportJSONRequest, principal: CanonicalPrincipal = Depends(get_canonical_principal)):
    try:
        return await ImportService.import_json(req, principal)
    except Exception as e:
        logger.error(f"Bulk JSON import failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bulk JSON import failed: {str(e)}"
        )

@router.post("/csv", response_model=ImportResponse, status_code=status.HTTP_201_CREATED)
async def import_csv(
    nodes_file: Optional[UploadFile] = File(None),
    relationships_file: Optional[UploadFile] = File(None),
    description: Optional[str] = Form(None),
    principal: CanonicalPrincipal = Depends(get_canonical_principal)
):
    if not nodes_file and not relationships_file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of nodes_file or relationships_file must be uploaded."
        )
        
    try:
        nodes_content = None
        if nodes_file:
            nodes_content = (await nodes_file.read()).decode("utf-8")
            
        relationships_content = None
        if relationships_file:
            relationships_content = (await relationships_file.read()).decode("utf-8")
            
        return await ImportService.import_csv(
            nodes_csv_content=nodes_content,
            relationships_csv_content=relationships_content,
            description=description,
            principal=principal
        )
    except Exception as e:
        logger.error(f"Bulk CSV import failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bulk CSV import failed: {str(e)}"
        )

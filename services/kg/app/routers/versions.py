from fastapi import APIRouter, HTTPException, status
from app.schemas.versions import VersionListResponse
from app.services.version_service import VersionNotFoundError, VersionService
from app.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/versions", tags=["Versioning & Rollback"])

@router.get("", response_model=VersionListResponse)
async def list_versions():
    try:
        versions = await VersionService.list_versions()
        return VersionListResponse(versions=versions)
    except Exception as e:
        logger.error(f"Failed to list graph versions: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list graph versions: {str(e)}"
        )

@router.post("/rollback/{version}", status_code=status.HTTP_200_OK)
async def rollback_to_version(version: int):
    try:
        count = await VersionService.rollback_to_version(version)
        return {
            "status": "success",
            "message": f"Graph successfully rolled back to version {version}. Marked {count} newer versions as rolled back.",
            "target_version": version,
            "rolled_back_versions_count": count
        }
    except VersionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to rollback graph to version {version}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rollback graph: {str(e)}"
        )

import io

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_user
from app.document_schemas import DocumentMetadata
from app.parsing import DuplicateDocumentError, parse_document, parser_metrics
from app.schemas import DocumentParseRequest, DocumentParseResponse

router = APIRouter(prefix="/documents", tags=["Documents"])

auth_dependency = Depends(get_current_user)


@router.post("/parse", response_model=DocumentParseResponse)
async def parse_document_endpoint(
    request: DocumentParseRequest,
    auth_payload: dict[str, str] = auth_dependency,
) -> DocumentParseResponse:
    try:
        stream = io.BytesIO(request.content.encode("utf-8"))
        metadata = parse_document(request.format, stream)
    except DuplicateDocumentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return DocumentParseResponse(
        metadata=DocumentMetadata.model_validate(metadata),
        duplicate=False,
        metrics=parser_metrics.snapshot(),
    )

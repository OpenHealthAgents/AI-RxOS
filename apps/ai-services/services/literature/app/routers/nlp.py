from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_user
from app.document_schemas import DocumentMetadata
from app.nlp.pipeline import process_document

router = APIRouter(prefix="/nlp", tags=["NLP"])

auth_dependency = Depends(get_current_user)


@router.post("/process")
async def nlp_process(
    doc: DocumentMetadata,
    auth_payload: dict[str, str] = auth_dependency,
):
    try:
        result = process_document(doc.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result

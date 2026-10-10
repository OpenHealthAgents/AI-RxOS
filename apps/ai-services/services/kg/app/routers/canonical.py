from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import AwareDatetime, BaseModel, Field

from app.core.canonical_security import CanonicalPrincipal, get_canonical_principal
from app.database.canonical_store import canonical_store
from app.schemas.canonical import (
    CanonicalEntityCreate,
    CanonicalEntityPage,
    CanonicalEntityResponse,
    CanonicalRelationshipCreate,
    ClaimCreate,
    ClinicalTrialIngest,
    EntityType,
    EvidenceLinkCreate,
    IdentityResolution,
    LicensingEventIngest,
    ObservationCreate,
    PatentRecordIngest,
    PubMedArticleIngest,
    RegulatoryEventIngest,
    RegulatoryEventType,
)
from app.schemas.decision_governance import (
    DecisionHistoryPage,
    DecisionReviewCreate,
    DecisionSnapshotCreate,
)
from app.services.canonical_repository import (
    CanonicalAuthorizationError,
    CanonicalConflictError,
    CanonicalNotFoundError,
    CanonicalRepository,
)
from app.services.decision_governance import DecisionGovernanceRepository
from app.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/canonical", tags=["Canonical Data"])
repository = CanonicalRepository(canonical_store)
decision_governance_repository = DecisionGovernanceRepository(canonical_store)


class SearchContextRequest(BaseModel):
    entity_ids: list[UUID] = Field(min_length=1, max_length=50)
    as_of: AwareDatetime | None = None


def _require_store() -> None:
    if canonical_store.pool is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="canonical store is unavailable")


def _raise_repository_error(exc: Exception) -> None:
    if isinstance(exc, CanonicalAuthorizationError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if isinstance(exc, CanonicalNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, CanonicalConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    logger.exception("Canonical request failed", exc_info=exc)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="canonical request failed") from exc


@router.post("/decision-snapshots")
async def create_decision_snapshot(
    payload: DecisionSnapshotCreate,
    response: Response,
    principal: CanonicalPrincipal = Depends(get_canonical_principal),
) -> dict[str, Any]:
    _require_store()
    try:
        snapshot, created = await decision_governance_repository.create_snapshot(
            payload, principal
        )
        response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return {"item": snapshot, "created": created}
    except Exception as exc:
        _raise_repository_error(exc)


@router.post("/decision-snapshots/{snapshot_id}/reviews")
async def create_decision_review(
    snapshot_id: UUID,
    payload: DecisionReviewCreate,
    response: Response,
    principal: CanonicalPrincipal = Depends(get_canonical_principal),
) -> dict[str, Any]:
    _require_store()
    try:
        review, created = await decision_governance_repository.create_review(
            snapshot_id, payload, principal
        )
        response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return {"item": review, "created": created}
    except Exception as exc:
        _raise_repository_error(exc)


@router.get("/decision-snapshots/history", response_model=DecisionHistoryPage)
async def get_decision_history(
    asset_id: UUID,
    as_of: AwareDatetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    principal: CanonicalPrincipal = Depends(get_canonical_principal),
) -> DecisionHistoryPage:
    _require_store()
    try:
        items, total = await decision_governance_repository.list_history(
            asset_id,
            principal,
            as_of=as_of,
            page=page,
            page_size=page_size,
        )
        return DecisionHistoryPage(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            as_of=as_of,
        )
    except Exception as exc:
        _raise_repository_error(exc)


@router.post("/search-context")
async def search_context(
    payload: SearchContextRequest,
    principal: CanonicalPrincipal = Depends(get_canonical_principal),
):
    _require_store()
    try:
        return {
            "items": await repository.get_search_context(
                payload.entity_ids, principal, as_of=payload.as_of
            ),
            "as_of": payload.as_of,
        }
    except Exception as exc:
        _raise_repository_error(exc)


@router.get("/entities", response_model=CanonicalEntityPage)
async def list_entities(
    entity_type: EntityType,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    principal: CanonicalPrincipal = Depends(get_canonical_principal),
) -> CanonicalEntityPage:
    _require_store()
    try:
        items, total = await repository.list_entities(entity_type.value, principal, page, page_size)
        return CanonicalEntityPage(items=items, total=total, page=page, page_size=page_size)
    except Exception as exc:
        _raise_repository_error(exc)


@router.post("/entities", response_model=CanonicalEntityResponse, status_code=status.HTTP_201_CREATED)
async def create_entity(
    payload: CanonicalEntityCreate,
    principal: CanonicalPrincipal = Depends(get_canonical_principal),
) -> CanonicalEntityResponse:
    _require_store()
    try:
        return await repository.create_entity(payload, principal)
    except Exception as exc:
        _raise_repository_error(exc)


@router.get("/entities/{entity_id}", response_model=CanonicalEntityResponse)
async def get_entity(
    entity_id: UUID,
    principal: CanonicalPrincipal = Depends(get_canonical_principal),
) -> CanonicalEntityResponse:
    _require_store()
    try:
        return await repository.get_entity(entity_id, principal)
    except Exception as exc:
        _raise_repository_error(exc)


@router.post("/relationships", status_code=status.HTTP_201_CREATED)
async def create_relationship(
    payload: CanonicalRelationshipCreate,
    principal: CanonicalPrincipal = Depends(get_canonical_principal),
):
    _require_store()
    try:
        return await repository.create_relationship(payload, principal)
    except Exception as exc:
        _raise_repository_error(exc)


@router.get("/relationships")
async def list_relationships(
    entity_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(1, ge=1, le=100),
    principal: CanonicalPrincipal = Depends(get_canonical_principal),
):
    _require_store()
    try:
        await repository.get_entity(entity_id, principal)
        items, total = await repository.list_relationships(entity_id, principal, page, page_size)
        return {"items": items, "total": total, "page": page, "page_size": page_size}
    except Exception as exc:
        _raise_repository_error(exc)


@router.post("/observations", status_code=status.HTTP_201_CREATED)
async def create_observation(
    payload: ObservationCreate,
    principal: CanonicalPrincipal = Depends(get_canonical_principal),
):
    _require_store()
    try:
        return await repository.create_observation(payload, principal)
    except Exception as exc:
        _raise_repository_error(exc)


@router.post("/claims", status_code=status.HTTP_201_CREATED)
async def create_claim(
    payload: ClaimCreate,
    principal: CanonicalPrincipal = Depends(get_canonical_principal),
):
    _require_store()
    try:
        return await repository.create_claim(payload, principal)
    except Exception as exc:
        _raise_repository_error(exc)


@router.post("/claims/{claim_id}/evidence", status_code=status.HTTP_201_CREATED)
async def link_claim_evidence(
    claim_id: UUID,
    payload: EvidenceLinkCreate,
    principal: CanonicalPrincipal = Depends(get_canonical_principal),
):
    _require_store()
    try:
        return await repository.link_evidence(claim_id, payload, principal)
    except Exception as exc:
        _raise_repository_error(exc)


@router.get("/entities/{entity_id}/claims")
async def list_claims(
    entity_id: UUID,
    as_of: AwareDatetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    principal: CanonicalPrincipal = Depends(get_canonical_principal),
):
    _require_store()
    try:
        return await repository.list_claims(entity_id, principal, page=page, page_size=page_size, as_of=as_of)
    except Exception as exc:
        _raise_repository_error(exc)


@router.get("/claims/{claim_id}/lineage")
async def get_claim_lineage(
    claim_id: UUID,
    as_of: AwareDatetime | None = None,
    principal: CanonicalPrincipal = Depends(get_canonical_principal),
):
    _require_store()
    try:
        return await repository.get_claim_lineage(claim_id, principal, as_of=as_of)
    except Exception as exc:
        _raise_repository_error(exc)


@router.get("/entities/{entity_id}/observations")
async def list_observations(
    entity_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(1, ge=1, le=100),
    principal: CanonicalPrincipal = Depends(get_canonical_principal),
):
    _require_store()
    try:
        await repository.get_entity(entity_id, principal)
        items, total = await repository.list_observations(entity_id, principal, page, page_size)
        return {"items": items, "total": total, "page": page, "page_size": page_size}
    except Exception as exc:
        _raise_repository_error(exc)


@router.get("/resolve", response_model=IdentityResolution)
async def resolve_identifier(
    namespace: str = Query(min_length=1, max_length=120),
    identifier_type: str = Query(min_length=1, max_length=80),
    value: str = Query(min_length=1, max_length=500),
    principal: CanonicalPrincipal = Depends(get_canonical_principal),
) -> IdentityResolution:
    _require_store()
    try:
        return await repository.resolve_identifier(namespace, identifier_type, value, principal)
    except Exception as exc:
        _raise_repository_error(exc)


@router.get("/resolve-name", response_model=IdentityResolution)
async def resolve_name(
    entity_type: EntityType,
    q: str = Query(min_length=1, max_length=500),
    principal: CanonicalPrincipal = Depends(get_canonical_principal),
) -> IdentityResolution:
    _require_store()
    try:
        return await repository.resolve_name(entity_type.value, q, principal)
    except Exception as exc:
        _raise_repository_error(exc)


@router.post("/reconcile")
async def reconcile_legacy_record(
    payload: dict[str, Any],
    principal: CanonicalPrincipal = Depends(get_canonical_principal),
):
    _require_store()
    try:
        return await repository.reconcile_legacy_record(payload, principal)
    except Exception as exc:
        _raise_repository_error(exc)


@router.post("/pubmed/ingest")
async def ingest_pubmed_article(
    payload: PubMedArticleIngest,
    principal: CanonicalPrincipal = Depends(get_canonical_principal),
):
    _require_store()
    try:
        return await repository.ingest_pubmed_article(payload, principal)
    except Exception as exc:
        _raise_repository_error(exc)


@router.post("/clinicaltrials/ingest")
async def ingest_clinical_trial(
    payload: ClinicalTrialIngest,
    principal: CanonicalPrincipal = Depends(get_canonical_principal),
):
    _require_store()
    try:
        return await repository.ingest_clinical_trial(payload, principal)
    except Exception as exc:
        _raise_repository_error(exc)


@router.post("/regulatory-events/ingest")
async def ingest_regulatory_event(
    payload: RegulatoryEventIngest,
    principal: CanonicalPrincipal = Depends(get_canonical_principal),
):
    _require_store()
    try:
        return await repository.ingest_regulatory_event(payload, principal)
    except Exception as exc:
        _raise_repository_error(exc)


@router.post("/ip/patents/ingest")
async def ingest_patent_record(
    payload: PatentRecordIngest,
    principal: CanonicalPrincipal = Depends(get_canonical_principal),
):
    _require_store()
    try:
        return await repository.ingest_patent_record(payload, principal)
    except Exception as exc:
        _raise_repository_error(exc)


@router.post("/ip/licensing-events/ingest")
async def ingest_licensing_event(
    payload: LicensingEventIngest,
    principal: CanonicalPrincipal = Depends(get_canonical_principal),
):
    _require_store()
    try:
        return await repository.ingest_licensing_event(payload, principal)
    except Exception as exc:
        _raise_repository_error(exc)


@router.get("/ip/history")
async def list_ip_history(
    entity_type: EntityType,
    source_identifier: str | None = Query(default=None, min_length=1, max_length=500),
    as_of: AwareDatetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    principal: CanonicalPrincipal = Depends(get_canonical_principal),
):
    _require_store()
    if entity_type not in {
        EntityType.PATENT, EntityType.PATENT_FAMILY, EntityType.LICENSING_EVENT
    }:
        raise HTTPException(status_code=422, detail="IP history requires an IP entity type")
    try:
        items, total = await repository.list_ip_entities(
            principal,
            entity_type=entity_type,
            source_identifier=source_identifier,
            as_of=as_of,
            page=page,
            page_size=page_size,
        )
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "as_of": as_of,
        }
    except Exception as exc:
        _raise_repository_error(exc)


@router.get("/regulatory-events/history")
async def list_regulatory_event_history(
    event_id: str | None = Query(default=None, min_length=1, max_length=500),
    regulator: str | None = Query(default=None, min_length=1, max_length=200),
    jurisdiction: str | None = Query(default=None, min_length=2, max_length=80),
    event_type: RegulatoryEventType | None = None,
    event_status: str | None = Query(default=None, min_length=1, max_length=120),
    as_of: AwareDatetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    principal: CanonicalPrincipal = Depends(get_canonical_principal),
):
    _require_store()
    try:
        items, total = await repository.list_regulatory_events(
            principal,
            event_id=event_id,
            regulator=regulator,
            jurisdiction=jurisdiction,
            event_type=event_type,
            event_status=event_status,
            as_of=as_of,
            page=page,
            page_size=page_size,
        )
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "as_of": as_of,
        }
    except Exception as exc:
        _raise_repository_error(exc)


def _register_entity_routes(path: str, entity_type: EntityType) -> None:
    async def list_domain_entities(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        principal: CanonicalPrincipal = Depends(get_canonical_principal),
    ) -> CanonicalEntityPage:
        _require_store()
        try:
            items, total = await repository.list_entities(entity_type.value, principal, page, page_size)
            return CanonicalEntityPage(items=items, total=total, page=page, page_size=page_size)
        except Exception as exc:
            _raise_repository_error(exc)

    async def create_domain_entity(
        payload: CanonicalEntityCreate,
        principal: CanonicalPrincipal = Depends(get_canonical_principal),
    ) -> CanonicalEntityResponse:
        if payload.entity_type != entity_type:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"entity_type must be '{entity_type.value}'")
        _require_store()
        try:
            return await repository.create_entity(payload, principal)
        except Exception as exc:
            _raise_repository_error(exc)

    async def get_domain_entity(
        entity_id: UUID,
        principal: CanonicalPrincipal = Depends(get_canonical_principal),
    ) -> CanonicalEntityResponse:
        _require_store()
        try:
            entity = await repository.get_entity(entity_id, principal)
            if entity["entity_type"] != entity_type.value:
                raise CanonicalNotFoundError("canonical entity not found")
            return entity
        except Exception as exc:
            _raise_repository_error(exc)

    router.add_api_route(f"/{path}", list_domain_entities, methods=["GET"], response_model=CanonicalEntityPage, name=f"list_{path}")
    router.add_api_route(f"/{path}", create_domain_entity, methods=["POST"], response_model=CanonicalEntityResponse, status_code=status.HTTP_201_CREATED, name=f"create_{path}")
    router.add_api_route(f"/{path}/{{entity_id}}", get_domain_entity, methods=["GET"], response_model=CanonicalEntityResponse, name=f"get_{path}")


for _path, _entity_type in (
    ("assets", EntityType.THERAPEUTIC_ASSET),
    ("targets", EntityType.TARGET),
    ("diseases", EntityType.DISEASE),
    ("indications", EntityType.INDICATION),
    ("biomarkers", EntityType.BIOMARKER),
    ("companies", EntityType.COMPANY),
    ("trials", EntityType.CLINICAL_TRIAL),
    ("publications", EntityType.PUBLICATION),
    ("patents", EntityType.PATENT),
    ("patent-families", EntityType.PATENT_FAMILY),
    ("licensing-events", EntityType.LICENSING_EVENT),
    ("regulatory-events", EntityType.REGULATORY_EVENT),
    ("mechanisms", EntityType.MECHANISM),
    ("combinations", EntityType.COMBINATION),
    ("resistance-mechanisms", EntityType.RESISTANCE_MECHANISM),
):
    _register_entity_routes(_path, _entity_type)

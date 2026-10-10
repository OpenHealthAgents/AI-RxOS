from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Literal, Protocol
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.opportunity_engine.discover.models import StructuredDiscoverFilters
from app.opportunity_engine.search.engine import SearchEngine
from app.opportunity_engine.search.models import (
    OperatorType,
    SearchMode,
    SearchQueryRequest,
    SearchTargetType,
    StructuredConstraint,
)
from app.opportunity_engine.search.parser import NaturalLanguageSearchParser
from app.opportunity_engine.search.router import get_search_engine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Opportunity Discovery"])

_SUPPORTED_FILTERS = {
    "target",
    "disease",
    "indication",
    "stage",
    "cns_active",
    "company",
    "owner",
}
_AS_OF_RE = re.compile(
    r"\bas\s+of\s+(\d{4}-\d{2}-\d{2}|\d{4})(?![\d-])\b",
    re.IGNORECASE,
)


class DiscoverFilterInput(StructuredDiscoverFilters):
    model_config = ConfigDict(from_attributes=True, extra="forbid", strict=True)

    @field_validator(
        "target",
        "disease",
        "indication",
        "modality",
        "biomarker",
        "mutation",
        "safety",
        "competition",
        "ownership",
        "licensing",
        "commercial_opportunity",
    )
    @classmethod
    def reject_blank_filter_values(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = value.strip()
        if not clean:
            raise ValueError("Filter values must not be empty.")
        return clean

    @field_validator("stage")
    @classmethod
    def reject_blank_stages(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        clean_values = [value.strip() for value in values]
        if any(not value for value in clean_values):
            raise ValueError("Stage filters must not be empty.")
        return clean_values


class DiscoverRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        strict=True,
    )

    query: str = Field(min_length=1, max_length=2000)
    filters: DiscoverFilterInput | None = None
    as_of: date | None = None
    save_as: str | None = Field(default=None, min_length=1, max_length=120)


class ParsedFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    operator: OperatorType
    value: str | int | float | bool | list[str] | list[int] | list[float]
    source_span: str | None = None


class ParsedIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: Literal["asset"]
    entities: dict[str, list[str]] = Field(default_factory=dict)


class DiscoverEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    evidence_type: str
    source_citation: str
    source_url: str | None = None


class CandidateScores(BaseModel):
    model_config = ConfigDict(extra="forbid")

    derived_search_score: float | None
    score_type: Literal["DETERMINISTIC_SEARCH_HEURISTIC"]
    ml_ranking_status: Literal["UNAVAILABLE"]
    ml_ranking_score: float | None = None
    ml_unavailable_reason: str | None = None


class DiscoverCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str
    name: str
    ranking: int
    scores: CandidateScores
    confidence: float | None = None
    confidence_status: Literal["UNKNOWN_UNCALIBRATED"]
    reasons: list[str] = Field(default_factory=list)
    evidence: list[DiscoverEvidence] = Field(default_factory=list)
    evidence_status: Literal["AVAILABLE", "UNKNOWN"]
    unknowns: list[str] = Field(default_factory=list)


class DiscoverResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_id: UUID
    query: str
    tenant_id: str | None = None
    evaluation_cutoff: date | None = None
    status: Literal["AVAILABLE", "UNAVAILABLE"]
    parsed_intent: ParsedIntent
    filters: list[ParsedFilter]
    candidates: list[DiscoverCandidate]
    ranking_status: Literal[
        "AVAILABLE_DERIVED_SEARCH",
        "UNAVAILABLE_POINT_IN_TIME_SEARCH_DATA",
    ]
    ml_ranking_status: Literal["UNAVAILABLE"]
    unknowns: list[str] = Field(default_factory=list)
    saved_search_id: UUID | None = None


class SavedSearchRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    saved_search_id: UUID
    tenant_id: str
    user_id: str
    name: str
    query: str
    filters: list[ParsedFilter]
    as_of: date | None = None
    created_at: datetime


class SavedSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    saved_search_id: UUID
    tenant_id: str
    name: str
    query: str
    filters: list[ParsedFilter]
    as_of: date | None = None
    created_at: datetime


class SavedSearchStore(Protocol):
    def save(self, record: SavedSearchRecord) -> None: ...

    def get(
        self, saved_search_id: UUID, *, tenant_id: str, user_id: str
    ) -> SavedSearchRecord | None: ...


class RedisSavedSearchStore:
    """Stores structured, owner-scoped saved searches in the configured Redis."""

    def __init__(self) -> None:
        self._client: Redis = Redis.from_url(
            get_settings().redis_url,
            decode_responses=True,
        )

    @staticmethod
    def _key(saved_search_id: UUID, tenant_id: str, user_id: str) -> str:
        tenant = quote(tenant_id, safe="")
        user = quote(user_id, safe="")
        return f"discover:saved:{tenant}:{user}:{saved_search_id}"

    def save(self, record: SavedSearchRecord) -> None:
        self._client.set(
            self._key(record.saved_search_id, record.tenant_id, record.user_id),
            record.model_dump_json(),
        )

    def get(
        self, saved_search_id: UUID, *, tenant_id: str, user_id: str
    ) -> SavedSearchRecord | None:
        value = self._client.get(self._key(saved_search_id, tenant_id, user_id))
        if value is None:
            return None
        return SavedSearchRecord.model_validate_json(value)


_saved_search_store: SavedSearchStore | None = None


def get_saved_search_store() -> SavedSearchStore:
    global _saved_search_store
    if _saved_search_store is None:
        _saved_search_store = RedisSavedSearchStore()
    return _saved_search_store


def get_optional_trusted_discover_identity(
    request: Request,
) -> tuple[str, str] | None:
    tenant_id = getattr(request.state, "tenant_id", None)
    user_id = getattr(request.state, "user_id", None)
    if tenant_id is None or user_id is None:
        return None
    if (
        not isinstance(tenant_id, str)
        or not tenant_id.strip()
        or not isinstance(user_id, str)
        or not user_id.strip()
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A trusted tenant and user context is required for saved searches.",
        )
    return tenant_id.strip(), user_id.strip()


def get_trusted_discover_identity(request: Request) -> tuple[str, str]:
    identity = get_optional_trusted_discover_identity(request)
    if identity is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A trusted tenant and user context is required for saved searches.",
        )
    return identity


def _as_of_from_query(query: str) -> date | None:
    match = _AS_OF_RE.search(query)
    if match is None:
        if re.search(r"\bas\s+of\b", query, re.IGNORECASE):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Use an ISO date or year after 'as of'.",
            )
        return None
    raw_date = match.group(1)
    try:
        if len(raw_date) == 4:
            return date(int(raw_date), 12, 31)
        return date.fromisoformat(raw_date)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The as-of date is invalid.",
        ) from exc


def _filters_from_search_constraints(
    query: str,
    explicit_filters: DiscoverFilterInput | None,
) -> tuple[list[ParsedFilter], list[StructuredConstraint]]:
    parsed = NaturalLanguageSearchParser.parse(
        query,
        target_type=SearchTargetType.ASSET,
    )
    constraints = list(parsed.structured_constraints)
    unsupported = sorted(
        {constraint.field for constraint in constraints}
        - _SUPPORTED_FILTERS
    )
    if unsupported:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Discovery cannot safely apply these parsed filters: {unsupported}",
        )

    if explicit_filters is not None:
        values = explicit_filters.model_dump(exclude_unset=True)
        unsupported_explicit = [
            field
            for field, value in values.items()
            if value not in (None, [])
            and field not in {"target", "disease", "indication", "stage", "cns_requirement", "ownership"}
        ]
        if unsupported_explicit:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Discovery cannot safely apply these filters: {sorted(unsupported_explicit)}",
            )
        for field, value in values.items():
            if value in (None, []):
                continue
            if field == "stage":
                if len(value) != 1:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Only one explicit stage filter is supported.",
                    )
                constraint = StructuredConstraint(
                    field="stage",
                    operator=OperatorType.EQUALS,
                    value=value[0],
                )
            elif field == "cns_requirement":
                constraint = StructuredConstraint(
                    field="cns_active",
                    operator=OperatorType.BOOLEAN_IS,
                    value=value,
                )
            elif field == "ownership":
                constraint = StructuredConstraint(
                    field="owner",
                    operator=OperatorType.CONTAINS,
                    value=value,
                )
            else:
                constraint = StructuredConstraint(
                    field=field,
                    operator=(
                        OperatorType.CONTAINS
                        if field in {"disease", "indication"}
                        else OperatorType.EQUALS
                    ),
                    value=value,
                )
            replaced_fields = {constraint.field}
            if constraint.field in {"disease", "indication"}:
                replaced_fields.update({"disease", "indication"})
            elif constraint.field in {"owner", "company"}:
                replaced_fields.update({"owner", "company"})
            constraints = [
                existing
                for existing in constraints
                if existing.field not in replaced_fields
            ]
            constraints.append(constraint)

    if any(constraint.field not in _SUPPORTED_FILTERS for constraint in constraints):
        unsupported_final = sorted(
            {constraint.field for constraint in constraints} - _SUPPORTED_FILTERS
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Discovery cannot safely apply these filters: {unsupported_final}",
        )

    filters = [
        ParsedFilter(
            field=constraint.field,
            operator=constraint.operator,
            value=constraint.value,
            source_span=constraint.source_span,
        )
        for constraint in constraints
    ]
    return filters, constraints


def _search_candidates(
    query: str,
    constraints: list[StructuredConstraint],
    engine: SearchEngine,
) -> list[DiscoverCandidate]:
    result = engine.search(
        SearchQueryRequest(
            query=query,
            target_type=SearchTargetType.ASSET,
            mode=SearchMode.STRUCTURED if constraints else SearchMode.SEMANTIC,
            explicit_constraints=constraints or None,
            limit=100,
        )
    )
    matched = [
        item
        for item in result.items
        if item.semantic_similarity and item.semantic_similarity > 0
        or any(reason != "Semantic query relevance match" for reason in item.match_reasons)
    ]
    candidates: list[DiscoverCandidate] = []
    for ranking, item in enumerate(matched, start=1):
        unknowns = list(item.unknowns)
        if not item.evidence:
            unknowns.append("Supporting evidence is unavailable for this candidate.")
        candidates.append(
            DiscoverCandidate(
                asset_id=item.id,
                name=item.title,
                ranking=ranking,
                scores=CandidateScores(
                    derived_search_score=item.score,
                    score_type="DETERMINISTIC_SEARCH_HEURISTIC",
                    ml_ranking_status="UNAVAILABLE",
                    ml_unavailable_reason=(
                        "A validated opportunity-ranking model and lineage are unavailable."
                    ),
                ),
                confidence=None,
                confidence_status="UNKNOWN_UNCALIBRATED",
                reasons=item.match_reasons,
                evidence=[
                    DiscoverEvidence(
                        evidence_id=evidence.evidence_id,
                        evidence_type=evidence.evidence_type,
                        source_citation=evidence.source_citation,
                        source_url=evidence.source_url,
                    )
                    for evidence in item.evidence
                ],
                evidence_status="AVAILABLE" if item.evidence else "UNKNOWN",
                unknowns=unknowns,
            )
        )
    return candidates


def _save_search(
    *,
    name: str,
    query: str,
    filters: list[ParsedFilter],
    as_of: date | None,
    identity: tuple[str, str],
    store: SavedSearchStore,
) -> UUID:
    tenant_id, user_id = identity
    record = SavedSearchRecord(
        saved_search_id=uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        name=name,
        query=query,
        filters=filters,
        as_of=as_of,
        created_at=datetime.now(timezone.utc),
    )
    store.save(record)
    return record.saved_search_id


@router.post("/discover", response_model=DiscoverResponse)
def discover(
    request_body: DiscoverRequest,
    request: Request,
    engine: SearchEngine = Depends(get_search_engine),
    store: SavedSearchStore = Depends(get_saved_search_store),
    identity: tuple[str, str] | None = Depends(
        get_optional_trusted_discover_identity
    ),
) -> DiscoverResponse:
    query = request_body.query.strip()
    if not query:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query must not be empty.",
        )
    query_as_of = _as_of_from_query(query)
    if (
        query_as_of is not None
        and request_body.as_of is not None
        and query_as_of != request_body.as_of
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The body as_of value conflicts with the query.",
        )
    cutoff = request_body.as_of or query_as_of
    if cutoff is not None and cutoff > datetime.now(timezone.utc).date():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The as-of date cannot be in the future.",
        )

    filters, constraints = _filters_from_search_constraints(
        query,
        request_body.filters,
    )
    tenant_id = identity[0] if identity is not None else getattr(
        request.state, "tenant_id", None
    )
    if tenant_id is not None and (
        not isinstance(tenant_id, str) or not tenant_id.strip()
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid tenant context.",
        )
    tenant_id = tenant_id.strip() if isinstance(tenant_id, str) else None

    saved_search_id = None
    if request_body.save_as is not None:
        if identity is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="A trusted tenant and user context is required for saved searches.",
            )
        try:
            saved_search_id = _save_search(
                name=request_body.save_as,
                query=query,
                filters=filters,
                as_of=cutoff,
                identity=identity,
                store=store,
            )
        except RedisError as exc:
            logger.exception("Redis unavailable while saving discovery query")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Saved-search storage is temporarily unavailable.",
            ) from exc

    historical_unavailable = cutoff is not None
    candidates = (
        []
        if historical_unavailable
        else _search_candidates(query, constraints, engine)
    )
    return DiscoverResponse(
        query_id=uuid4(),
        query=query,
        tenant_id=tenant_id,
        evaluation_cutoff=cutoff,
        status="UNAVAILABLE" if historical_unavailable else "AVAILABLE",
        parsed_intent=ParsedIntent(
            target_type=SearchTargetType.ASSET.value,
            entities=NaturalLanguageSearchParser.parse(
                query,
                target_type=SearchTargetType.ASSET,
            ).extracted_entities,
        ),
        filters=filters,
        candidates=candidates,
        ranking_status=(
            "UNAVAILABLE_POINT_IN_TIME_SEARCH_DATA"
            if historical_unavailable
            else "AVAILABLE_DERIVED_SEARCH"
        ),
        ml_ranking_status="UNAVAILABLE",
        unknowns=(
            [
                "Point-in-time candidate and ranking data are unavailable; "
                "no current data was used for this historical query."
            ]
            if historical_unavailable
            else []
        ),
        saved_search_id=saved_search_id,
    )


@router.get(
    "/discover/saved-searches/{saved_search_id}",
    response_model=SavedSearchResponse,
)
def get_saved_search(
    saved_search_id: UUID,
    identity: tuple[str, str] = Depends(get_trusted_discover_identity),
    store: SavedSearchStore = Depends(get_saved_search_store),
) -> SavedSearchResponse:
    tenant_id, user_id = identity
    try:
        record = store.get(
            saved_search_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
    except RedisError as exc:
        logger.exception("Redis unavailable while retrieving saved discovery query")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Saved-search storage is temporarily unavailable.",
        ) from exc
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saved search not found.",
        )
    return SavedSearchResponse(
        saved_search_id=record.saved_search_id,
        tenant_id=record.tenant_id,
        name=record.name,
        query=record.query,
        filters=record.filters,
        as_of=record.as_of,
        created_at=record.created_at,
    )

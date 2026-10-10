from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated, Any, Generic, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, ConfigDict, Field

from app.opportunity_engine.biology.models import BiologyIntelligence
from app.opportunity_engine.biology.router import get_asset_biology_intelligence
from app.opportunity_engine.clinical.models import ClinicalIntelligence
from app.opportunity_engine.clinical.router import get_asset_clinical_intelligence
from app.opportunity_engine.cns.models import CNSIntelligence
from app.opportunity_engine.cns.router import get_asset_cns_intelligence
from app.opportunity_engine.combination.router import get_asset_combination_intelligence
from app.opportunity_engine.commercial.models import CommercialOpportunityProfile
from app.opportunity_engine.commercial.router import get_asset_commercial_profile
from app.opportunity_engine.competitive.models import CompetitiveIntelligenceProfile
from app.opportunity_engine.competitive.router import get_asset_competitive_profile
from app.opportunity_engine.data.fixtures import get_fixture_asset, list_fixture_assets
from app.opportunity_engine.decision.engine import MasterDecisionEngine
from app.opportunity_engine.decision.models import DecisionResult
from app.opportunity_engine.decision.action import ActionIntelligence, ActionResult
from app.opportunity_engine.decision.why import WhyEngine, WhyResult
from app.opportunity_engine.domain.schemas import AssetIntelligence
from app.opportunity_engine.evidence.models import Evidence
from app.opportunity_engine.evidence.service import EvidenceService
from app.opportunity_engine.intelligence import (
    IntelligenceValue,
    IntelligenceValueStatus,
)
from app.opportunity_engine.intelligence_47_49 import (
    CombinationIntelligence,
    PatientMatchIntelligence,
    ResistanceIntelligence,
)
from app.opportunity_engine.licensing.models import AssetOwnershipProfile
from app.opportunity_engine.licensing.service import OwnershipAndLicensingService
from app.opportunity_engine.patient_match.router import (
    get_asset_patient_match_intelligence,
)
from app.opportunity_engine.resistance.router import get_asset_resistance_intelligence
from app.opportunity_engine.request_context import _trusted_tenant_id
from app.opportunity_engine.safety.models import SafetyIntelligenceProfile
from app.opportunity_engine.safety.router import get_asset_safety_profile
from app.opportunity_engine.temporal.engine import TemporalIntelligenceEngine
from app.opportunity_engine.temporal.models import HistoricalTimelineItem

router = APIRouter(prefix="/api/assets", tags=["Core Asset APIs"])

T = TypeVar("T")
_ASSET_ID = Path(
    ...,
    alias="id",
    min_length=1,
    max_length=128,
    pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
)
_decision_engine = MasterDecisionEngine()
_why_engine = WhyEngine()
_action_intelligence = ActionIntelligence()
_evidence_service = EvidenceService()
_licensing_service = OwnershipAndLicensingService()
_temporal_engine = TemporalIntelligenceEngine()

_EVIDENCE_ASSET_IDS: dict[str, UUID] = {
    "zongertinib": UUID("33333333-3333-3333-3333-333333333333"),
    "tucatinib": UUID("44444444-4444-4444-4444-444444444444"),
    "neratinib": UUID("55555555-5555-5555-5555-555555555555"),
    "poziotinib": UUID("66666666-6666-6666-6666-666666666666"),
}
_LICENSING_ASSET_IDS: dict[str, UUID] = {
    "zongertinib": UUID("00000000-0000-0000-0000-000000000001"),
    "tucatinib": UUID("11111111-1111-1111-1111-111111111111"),
    "poziotinib": UUID("33333333-3333-3333-3333-333333333333"),
}


def _current_date() -> date:
    return datetime.now(timezone.utc).date()


class AssetResource(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    asset_id: str
    tenant_id: str | None = None
    asset: AssetIntelligence


class AssetCatalogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tenant_id: str | None = None
    assets: list[AssetIntelligence]


class AssetDomainResponse(BaseModel, Generic[T]):
    model_config = ConfigDict(from_attributes=True)

    asset_id: str
    tenant_id: str | None = None
    evaluation_cutoff: date | None = None
    status: IntelligenceValueStatus
    data: T | None = None
    reason: str | None = None


class AssetEvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    asset_id: str
    tenant_id: str | None = None
    cutoff: date | None = None
    status: IntelligenceValueStatus
    evidence: list[Evidence] = Field(default_factory=list)


class AssetHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    asset_id: str
    tenant_id: str | None = None
    as_of: date
    evidence: list[Evidence] = Field(default_factory=list)
    milestones: list[HistoricalTimelineItem] = Field(default_factory=list)


class AssetEvaluationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    asset_id: str
    tenant_id: str | None = None
    evaluation_cutoff: date
    biology: AssetDomainResponse[BiologyIntelligence]
    clinical: AssetDomainResponse[ClinicalIntelligence]
    cns: AssetDomainResponse[CNSIntelligence]
    patients: AssetDomainResponse[PatientMatchIntelligence]
    safety: AssetDomainResponse[SafetyIntelligenceProfile]
    resistance: AssetDomainResponse[ResistanceIntelligence]
    combinations: AssetDomainResponse[CombinationIntelligence]
    competitive: AssetDomainResponse[CompetitiveIntelligenceProfile]
    licensing: AssetDomainResponse[AssetOwnershipProfile]
    commercial: AssetDomainResponse[CommercialOpportunityProfile]
    decision: DecisionResult
    why: WhyResult
    action_intelligence: ActionResult


def _require_asset(asset_id: str) -> AssetIntelligence:
    asset = get_fixture_asset(asset_id.lower())
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset '{asset_id}' not found.",
        )
    return asset


def _domain_response(
    asset_id: str,
    tenant_id: str | None,
    cutoff: date | None,
    data: T | None,
    *,
    response_status: IntelligenceValueStatus | None = None,
    reason: str | None = None,
) -> AssetDomainResponse[T]:
    return AssetDomainResponse(
        asset_id=asset_id,
        tenant_id=tenant_id,
        evaluation_cutoff=cutoff,
        status=response_status
        or (
            IntelligenceValueStatus.AVAILABLE
            if data is not None
            else IntelligenceValueStatus.UNKNOWN
        ),
        data=data,
        reason=reason,
    )


def _intelligence_signal(value: IntelligenceValue) -> dict[str, Any]:
    """Preserve the upstream epistemic state and lineage for Prompt 54."""
    return {
        "value": value.value,
        "status": value.status.value,
        "confidence": value.confidence,
        "reason": value.reason,
        "supporting_evidence": [
            evidence.model_dump(mode="json") for evidence in value.supporting_evidence
        ],
        "provenance": value.provenance,
        "epistemic_class": value.epistemic_class.value,
        "model_version": value.provenance.get("model_version"),
        "feature_version": value.provenance.get("feature_version"),
    }


def _numeric_profile_signal(
    value: Any,
    *,
    confidence: float | None = None,
    reason: str | None = None,
    evidence: list[str] | None = None,
) -> dict[str, Any]:
    if value is None or isinstance(value, bool):
        return {
            "status": IntelligenceValueStatus.UNKNOWN.value,
            "value": None,
            "confidence": confidence,
            "reason": reason or "No supported numeric signal is available.",
            "supporting_evidence": evidence or [],
        }
    return {
        "status": IntelligenceValueStatus.AVAILABLE.value,
        "value": value,
        "confidence": confidence,
        "reason": reason,
        "supporting_evidence": evidence or [],
    }


def _evaluate_components(
    asset_id: str,
    tenant_id: str | None,
    cutoff: date,
) -> dict[str, Any]:
    _require_asset(asset_id)
    biology = get_asset_biology_intelligence(
        asset_id, prediction_cutoff=cutoff, tenant_id=tenant_id
    )
    clinical = get_asset_clinical_intelligence(
        asset_id, prediction_cutoff=cutoff, tenant_id=tenant_id
    )
    cns = get_asset_cns_intelligence(
        asset_id, prediction_cutoff=cutoff, tenant_id=tenant_id
    )
    patients = get_asset_patient_match_intelligence(
        asset_id, prediction_cutoff=cutoff, tenant_id=tenant_id
    )
    safety = (
        get_asset_safety_profile(asset_id)
        if cutoff >= _current_date()
        else None
    )
    resistance = get_asset_resistance_intelligence(
        asset_id, prediction_cutoff=cutoff, tenant_id=tenant_id
    )
    combinations = get_asset_combination_intelligence(
        asset_id, prediction_cutoff=cutoff, tenant_id=tenant_id
    )
    competitive = (
        get_asset_competitive_profile(asset_id)
        if cutoff >= _current_date()
        else None
    )
    licensing_id = _LICENSING_ASSET_IDS.get(asset_id.lower())
    licensing = (
        _licensing_service.get_ownership_profile(licensing_id, cutoff_date=cutoff)
        if licensing_id is not None
        else None
    )
    commercial = (
        get_asset_commercial_profile(asset_id)
        if cutoff >= _current_date()
        else None
    )
    return {
        "biology": biology,
        "clinical": clinical,
        "cns": cns,
        "patients": patients,
        "safety": safety,
        "resistance": resistance,
        "combinations": combinations,
        "competitive": competitive,
        "licensing": licensing,
        "commercial": commercial,
    }


def _decision_and_why(
    asset_id: str,
    tenant_id: str | None,
    cutoff: date,
    components: dict[str, Any],
) -> tuple[DecisionResult, WhyResult]:
    biology: BiologyIntelligence = components["biology"]
    clinical: ClinicalIntelligence = components["clinical"]
    cns: CNSIntelligence = components["cns"]
    patients: PatientMatchIntelligence = components["patients"]
    safety: SafetyIntelligenceProfile | None = components["safety"]
    resistance: ResistanceIntelligence = components["resistance"]
    competitive: CompetitiveIntelligenceProfile | None = components["competitive"]
    licensing: AssetOwnershipProfile | None = components["licensing"]
    commercial: CommercialOpportunityProfile | None = components["commercial"]

    cns_decision_value = cns.predicted_cns_potential

    resistance_risk = resistance.predicted_resistance_risk
    if resistance_risk.status == IntelligenceValueStatus.AVAILABLE:
        resistance_signal = {
            "status": IntelligenceValueStatus.UNKNOWN.value,
            "value": None,
            "confidence": resistance_risk.confidence,
            "reason": (
                "The resistance-risk prediction cannot be interpreted as a "
                "positive-direction resistance score by the existing decision policy."
            ),
            "supporting_evidence": [
                item.model_dump(mode="json")
                for item in resistance_risk.supporting_evidence
            ],
            "model_version": resistance_risk.provenance.get("model_version"),
            "feature_version": resistance_risk.provenance.get("feature_version"),
            "epistemic_class": resistance_risk.epistemic_class.value,
            "provenance": resistance_risk.provenance,
        }
    else:
        resistance_signal = _intelligence_signal(resistance_risk)

    competition_signal = _numeric_profile_signal(None, reason="No comparable positive-direction competitive score is exposed.")
    if competitive is not None:
        differentiation = getattr(
            getattr(competitive, "differentiation", None),
            "differentiation_score",
            None,
        )
        competition_signal = _numeric_profile_signal(
            differentiation,
            evidence=list(competitive.evidence_citations),
            reason="Competitive differentiation score from the existing competitive engine.",
        )

    commercial_signal = _numeric_profile_signal(None, reason="Commercial score is unavailable.")
    if commercial is not None:
        commercial_signal = _numeric_profile_signal(
            getattr(commercial, "commercial_opportunity_score", None),
            confidence=getattr(commercial, "commercial_confidence", None),
            reason="Commercial opportunity score from the existing commercial engine.",
        )

    # The licensing profile is categorical ownership/deal evidence, not a numerical
    # availability score. Keep it UNKNOWN rather than inventing a score or deal status.
    licensing_signal = {
        "status": IntelligenceValueStatus.UNKNOWN.value,
        "value": None,
        "confidence": None,
        "reason": (
            "Licensing availability is not represented by a numeric score; "
            "the ownership profile must not be converted into an availability claim."
            if licensing is not None
            else "No licensing profile is available for this asset."
        ),
        "supporting_evidence": (
            [licensing.licensing_verification_source]
            if licensing is not None and licensing.licensing_verification_source
            else []
        ),
    }

    # CNS exposure is not a clinical efficacy score. Only a model-derived potential
    # explicitly exposed as an available score is passed to the decision engine.
    inputs: dict[str, Any] = {
        "biology": _intelligence_signal(biology.biology_validation),
        "clinical": _intelligence_signal(clinical.clinical_readiness),
        "cns": _intelligence_signal(cns_decision_value),
        "patient": _intelligence_signal(patients.patient_match_score),
        "safety": (
            {
                "status": IntelligenceValueStatus.INSUFFICIENT_EVIDENCE.value,
                "value": None,
                "confidence": None,
                "reason": "Safety engine has no historical as-of evaluation; safety is unavailable for this cutoff.",
            }
            if safety is None
            else (
                {
                    "status": IntelligenceValueStatus.INSUFFICIENT_EVIDENCE.value,
                    "value": None,
                    "confidence": safety.safety_confidence,
                    "reason": "Safety profile explicitly reports missing evidence.",
                    "supporting_evidence": safety.evidence_citations,
                }
                if safety.has_missing_evidence
                else _numeric_profile_signal(
                    safety.safety_score,
                    confidence=safety.safety_confidence,
                    reason="Safety score from the existing safety engine.",
                    evidence=[
                        str(item.get("source_reference") or item.get("citation"))
                        for item in safety.evidence_citations
                        if item.get("source_reference") or item.get("citation")
                    ],
                )
            )
        ),
        "resistance": resistance_signal,
        "combination": {
            "status": IntelligenceValueStatus.UNKNOWN.value,
            "value": None,
            "confidence": None,
            "reason": "The combination engine does not expose a single comparable decision score.",
            "supporting_evidence": [],
        },
        "competition": competition_signal,
        "licensing": licensing_signal,
        "commercial": commercial_signal,
        "evidence_quality": {
            "status": IntelligenceValueStatus.UNKNOWN.value,
            "value": None,
            "confidence": None,
            "reason": "No single comparable evidence-quality score is available from the evaluated profiles.",
        },
        "ml_predictions": {
            "status": IntelligenceValueStatus.UNAVAILABLE.value,
            "value": None,
            "confidence": None,
            "reason": "No single cross-domain ML prediction is defined by the existing engines.",
        },
    }
    decision = _decision_engine.evaluate(
        asset_id=asset_id,
        tenant_id=tenant_id,
        evaluation_cutoff=cutoff,
        **inputs,
    )
    why = _why_engine.explain(decision, inputs=inputs)
    return decision, why


@router.get("", response_model=AssetCatalogResponse)
def list_assets(
    tenant_id: str | None = Depends(_trusted_tenant_id),
) -> AssetCatalogResponse:
    """List globally visible assets from the existing registered asset catalog."""
    return AssetCatalogResponse(
        tenant_id=tenant_id,
        assets=list_fixture_assets(),
    )


@router.get("/{id}", response_model=AssetResource)
def get_asset(
    asset_id: str = _ASSET_ID,
    tenant_id: str | None = Depends(_trusted_tenant_id),
) -> AssetResource:
    asset = _require_asset(asset_id)
    return AssetResource(asset_id=asset.id, tenant_id=tenant_id, asset=asset)


@router.get("/{id}/evaluate", response_model=AssetEvaluationResponse)
def evaluate_asset(
    asset_id: str = _ASSET_ID,
    tenant_id: str | None = Depends(_trusted_tenant_id),
    cutoff: Annotated[date | None, Query()] = None,
) -> AssetEvaluationResponse:
    cutoff = cutoff or _current_date()
    components = _evaluate_components(asset_id, tenant_id, cutoff)
    decision, why = _decision_and_why(asset_id, tenant_id, cutoff, components)
    action_intelligence = _action_intelligence.rank_actions(decision, why)
    return AssetEvaluationResponse(
        asset_id=asset_id,
        tenant_id=tenant_id,
        evaluation_cutoff=cutoff,
        biology=_domain_response(asset_id, tenant_id, cutoff, components["biology"]),
        clinical=_domain_response(asset_id, tenant_id, cutoff, components["clinical"]),
        cns=_domain_response(asset_id, tenant_id, cutoff, components["cns"]),
        patients=_domain_response(asset_id, tenant_id, cutoff, components["patients"]),
        safety=_domain_response(
            asset_id,
            tenant_id,
            cutoff,
            components["safety"],
            response_status=(
                IntelligenceValueStatus.UNAVAILABLE
                if cutoff < _current_date()
                else (
                    IntelligenceValueStatus.INSUFFICIENT_EVIDENCE
                    if components["safety"] is not None
                    and components["safety"].has_missing_evidence
                    else None
                )
            ),
            reason=(
                "The existing safety engine does not provide historical as-of reconstruction."
                if cutoff < _current_date()
                else (
                    "; ".join(components["safety"].missing_evidence_details)
                    if components["safety"] is not None
                    and components["safety"].has_missing_evidence
                    else None
                )
            ),
        ),
        resistance=_domain_response(asset_id, tenant_id, cutoff, components["resistance"]),
        combinations=_domain_response(asset_id, tenant_id, cutoff, components["combinations"]),
        competitive=_domain_response(
            asset_id,
            tenant_id,
            cutoff,
            components["competitive"],
            response_status=(
                IntelligenceValueStatus.UNAVAILABLE
                if cutoff < _current_date()
                else None
            ),
            reason=(
                "The existing competitive engine does not provide historical as-of reconstruction."
                if cutoff < _current_date()
                else None
            ),
        ),
        licensing=_domain_response(
            asset_id,
            tenant_id,
            cutoff,
            components["licensing"],
            reason=(
                None
                if components["licensing"] is not None
                else "No ownership/licensing profile is registered for this asset."
            ),
        ),
        commercial=_domain_response(
            asset_id,
            tenant_id,
            cutoff,
            components["commercial"],
            response_status=(
                IntelligenceValueStatus.UNAVAILABLE
                if cutoff < _current_date()
                else None
            ),
            reason=(
                "The existing commercial engine does not provide historical as-of reconstruction."
                if cutoff < _current_date()
                else None
            ),
        ),
        decision=decision,
        why=why,
        action_intelligence=action_intelligence,
    )


@router.get("/{id}/biology", response_model=AssetDomainResponse[BiologyIntelligence])
def get_biology(
    asset_id: str = _ASSET_ID,
    tenant_id: str | None = Depends(_trusted_tenant_id),
    cutoff: Annotated[date | None, Query()] = None,
) -> AssetDomainResponse[BiologyIntelligence]:
    _require_asset(asset_id)
    cutoff = cutoff or _current_date()
    result = get_asset_biology_intelligence(asset_id, prediction_cutoff=cutoff, tenant_id=tenant_id)
    return _domain_response(asset_id, tenant_id, cutoff, result)


@router.get("/{id}/clinical", response_model=AssetDomainResponse[ClinicalIntelligence])
def get_clinical(
    asset_id: str = _ASSET_ID,
    tenant_id: str | None = Depends(_trusted_tenant_id),
    cutoff: Annotated[date | None, Query()] = None,
) -> AssetDomainResponse[ClinicalIntelligence]:
    _require_asset(asset_id)
    cutoff = cutoff or _current_date()
    result = get_asset_clinical_intelligence(asset_id, prediction_cutoff=cutoff, tenant_id=tenant_id)
    return _domain_response(asset_id, tenant_id, cutoff, result)


@router.get("/{id}/cns", response_model=AssetDomainResponse[CNSIntelligence])
def get_cns(
    asset_id: str = _ASSET_ID,
    tenant_id: str | None = Depends(_trusted_tenant_id),
    cutoff: Annotated[date | None, Query()] = None,
) -> AssetDomainResponse[CNSIntelligence]:
    _require_asset(asset_id)
    cutoff = cutoff or _current_date()
    result = get_asset_cns_intelligence(asset_id, prediction_cutoff=cutoff, tenant_id=tenant_id)
    return _domain_response(asset_id, tenant_id, cutoff, result)


@router.get("/{id}/patients", response_model=AssetDomainResponse[PatientMatchIntelligence])
def get_patients(
    asset_id: str = _ASSET_ID,
    tenant_id: str | None = Depends(_trusted_tenant_id),
    cutoff: Annotated[date | None, Query()] = None,
) -> AssetDomainResponse[PatientMatchIntelligence]:
    _require_asset(asset_id)
    cutoff = cutoff or _current_date()
    result = get_asset_patient_match_intelligence(asset_id, prediction_cutoff=cutoff, tenant_id=tenant_id)
    return _domain_response(asset_id, tenant_id, cutoff, result)


@router.get("/{id}/safety", response_model=AssetDomainResponse[SafetyIntelligenceProfile])
def get_safety(
    asset_id: str = _ASSET_ID,
    tenant_id: str | None = Depends(_trusted_tenant_id),
) -> AssetDomainResponse[SafetyIntelligenceProfile]:
    _require_asset(asset_id)
    result = get_asset_safety_profile(asset_id)
    return _domain_response(
        asset_id,
        tenant_id,
        None,
        result,
        response_status=(
            IntelligenceValueStatus.INSUFFICIENT_EVIDENCE
            if result.has_missing_evidence
            else None
        ),
        reason=(
            "; ".join(result.missing_evidence_details)
            if result.has_missing_evidence
            else None
        ),
    )


@router.get("/{id}/resistance", response_model=AssetDomainResponse[ResistanceIntelligence])
def get_resistance(
    asset_id: str = _ASSET_ID,
    tenant_id: str | None = Depends(_trusted_tenant_id),
    cutoff: Annotated[date | None, Query()] = None,
) -> AssetDomainResponse[ResistanceIntelligence]:
    _require_asset(asset_id)
    cutoff = cutoff or _current_date()
    result = get_asset_resistance_intelligence(asset_id, prediction_cutoff=cutoff, tenant_id=tenant_id)
    return _domain_response(asset_id, tenant_id, cutoff, result)


@router.get("/{id}/combinations", response_model=AssetDomainResponse[CombinationIntelligence])
def get_combinations(
    asset_id: str = _ASSET_ID,
    tenant_id: str | None = Depends(_trusted_tenant_id),
    cutoff: Annotated[date | None, Query()] = None,
) -> AssetDomainResponse[CombinationIntelligence]:
    _require_asset(asset_id)
    cutoff = cutoff or _current_date()
    result = get_asset_combination_intelligence(asset_id, prediction_cutoff=cutoff, tenant_id=tenant_id)
    return _domain_response(asset_id, tenant_id, cutoff, result)


@router.get("/{id}/competitive", response_model=AssetDomainResponse[CompetitiveIntelligenceProfile])
def get_competitive(
    asset_id: str = _ASSET_ID,
    tenant_id: str | None = Depends(_trusted_tenant_id),
    cutoff: Annotated[date | None, Query()] = None,
) -> AssetDomainResponse[CompetitiveIntelligenceProfile]:
    _require_asset(asset_id)
    cutoff = cutoff or _current_date()
    if cutoff < _current_date():
        return _domain_response(
            asset_id,
            tenant_id,
            cutoff,
            None,
            response_status=IntelligenceValueStatus.UNAVAILABLE,
            reason="The existing competitive engine does not provide historical as-of reconstruction.",
        )
    result = get_asset_competitive_profile(asset_id)
    return _domain_response(asset_id, tenant_id, cutoff, result)


@router.get("/{id}/licensing", response_model=AssetDomainResponse[AssetOwnershipProfile])
def get_licensing(
    asset_id: str = _ASSET_ID,
    tenant_id: str | None = Depends(_trusted_tenant_id),
    cutoff: Annotated[date | None, Query()] = None,
) -> AssetDomainResponse[AssetOwnershipProfile]:
    _require_asset(asset_id)
    cutoff = cutoff or _current_date()
    ownership_id = _LICENSING_ASSET_IDS.get(asset_id.lower())
    result = (
        _licensing_service.get_ownership_profile(ownership_id, cutoff_date=cutoff)
        if ownership_id is not None
        else None
    )
    return _domain_response(
        asset_id,
        tenant_id,
        cutoff,
        result,
        reason=None if result is not None else "No ownership/licensing profile is registered for this asset.",
    )


@router.get("/{id}/commercial", response_model=AssetDomainResponse[CommercialOpportunityProfile])
def get_commercial(
    asset_id: str = _ASSET_ID,
    tenant_id: str | None = Depends(_trusted_tenant_id),
    cutoff: Annotated[date | None, Query()] = None,
) -> AssetDomainResponse[CommercialOpportunityProfile]:
    _require_asset(asset_id)
    cutoff = cutoff or _current_date()
    if cutoff < _current_date():
        return _domain_response(
            asset_id,
            tenant_id,
            cutoff,
            None,
            response_status=IntelligenceValueStatus.UNAVAILABLE,
            reason="The existing commercial engine does not provide historical as-of reconstruction.",
        )
    result = get_asset_commercial_profile(asset_id)
    return _domain_response(asset_id, tenant_id, cutoff, result)


@router.get("/{id}/evidence", response_model=AssetEvidenceResponse)
def get_evidence(
    asset_id: str = _ASSET_ID,
    tenant_id: str | None = Depends(_trusted_tenant_id),
    cutoff: Annotated[date | None, Query()] = None,
) -> AssetEvidenceResponse:
    _require_asset(asset_id)
    evidence_asset_id = _EVIDENCE_ASSET_IDS.get(asset_id.lower())
    evidence = (
        _evidence_service.get_asset_evidence(evidence_asset_id, cutoff_date=cutoff)
        if evidence_asset_id is not None
        else []
    )
    return AssetEvidenceResponse(
        asset_id=asset_id,
        tenant_id=tenant_id,
        cutoff=cutoff,
        status=(
            IntelligenceValueStatus.AVAILABLE
            if evidence
            else IntelligenceValueStatus.UNKNOWN
        ),
        evidence=evidence,
    )


@router.get("/{id}/why", response_model=WhyResult)
def get_why(
    asset_id: str = _ASSET_ID,
    tenant_id: str | None = Depends(_trusted_tenant_id),
    cutoff: Annotated[date | None, Query()] = None,
) -> WhyResult:
    cutoff = cutoff or _current_date()
    components = _evaluate_components(asset_id, tenant_id, cutoff)
    _, why = _decision_and_why(asset_id, tenant_id, cutoff, components)
    return why


@router.get("/{id}/history", response_model=AssetHistoryResponse)
def get_history(
    asset_id: str = _ASSET_ID,
    tenant_id: str | None = Depends(_trusted_tenant_id),
    as_of: Annotated[date | None, Query()] = None,
) -> AssetHistoryResponse:
    _require_asset(asset_id)
    as_of = as_of or _current_date()
    evidence_asset_id = _EVIDENCE_ASSET_IDS.get(asset_id.lower())
    evidence = (
        _evidence_service.get_asset_evidence(evidence_asset_id, cutoff_date=as_of)
        if evidence_asset_id is not None
        else []
    )
    try:
        timeline = _temporal_engine.get_historical_timeline(asset_id.lower())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    milestones = [
        item for item in timeline.milestones if item.prediction_cutoff <= as_of
    ]
    return AssetHistoryResponse(
        asset_id=asset_id,
        tenant_id=tenant_id,
        as_of=as_of,
        evidence=evidence,
        milestones=milestones,
    )


__all__ = [
    "AssetCatalogResponse",
    "AssetDomainResponse",
    "AssetEvaluationResponse",
    "AssetEvidenceResponse",
    "AssetHistoryResponse",
    "AssetResource",
    "router",
]

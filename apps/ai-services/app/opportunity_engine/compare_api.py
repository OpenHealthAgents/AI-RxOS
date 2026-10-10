from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

from app.opportunity_engine.core_api import (
    _current_date,
    _evaluate_components,
    _require_asset,
    _trusted_tenant_id,
)
from app.opportunity_engine.data.fixtures import list_fixture_assets
from app.opportunity_engine.intelligence import (
    IntelligenceValue,
    IntelligenceValueStatus,
)

router = APIRouter(prefix="/api", tags=["Asset Comparison"])

DimensionName = Literal[
    "biology",
    "clinical",
    "cns",
    "patient",
    "safety",
    "resistance",
    "competition",
    "licensing",
    "commercial",
]

AssetIdentifier = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
]


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_ids: list[AssetIdentifier] = Field(min_length=2, max_length=20)
    cutoff: date | None = None

    @field_validator("asset_ids")
    @classmethod
    def asset_ids_must_be_unique(cls, asset_ids: list[str]) -> list[str]:
        normalized = [asset_id.casefold() for asset_id in asset_ids]
        if len(set(normalized)) != len(normalized):
            raise ValueError("Asset IDs must be unique.")
        return asset_ids


class ComparisonMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    status: IntelligenceValueStatus
    raw_value: Any = None
    normalized_value: float | None = None
    normalization: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    epistemic_class: str = "UNKNOWN"
    supporting_evidence: list[dict[str, Any]] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    source_output: dict[str, Any] = Field(default_factory=dict)
    unknowns: list[str] = Field(default_factory=list)
    rationale: str | None = None


class AssetDimensionComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str
    metrics: list[ComparisonMetric]


class DimensionComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: DimensionName
    comparison_metric: str | None = None
    normalized_comparison: list[AssetDimensionComparison]
    winner_asset_id: str | None = None
    winner_status: Literal[
        "WINNER_IDENTIFIED",
        "UNKNOWN",
        "INSUFFICIENT_EVIDENCE",
        "NOT_COMPARABLE",
        "NOT_DISTINGUISHABLE",
    ]
    contradictory_evidence_status: Literal["AVAILABLE", "NOT_CLASSIFIED"] = (
        "NOT_CLASSIFIED"
    )
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    supporting_evidence: list[dict[str, Any]] = Field(default_factory=list)
    contradictory_evidence: list[dict[str, Any]] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    explanation: str


class CompareResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str | None = None
    evaluation_cutoff: date
    asset_ids: list[str]
    dimensions: list[DimensionComparison]


def _json_output(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {}
    return {}


def _profile_unknowns(profile: Any) -> list[str]:
    if profile is None:
        return ["The existing intelligence profile is unavailable."]
    unknowns = getattr(profile, "unknowns", [])
    result = [str(item) for item in unknowns if item]
    excluded = getattr(profile, "excluded_undated_evidence", [])
    if excluded:
        result.append(
            "Undated evidence was excluded by the requested evaluation cutoff."
        )
    return result


def _intelligence_metric(
    name: str,
    signal: IntelligenceValue | None,
    profile: Any,
    *,
    normalization_scale: float | None = None,
    unknowns: list[str] | None = None,
    rationale: str | None = None,
) -> ComparisonMetric:
    profile_data = _json_output(profile)
    if signal is None:
        return ComparisonMetric(
            metric=name,
            status=IntelligenceValueStatus.UNKNOWN,
            source_output=profile_data,
            unknowns=unknowns or _profile_unknowns(profile),
            rationale=rationale or "No comparable intelligence value is available.",
        )

    raw = signal.value
    normalized = None
    normalization = None
    if (
        signal.status == IntelligenceValueStatus.AVAILABLE
        and isinstance(raw, (int, float))
        and not isinstance(raw, bool)
        and normalization_scale is not None
        and normalization_scale > 0.0
        and 0.0 <= float(raw) <= normalization_scale
    ):
        normalized = float(raw) / normalization_scale
        normalization = (
            f"Original 0-{normalization_scale:g} score divided by "
            f"{normalization_scale:g}; raw value is retained."
        )

    evidence = [
        item.model_dump(mode="json")
        for item in signal.supporting_evidence
    ]
    metric_unknowns = list(unknowns or _profile_unknowns(profile))
    if signal.status != IntelligenceValueStatus.AVAILABLE:
        metric_unknowns.append(
            signal.reason or f"{name} is {signal.status.value.lower()}."
        )
    elif not evidence:
        metric_unknowns.append(
            f"{name} has no supporting evidence attached to the intelligence value."
        )

    return ComparisonMetric(
        metric=name,
        status=signal.status,
        raw_value=raw,
        normalized_value=normalized,
        normalization=normalization,
        confidence=signal.confidence,
        epistemic_class=signal.epistemic_class.value,
        supporting_evidence=evidence,
        provenance=signal.provenance,
        source_output=profile_data,
        unknowns=list(dict.fromkeys(metric_unknowns)),
        rationale=signal.reason or rationale,
    )


def _score_metric(
    name: str,
    score: Any,
    *,
    profile: Any,
    confidence: float | None,
    evidence: list[dict[str, Any]],
    unavailable_reason: str | None = None,
    unknowns: list[str] | None = None,
    epistemic_class: str = "DERIVED_FEATURE",
) -> ComparisonMetric:
    profile_data = _json_output(profile)
    status_value = (
        IntelligenceValueStatus.UNAVAILABLE
        if profile is None and unavailable_reason
        else IntelligenceValueStatus.AVAILABLE
        if isinstance(score, (int, float))
        and not isinstance(score, bool)
        and unavailable_reason is None
        else IntelligenceValueStatus.INSUFFICIENT_EVIDENCE
        if unavailable_reason
        else IntelligenceValueStatus.UNKNOWN
    )
    normalized = None
    normalization = None
    if (
        status_value == IntelligenceValueStatus.AVAILABLE
        and 0.0 <= float(score) <= 100.0
    ):
        normalized = float(score) / 100.0
        normalization = "Original 0-100 score divided by 100; raw value is retained."

    metric_unknowns = list(unknowns or _profile_unknowns(profile))
    if unavailable_reason:
        metric_unknowns.append(unavailable_reason)
    if status_value == IntelligenceValueStatus.AVAILABLE and not evidence:
        metric_unknowns.append(
            f"{name} has no source evidence attached to the existing profile."
        )
    return ComparisonMetric(
        metric=name,
        status=status_value,
        raw_value=score,
        normalized_value=normalized,
        normalization=normalization,
        confidence=confidence,
        epistemic_class=epistemic_class,
        supporting_evidence=evidence,
        provenance={},
        source_output=profile_data,
        unknowns=list(dict.fromkeys(metric_unknowns)),
        rationale=unavailable_reason,
    )


def _evidence_from_citations(citations: list[Any], source_type: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for citation in citations:
        if isinstance(citation, dict):
            reference = (
                citation.get("source_reference")
                or citation.get("citation")
                or citation.get("source_id")
            )
            if reference:
                output.append(
                    {
                        "source_type": citation.get("source_type", source_type),
                        "source_reference": str(reference),
                        "confidence": citation.get("confidence"),
                        "provenance": citation.get("provenance", {}),
                    }
                )
        elif citation:
            output.append(
                {
                    "source_type": source_type,
                    "source_reference": str(citation),
                    "confidence": None,
                    "provenance": {},
                }
            )
    return output


def _dimension_metrics(
    dimension: DimensionName,
    profile: Any,
) -> list[ComparisonMetric]:
    if dimension == "biology":
        return [
            _intelligence_metric(
                "biology_validation",
                getattr(profile, "biology_validation", None),
                profile,
                normalization_scale=100.0,
            )
        ]
    if dimension == "clinical":
        return [
            _intelligence_metric(
                "clinical_success_probability",
                getattr(profile, "clinical_success_probability", None),
                profile,
                normalization_scale=1.0,
                rationale=(
                    "Model-derived clinical success probability, when available, "
                    "is retained separately from observed clinical readiness."
                ),
            ),
            _intelligence_metric(
                "clinical_readiness",
                getattr(profile, "clinical_readiness", None),
                profile,
            )
        ]
    if dimension == "cns":
        return [
            _intelligence_metric(
                "cns_exposure_signal",
                getattr(profile, "cns_exposure", None),
                profile,
                rationale="CNS exposure is reported with its original epistemic class and evidence; it is not conflated with predicted potential.",
            ),
            _intelligence_metric(
                "measured_cns_activity",
                getattr(profile, "cns_activity", None),
                profile,
                rationale="CNS activity is reported separately from CNS exposure.",
            ),
            _intelligence_metric(
                "predicted_cns_potential",
                getattr(profile, "predicted_cns_potential", None),
                profile,
                rationale="Prediction is kept separate from measured CNS evidence.",
            ),
            _intelligence_metric(
                "predicted_cns_activity",
                getattr(profile, "predicted_cns_activity", None),
                profile,
                rationale="Predicted activity is kept separate from measured CNS activity.",
            ),
            _intelligence_metric(
                "brain_metastasis_relevance",
                getattr(profile, "brain_metastasis_relevance", None),
                profile,
                rationale=(
                    "Brain-metastasis relevance remains a separate CNS evidence signal."
                ),
            ),
        ]
    if dimension == "patient":
        return [
            _intelligence_metric(
                "patient_match_score",
                getattr(profile, "patient_match_score", None),
                profile,
                normalization_scale=100.0,
            )
        ]
    if dimension == "safety":
        if profile is None:
            return [
                _score_metric(
                    "safety_score",
                    None,
                    profile=None,
                    confidence=None,
                    evidence=[],
                    unavailable_reason="Safety intelligence is unavailable for this cutoff.",
                )
            ]
        citations = _evidence_from_citations(
            getattr(profile, "evidence_citations", []),
            "SAFETY_EVIDENCE",
        )
        missing = bool(getattr(profile, "has_missing_evidence", False))
        missing_details = [
            str(item)
            for item in getattr(profile, "missing_evidence_details", [])
        ]
        return [
            _score_metric(
                "safety_score",
                getattr(profile, "safety_score", None),
                profile=profile,
                confidence=getattr(profile, "safety_confidence", None),
                evidence=citations,
                unavailable_reason=(
                    "The safety profile reports missing evidence; no winner is inferred."
                    if missing
                    else None
                ),
                unknowns=missing_details,
                epistemic_class="DERIVED_FEATURE",
            )
        ]
    if dimension == "resistance":
        if profile is None:
            return [
                _intelligence_metric(
                    "resistance_risk",
                    None,
                    profile,
                )
            ]
        mechanisms = getattr(profile, "top_escape_mechanisms", [])
        evidence = [
            item.model_dump(mode="json")
            for mechanism in mechanisms
            for item in getattr(mechanism, "supporting_evidence", [])
        ]
        return [
            _intelligence_metric(
                "resistance_risk",
                getattr(profile, "predicted_resistance_risk", None),
                profile,
                rationale=(
                    "Resistance risk is retained as reported; the existing engine "
                    "does not establish a cross-asset favorable direction."
                ),
            ),
            ComparisonMetric(
                metric="evidenced_escape_mechanisms",
                status=(
                    IntelligenceValueStatus.AVAILABLE
                    if mechanisms
                    else IntelligenceValueStatus.UNKNOWN
                ),
                raw_value=[
                    mechanism.model_dump(mode="json")
                    for mechanism in mechanisms
                ],
                confidence=None,
                epistemic_class="FACT" if evidence else "UNKNOWN",
                supporting_evidence=evidence,
                source_output=_json_output(profile),
                unknowns=(
                    []
                    if mechanisms
                    else ["No cutoff-valid resistance mechanisms are available."]
                ),
                rationale=(
                    "Mechanisms describe evidence differences, not a ranked resistance outcome."
                ),
            ),
        ]
    if dimension == "competition":
        differentiation = getattr(
            getattr(profile, "differentiation", None),
            "differentiation_score",
            None,
        )
        citations = _evidence_from_citations(
            getattr(profile, "evidence_citations", []),
            "COMPETITIVE_INTELLIGENCE",
        )
        risk = getattr(
            getattr(profile, "competitive_risk", None),
            "risk_score",
            None,
        )
        return [
            _score_metric(
                "differentiation_score",
                differentiation,
                profile=profile,
                confidence=None,
                evidence=citations,
                unavailable_reason=(
                    "Competitive profile is unavailable for this cutoff."
                    if profile is None
                    else None
                ),
            ),
            _score_metric(
                "competitive_risk_score",
                risk,
                profile=profile,
                confidence=None,
                evidence=citations,
                unavailable_reason=(
                    "Competitive risk profile is unavailable for this cutoff."
                    if profile is None
                    else None
                ),
                epistemic_class="DERIVED_FEATURE",
            ),
        ]
    if dimension == "licensing":
        if profile is None:
            return [
                ComparisonMetric(
                    metric="licensing_status",
                    status=IntelligenceValueStatus.UNKNOWN,
                    unknowns=["No ownership/licensing profile is available."],
                )
            ]
        citation = getattr(profile, "licensing_verification_source", None)
        evidence = _evidence_from_citations(
            [citation] if citation else [],
            "LICENSING_VERIFICATION",
        )
        verified = bool(getattr(profile, "licensing_status_verified", False))
        licensing_status = getattr(profile, "licensing_status", None)
        return [
            ComparisonMetric(
                metric="licensing_status",
                status=(
                    IntelligenceValueStatus.AVAILABLE
                    if verified and evidence
                    else IntelligenceValueStatus.UNKNOWN
                ),
                raw_value=(
                    licensing_status.value
                    if hasattr(licensing_status, "value")
                    else licensing_status
                ),
                confidence=None,
                epistemic_class="FACT" if verified and evidence else "UNKNOWN",
                supporting_evidence=evidence,
                source_output=_json_output(profile),
                unknowns=(
                    []
                    if verified and evidence
                    else [
                        "Licensing status is not independently verified with a source; "
                        "availability is not inferred."
                    ]
                ),
                rationale=(
                    "Categorical deal/ownership status is not converted into a comparative score."
                ),
            )
        ]
    if dimension == "commercial":
        if profile is None:
            return [
                _score_metric(
                    "commercial_opportunity_score",
                    None,
                    profile=None,
                    confidence=None,
                    evidence=[],
                    unavailable_reason="Commercial intelligence is unavailable for this cutoff.",
                )
            ]
        assumptions = getattr(profile, "assumptions_audit", [])
        evidence = _evidence_from_citations(
            [
                {
                    "source_type": assumption.provenance.value,
                    "source_reference": assumption.source_citation,
                    "confidence": assumption.confidence,
                }
                for assumption in assumptions
                if getattr(assumption, "source_citation", None)
            ],
            "COMMERCIAL_ASSUMPTION",
        )
        has_unknowns = bool(getattr(profile, "has_unknown_assumptions", False))
        unknown_assumptions = [
            f"{item.key}: {item.parameter_label}"
            for item in assumptions
            if getattr(getattr(item, "provenance", None), "value", None) == "Unknown"
        ]
        return [
            _score_metric(
                "commercial_opportunity_score",
                getattr(profile, "commercial_opportunity_score", None),
                profile=profile,
                confidence=getattr(profile, "commercial_confidence", None),
                evidence=evidence,
                unavailable_reason=(
                    "The commercial profile has unknown assumptions; its score is not "
                    "used to declare a winner."
                    if has_unknowns
                    else None
                ),
                unknowns=unknown_assumptions,
                epistemic_class="DERIVED_FEATURE",
            )
        ]
    raise ValueError(f"Unsupported comparison dimension: {dimension}")


def _make_dimension_comparison(
    dimension: DimensionName,
    asset_ids: list[str],
    profiles: dict[str, Any],
) -> DimensionComparison:
    rows = [
        AssetDimensionComparison(
            asset_id=asset_id,
            metrics=_dimension_metrics(dimension, profiles[asset_id]),
        )
        for asset_id in asset_ids
    ]
    unknowns = list(
        dict.fromkeys(
            unknown
            for row in rows
            for metric in row.metrics
            for unknown in metric.unknowns
        )
    )

    primary_by_dimension: dict[DimensionName, str | None] = {
        "biology": "biology_validation",
        "clinical": "clinical_success_probability",
        "cns": "cns_exposure_signal",
        "patient": "patient_match_score",
        "safety": "safety_score",
        "resistance": None,
        "competition": "differentiation_score",
        "licensing": None,
        "commercial": "commercial_opportunity_score",
    }
    primary = primary_by_dimension[dimension]
    if primary is None:
        status_value: Literal[
            "WINNER_IDENTIFIED",
            "UNKNOWN",
            "INSUFFICIENT_EVIDENCE",
            "NOT_COMPARABLE",
            "NOT_DISTINGUISHABLE",
        ] = "NOT_COMPARABLE" if dimension == "licensing" else "UNKNOWN"
        explanation = (
            "A licensing status is categorical and is not ranked as availability "
            "without an explicitly comparable verified signal."
            if dimension == "licensing"
            else "Resistance mechanisms and risk outputs do not establish a common favorable direction."
        )
        return DimensionComparison(
            dimension=dimension,
            normalized_comparison=rows,
            winner_status=status_value,
            unknowns=unknowns or [explanation],
            explanation=explanation,
            contradictory_evidence_status="NOT_CLASSIFIED",
        )

    selected: list[tuple[str, ComparisonMetric]] = []
    for row in rows:
        metric = next(
            (item for item in row.metrics if item.metric == primary),
            None,
        )
        if metric is not None:
            selected.append((row.asset_id, metric))

    comparable = len(selected) == len(asset_ids) and all(
        metric.status == IntelligenceValueStatus.AVAILABLE
        and metric.normalized_value is not None
        and metric.confidence is not None
        and bool(metric.supporting_evidence)
        and not metric.unknowns
        and (
            dimension != "cns"
            or metric.epistemic_class == "FACT"
        )
        for _, metric in selected
    )
    model_lineages = [
        (
            metric.provenance.get("model_name"),
            metric.provenance.get("model_version"),
            metric.provenance.get("feature_version"),
        )
        for _, metric in selected
        if metric.epistemic_class == "ML_PREDICTION"
    ]
    if model_lineages:
        comparable = comparable and len(model_lineages) == len(selected) and all(
            all(lineage) for lineage in model_lineages
        ) and len(set(model_lineages)) == 1
    if not comparable:
        has_supported_values = any(
            metric.status == IntelligenceValueStatus.AVAILABLE
            and metric.normalized_value is not None
            for _, metric in selected
        )
        return DimensionComparison(
            dimension=dimension,
            comparison_metric=primary,
            normalized_comparison=rows,
            winner_status=(
                "INSUFFICIENT_EVIDENCE"
                if has_supported_values
                else "UNKNOWN"
            ),
            unknowns=unknowns or [
                "A comparable, evidence-backed value with confidence is not available for every asset."
            ],
            explanation=(
                "No winner is selected unless every compared asset has an available, "
                "confidence-bearing, provenance-backed value for the same metric."
            ),
            contradictory_evidence_status="NOT_CLASSIFIED",
        )

    ranked = sorted(
        selected,
        key=lambda pair: pair[1].normalized_value
        if pair[1].normalized_value is not None
        else float("-inf"),
        reverse=True,
    )
    top_value = ranked[0][1].normalized_value
    leaders = [
        asset_id
        for asset_id, metric in ranked
        if metric.normalized_value == top_value
    ]
    evidence = [
        {
            "asset_id": asset_id,
            "evidence": metric.supporting_evidence,
        }
        for asset_id, metric in selected
    ]
    if len(leaders) > 1:
        return DimensionComparison(
            dimension=dimension,
            comparison_metric=primary,
            normalized_comparison=rows,
            winner_status="NOT_DISTINGUISHABLE",
            confidence=min(
                metric.confidence for _, metric in selected
                if metric.confidence is not None
            ),
            supporting_evidence=evidence,
            explanation=(
                "All assets share the same highest normalized value; no unique winner is identified."
            ),
            contradictory_evidence_status="NOT_CLASSIFIED",
        )
    return DimensionComparison(
        dimension=dimension,
        comparison_metric=primary,
        normalized_comparison=rows,
        winner_asset_id=leaders[0],
        winner_status="WINNER_IDENTIFIED",
        confidence=min(
            metric.confidence for _, metric in selected
            if metric.confidence is not None
        ),
        supporting_evidence=evidence,
        explanation=(
            f"{leaders[0]} has the highest comparable {primary} value. "
            "The winner uses only the source-backed normalized values shown."
        ),
        contradictory_evidence_status="NOT_CLASSIFIED",
    )


@router.post("/compare", response_model=CompareResponse)
def compare_assets(
    request: CompareRequest,
    tenant_id: str | None = Depends(_trusted_tenant_id),
) -> CompareResponse:
    cutoff = request.cutoff or _current_date()
    if cutoff > datetime.now(timezone.utc).date():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The evaluation cutoff cannot be in the future.",
        )

    canonical_ids = [asset_id.lower() for asset_id in request.asset_ids]
    assets = {asset.id.lower(): asset for asset in list_fixture_assets()}
    unknown = [asset_id for asset_id in canonical_ids if asset_id not in assets]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"unknown_asset_ids": unknown},
        )

    resolved = {asset_id: _require_asset(asset_id) for asset_id in canonical_ids}
    components_by_asset = {
        asset_id: _evaluate_components(asset_id, tenant_id, cutoff)
        for asset_id in canonical_ids
    }
    dimensions_to_build: list[tuple[DimensionName, str]] = [
        ("biology", "biology"),
        ("clinical", "clinical"),
        ("cns", "cns"),
        ("patient", "patients"),
        ("safety", "safety"),
        ("resistance", "resistance"),
        ("competition", "competitive"),
        ("licensing", "licensing"),
        ("commercial", "commercial"),
    ]
    dimensions = [
        _make_dimension_comparison(
            name,
            canonical_ids,
            {
                asset_id: components_by_asset[asset_id][component]
                for asset_id in canonical_ids
            },
        )
        for name, component in dimensions_to_build
    ]
    return CompareResponse(
        tenant_id=tenant_id,
        evaluation_cutoff=cutoff,
        asset_ids=[asset.id for asset in resolved.values()],
        dimensions=dimensions,
    )

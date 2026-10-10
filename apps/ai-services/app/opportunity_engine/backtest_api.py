from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from typing_extensions import Annotated

from app.ml.models import ModelArtifact, StoredPrediction
from app.ml.pipeline import ValidationPipeline
from app.ml.prediction_store import PredictionStore
from app.ml.registry import ModelRegistry
from app.ml.router import get_shared_ml_backtest_services
from app.opportunity_engine.core_api import _current_date, _trusted_tenant_id
from app.opportunity_engine.data.fixtures import list_fixture_assets
from app.opportunity_engine.temporal.engine import TemporalIntelligenceEngine
from app.opportunity_engine.temporal.models import OutcomeType

router = APIRouter(prefix="/api", tags=["Historical Backtesting"])

AssetIdentifier = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
]

_temporal_engine = TemporalIntelligenceEngine()
_MIN_METRIC_LABELS = 5
_MIN_CALIBRATION_LABELS = 10


class BacktestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_ids: list[AssetIdentifier] = Field(min_length=1, max_length=20)
    cutoff: date
    evaluation_window_end: date | None = None
    model_name: str | None = Field(default=None, min_length=1, max_length=128)
    model_version: str | None = Field(default=None, min_length=1, max_length=128)
    feature_version: str | None = Field(default=None, min_length=1, max_length=128)
    outcome_type: OutcomeType | None = None
    top_k: int = Field(default=5, ge=1, le=20)
    decision_threshold: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("asset_ids")
    @classmethod
    def asset_ids_must_be_unique(cls, asset_ids: list[str]) -> list[str]:
        normalized = [asset_id.casefold() for asset_id in asset_ids]
        if len(set(normalized)) != len(normalized):
            raise ValueError("Asset IDs must be unique.")
        return asset_ids

    @model_validator(mode="after")
    def model_selector_must_be_consistent(self) -> BacktestRequest:
        if self.model_version is not None and self.model_name is None:
            return self
        if self.feature_version is not None and self.model_name is None and self.model_version is None:
            raise ValueError("feature_version requires a model_name or model_version.")
        return self


class BacktestEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    source_type: str
    source_reference: str
    citation: str | None = None
    observed_at: date | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class FeatureLineageItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_name: str
    feature_version: str
    observation_date: date
    prediction_cutoff: date
    evidence_references: list[str]
    provenance: dict[str, Any]


class HistoricalPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["AVAILABLE", "INSUFFICIENT_HISTORY"]
    prediction_id: UUID | None = None
    prediction_type: Literal["MODEL_PREDICTED", "UNKNOWN"]
    model_name: str | None = None
    model_version: str | None = None
    feature_version: str | None = None
    target_name: str | None = None
    predicted_value: float | None = None
    predicted_class: int | None = None
    confidence: float | None = None
    prediction_cutoff: date | None = None
    prediction_timestamp: datetime | None = None
    feature_lineage: list[FeatureLineageItem] = Field(default_factory=list)
    model_lineage: dict[str, Any] = Field(default_factory=dict)
    evidence_references: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    unknowns: list[str] = Field(default_factory=list)


class ObservedOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["AVAILABLE", "UNKNOWN"]
    epistemic_class: Literal["OBSERVED", "UNKNOWN"]
    outcome_type: str | None = None
    headline: str | None = None
    outcome_value: float | None = None
    favorable: bool | None = None
    event_date: date | None = None
    publicly_known_date: date | None = None
    source: str | None = None
    source_url: str | None = None
    evidence_references: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    unknowns: list[str] = Field(default_factory=list)


class PredictionOutcomeComparability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["COMPARABLE", "UNKNOWN", "NOT_COMPARABLE"]
    outcome_value: float | None = None
    outcome_observed_date: date | None = None
    outcome_evidence_references: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    reason: str


class SensitivityAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["AVAILABLE", "UNAVAILABLE"]
    analysis_type: Literal["HYPOTHETICAL_THRESHOLD_SENSITIVITY"]
    decision_threshold: float
    hypothetical_class: int | None = None
    differs_from_stored_class: bool | None = None
    interpretation: str


class BacktestCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str
    asset_name: str
    prediction: HistoricalPrediction
    observed_outcomes: list[ObservedOutcome]
    prediction_outcome: PredictionOutcomeComparability
    sensitivity_analysis: SensitivityAnalysis


class MetricResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    status: Literal["AVAILABLE", "INSUFFICIENT_LABELS", "UNDEFINED", "UNAVAILABLE"]
    value: float | None = None
    sample_count: int
    reason: str | None = None


class BacktestMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label_status: Literal["AVAILABLE", "INSUFFICIENT_LABELS"]
    cutoff: date
    label_count: int
    minimum_required_labels: int
    model_lineage: dict[str, Any] = Field(default_factory=dict)
    outcome_evidence_references: list[str] = Field(default_factory=list)
    metrics: list[MetricResult]


class RankingBacktest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["AVAILABLE", "INSUFFICIENT_HISTORY", "NOT_COMPARABLE"]
    ranked_assets: list[dict[str, Any]] = Field(default_factory=list)
    top_k: int
    numerator: int | None = None
    denominator: int | None = None
    hit_rate: float | None = None
    reason: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class EnrichmentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["AVAILABLE", "INSUFFICIENT_DATA", "NOT_COMPARABLE"]
    numerator: int | None = None
    denominator: int | None = None
    enrichment: float | None = None
    comparison_population: str | None = None
    confidence_status: Literal["NOT_ESTIMATED", "INSUFFICIENT_DATA"]
    reason: str | None = None


class CalibrationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["AVAILABLE", "INSUFFICIENT_LABELS", "UNAVAILABLE"]
    sample_count: int
    model_name: str | None = None
    model_version: str | None = None
    feature_version: str | None = None
    cutoff: date
    brier_score: float | None = None
    expected_calibration_error: float | None = None
    outcome_evidence_references: list[str] = Field(default_factory=list)
    reason: str | None = None


class BacktestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str | None = None
    cutoff: date
    evaluation_window_end: date
    outcome_type: str | None = None
    candidates: list[BacktestCandidate]
    metrics: BacktestMetrics
    ranking: RankingBacktest
    enrichment: EnrichmentResult
    calibration: CalibrationResult
    counterfactual_status: Literal["HYPOTHETICAL_SENSITIVITY_ONLY"]
    unknowns: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


def _eod(value: date) -> datetime:
    return datetime.combine(value, time.max, tzinfo=timezone.utc)


def _resolve_models(
    request: BacktestRequest,
    registry: ModelRegistry,
    tenant_id: str | None,
) -> list[ModelArtifact]:
    visible_models = [
        model
        for model in registry.list_models()
        if model.tenant_id is None or model.tenant_id == tenant_id
    ]
    if request.model_name is not None:
        visible_models = [
            model for model in visible_models if model.name == request.model_name
        ]
    if request.model_version is not None:
        visible_models = [
            model for model in visible_models if model.version == request.model_version
        ]
    if request.feature_version is not None:
        visible_models = [
            model
            for model in visible_models
            if request.feature_version in model.feature_versions
        ]
    if (request.model_name or request.model_version or request.feature_version) and not visible_models:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The requested model/feature version is not registered and compatible in this tenant scope.",
        )
    return visible_models


def _feature_lineage(
    prediction: StoredPrediction,
    model: ModelArtifact,
    cutoff: date,
) -> tuple[list[FeatureLineageItem] | None, list[str]]:
    snapshot = prediction.input_snapshot
    snapshot_cutoff = snapshot.get("prediction_cutoff")
    if not snapshot_cutoff:
        return None, ["Prediction snapshot has no point-in-time cutoff."]
    try:
        snapshot_date = date.fromisoformat(str(snapshot_cutoff))
    except ValueError:
        return None, ["Prediction snapshot cutoff is invalid."]
    if snapshot_date > cutoff:
        return None, ["Prediction feature snapshot is after the requested cutoff."]
    prediction_cutoff = prediction.prediction_cutoff
    if prediction_cutoff is None or prediction_cutoff > cutoff:
        return None, ["Prediction cutoff is missing or after the requested cutoff."]

    observation_dates = snapshot.get("observation_dates")
    if not isinstance(observation_dates, dict):
        return None, ["Prediction has no feature-level temporal lineage."]

    output: list[FeatureLineageItem] = []
    errors: list[str] = []
    for feature_name in model.feature_names:
        metadata = observation_dates.get(feature_name)
        if not isinstance(metadata, dict):
            errors.append(f"Feature '{feature_name}' has no stored lineage.")
            continue
        if metadata.get("provenance_available") is not True:
            errors.append(f"Feature '{feature_name}' provenance is unavailable.")
            continue
        references = metadata.get("evidence_references")
        if not isinstance(references, list) or not references:
            errors.append(f"Feature '{feature_name}' has no evidence references.")
            continue
        if any(str(reference).lower().startswith("test-only:") for reference in references):
            errors.append(f"Feature '{feature_name}' contains test-only evidence.")
            continue
        try:
            observed_at = date.fromisoformat(str(metadata["observation_date"]))
            feature_cutoff = date.fromisoformat(str(metadata["prediction_cutoff"]))
        except (KeyError, TypeError, ValueError):
            errors.append(f"Feature '{feature_name}' has invalid temporal metadata.")
            continue
        feature_version = metadata.get("feature_version")
        if feature_version != prediction.feature_version:
            errors.append(f"Feature '{feature_name}' version does not match prediction.")
            continue
        if observed_at > prediction_cutoff or feature_cutoff > prediction_cutoff:
            errors.append(f"Feature '{feature_name}' contains post-prediction-cutoff data.")
            continue
        if observed_at > cutoff or feature_cutoff > cutoff:
            errors.append(f"Feature '{feature_name}' contains post-request-cutoff data.")
            continue
        if feature_name not in prediction.features_used:
            errors.append(f"Feature '{feature_name}' was not included in the prediction.")
            continue
        output.append(
            FeatureLineageItem(
                feature_name=feature_name,
                feature_version=feature_version,
                observation_date=observed_at,
                prediction_cutoff=feature_cutoff,
                evidence_references=[str(reference) for reference in references],
                provenance=metadata.get("provenance", {}),
            )
        )
    return (output if not errors else None), errors


def _eligible_prediction(
    prediction: StoredPrediction,
    models: list[ModelArtifact],
    request: BacktestRequest,
) -> tuple[ModelArtifact | None, list[FeatureLineageItem] | None, list[str]]:
    cutoff_end = _eod(request.cutoff)
    if prediction.prediction_timestamp.tzinfo is None:
        return None, None, ["Prediction timestamp is not timezone-aware."]
    now = datetime.now(timezone.utc)
    if prediction.prediction_timestamp > min(cutoff_end, now):
        return None, None, ["Prediction was created after the requested cutoff."]
    if prediction.prediction_cutoff is None or prediction.prediction_cutoff > request.cutoff:
        return None, None, ["Prediction cutoff is missing or later than requested cutoff."]
    if prediction.model_version != (request.model_version or prediction.model_version):
        return None, None, ["Prediction model version does not match the requested version."]
    if request.model_name is not None and prediction.model_name != request.model_name:
        return None, None, ["Prediction model name does not match the requested model."]
    if request.feature_version is not None and prediction.feature_version != request.feature_version:
        return None, None, ["Prediction feature version does not match the requested version."]

    model = next(
        (
            item
            for item in models
            if item.model_id == prediction.model_id
            and item.name == prediction.model_name
            and item.version == prediction.model_version
            and prediction.feature_version in item.feature_versions
        ),
        None,
    )
    if model is None:
        return None, None, ["The exact registered model artifact is unavailable or incompatible."]
    if model.registered_at.tzinfo is None or model.registered_at > cutoff_end:
        return None, None, ["The model was not registered by the requested cutoff."]
    if model.training_cutoff is None or model.training_cutoff > prediction.prediction_cutoff:
        return None, None, ["The model training cutoff is unavailable or later than the prediction cutoff."]
    if prediction.prediction_timestamp < model.registered_at:
        return None, None, ["Prediction timestamp precedes model registration."]

    lineage, errors = _feature_lineage(prediction, model, request.cutoff)
    if lineage is None:
        return None, None, errors
    return model, lineage, []


def _outcome_events(
    asset_id: str,
    cutoff: date,
    window_end: date,
    outcome_type: OutcomeType | None,
) -> list[ObservedOutcome]:
    events = _temporal_engine.outcomes.get(asset_id.lower(), [])
    output: list[ObservedOutcome] = []
    for event in events:
        if outcome_type is not None and event.outcome_type != outcome_type:
            continue
        if not cutoff < event.publicly_known_date <= window_end:
            continue
        if event.publicly_known_date > _current_date():
            continue
        if event.event_date > window_end or event.event_date > _current_date():
            continue
        output.append(
            ObservedOutcome(
                status="AVAILABLE",
                epistemic_class="OBSERVED",
                outcome_type=event.outcome_type.value,
                headline=event.headline,
                favorable=event.is_favorable,
                event_date=event.event_date,
                publicly_known_date=event.publicly_known_date,
                source=event.disclosure_source,
                source_url=event.disclosure_url,
                evidence_references=[
                    reference
                    for reference in (
                        event.disclosure_url,
                        event.disclosure_source,
                        str(event.id),
                    )
                    if reference
                ],
                provenance={
                    "event_id": str(event.id),
                    "outcome_date": event.event_date.isoformat(),
                    "publicly_known_date": event.publicly_known_date.isoformat(),
                    "temporal_source": "existing TemporalIntelligenceEngine",
                },
            )
        )
    return sorted(
        output,
        key=lambda item: (
            item.publicly_known_date or date.max,
            item.outcome_type or "",
            item.headline or "",
        ),
    )


def _stored_actual_outcome(
    prediction: StoredPrediction,
    model: ModelArtifact,
    window_end: date,
) -> PredictionOutcomeComparability:
    references = prediction.lineage.get("outcome_evidence_references", [])
    target_name = model.lineage.get("target_name")
    outcome_target = prediction.lineage.get("outcome_target_name")
    observed_date = prediction.outcome_observed_date
    if prediction.actual_outcome is None or observed_date is None:
        return PredictionOutcomeComparability(
            status="UNKNOWN",
            reason="No recorded actual outcome is available for this prediction.",
        )
    if observed_date <= (prediction.prediction_cutoff or date.max):
        return PredictionOutcomeComparability(
            status="NOT_COMPARABLE",
            reason="Outcome observation is not strictly after the prediction cutoff.",
        )
    if observed_date > window_end:
        return PredictionOutcomeComparability(
            status="NOT_COMPARABLE",
            reason="Outcome observation is outside the requested evaluation window.",
        )
    if not isinstance(references, list) or not references:
        return PredictionOutcomeComparability(
            status="UNKNOWN",
            reason="Recorded outcome has no source evidence references.",
        )
    if any(str(reference).lower().startswith("test-only:") for reference in references):
        return PredictionOutcomeComparability(
            status="UNKNOWN",
            reason="Test-only outcome references are not eligible as backtest labels.",
        )
    if not target_name or outcome_target != target_name:
        return PredictionOutcomeComparability(
            status="NOT_COMPARABLE",
            reason="Outcome target lineage does not match the registered model target.",
        )
    if prediction.actual_outcome not in (0.0, 1.0):
        return PredictionOutcomeComparability(
            status="NOT_COMPARABLE",
            reason="Recorded outcome is not a supported binary label.",
        )
    return PredictionOutcomeComparability(
        status="COMPARABLE",
        outcome_value=prediction.actual_outcome,
        outcome_observed_date=observed_date,
        outcome_evidence_references=[str(reference) for reference in references],
        provenance={
            "target_name": target_name,
            "label_version": prediction.lineage.get("label_version"),
            "prediction_id": str(prediction.prediction_id),
        },
        reason="Outcome label is recorded, evidence-backed, temporally valid, and target-compatible.",
    )


def _metric_results(
    predictions: list[BacktestCandidate],
    threshold: float,
    cutoff: date,
) -> BacktestMetrics:
    pairs = [
        candidate
        for candidate in predictions
        if candidate.prediction.status == "AVAILABLE"
        and candidate.prediction_outcome.status == "COMPARABLE"
        and candidate.prediction.predicted_value is not None
        and candidate.prediction_outcome.outcome_value is not None
    ]
    count = len(pairs)
    metrics: list[MetricResult] = []
    model_lineages = {
        (
            candidate.prediction.model_lineage.get("model_id"),
            candidate.prediction.model_name,
            candidate.prediction.model_version,
            candidate.prediction.feature_version,
        )
        for candidate in pairs
    }
    lineage = (
        pairs[0].prediction.model_lineage
        if pairs and len(model_lineages) == 1
        else {}
    )
    outcome_references = sorted(
        {
            reference
            for candidate in pairs
            for reference in candidate.prediction_outcome.outcome_evidence_references
        }
    )
    if len(model_lineages) > 1:
        reason = (
            "Metrics cannot combine predictions from different model or feature versions."
        )
        return BacktestMetrics(
            label_status="INSUFFICIENT_LABELS",
            cutoff=cutoff,
            label_count=count,
            minimum_required_labels=_MIN_METRIC_LABELS,
            model_lineage=lineage,
            outcome_evidence_references=outcome_references,
            metrics=[
                MetricResult(
                    metric=name,
                    status="UNAVAILABLE",
                    sample_count=count,
                    reason=reason,
                )
                for name in (
                    "accuracy",
                    "precision",
                    "recall",
                    "f1",
                    "auroc",
                    "auprc",
                    "brier_score",
                    "log_loss",
                )
            ],
        )
    if count < _MIN_METRIC_LABELS:
        for name in (
            "accuracy",
            "precision",
            "recall",
            "f1",
            "auroc",
            "auprc",
            "brier_score",
            "log_loss",
        ):
            metrics.append(
                MetricResult(
                    metric=name,
                    status="INSUFFICIENT_LABELS",
                    sample_count=count,
                    reason=(
                        f"At least {_MIN_METRIC_LABELS} evidence-backed "
                        f"prediction/outcome pairs are required; found {count}."
                    ),
                )
            )
        return BacktestMetrics(
            label_status="INSUFFICIENT_LABELS",
            cutoff=cutoff,
            label_count=count,
            minimum_required_labels=_MIN_METRIC_LABELS,
            model_lineage=lineage,
            outcome_evidence_references=outcome_references,
            metrics=metrics,
        )

    labels = [
        float(candidate.prediction_outcome.outcome_value)
        for candidate in pairs
        if candidate.prediction_outcome.outcome_value is not None
    ]
    probabilities = [
        float(candidate.prediction.predicted_value)
        for candidate in pairs
        if candidate.prediction.predicted_value is not None
    ]
    measured = ValidationPipeline.evaluate(labels, probabilities, threshold=threshold)
    has_both_classes = 0.0 in labels and 1.0 in labels
    for name, value in (
        ("accuracy", measured.accuracy),
        ("precision", measured.precision),
        ("recall", measured.recall),
        ("f1", measured.f1_score),
        ("auroc", measured.roc_auc if has_both_classes else None),
        ("auprc", measured.auprc if has_both_classes else None),
        ("brier_score", measured.brier_score),
        ("log_loss", measured.log_loss),
    ):
        metrics.append(
            MetricResult(
                metric=name,
                status="AVAILABLE" if value is not None else "UNDEFINED",
                value=value,
                sample_count=count,
                reason=(
                    None
                    if value is not None
                    else "The available label distribution does not support this metric."
                ),
            )
        )
    return BacktestMetrics(
        label_status="AVAILABLE",
        cutoff=cutoff,
        label_count=count,
        minimum_required_labels=_MIN_METRIC_LABELS,
        model_lineage=lineage,
        outcome_evidence_references=outcome_references,
        metrics=metrics,
    )


def _ranking(
    candidates: list[BacktestCandidate],
    top_k: int,
) -> tuple[RankingBacktest, EnrichmentResult]:
    scored = [
        candidate
        for candidate in candidates
        if candidate.prediction.status == "AVAILABLE"
        and candidate.prediction.predicted_value is not None
    ]
    scored.sort(
        key=lambda candidate: (
            -float(candidate.prediction.predicted_value or 0.0),
            candidate.asset_id,
        )
    )
    model_lineages = {
        (
            candidate.prediction.model_lineage.get("model_id"),
            candidate.prediction.model_name,
            candidate.prediction.model_version,
            candidate.prediction.feature_version,
        )
        for candidate in scored
    }
    ranking_provenance = {
        "ranking_population": "eligible stored predictions",
        "model_lineage": scored[0].prediction.model_lineage if scored else {},
        "prediction_ids": sorted(
            str(candidate.prediction.prediction_id) for candidate in scored
        ),
        "outcome_evidence_references": sorted(
            {
                reference
                for candidate in candidates
                for reference in candidate.prediction_outcome.outcome_evidence_references
            }
        ),
    }
    ranked_assets = [
        {
            "asset_id": item.asset_id,
            "rank": index,
            "prediction_id": str(item.prediction.prediction_id),
            "probability": item.prediction.predicted_value,
            "model_version": item.prediction.model_version,
            "feature_version": item.prediction.feature_version,
        }
        for index, item in enumerate(scored, start=1)
    ]
    labels = {
        candidate.asset_id: candidate.prediction_outcome.outcome_value
        for candidate in candidates
        if candidate.prediction_outcome.status == "COMPARABLE"
    }
    if not scored:
        reason = "No eligible historical predictions are available for ranking."
        return (
            RankingBacktest(
                status="INSUFFICIENT_HISTORY",
                ranked_assets=[],
                top_k=top_k,
                reason=reason,
            ),
            EnrichmentResult(
                status="INSUFFICIENT_DATA",
                confidence_status="INSUFFICIENT_DATA",
                reason=reason,
            ),
        )
    if len(model_lineages) > 1:
        reason = (
            "Predictions from different model or feature versions are not ranked together."
        )
        return (
            RankingBacktest(
                status="NOT_COMPARABLE",
                ranked_assets=[],
                top_k=top_k,
                reason=reason,
            ),
            EnrichmentResult(
                status="NOT_COMPARABLE",
                confidence_status="INSUFFICIENT_DATA",
                reason=reason,
            ),
        )
    if len(scored) != len(candidates):
        reason = (
            "The requested cohort has missing historical predictions; ranking "
            "metrics are not reported on an incomplete candidate set."
        )
        return (
            RankingBacktest(
                status="INSUFFICIENT_HISTORY",
                ranked_assets=ranked_assets,
                top_k=top_k,
                reason=reason,
                provenance={
                    **ranking_provenance,
                    "ranking_population": "partial stored prediction cohort",
                },
            ),
            EnrichmentResult(
                status="INSUFFICIENT_DATA",
                confidence_status="INSUFFICIENT_DATA",
                reason=reason,
            ),
        )
    top = scored[: min(top_k, len(scored))]
    if len(labels) != len(scored):
        reason = (
            "Ranking metrics require evidence-backed outcomes for every eligible "
            "ranked asset; missing outcomes are not treated as failures."
        )
        return (
            RankingBacktest(
                status="INSUFFICIENT_HISTORY",
                ranked_assets=ranked_assets,
                top_k=top_k,
                reason=reason,
                provenance={"ranking_population": "eligible stored predictions"},
            ),
            EnrichmentResult(
                status="INSUFFICIENT_DATA",
                confidence_status="INSUFFICIENT_DATA",
                reason=reason,
            ),
        )

    numerator = sum(labels[item.asset_id] == 1.0 for item in top)
    denominator = len(top)
    hit_rate = numerator / denominator if denominator else None
    remainder = scored[len(top) :]
    if not remainder:
        return (
            RankingBacktest(
                status="AVAILABLE",
                ranked_assets=ranked_assets,
                top_k=top_k,
                numerator=numerator,
                denominator=denominator,
                hit_rate=hit_rate,
                provenance=ranking_provenance,
            ),
            EnrichmentResult(
                status="INSUFFICIENT_DATA",
                numerator=numerator,
                denominator=denominator,
                confidence_status="INSUFFICIENT_DATA",
                reason="A separate comparison population is unavailable.",
            ),
        )

    top_rate = numerator / denominator
    other_hits = sum(labels[item.asset_id] == 1.0 for item in remainder)
    other_rate = other_hits / len(remainder)
    enrichment = top_rate / other_rate if other_rate > 0.0 else None
    return (
        RankingBacktest(
            status="AVAILABLE",
            ranked_assets=ranked_assets,
            top_k=top_k,
            numerator=numerator,
            denominator=denominator,
            hit_rate=hit_rate,
            provenance=ranking_provenance,
        ),
        EnrichmentResult(
            status="AVAILABLE" if enrichment is not None else "INSUFFICIENT_DATA",
            numerator=numerator,
            denominator=denominator,
            enrichment=enrichment,
            comparison_population="remaining labeled assets in the requested cohort",
            confidence_status="NOT_ESTIMATED",
            reason=(
                None
                if enrichment is not None
                else "No favorable outcomes occurred in the comparison population; enrichment is undefined."
            ),
        ),
    )


def _calibration(
    candidates: list[BacktestCandidate],
    cutoff: date,
) -> CalibrationResult:
    pairs = [
        candidate
        for candidate in candidates
        if candidate.prediction.status == "AVAILABLE"
        and candidate.prediction_outcome.status == "COMPARABLE"
        and candidate.prediction.predicted_value is not None
        and candidate.prediction_outcome.outcome_value is not None
    ]
    model = next(
        (candidate.prediction for candidate in pairs),
        None,
    )
    model_lineages = {
        (
            candidate.prediction.model_lineage.get("model_id"),
            candidate.prediction.model_name,
            candidate.prediction.model_version,
            candidate.prediction.feature_version,
        )
        for candidate in pairs
    }
    evidence_refs = sorted(
        {
            reference
            for candidate in pairs
            for reference in candidate.prediction_outcome.outcome_evidence_references
        }
    )
    if len(pairs) < _MIN_CALIBRATION_LABELS:
        return CalibrationResult(
            status="INSUFFICIENT_LABELS",
            sample_count=len(pairs),
            model_name=model.model_name if model else None,
            model_version=model.model_version if model else None,
            feature_version=model.feature_version if model else None,
            cutoff=cutoff,
            outcome_evidence_references=evidence_refs,
            reason=(
                f"At least {_MIN_CALIBRATION_LABELS} evidence-backed labels are required "
                f"for calibration; found {len(pairs)}."
            ),
        )
    if len(model_lineages) > 1:
        return CalibrationResult(
            status="UNAVAILABLE",
            sample_count=len(pairs),
            cutoff=cutoff,
            outcome_evidence_references=evidence_refs,
            reason="Calibration cannot combine different model or feature versions.",
        )
    labels = [
        float(item.prediction_outcome.outcome_value)
        for item in pairs
        if item.prediction_outcome.outcome_value is not None
    ]
    probabilities = [
        float(item.prediction.predicted_value)
        for item in pairs
        if item.prediction.predicted_value is not None
    ]
    metrics = ValidationPipeline.evaluate(labels, probabilities)
    ece = ValidationPipeline.expected_calibration_error(labels, probabilities)
    return CalibrationResult(
        status="AVAILABLE",
        sample_count=len(pairs),
        model_name=model.model_name if model else None,
        model_version=model.model_version if model else None,
        feature_version=model.feature_version if model else None,
        cutoff=cutoff,
        brier_score=metrics.brier_score,
        expected_calibration_error=ece,
        outcome_evidence_references=evidence_refs,
    )


def _candidate_prediction(
    asset_id: str,
    request: BacktestRequest,
    tenant_id: str | None,
    models: list[ModelArtifact],
    store: PredictionStore,
) -> tuple[HistoricalPrediction, StoredPrediction | None, ModelArtifact | None]:
    records = store.list_predictions(
        entity_id=asset_id,
        tenant_id=tenant_id,
        model_version=request.model_version,
        feature_version=request.feature_version,
        window_end=_eod(request.cutoff),
        limit=100_000,
    )
    records = [
        item
        for item in records
        if request.model_name is None or item.model_name == request.model_name
    ]
    reasons: list[str] = []
    eligible: list[tuple[StoredPrediction, ModelArtifact, list[FeatureLineageItem]]] = []
    for prediction in records:
        if prediction.asset_id and prediction.asset_id.casefold() != asset_id.casefold():
            reasons.append("Stored prediction canonical asset ID does not match the request.")
            continue
        model, lineage, errors = _eligible_prediction(prediction, models, request)
        if model is not None and lineage is not None:
            eligible.append((prediction, model, lineage))
        else:
            reasons.extend(errors)
    if not eligible:
        return (
            HistoricalPrediction(
                status="INSUFFICIENT_HISTORY",
                prediction_type="UNKNOWN",
                model_name=request.model_name,
                model_version=request.model_version,
                feature_version=request.feature_version,
                unknowns=list(
                    dict.fromkeys(
                        reasons
                        or [
                            "No stored model prediction and point-in-time feature lineage are available."
                        ]
                    )
                ),
            ),
            None,
            None,
        )

    prediction, model, feature_lineage = max(
        eligible,
        key=lambda item: (
            item[0].prediction_timestamp,
            item[0].prediction_cutoff or date.min,
            str(item[0].prediction_id),
        ),
    )
    predicted_value = prediction.probability
    if predicted_value is None:
        predicted_value = prediction.predicted_probability
    if predicted_value is None or not 0.0 <= predicted_value <= 1.0:
        return (
            HistoricalPrediction(
                status="INSUFFICIENT_HISTORY",
                prediction_type="UNKNOWN",
                model_name=model.name,
                model_version=model.version,
                feature_version=prediction.feature_version,
                unknowns=["Stored prediction has no valid probability."],
            ),
            None,
            None,
        )
    target_name = model.lineage.get("target_name")
    evidence_references = sorted(
        {
            reference
            for item in feature_lineage
            for reference in item.evidence_references
        }
    )
    return (
        HistoricalPrediction(
            status="AVAILABLE",
            prediction_id=prediction.prediction_id,
            prediction_type="MODEL_PREDICTED",
            model_name=model.name,
            model_version=model.version,
            feature_version=prediction.feature_version,
            target_name=target_name,
            predicted_value=predicted_value,
            predicted_class=prediction.predicted_class,
            confidence=prediction.confidence,
            prediction_cutoff=prediction.prediction_cutoff,
            prediction_timestamp=prediction.prediction_timestamp,
            feature_lineage=feature_lineage,
            model_lineage={
                "model_id": str(model.model_id),
                "model_name": model.name,
                "model_version": model.version,
                "architecture": model.architecture.value,
                "training_cutoff": model.training_cutoff.isoformat()
                if model.training_cutoff
                else None,
                "registered_at": model.registered_at.isoformat(),
                "dataset_version": model.dataset_version,
                "feature_versions": model.feature_versions,
                "label_versions": model.label_versions,
                "target_name": target_name,
                "artifact_reference": model.artifact_reference,
                "lineage": model.lineage,
            },
            evidence_references=evidence_references,
            provenance={
                "prediction_id": str(prediction.prediction_id),
                "tenant_id": prediction.tenant_id,
                "prediction_cutoff": prediction.prediction_cutoff.isoformat()
                if prediction.prediction_cutoff
                else None,
                "prediction_timestamp": prediction.prediction_timestamp.isoformat(),
                "stored_lineage": prediction.lineage,
            },
        ),
        prediction,
        model,
    )


@router.post("/backtest", response_model=BacktestResponse)
def backtest(
    request: BacktestRequest,
    tenant_id: str | None = Depends(_trusted_tenant_id),
    services: tuple[ModelRegistry, PredictionStore] = Depends(
        get_shared_ml_backtest_services
    ),
) -> BacktestResponse:
    registry, prediction_store = services
    today = _current_date()
    if request.cutoff > today:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The historical cutoff cannot be in the future.",
        )
    default_end = min(request.cutoff + timedelta(days=365), today)
    window_end = request.evaluation_window_end or default_end
    if window_end <= request.cutoff:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The evaluation window end must be after the historical cutoff.",
        )
    if window_end > today:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The evaluation window cannot extend into the future.",
        )

    assets = {asset.id.lower(): asset for asset in list_fixture_assets()}
    normalized_ids = [asset_id.lower() for asset_id in request.asset_ids]
    unknown = [asset_id for asset_id in normalized_ids if asset_id not in assets]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"unknown_asset_ids": unknown},
        )

    models = _resolve_models(request, registry, tenant_id)
    candidates: list[BacktestCandidate] = []
    for asset_id in normalized_ids:
        prediction_result, stored_prediction, model = _candidate_prediction(
            asset_id,
            request,
            tenant_id,
            models,
            prediction_store,
        )
        observed_outcomes = _outcome_events(
            asset_id,
            request.cutoff,
            window_end,
            request.outcome_type,
        )
        if stored_prediction is not None and model is not None:
            prediction_outcome = _stored_actual_outcome(
                stored_prediction,
                model,
                window_end,
            )
        else:
            prediction_outcome = PredictionOutcomeComparability(
                status="UNKNOWN",
                reason=(
                    "No eligible historical model prediction exists to associate "
                    "with an actual outcome."
                ),
            )
        probability = prediction_result.predicted_value
        sensitivity_available = (
            prediction_result.status == "AVAILABLE"
            and probability is not None
        )
        hypothetical_class = (
            1 if probability >= request.decision_threshold else 0
        ) if sensitivity_available else None
        candidates.append(
            BacktestCandidate(
                asset_id=assets[asset_id].id,
                asset_name=assets[asset_id].name,
                prediction=prediction_result,
                observed_outcomes=observed_outcomes
                or [
                    ObservedOutcome(
                        status="UNKNOWN",
                        epistemic_class="UNKNOWN",
                        unknowns=[
                            "No source-backed outcome was observed in the evaluation window."
                        ],
                    )
                ],
                prediction_outcome=prediction_outcome,
                sensitivity_analysis=SensitivityAnalysis(
                    status="AVAILABLE" if sensitivity_available else "UNAVAILABLE",
                    analysis_type="HYPOTHETICAL_THRESHOLD_SENSITIVITY",
                    decision_threshold=request.decision_threshold,
                    hypothetical_class=hypothetical_class,
                    differs_from_stored_class=(
                        hypothetical_class != stored_prediction.predicted_class
                        if sensitivity_available
                        and stored_prediction is not None
                        and stored_prediction.predicted_class is not None
                        else None
                    ),
                    interpretation=(
                        "Hypothetical classification under the requested probability threshold; "
                        "this is sensitivity analysis, not an observed or causal counterfactual."
                        if sensitivity_available
                        else "Sensitivity analysis is unavailable without a valid historical prediction."
                    ),
                ),
            )
        )

    metrics = _metric_results(candidates, request.decision_threshold, request.cutoff)
    ranking, enrichment = _ranking(candidates, request.top_k)
    calibration = _calibration(candidates, request.cutoff)
    return BacktestResponse(
        tenant_id=tenant_id,
        cutoff=request.cutoff,
        evaluation_window_end=window_end,
        outcome_type=request.outcome_type.value if request.outcome_type else None,
        candidates=candidates,
        metrics=metrics,
        ranking=ranking,
        enrichment=enrichment,
        calibration=calibration,
        counterfactual_status="HYPOTHETICAL_SENSITIVITY_ONLY",
        unknowns=[
            "No result is scored unless the historical prediction, matching outcome, "
            "feature lineage, model lineage, and outcome evidence are all available."
        ],
        limitations=[
            "The asset catalog is fixture-backed and the temporal engine uses seeded outcome records; this endpoint is not a validated real-world ML benchmark.",
            "The API retrieves stored predictions only; it does not generate retrospective predictions from current asset state.",
            "Temporal public outcome records are descriptive unless a prediction has a target-compatible, evidence-backed stored label.",
            "Ranking, enrichment, and calibration require evidence-backed labels and remain unavailable when labels are insufficient.",
        ],
    )

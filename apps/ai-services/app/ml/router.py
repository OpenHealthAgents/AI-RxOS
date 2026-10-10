"""
FastAPI Router for Interpretable ML Subsystem.

Provides RESTful endpoints for:
- Training baseline models (Logistic Regression, Random Forest, Gradient Boosting)
- Real-time serving with explainable feature attributions
- Model Registry inspection and stage promotions
- Feature Store definitions retrieval
- Prediction Store audit lookups
- Population Stability Index (PSI) drift monitoring
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .dataset import DatasetBuilder
from .features import FeatureStore
from .models import (
    DriftReport,
    FeatureDefinition,
    InferenceRequest,
    ModelArchitecture,
    ModelArtifact,
    ModelMonitoringReport,
    ModelStage,
    PredictionExplanation,
    StoredPrediction,
)
from .monitoring import DriftDetectionEngine
from .pipeline import TrainingPipeline
from .prediction_store import PredictionStore
from .registry import ModelRegistry
from .serving import ModelServingEngine

router = APIRouter(prefix="/api/v1/ml", tags=["Machine Learning"])

# Singleton shared services for local serving runtime
_feature_store = FeatureStore()
_model_registry = ModelRegistry()
_prediction_store = PredictionStore()
_serving_engine = ModelServingEngine(
    registry=_model_registry,
    feature_store=_feature_store,
    prediction_store=_prediction_store,
)


def get_shared_ml_services() -> tuple[FeatureStore, ModelRegistry]:
    """Return the shared feature store and model registry used by ML serving."""
    return _feature_store, _model_registry


def get_shared_ml_backtest_services() -> tuple[ModelRegistry, PredictionStore]:
    """Return the shared model registry and prediction store for audited backtests."""
    return _model_registry, _prediction_store


# Request schemas for router
class MLTrainRequest(BaseModel):
    dataset_name: str = "oncology_opportunity_v1"
    architecture: ModelArchitecture = ModelArchitecture.LOGISTIC_REGRESSION
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    stage: ModelStage = ModelStage.DEVELOPMENT
    model_name: str | None = None
    model_version: str | None = None


class PromoteModelRequest(BaseModel):
    stage: ModelStage


class DriftEvaluationRequest(BaseModel):
    model_version: str
    feature_version: str | None = None
    current_features: dict[str, list[float]] | None = None


class MonitoringEvaluationRequest(BaseModel):
    model_version: str
    feature_version: str | None = None
    tenant_id: str | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    psi_warning_threshold: float = Field(default=0.10, ge=0.0, lt=1.0)
    psi_critical_threshold: float = Field(default=0.25, gt=0.0, le=1.0)
    missing_rate_delta_threshold: float = Field(default=0.10, ge=0.0, le=1.0)
    performance_drop_threshold: float = Field(default=0.10, ge=0.0, le=1.0)
    calibration_error_threshold: float = Field(default=0.05, ge=0.0, le=1.0)
    min_outcomes: int = Field(default=5, ge=1)


def _resolve_registered_model(
    model_version: str,
    tenant_id: str | None,
) -> ModelArtifact:
    visible = [
        model for model in _model_registry.list_models()
        if model.version == model_version
        and (model.tenant_id is None or model.tenant_id == tenant_id)
    ]
    if len(visible) != 1:
        raise HTTPException(
            status_code=404 if not visible else 409,
            detail="Model version was not found or is ambiguous in the requested tenant scope.",
        )
    return visible[0]


@router.post("/train", response_model=ModelArtifact, status_code=201)
def train_model(req: MLTrainRequest) -> ModelArtifact:
    """Trains an interpretable baseline model on assembled features and ground-truth labels."""
    builder = DatasetBuilder(feature_store=_feature_store)
    dataset = builder.build_dataset(name=req.dataset_name)

    pipeline = TrainingPipeline()
    artifact = pipeline.train(
        dataset=dataset,
        architecture=req.architecture,
        hyperparameters=req.hyperparameters,
        stage=req.stage,
        model_name=req.model_name,
        model_version=req.model_version,
    )
    _model_registry.register(artifact)
    return artifact


@router.post("/predict", response_model=StoredPrediction)
def predict(req: InferenceRequest) -> StoredPrediction:
    """Executes real-time ML inference with local feature attributions and audit persistence."""
    try:
        return _serving_engine.predict(req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/models", response_model=list[ModelArtifact])
def list_models(
    stage: Annotated[ModelStage | None, Query()] = None,
    tenant_id: Annotated[str | None, Query()] = None,
) -> list[ModelArtifact]:
    """Lists registered models with evaluation metrics, optionally filtered by lifecycle stage."""
    return [
        model for model in _model_registry.list_models(stage=stage)
        if model.tenant_id is None or model.tenant_id == tenant_id
    ]


@router.get("/models/{model_id}", response_model=ModelArtifact)
def get_model(
    model_id: str,
    tenant_id: Annotated[str | None, Query()] = None,
) -> ModelArtifact:
    """Retrieves a registered model artifact by UUID."""
    model = _model_registry.get_model(model_id)
    if not model or (model.tenant_id is not None and model.tenant_id != tenant_id):
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found.")
    return model


@router.post("/models/{model_id}/promote", response_model=ModelArtifact)
def promote_model(
    model_id: str,
    req: PromoteModelRequest,
    tenant_id: Annotated[str | None, Query()] = None,
) -> ModelArtifact:
    """Promotes a registered model to a new lifecycle stage (e.g. STAGING or PRODUCTION)."""
    model = _model_registry.get_model(model_id)
    if model is not None and model.tenant_id is not None and model.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found.")
    try:
        return _model_registry.promote_model(model_id, req.stage)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found.")


@router.get("/features", response_model=list[FeatureDefinition])
def list_features() -> list[FeatureDefinition]:
    """Returns canonical feature definitions from the Feature Store."""
    return _feature_store.CANONICAL_FEATURES


@router.get("/predictions/{prediction_id}", response_model=StoredPrediction)
def get_prediction(
    prediction_id: str,
    tenant_id: Annotated[str | None, Query()] = None,
) -> StoredPrediction:
    """Retrieves an inference record from the Prediction Store."""
    pred = _prediction_store.get_prediction(prediction_id, tenant_id=tenant_id)
    if not pred:
        raise HTTPException(status_code=404, detail=f"Prediction '{prediction_id}' not found.")
    return pred


@router.get("/predictions/{prediction_id}/explanation", response_model=PredictionExplanation)
def explain_prediction(
    prediction_id: str,
    tenant_id: Annotated[str | None, Query()] = None,
) -> PredictionExplanation:
    """Explains the exact registered model and immutable input snapshot of a prediction."""
    try:
        explanation = _serving_engine.explain_prediction(prediction_id, tenant_id=tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if explanation is None:
        raise HTTPException(status_code=404, detail=f"Prediction '{prediction_id}' not found.")
    return explanation


@router.post("/monitoring/evaluate", response_model=ModelMonitoringReport)
def evaluate_monitoring(req: MonitoringEvaluationRequest) -> ModelMonitoringReport:
    """Evaluates production signals for one exact model/feature/tenant/time scope."""
    model = _resolve_registered_model(req.model_version, req.tenant_id)
    end = req.window_end or datetime.now(timezone.utc)
    start = req.window_start or end - timedelta(days=1)
    try:
        report = DriftDetectionEngine.evaluate_model(
            model=model,
            predictions=_prediction_store.list_predictions(
                tenant_id=req.tenant_id,
                model_version=model.version,
                feature_version=req.feature_version,
                window_start=start,
                window_end=end,
                limit=100_000,
            ),
            failures=_prediction_store.list_failures(
                tenant_id=req.tenant_id,
                model_version=model.version,
                feature_version=req.feature_version,
                window_start=start,
                window_end=end,
            ),
            window_start=start,
            window_end=end,
            tenant_id=req.tenant_id,
            feature_version=req.feature_version,
            psi_warning_threshold=req.psi_warning_threshold,
            psi_critical_threshold=req.psi_critical_threshold,
            missing_rate_delta_threshold=req.missing_rate_delta_threshold,
            performance_drop_threshold=req.performance_drop_threshold,
            calibration_error_threshold=req.calibration_error_threshold,
            min_outcomes=req.min_outcomes,
        )
        return _prediction_store.save_monitoring_report(report)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/monitoring/reports/{report_id}", response_model=ModelMonitoringReport)
def get_monitoring_report(
    report_id: str,
    tenant_id: Annotated[str | None, Query()] = None,
) -> ModelMonitoringReport:
    """Retrieves a prior monitoring report within its exact tenant scope."""
    report = _prediction_store.get_monitoring_report(report_id, tenant_id=tenant_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Monitoring report '{report_id}' not found.")
    return report


@router.post("/drift/evaluate", response_model=DriftReport)
def evaluate_drift(req: DriftEvaluationRequest) -> DriftReport:
    """Compatibility PSI endpoint using the registered model's training reference."""
    model = _resolve_registered_model(req.model_version, tenant_id=None)
    feature_version = req.feature_version
    if feature_version is None:
        if len(model.feature_versions) != 1:
            raise HTTPException(status_code=400, detail="feature_version is required for this model.")
        feature_version = model.feature_versions[0]
    if feature_version not in model.feature_versions:
        raise HTTPException(status_code=400, detail="Requested feature version is not registered for this model.")

    baseline_features = model.monitoring_reference.get("feature_distributions", {})
    if not isinstance(baseline_features, dict):
        baseline_features = {}
    if req.current_features is not None:
        current_features = req.current_features
    else:
        current_records = _prediction_store.list_predictions(
            tenant_id=None,
            model_version=model.version,
            feature_version=feature_version,
            limit=100_000,
        )
        current_features = {name: [] for name in model.feature_names}
        for prediction in current_records:
            values = prediction.input_snapshot.get("feature_values", {})
            if isinstance(values, dict):
                for name in model.feature_names:
                    value = values.get(name)
                    if isinstance(value, (int, float)):
                        current_features[name].append(float(value))
    return DriftDetectionEngine.evaluate_drift(
        model_version=model.version,
        baseline_features=baseline_features,
        current_features=current_features,
    )

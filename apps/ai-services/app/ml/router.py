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

from typing import Any, Dict, List, Optional
from uuid import UUID

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
    ModelStage,
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


# Request schemas for router
class MLTrainRequest(BaseModel):
    dataset_name: str = "oncology_opportunity_v1"
    architecture: ModelArchitecture = ModelArchitecture.LOGISTIC_REGRESSION
    hyperparameters: Dict[str, Any] = Field(default_factory=dict)
    stage: ModelStage = ModelStage.DEVELOPMENT
    model_name: Optional[str] = None
    model_version: Optional[str] = None


class PromoteModelRequest(BaseModel):
    stage: ModelStage


class DriftEvaluationRequest(BaseModel):
    model_version: Optional[str] = None
    current_features: Optional[Dict[str, List[float]]] = None


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
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/models", response_model=List[ModelArtifact])
def list_models(stage: Optional[ModelStage] = Query(None)) -> List[ModelArtifact]:
    """Lists registered models with evaluation metrics, optionally filtered by lifecycle stage."""
    return _model_registry.list_models(stage=stage)


@router.get("/models/{model_id}", response_model=ModelArtifact)
def get_model(model_id: str) -> ModelArtifact:
    """Retrieves a registered model artifact by UUID."""
    model = _model_registry.get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found.")
    return model


@router.post("/models/{model_id}/promote", response_model=ModelArtifact)
def promote_model(model_id: str, req: PromoteModelRequest) -> ModelArtifact:
    """Promotes a registered model to a new lifecycle stage (e.g. STAGING or PRODUCTION)."""
    try:
        return _model_registry.promote_model(model_id, req.stage)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found.")


@router.get("/features", response_model=List[FeatureDefinition])
def list_features() -> List[FeatureDefinition]:
    """Returns canonical feature definitions from the Feature Store."""
    return _feature_store.CANONICAL_FEATURES


@router.get("/predictions/{prediction_id}", response_model=StoredPrediction)
def get_prediction(prediction_id: str) -> StoredPrediction:
    """Retrieves an inference record from the Prediction Store."""
    pred = _prediction_store.get_prediction(prediction_id)
    if not pred:
        raise HTTPException(status_code=404, detail=f"Prediction '{prediction_id}' not found.")
    return pred


@router.post("/drift/evaluate", response_model=DriftReport)
def evaluate_drift(req: DriftEvaluationRequest) -> DriftReport:
    """Calculates Population Stability Index (PSI) drift report against baseline distribution."""
    # Build baseline distributions from feature store fixtures
    baseline_records = _feature_store.extract_batch()
    feature_names = [f.name for f in _feature_store.CANONICAL_FEATURES]

    baseline_features: Dict[str, List[float]] = {
        name: [vec.features.get(name, 0.0) for vec in baseline_records]
        for name in feature_names
    }

    current_features = req.current_features or baseline_features
    model_version = req.model_version or "champion"

    return DriftDetectionEngine.evaluate_drift(
        model_version=model_version,
        baseline_features=baseline_features,
        current_features=current_features,
    )

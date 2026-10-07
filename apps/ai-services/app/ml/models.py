"""
ML Subsystem Core Data Models and Schema Definitions.

Defines schemas for:
- Feature Store (definitions, values, views)
- Label Generator (ground truth outcomes, horizon-based targets)
- Dataset Builder (training/validation/test splits, snapshots)
- Model Registry (model versions, architectures, artifacts, promotion status)
- Model Serving (inference requests, predictions, latencies)
- Prediction Store (persisted predictions, actuals, outcomes)
- Explainability (feature attributions, directional impact, top drivers)
- Monitoring & Drift Detection (PSI, KS-statistic, feature drift, concept drift)
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any, Dict, List, Literal, Optional, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


# ==============================================================================
# 1. Architecture & Model Lifecycle Enums
# ==============================================================================

class ModelArchitecture(StrEnum):
    LOGISTIC_REGRESSION = "logistic_regression"
    RANDOM_FOREST = "random_forest"
    GRADIENT_BOOSTING = "gradient_boosting"


class ModelStage(StrEnum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    ARCHIVED = "archived"


class FeatureDataType(StrEnum):
    FLOAT = "float"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    CATEGORICAL = "categorical"


class DriftStatus(StrEnum):
    NO_DRIFT = "no_drift"
    MODERATE_DRIFT = "moderate_drift"
    SEVERE_DRIFT = "severe_drift"


# ==============================================================================
# 2. Feature Store Models
# ==============================================================================

class FeatureDefinition(BaseModel):
    """Schema definition for an engineered ML feature."""
    model_config = ConfigDict(from_attributes=True)

    name: str
    feature_group: str
    data_type: FeatureDataType
    description: str
    default_value: float = 0.0
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    version: str = "v1"


class FeatureVector(BaseModel):
    """Point-in-time feature vector for an asset."""
    model_config = ConfigDict(from_attributes=True)

    entity_id: str
    as_of_date: date
    features: Dict[str, float]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================================
# 3. Label Generator Models
# ==============================================================================

class TargetLabel(BaseModel):
    """Supervised target label for binary classification or regression."""
    model_config = ConfigDict(from_attributes=True)

    entity_id: str
    target_name: str  # e.g., phase_transition_success, approval_success, resistance_event
    outcome_value: float  # 1.0 or 0.0 for binary classification
    observation_horizon_date: date
    is_known_at_cutoff: bool = True
    outcome_evidence_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================================
# 4. Dataset Builder Models
# ==============================================================================

class DatasetRecord(BaseModel):
    """A single observation row combining features and ground truth label."""
    entity_id: str
    as_of_date: date
    features: Dict[str, float]
    label: float
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MLDataset(BaseModel):
    """Immutably split training, validation, and test datasets."""
    model_config = ConfigDict(from_attributes=True)

    dataset_id: UUID = Field(default_factory=uuid4)
    name: str
    version: str
    feature_names: List[str]
    target_name: str
    train_records: List[DatasetRecord] = Field(default_factory=list)
    val_records: List[DatasetRecord] = Field(default_factory=list)
    test_records: List[DatasetRecord] = Field(default_factory=list)
    cutoff_date: Optional[date] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================================
# 5. Model Registry & Metadata Models
# ==============================================================================

class ModelEvaluationMetrics(BaseModel):
    """Validation performance metrics."""
    accuracy: float = Field(ge=0.0, le=1.0)
    precision: float = Field(ge=0.0, le=1.0)
    recall: float = Field(ge=0.0, le=1.0)
    f1_score: float = Field(ge=0.0, le=1.0)
    roc_auc: float = Field(ge=0.0, le=1.0)
    brier_score: float = Field(ge=0.0, le=1.0)
    log_loss: float = Field(ge=0.0)


class ModelArtifact(BaseModel):
    """Registered ML model metadata and serialized weights."""
    model_config = ConfigDict(from_attributes=True)

    model_id: UUID = Field(default_factory=uuid4)
    name: str
    version: str
    architecture: ModelArchitecture
    stage: ModelStage = ModelStage.DEVELOPMENT
    feature_names: List[str]
    hyperparameters: Dict[str, Any] = Field(default_factory=dict)
    coefficients_or_weights: Dict[str, Any] = Field(default_factory=dict)
    intercept: float = 0.0
    metrics: ModelEvaluationMetrics
    dataset_version: str
    registered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True


# ==============================================================================
# 6. Explainability Models
# ==============================================================================

class FeatureAttribution(BaseModel):
    """Individual feature contribution to a specific prediction."""
    feature_name: str
    feature_value: float
    importance_weight: float
    attribution_score: float
    directional_impact: Literal["POSITIVE", "NEGATIVE", "NEUTRAL"]
    explanation: str


class PredictionExplanation(BaseModel):
    """Complete explainability report for a model prediction."""
    model_config = ConfigDict(from_attributes=True)

    prediction_id: UUID
    entity_id: str
    model_version: str
    predicted_probability: float
    base_value: float
    top_drivers: List[FeatureAttribution]
    summary_narrative: str


# ==============================================================================
# 7. Model Serving & Prediction Store Models
# ==============================================================================

class InferenceRequest(BaseModel):
    """Inference request for one or more entities."""
    entity_id: str
    features: Optional[Dict[str, float]] = None
    model_version: Optional[str] = None


class StoredPrediction(BaseModel):
    """Persisted inference record in the prediction store."""
    model_config = ConfigDict(from_attributes=True)

    prediction_id: UUID = Field(default_factory=uuid4)
    entity_id: str
    model_id: UUID
    model_version: str
    architecture: ModelArchitecture
    predicted_probability: float
    predicted_class: int
    features_used: Dict[str, float]
    explanation: Optional[PredictionExplanation] = None
    actual_outcome: Optional[float] = None
    outcome_observed_date: Optional[date] = None
    latency_ms: float
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================================
# 8. Monitoring & Drift Detection Models
# ==============================================================================

class FeatureDriftMetric(BaseModel):
    """Population Stability Index (PSI) and statistics for a single feature."""
    feature_name: str
    baseline_mean: float
    current_mean: float
    psi: float
    drift_status: DriftStatus
    flagged: bool


class DriftReport(BaseModel):
    """Model performance and feature distribution drift assessment."""
    model_config = ConfigDict(from_attributes=True)

    report_id: UUID = Field(default_factory=uuid4)
    model_version: str
    evaluation_window_start: date
    evaluation_window_end: date
    total_inferences_evaluated: int
    overall_drift_status: DriftStatus
    feature_drifts: Dict[str, FeatureDriftMetric]
    drift_alert_triggered: bool
    recommended_action: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

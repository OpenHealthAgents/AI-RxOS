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
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ==============================================================================
# 1. Architecture & Model Lifecycle Enums
# ==============================================================================

class ModelArchitecture(StrEnum):
    LOGISTIC_REGRESSION = "logistic_regression"
    RANDOM_FOREST = "random_forest"
    GRADIENT_BOOSTING = "gradient_boosting"


class ModelStage(StrEnum):
    DEVELOPMENT = "development"
    CANDIDATE = "candidate"
    STAGING = "staging"
    PRODUCTION = "production"
    RETIRED = "retired"
    ARCHIVED = "archived"


class TrainingRunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class FeatureDataType(StrEnum):
    FLOAT = "float"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    CATEGORICAL = "categorical"


class DriftStatus(StrEnum):
    NO_DRIFT = "no_drift"
    MODERATE_DRIFT = "moderate_drift"
    SEVERE_DRIFT = "severe_drift"
    INSUFFICIENT_DATA = "insufficient_data"


class MonitoringStatus(StrEnum):
    HEALTHY = "healthy"
    WARNING = "warning"
    DRIFT_DETECTED = "drift_detected"
    DEGRADED = "degraded"
    INSUFFICIENT_DATA = "insufficient_data"


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
    min_value: float | None = None
    max_value: float | None = None
    version: str = "v1"


class FeatureVector(BaseModel):
    """Point-in-time feature vector for an asset."""
    model_config = ConfigDict(from_attributes=True)

    entity_id: str
    as_of_date: date
    features: dict[str, float]
    feature_version: str = "v1"
    unit: str = "%"
    observation_date: date | None = None
    prediction_cutoff: date | None = None
    evidence_references: list[str] = Field(default_factory=list)
    extraction_method: str = "point_in_time_feature_extraction"
    confidence: float = Field(default=0.90, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FeatureRecord(BaseModel):
    """Versioned feature snapshot with provenance and temporal metadata."""
    model_config = ConfigDict(from_attributes=True)

    feature_name: str
    value: float | int | bool | str | None = None
    unit: str = ""
    asset: str
    asset_id: str | None = None
    tenant_id: str | None = None
    organization_id: str | None = None
    evidence_references: list[str] = Field(default_factory=list)
    evidence_ids: list[str] | None = None
    observation_date: date
    prediction_cutoff: date
    feature_version: str = "v1"
    extraction_method: str = "point_in_time_feature_extraction"
    confidence: float = Field(default=0.90, ge=0.0, le=1.0)
    provenance: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_missing(self) -> bool:
        return self.value is None

    @model_validator(mode="before")
    @classmethod
    def sync_feature_record_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        if data.get("asset_id") is None and data.get("asset") is not None:
            data["asset_id"] = data["asset"]
        if data.get("asset") is None and data.get("asset_id") is not None:
            data["asset"] = data["asset_id"]
        if data.get("tenant_id") is None and data.get("organization_id") is not None:
            data["tenant_id"] = data["organization_id"]

        if data.get("evidence_references") is None and data.get("evidence_ids") is not None:
            data["evidence_references"] = data["evidence_ids"]
        elif data.get("evidence_ids") is None and data.get("evidence_references") is not None:
            data["evidence_ids"] = data["evidence_references"]

        return data


# ==============================================================================
# 3. Label Generator Models
# ==============================================================================

class TargetLabel(BaseModel):
    """Supervised target label for binary classification or regression."""
    model_config = ConfigDict(from_attributes=True)

    entity_id: str
    target_name: str  # e.g., phase_transition_success, approval_success, resistance_event
    outcome_value: float | None = None  # 1.0 or 0.0 for binary classification; None preserves missing/unknown states
    observation_horizon_date: date | None = None
    is_known_at_cutoff: bool = True
    outcome_evidence_id: str | None = None
    asset_id: str | None = None
    asset: str | None = None
    tenant_id: str | None = None
    organization_id: str | None = None
    evidence_references: list[str] = Field(default_factory=list)
    evidence_ids: list[str] | None = None
    observation_date: date | None = None
    prediction_cutoff: date | None = None
    label_version: str = "v1"
    derivation_method: str = "direct_observation"
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    provenance: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="before")
    @classmethod
    def sync_label_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if data.get("asset_id") is None and data.get("asset") is not None:
            data["asset_id"] = data["asset"]
        if data.get("asset") is None and data.get("asset_id") is not None:
            data["asset"] = data["asset_id"]
        if data.get("tenant_id") is None and data.get("organization_id") is not None:
            data["tenant_id"] = data["organization_id"]
        if data.get("evidence_references") is None and data.get("evidence_ids") is not None:
            data["evidence_references"] = data["evidence_ids"]
        elif data.get("evidence_ids") is None and data.get("evidence_references") is not None:
            data["evidence_ids"] = data["evidence_references"]
        return data


# ==============================================================================
# 4. Dataset Builder Models
# ==============================================================================

class DatasetRecord(BaseModel):
    """A single observation row combining features and ground truth label."""
    entity_id: str
    as_of_date: date
    features: dict[str, float | None] = Field(default_factory=dict)
    label: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MLDataset(BaseModel):
    """Immutably split training, validation, and test datasets."""
    model_config = ConfigDict(from_attributes=True)

    dataset_id: UUID = Field(default_factory=uuid4)
    name: str
    version: str
    feature_names: list[str]
    target_name: str
    train_records: list[DatasetRecord] = Field(default_factory=list)
    val_records: list[DatasetRecord] = Field(default_factory=list)
    test_records: list[DatasetRecord] = Field(default_factory=list)
    cutoff_date: date | None = None
    feature_versions: list[str] = Field(default_factory=list)
    label_versions: list[str] = Field(default_factory=list)
    prediction_cutoffs: dict[str, date] = Field(default_factory=dict)
    asset_scope: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================================
# 5. Model Registry & Metadata Models
# ==============================================================================

class ModelEvaluationMetrics(BaseModel):
    """Validation performance metrics."""
    accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    precision: float | None = Field(default=None, ge=0.0, le=1.0)
    recall: float | None = Field(default=None, ge=0.0, le=1.0)
    f1_score: float | None = Field(default=None, ge=0.0, le=1.0)
    roc_auc: float | None = Field(default=None, ge=0.0, le=1.0)
    average_precision: float | None = Field(default=None, ge=0.0, le=1.0)
    auprc: float | None = Field(default=None, ge=0.0, le=1.0)
    brier_score: float | None = Field(default=None, ge=0.0, le=1.0)
    log_loss: float | None = Field(default=None, ge=0.0)


class ModelCalibration(BaseModel):
    """Probability calibration metadata for probabilistic models."""
    model_config = ConfigDict(from_attributes=True)

    performed: bool = False
    method: str | None = None
    dataset_split: str | None = None
    metrics: dict[str, float | None] = Field(default_factory=dict)
    artifact_version: str | None = None
    calibration_timestamp: datetime | None = None


class TrainingRunMetadata(BaseModel):
    """Immutable provenance and metadata for a training run."""
    model_config = ConfigDict(from_attributes=True)

    run_id: UUID = Field(default_factory=uuid4)
    model_name: str
    model_type: str
    dataset_name: str | None = None
    dataset_version: str
    feature_versions: list[str] = Field(default_factory=list)
    label_versions: list[str] = Field(default_factory=list)
    selected_features: list[str] = Field(default_factory=list)
    selected_labels: list[str] = Field(default_factory=list)
    training_cutoff: date | None = None
    validation_cutoff: date | None = None
    test_cutoff: date | None = None
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    random_seed: int | None = None
    metrics: dict[str, float | None] = Field(default_factory=dict)
    calibration: ModelCalibration | None = None
    artifact_reference: str | None = None
    training_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: TrainingRunStatus = TrainingRunStatus.CREATED
    tenant_id: str | None = None


class ModelArtifact(BaseModel):
    """Registered ML model metadata and serialized weights."""
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)

    model_id: UUID = Field(default_factory=uuid4)
    name: str
    version: str
    architecture: ModelArchitecture
    stage: ModelStage = ModelStage.DEVELOPMENT
    feature_names: list[str]
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    coefficients_or_weights: dict[str, Any] = Field(default_factory=dict)
    intercept: float = 0.0
    metrics: ModelEvaluationMetrics
    dataset_version: str
    feature_versions: list[str] = Field(default_factory=list)
    label_versions: list[str] = Field(default_factory=list)
    training_cutoff: date | None = None
    validation_cutoff: date | None = None
    test_cutoff: date | None = None
    artifact_reference: str | None = None
    calibration: ModelCalibration | None = None
    random_seed: int | None = None
    training_run_id: UUID | None = None
    tenant_id: str | None = None
    lineage: dict[str, Any] = Field(default_factory=dict)
    monitoring_reference: dict[str, Any] = Field(default_factory=dict, exclude=True, repr=False)
    fitted_model: Any | None = Field(default=None, exclude=True, repr=False)
    registered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True


# ==============================================================================
# 6. Explainability Models
# ==============================================================================

class FeatureAttribution(BaseModel):
    """Individual feature contribution to a specific prediction."""
    feature_name: str
    feature_value: float
    importance_weight: float = Field(
        description="Global normalized model importance; it is not the instance contribution."
    )
    attribution_score: float = Field(
        description="Instance-specific model contribution, using contribution_unit."
    )
    directional_impact: Literal["POSITIVE", "NEGATIVE", "NEUTRAL"]
    explanation: str
    feature_version: str = ""
    contribution_unit: str = "model_output"


class FeatureUncertainty(BaseModel):
    """A reason why a feature limits interpretation, without inventing a score."""

    feature_name: str
    reason: str
    feature_value: float | None = None
    confidence: float | None = None
    feature_version: str = ""


class PredictionExplanation(BaseModel):
    """Complete explainability report for a model prediction."""
    model_config = ConfigDict(from_attributes=True)

    prediction_id: UUID
    entity_id: str
    asset_id: str | None = None
    model_name: str = ""
    model_version: str
    feature_version: str = ""
    explanation_type: Literal["MODEL_EXPLANATION"] = "MODEL_EXPLANATION"
    attribution_method: str = ""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    input_snapshot: dict[str, Any] = Field(default_factory=dict)
    feature_evidence_references: dict[str, list[str]] = Field(default_factory=dict)
    scientific_evidence_citations: list[str] = Field(default_factory=list)
    evidence_scope: str = "Feature provenance only; this explanation is not scientific evidence."
    explanation_available: bool = True
    unavailable_reason: str | None = None
    predicted_probability: float
    base_value: float
    top_drivers: list[FeatureAttribution]
    positive_contributors: list[FeatureAttribution] = Field(default_factory=list)
    negative_contributors: list[FeatureAttribution] = Field(default_factory=list)
    uncertain_features: list[FeatureUncertainty] = Field(default_factory=list)
    missing_features: list[str] = Field(default_factory=list)
    summary_narrative: str


# ==============================================================================
# 7. Model Serving & Prediction Store Models
# ==============================================================================

class InferenceRequest(BaseModel):
    """Explicit versioned inference request for a single asset or entity."""
    entity_id: str
    asset_id: str | None = None
    features: dict[str, float | None] | None = None
    model_version: str | None = None
    feature_version: str | None = None
    prediction_cutoff: date | None = None
    tenant_id: str | None = None
    model_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StoredPrediction(BaseModel):
    """Persisted prediction record with explicit versioned inputs and audit metadata."""
    model_config = ConfigDict(from_attributes=True)

    prediction_id: UUID = Field(default_factory=uuid4)
    entity_id: str
    asset_id: str | None = None
    tenant_id: str | None = None
    model_name: str = ""
    model_id: UUID
    model_version: str
    model_type: str = ""
    architecture: ModelArchitecture | None = None
    feature_version: str = ""
    feature_versions: list[str] = Field(default_factory=list)
    input_snapshot: dict[str, Any] = Field(default_factory=dict)
    prediction: int | None = None
    patient_segment: str | None = None
    outcome_probabilities: dict[str, float] = Field(default_factory=dict)
    outcome_predictions: dict[str, int] = Field(default_factory=dict)
    uncertainty_reasons: list[str] = Field(default_factory=list)
    probability: float | None = None
    confidence: float | None = None
    predicted_probability: float | None = None
    predicted_class: int | None = None
    prediction_cutoff: date | None = None
    prediction_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    features_used: dict[str, float] = Field(default_factory=dict)
    explanation: PredictionExplanation | None = None
    actual_outcome: float | None = None
    outcome_observed_date: date | None = None
    artifact_reference: str | None = None
    lineage: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="before")
    @classmethod
    def sync_prediction_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if data.get("prediction") is None and data.get("predicted_class") is not None:
            data["prediction"] = data["predicted_class"]
        if data.get("predicted_class") is None and data.get("prediction") is not None:
            data["predicted_class"] = data["prediction"]
        if data.get("probability") is None and data.get("predicted_probability") is not None:
            data["probability"] = data["predicted_probability"]
        if data.get("predicted_probability") is None and data.get("probability") is not None:
            data["predicted_probability"] = data["probability"]
        if data.get("prediction_timestamp") is None:
            data["prediction_timestamp"] = datetime.now(timezone.utc)
        return data


# ==============================================================================
# 8. Monitoring & Drift Detection Models
# ==============================================================================

class FeatureDriftMetric(BaseModel):
    """Population Stability Index (PSI) and statistics for a single feature."""
    feature_name: str
    baseline_mean: float | None = None
    current_mean: float | None = None
    psi: float | None = None
    drift_status: DriftStatus
    flagged: bool
    feature_version: str = ""
    baseline_dataset_version: str | None = None
    baseline_count: int = 0
    current_count: int = 0
    baseline_missing_rate: float | None = None
    current_missing_rate: float | None = None
    missing_rate_delta: float | None = None


class MonitoringAlert(BaseModel):
    """A threshold-backed monitoring signal for one model/version/window."""

    alert_id: UUID = Field(default_factory=uuid4)
    tenant_id: str | None = None
    model_name: str
    model_version: str
    feature_version: str | None = None
    metric: str
    baseline_value: float | None = None
    current_value: float | None = None
    threshold: float
    severity: Literal["warning", "critical"]
    window_start: datetime
    window_end: datetime
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ModelMonitoringReport(BaseModel):
    """Version- and tenant-scoped production monitoring snapshot."""

    report_id: UUID = Field(default_factory=uuid4)
    tenant_id: str | None = None
    model_name: str
    model_version: str
    feature_versions: list[str] = Field(default_factory=list)
    dataset_version: str
    window_start: datetime
    window_end: datetime
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: MonitoringStatus
    prediction_count: int = 0
    failure_count: int = 0
    failure_types: dict[str, int] = Field(default_factory=dict)
    mean_latency_ms: float | None = None
    prediction_class_counts: dict[str, int] = Field(default_factory=dict)
    probability_mean: float | None = None
    probability_min: float | None = None
    probability_max: float | None = None
    confidence_mean: float | None = None
    feature_drifts: dict[str, FeatureDriftMetric] = Field(default_factory=dict)
    performance_metrics: dict[str, float | None] = Field(default_factory=dict)
    calibration_metrics: dict[str, float | None] = Field(default_factory=dict)
    outcome_count: int = 0
    signals: dict[str, Any] = Field(default_factory=dict)
    alerts: list[MonitoringAlert] = Field(default_factory=list)
    insufficient_data_reasons: list[str] = Field(default_factory=list)


class PredictionFailure(BaseModel):
    """Tenant-scoped audit event for a rejected or failed prediction attempt."""

    failure_id: UUID = Field(default_factory=uuid4)
    tenant_id: str | None = None
    asset_id: str
    model_name: str | None = None
    model_version: str | None = None
    feature_version: str | None = None
    failed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error_type: str
    message: str
    missing_features: list[str] = Field(default_factory=list)


class DriftReport(BaseModel):
    """Model performance and feature distribution drift assessment."""
    model_config = ConfigDict(from_attributes=True)

    report_id: UUID = Field(default_factory=uuid4)
    model_version: str
    evaluation_window_start: date
    evaluation_window_end: date
    total_inferences_evaluated: int
    overall_drift_status: DriftStatus
    feature_drifts: dict[str, FeatureDriftMetric]
    drift_alert_triggered: bool
    recommended_action: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

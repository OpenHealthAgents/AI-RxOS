"""
Machine Learning Subsystem for Oncology Drug Candidate Intelligence.

A first-class, interpretable statistical ML subsystem decoupled from the LLM layer:
1. Dataset Builder: Point-in-time joins and deterministic splits
2. Feature Engineering & Feature Store: 8 canonical oncology features
3. Label Generator: Supervised target generation without temporal leakage
4. Training Pipeline: Fits interpretable statistical baselines
5. Validation Pipeline: Rigorous metrics (ROC-AUC, Brier score, log-loss)
6. Model Registry: Versioning and champion/challenger lifecycle
7. Model Serving: Low-latency inference engine
8. Prediction Store: Persisted inference audits and delayed actuals
9. Explainability Engine: Linear & marginal feature attributions
10. Drift Detection Engine: Population Stability Index (PSI) monitoring
11. Interpretable Baselines: Logistic Regression, Random Forest, Gradient Boosting
"""

from .algorithms import (
    GradientBoostingBaseline,
    LogisticRegressionModel,
    RandomForestBaseline,
)
from .dataset import DatasetBuilder, LabelGenerator
from .explainability import ExplainabilityEngine
from .features import FeatureEngineeringEngine, FeatureStore
from .models import (
    DatasetRecord,
    DriftReport,
    DriftStatus,
    FeatureAttribution,
    FeatureDataType,
    FeatureDefinition,
    FeatureDriftMetric,
    FeatureRecord,
    FeatureUncertainty,
    FeatureVector,
    InferenceRequest,
    MLDataset,
    ModelArchitecture,
    ModelArtifact,
    ModelEvaluationMetrics,
    ModelMonitoringReport,
    ModelStage,
    MonitoringAlert,
    MonitoringStatus,
    PredictionExplanation,
    PredictionFailure,
    StoredPrediction,
    TargetLabel,
)
from .monitoring import (
    DriftDetectionEngine,
    DriftDetector,
    PopulationStabilityIndexDetector,
)
from .pipeline import TrainingPipeline, ValidationPipeline
from .prediction_store import PredictionStore
from .registry import ModelRegistry
from .serving import ModelServingEngine

__all__ = [
    "DatasetBuilder",
    "DatasetRecord",
    "DriftDetectionEngine",
    "DriftDetector",
    "DriftReport",
    "DriftStatus",
    "ExplainabilityEngine",
    "FeatureAttribution",
    "FeatureDataType",
    "FeatureDefinition",
    "FeatureDriftMetric",
    "FeatureEngineeringEngine",
    "FeatureRecord",
    "FeatureStore",
    "FeatureUncertainty",
    "FeatureVector",
    "GradientBoostingBaseline",
    "InferenceRequest",
    "LabelGenerator",
    "LogisticRegressionModel",
    "MLDataset",
    "ModelArchitecture",
    "ModelArtifact",
    "ModelEvaluationMetrics",
    "ModelMonitoringReport",
    "ModelRegistry",
    "ModelServingEngine",
    "ModelStage",
    "MonitoringAlert",
    "MonitoringStatus",
    "PopulationStabilityIndexDetector",
    "PredictionExplanation",
    "PredictionFailure",
    "PredictionStore",
    "RandomForestBaseline",
    "StoredPrediction",
    "TargetLabel",
    "TrainingPipeline",
    "ValidationPipeline",
]

"""
Model Serving Engine.

Real-time, low-latency prediction service with:
- Model Registry lookup (champion/active production model)
- Feature Store integration for point-in-time retrieval
- Model execution (Logistic Regression, Random Forest, Gradient Boosting)
- Local Explainability attribution computation
- Prediction Store persistence
"""

from __future__ import annotations

import time
from typing import Optional
from uuid import uuid4

from .algorithms import (
    GradientBoostingBaseline,
    LogisticRegressionModel,
    RandomForestBaseline,
)
from .dataset import DatasetBuilder
from .explainability import ExplainabilityEngine
from .features import FeatureStore
from .models import (
    InferenceRequest,
    ModelArchitecture,
    ModelArtifact,
    ModelStage,
    StoredPrediction,
)
from .pipeline import TrainingPipeline
from .prediction_store import PredictionStore
from .registry import ModelRegistry


class ModelServingEngine:
    """
    Production serving orchestrator for interpretable oncology predictions.
    """

    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        feature_store: Optional[FeatureStore] = None,
        prediction_store: Optional[PredictionStore] = None,
    ) -> None:
        self.registry = registry or ModelRegistry()
        self.feature_store = feature_store or FeatureStore()
        self.prediction_store = prediction_store or PredictionStore()
        self._ensure_baseline_champion()

    def _ensure_baseline_champion(self) -> None:
        """Bootstraps a default production champion model if registry is empty."""
        if self.registry.get_production_model() is None:
            builder = DatasetBuilder(feature_store=self.feature_store)
            dataset = builder.build_dataset(name="bootstrap_opportunity_v1")
            pipeline = TrainingPipeline()
            model = pipeline.train(
                dataset=dataset,
                architecture=ModelArchitecture.LOGISTIC_REGRESSION,
                stage=ModelStage.PRODUCTION,
                model_name="opportunity_pursuit_logistic_regression",
                model_version="v1.0.0",
            )
            self.registry.register(model)

    def predict(self, request: InferenceRequest) -> StoredPrediction:
        """
        Executes real-time inference with feature extraction, prediction,
        local explanation, and prediction store persistence.
        """
        start_time = time.perf_counter()

        # 1. Resolve Model
        model: Optional[ModelArtifact] = None
        if request.model_version:
            for m in self.registry.list_models():
                if m.version == request.model_version:
                    model = m
                    break

        if model is None:
            model = self.registry.get_production_model()

        if model is None:
            raise RuntimeError("No active model available for inference.")

        # 2. Extract or Resolve Features
        features = request.features
        if features is None:
            vec = self.feature_store.get_features(request.entity_id)
            features = vec.features

        feature_vector = [features.get(f, 0.0) for f in model.feature_names]

        # 3. Model Inference Execution
        if model.architecture == ModelArchitecture.LOGISTIC_REGRESSION:
            algo = LogisticRegressionModel.from_dict(model.coefficients_or_weights)
            probs = algo.predict_proba([feature_vector])
        elif model.architecture == ModelArchitecture.RANDOM_FOREST:
            algo = RandomForestBaseline.from_dict(model.coefficients_or_weights)
            probs = algo.predict_proba([feature_vector])
        elif model.architecture == ModelArchitecture.GRADIENT_BOOSTING:
            algo = GradientBoostingBaseline.from_dict(model.coefficients_or_weights)
            probs = algo.predict_proba([feature_vector])
        else:
            raise ValueError(f"Unsupported model architecture: {model.architecture}")

        prob = max(0.0, min(1.0, probs[0]))
        predicted_class = 1 if prob >= 0.5 else 0

        pred_id = uuid4()
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # 4. Generate Explainability Report
        explanation = ExplainabilityEngine.explain_prediction(
            model=model,
            features=features,
            predicted_probability=prob,
            entity_id=request.entity_id,
            prediction_id=pred_id,
        )

        # 5. Persist to Prediction Store
        stored = StoredPrediction(
            prediction_id=pred_id,
            entity_id=request.entity_id,
            model_id=model.model_id,
            model_version=model.version,
            architecture=model.architecture,
            predicted_probability=round(prob, 4),
            predicted_class=predicted_class,
            features_used=features,
            explanation=explanation,
            latency_ms=latency_ms,
        )

        self.prediction_store.save_prediction(stored)
        return stored

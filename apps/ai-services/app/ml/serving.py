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
from datetime import datetime, timezone
from typing import Any
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
    PredictionExplanation,
    PredictionFailure,
    StoredPrediction,
)
from .pipeline import TrainingPipeline
from .prediction_store import PredictionStore
from .registry import ModelRegistry


class MissingRequiredFeaturesError(ValueError):
    """Prediction rejection that retains the exact unavailable feature names."""

    def __init__(self, feature_names: list[str]) -> None:
        self.feature_names = feature_names
        super().__init__(f"Required features missing for prediction: {feature_names}")


class ModelServingEngine:
    """Production serving orchestrator for interpretable oncology predictions."""

    def __init__(
        self,
        registry: ModelRegistry | None = None,
        feature_store: FeatureStore | None = None,
        prediction_store: PredictionStore | None = None,
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

    def _resolve_model(self, request: InferenceRequest) -> ModelArtifact:
        if request.model_version:
            candidates = [
                m for m in self.registry.list_models()
                if m.version == request.model_version
                and (
                    m.tenant_id is None
                    or (request.tenant_id is not None and m.tenant_id == request.tenant_id)
                )
                and (request.model_name is None or m.name == request.model_name)
            ]
            if not candidates:
                raise ValueError(f"Model version '{request.model_version}' is not registered or is not tenant-visible.")
            if len(candidates) > 1:
                raise ValueError("model_name is required to disambiguate this registered model version.")
            return candidates[0]

        production_model = self.registry.get_production_model()
        if production_model is not None:
            if production_model.tenant_id is not None and production_model.tenant_id != request.tenant_id:
                raise ValueError("Requested tenant does not match the production model tenant.")
            return production_model

        raise ValueError("Model version is required unless a single production model is explicitly available.")

    def _resolve_feature_version(self, model: ModelArtifact, request: InferenceRequest) -> str:
        feature_version = request.feature_version
        if feature_version is None:
            if len(model.feature_versions) == 1:
                feature_version = model.feature_versions[0]
            else:
                raise ValueError("feature_version is required when the model has multiple registered feature versions.")
        if feature_version not in model.feature_versions:
            raise ValueError(
                f"Feature version '{feature_version}' is not compatible with model '{model.name}:{model.version}'."
            )
        return feature_version

    def _resolve_input_snapshot(self, model: ModelArtifact, request: InferenceRequest, feature_version: str) -> tuple[dict, dict]:
        asset_id = request.asset_id or request.entity_id
        cutoff = request.prediction_cutoff or model.training_cutoff or datetime.now(timezone.utc).date()
        tenant_id = request.tenant_id or model.tenant_id

        metadata: dict[str, Any] = {}
        if request.features is not None:
            features = dict(request.features)
            metadata = {
                name: {
                    "value": value,
                    "unit": None,
                    "observation_date": None,
                    "prediction_cutoff": cutoff.isoformat(),
                    "evidence_references": [],
                    "confidence": None,
                    "provenance_available": False,
                }
                for name, value in features.items()
            }
        else:
            feature_rows = self.feature_store.get_feature_records_for_asset(asset_id, tenant_id=tenant_id)
            selected: dict[str, float] = {}
            for row in feature_rows:
                if row.feature_version != feature_version:
                    continue
                if row.prediction_cutoff and row.prediction_cutoff > cutoff:
                    raise ValueError(f"Future feature data at cutoff {cutoff.isoformat()} is not admissible for asset '{asset_id}'.")
                if row.observation_date and row.observation_date > cutoff:
                    raise ValueError(f"Feature observation date {row.observation_date.isoformat()} exceeds prediction cutoff {cutoff.isoformat()}.")
                if row.feature_name in model.feature_names:
                    if isinstance(row.value, (int, float)):
                        selected[row.feature_name] = float(row.value)
                    evidence_references = row.evidence_references
                    if row.provenance.get("source_count") == 0:
                        evidence_references = []
                    metadata[row.feature_name] = {
                        "value": row.value,
                        "unit": row.unit,
                        "observation_date": row.observation_date.isoformat() if row.observation_date else None,
                        "prediction_cutoff": row.prediction_cutoff.isoformat() if row.prediction_cutoff else None,
                        "evidence_references": evidence_references,
                        "confidence": row.confidence,
                        "extraction_method": row.extraction_method,
                        "feature_version": row.feature_version,
                        "provenance": row.provenance,
                        "provenance_available": True,
                    }

            if not selected:
                asset = next((asset for asset in __import__('app.opportunity_engine.data.fixtures', fromlist=['list_fixture_assets']).list_fixture_assets() if asset.id == asset_id), None)
                if asset is None:
                    raise ValueError(f"No feature snapshot exists for asset '{asset_id}' at feature version '{feature_version}'.")

                name_key = (model.name or "").lower()
                if "patient_response" in name_key:
                    generated_rows = self.feature_store.create_prompt_39_feature_records(
                        asset,
                        observation_date=cutoff,
                        prediction_cutoff=cutoff,
                        feature_version=feature_version,
                        tenant_id=tenant_id,
                    )
                elif "safety" in name_key:
                    generated_rows = self.feature_store.create_prompt_40_feature_records(
                        asset,
                        observation_date=cutoff,
                        prediction_cutoff=cutoff,
                        feature_version=feature_version,
                        tenant_id=tenant_id,
                    )
                elif "clinical_success" in name_key or "phase_ii" in name_key or "phase_iii" in name_key:
                    generated_rows = self.feature_store.create_prompt_38_feature_records(
                        asset,
                        observation_date=cutoff,
                        prediction_cutoff=cutoff,
                        feature_version=feature_version,
                        tenant_id=tenant_id,
                    )
                elif "translational" in name_key or "biology" in name_key:
                    generated_rows = self.feature_store.create_prompt_37_feature_records(
                        asset,
                        observation_date=cutoff,
                        prediction_cutoff=cutoff,
                        feature_version=feature_version,
                        tenant_id=tenant_id,
                    )
                else:
                    generated_rows = self.feature_store.create_prompt_29_feature_records(
                        asset,
                        observation_date=cutoff,
                        prediction_cutoff=cutoff,
                        feature_version=feature_version,
                        tenant_id=tenant_id,
                    )

                for row in generated_rows:
                    if row.feature_version != feature_version:
                        continue
                    if row.feature_name in model.feature_names:
                        if row.value is not None and isinstance(row.value, (int, float)):
                            selected[row.feature_name] = float(row.value)
                        metadata[row.feature_name] = {
                            "value": row.value,
                            "unit": row.unit,
                            "observation_date": row.observation_date.isoformat() if row.observation_date else None,
                            "prediction_cutoff": row.prediction_cutoff.isoformat() if row.prediction_cutoff else None,
                            "evidence_references": row.evidence_references,
                            "confidence": row.confidence,
                            "extraction_method": row.extraction_method,
                            "feature_version": row.feature_version,
                            "provenance": row.provenance,
                            "provenance_available": True,
                        }

                if not selected:
                    raise ValueError(f"No feature snapshot exists for asset '{asset_id}' at feature version '{feature_version}'.")
            features = selected

        missing_required = [name for name in model.feature_names if name not in features or features.get(name) is None]
        imputed_features: list[str] = []
        if missing_required and model.name == "safety":
            imputation_values = model.monitoring_reference.get("feature_imputation_values", {})
            if isinstance(imputation_values, dict):
                for name in list(missing_required):
                    value = imputation_values.get(name)
                    if isinstance(value, (int, float)):
                        features[name] = float(value)
                        imputed_features.append(name)
                        missing_required.remove(name)
        if missing_required:
            raise MissingRequiredFeaturesError(missing_required)

        if not all(isinstance(features[name], (int, float)) for name in model.feature_names):
            raise ValueError("Feature inputs must be numeric for prediction execution.")

        input_snapshot = {
            "asset_id": asset_id,
            "entity_id": request.entity_id,
            "tenant_id": tenant_id,
            "feature_version": feature_version,
            "feature_names": list(model.feature_names),
            "feature_values": {name: float(features[name]) for name in model.feature_names},
            "observed_feature_values": {
                name: metadata.get(name, {}).get("value")
                for name in model.feature_names
            },
            "missing_features": imputed_features,
            "prediction_cutoff": cutoff.isoformat(),
            "feature_units": {
                name: metadata.get(name, {}).get("unit")
                for name in model.feature_names
            },
            "feature_version_by_name": {
                name: feature_version for name in model.feature_names
            },
            "observation_dates": metadata,
            "model_version": model.version,
            "artifact_reference": model.artifact_reference,
        }
        return features, input_snapshot

    def predict(self, request: InferenceRequest) -> StoredPrediction:
        """Record failed attempts for monitoring, while preserving the original error."""
        try:
            return self._predict(request)
        except Exception as exc:
            model_name = request.model_name
            model_version = request.model_version
            feature_version = request.feature_version
            if model_version is None:
                production_model = self.registry.get_production_model()
                if production_model is not None and (
                    production_model.tenant_id is None
                    or production_model.tenant_id == request.tenant_id
                ):
                    model_name = production_model.name
                    model_version = production_model.version
                    if feature_version is None and len(production_model.feature_versions) == 1:
                        feature_version = production_model.feature_versions[0]
            self.prediction_store.record_failure(
                PredictionFailure(
                    tenant_id=request.tenant_id,
                    asset_id=request.asset_id or request.entity_id,
                    model_name=model_name,
                    model_version=model_version,
                    feature_version=feature_version,
                    error_type=type(exc).__name__,
                    message=str(exc),
                    missing_features=(
                        exc.feature_names if isinstance(exc, MissingRequiredFeaturesError) else []
                    ),
                )
            )
            raise

    def _predict(self, request: InferenceRequest) -> StoredPrediction:
        """Executes a versioned and temporally valid prediction with immutable snapshot metadata."""
        start_time = time.perf_counter()
        model = self._resolve_model(request)
        if request.tenant_id is not None and model.tenant_id not in (None, request.tenant_id):
            raise ValueError("Tenant mismatch: requested tenant cannot access the selected model.")
        if model.stage in (ModelStage.RETIRED, ModelStage.ARCHIVED):
            raise ValueError(f"Model '{model.name}:{model.version}' is not prediction-eligible.")

        feature_version = self._resolve_feature_version(model, request)
        features, input_snapshot = self._resolve_input_snapshot(model, request, feature_version)
        feature_vector = [float(features[f]) for f in model.feature_names]

        outcome_probabilities: dict[str, float] = {}
        outcome_predictions: dict[str, int] = {}
        if model.name == "safety" and model.fitted_model is not None and hasattr(model.fitted_model, "target_names"):
            raw_outcomes = model.fitted_model.predict_proba([feature_vector])
            outcome_probabilities = {
                target_name: max(0.0, min(1.0, float(probabilities[0])))
                for target_name, probabilities in raw_outcomes.items()
            }
            outcome_predictions = {
                target_name: int(probability >= 0.5)
                for target_name, probability in outcome_probabilities.items()
            }
            prob = outcome_probabilities["grade_ge_3_ae"]
        elif model.architecture == ModelArchitecture.LOGISTIC_REGRESSION:
            if model.fitted_model is not None and hasattr(model.fitted_model, "predict_proba"):
                probs = model.fitted_model.predict_proba([feature_vector])
            else:
                logistic_model = LogisticRegressionModel.from_dict(model.coefficients_or_weights)
                probs = logistic_model.predict_proba([feature_vector])
        elif model.architecture == ModelArchitecture.RANDOM_FOREST:
            if model.fitted_model is not None and hasattr(model.fitted_model, "predict_proba"):
                probs = model.fitted_model.predict_proba([feature_vector])
            else:
                forest_model = RandomForestBaseline.from_dict(model.coefficients_or_weights)
                probs = forest_model.predict_proba([feature_vector])
        elif model.architecture == ModelArchitecture.GRADIENT_BOOSTING:
            if model.fitted_model is not None and hasattr(model.fitted_model, "predict_proba"):
                probs = model.fitted_model.predict_proba([feature_vector])
            else:
                boosting_model = GradientBoostingBaseline.from_dict(model.coefficients_or_weights)
                probs = boosting_model.predict_proba([feature_vector])
        else:
            raise ValueError(f"Unsupported model architecture: {model.architecture}")

        if not outcome_probabilities:
            if hasattr(probs, "tolist"):
                probs = probs.tolist()
            prob = max(0.0, min(1.0, float(probs[0][1] if isinstance(probs[0], (list, tuple)) else probs[0])))
        pred = 1 if prob >= 0.5 else 0
        confidence = None
        if hasattr(model.fitted_model, "predict_proba"):
            try:
                confidence = float(max(0.0, min(1.0, abs(prob - 0.5) * 2.0)))
                if outcome_probabilities and model.feature_names:
                    observed_fraction = (
                        len(model.feature_names) - len(input_snapshot.get("missing_features", []))
                    ) / len(model.feature_names)
                    confidence *= observed_fraction
            except Exception:
                confidence = None
        pred_id = uuid4()
        pred_time = datetime.now(timezone.utc)
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

        explanation = ExplainabilityEngine.explain_prediction(
            model=model,
            features=features,
            predicted_probability=prob,
            entity_id=request.entity_id,
            prediction_id=pred_id,
            feature_version=feature_version,
            asset_id=request.asset_id or request.entity_id,
            input_snapshot=input_snapshot,
        )

        stored = StoredPrediction(
            prediction_id=pred_id,
            entity_id=request.entity_id,
            asset_id=request.asset_id or request.entity_id,
            tenant_id=request.tenant_id or model.tenant_id,
            model_name=model.name,
            model_id=model.model_id,
            model_version=model.version,
            model_type=model.architecture.value,
            architecture=model.architecture,
            feature_version=feature_version,
            feature_versions=model.feature_versions,
            input_snapshot=input_snapshot,
            prediction=pred,
            outcome_probabilities=outcome_probabilities,
            outcome_predictions=outcome_predictions,
            uncertainty_reasons=[
                f"{feature_name} was missing and median-imputed from the training dataset."
                for feature_name in input_snapshot.get("missing_features", [])
            ],
            patient_segment=(
                ("likely_responder" if pred == 1 else "unlikely_responder")
                if model.name == "patient_response"
                else None
            ),
            probability=round(prob, 4),
            confidence=confidence,
            predicted_probability=round(prob, 4),
            predicted_class=pred,
            prediction_cutoff=request.prediction_cutoff or model.training_cutoff or datetime.now(timezone.utc).date(),
            prediction_timestamp=pred_time,
            features_used={name: float(features[name]) for name in model.feature_names},
            explanation=explanation,
            artifact_reference=model.artifact_reference,
            lineage={
                "dataset_version": model.dataset_version,
                "feature_versions": model.feature_versions,
                "label_versions": model.label_versions,
                "training_cutoff": model.training_cutoff.isoformat() if model.training_cutoff else None,
                "validation_cutoff": model.validation_cutoff.isoformat() if model.validation_cutoff else None,
                "artifact_reference": model.artifact_reference,
            },
            latency_ms=latency_ms,
        )

        self.prediction_store.save_prediction(stored)
        return stored

    def explain_prediction(
        self,
        prediction_id: str,
        tenant_id: str | None = None,
    ) -> PredictionExplanation | None:
        """Re-explain only the immutable snapshot and registered artifact of a prediction."""
        prediction = self.prediction_store.get_prediction(prediction_id, tenant_id=tenant_id)
        if prediction is None:
            return None
        model = self.registry.get_model(prediction.model_id)
        if model is None or model.version != prediction.model_version:
            raise ValueError("The prediction's exact registered model version is unavailable.")
        if prediction.probability is None:
            raise ValueError("The prediction has no recorded probability to explain.")
        values = prediction.input_snapshot.get("feature_values", {})
        if not isinstance(values, dict):
            values = {}
        return ExplainabilityEngine.explain_prediction(
            model=model,
            features=values,
            predicted_probability=prediction.probability,
            entity_id=prediction.entity_id,
            prediction_id=prediction.prediction_id,
            feature_version=prediction.feature_version,
            asset_id=prediction.asset_id,
            input_snapshot=prediction.input_snapshot,
        )

"""Snapshot-bound model explanations for the registered baseline algorithms."""

from __future__ import annotations

import math
from typing import Any, Literal
from uuid import UUID

from .models import (
    FeatureAttribution,
    FeatureUncertainty,
    ModelArchitecture,
    ModelArtifact,
    PredictionExplanation,
)


class ExplainabilityEngine:
    """Explain model behavior without presenting it as scientific evidence."""

    @staticmethod
    def _mean_leaf_value(node: dict[str, Any]) -> float:
        if "value" in node:
            return float(node["value"])
        children = [node.get("left"), node.get("right")]
        values = [ExplainabilityEngine._mean_leaf_value(child) for child in children if child]
        if not values:
            raise ValueError("Tree artifact contains a node with no leaf values.")
        return sum(values) / len(values)

    @classmethod
    def _random_forest_contributions(
        cls,
        model: ModelArtifact,
        feature_values: dict[str, float],
    ) -> tuple[dict[str, float], float]:
        trees = model.coefficients_or_weights.get("trees")
        if not isinstance(trees, list) or not trees:
            raise ValueError("Registered random-forest artifact does not contain tree structures.")

        contributions = {name: 0.0 for name in model.feature_names}
        baseline = 0.0
        for tree in trees:
            if not isinstance(tree, dict):
                raise TypeError("Registered random-forest artifact contains an invalid tree.")
            node = tree
            node_value = cls._mean_leaf_value(node)
            baseline += node_value / len(trees)
            while "value" not in node:
                feature_index = node.get("feature_idx")
                threshold = node.get("threshold")
                if not isinstance(feature_index, int) or feature_index >= len(model.feature_names) or threshold is None:
                    raise ValueError("Registered random-forest artifact contains an invalid split.")
                feature_name = model.feature_names[feature_index]
                feature_value = feature_values[feature_name]
                child = node.get("left") if feature_value <= float(threshold) else node.get("right")
                if not isinstance(child, dict):
                    raise TypeError("Registered random-forest artifact contains a missing branch.")
                child_value = cls._mean_leaf_value(child)
                contributions[feature_name] += (child_value - node_value) / len(trees)
                node, node_value = child, child_value

        return contributions, baseline

    @classmethod
    def _gradient_boosting_contributions(
        cls,
        model: ModelArtifact,
        feature_values: dict[str, float],
    ) -> tuple[dict[str, float], float]:
        weights = model.coefficients_or_weights
        stumps = weights.get("stumps")
        if not isinstance(stumps, list) or not stumps:
            raise ValueError("Registered gradient-boosting artifact does not contain stump structures.")

        learning_rate = float(weights.get("learning_rate", 0.1))
        contributions = {name: 0.0 for name in model.feature_names}
        baseline = float(weights.get("base_log_odds", model.intercept))
        for stump in stumps:
            if not isinstance(stump, dict):
                raise TypeError("Registered gradient-boosting artifact contains an invalid stump.")
            feature_index = stump.get("feature_idx")
            if feature_index is None:
                continue
            if not isinstance(feature_index, int) or feature_index >= len(model.feature_names):
                raise ValueError("Registered gradient-boosting artifact contains an invalid feature index.")
            feature_name = model.feature_names[feature_index]
            left = float(stump["left_value"])
            right = float(stump["right_value"])
            stump_baseline = (left + right) / 2.0
            baseline += learning_rate * stump_baseline
            observed = left if feature_values[feature_name] <= float(stump["threshold"]) else right
            contributions[feature_name] += learning_rate * (observed - stump_baseline)
        return contributions, 1.0 / (1.0 + math.exp(-max(min(baseline, 35.0), -35.0)))

    @classmethod
    def explain_prediction(
        cls,
        model: ModelArtifact,
        features: dict[str, Any],
        predicted_probability: float,
        entity_id: str,
        prediction_id: UUID,
        *,
        feature_version: str = "",
        asset_id: str | None = None,
        input_snapshot: dict[str, Any] | None = None,
        near_zero_tolerance: float = 0.01,
    ) -> PredictionExplanation:
        snapshot = dict(input_snapshot or {})
        snapshot_features = snapshot.get("feature_values", features)
        if not isinstance(snapshot_features, dict):
            snapshot_features = {}
        numeric_values = {
            name: float(snapshot_features[name])
            for name in model.feature_names
            if name in snapshot_features and isinstance(snapshot_features[name], (int, float))
        }
        missing = [name for name in model.feature_names if name not in numeric_values]
        recorded_missing = snapshot.get("missing_features", [])
        recorded_missing = (
            [name for name in recorded_missing if name in model.feature_names]
            if isinstance(recorded_missing, list)
            else []
        )
        feature_metadata = snapshot.get("observation_dates", snapshot.get("feature_metadata", {}))
        if not isinstance(feature_metadata, dict):
            feature_metadata = {}
        evidence_references: dict[str, list[str]] = {}
        uncertain: list[FeatureUncertainty] = []

        for name in model.feature_names:
            metadata = feature_metadata.get(name)
            metadata = metadata if isinstance(metadata, dict) else {}
            references = metadata.get("evidence_references", [])
            provenance = metadata.get("provenance", {})
            if isinstance(provenance, dict) and provenance.get("source_count") == 0:
                references = []
            evidence_references[name] = [str(ref) for ref in references] if isinstance(references, list) else []
            confidence = metadata.get("confidence")
            if name in missing:
                uncertain.append(
                    FeatureUncertainty(
                        feature_name=name,
                        reason="Feature value was unavailable in the recorded prediction snapshot.",
                        feature_version=feature_version,
                    )
                )
            elif name in recorded_missing:
                uncertain.append(
                    FeatureUncertainty(
                        feature_name=name,
                        reason="Feature value was missing and median-imputed for model execution; its attribution is conditional, not observed evidence.",
                        feature_value=numeric_values[name],
                        feature_version=feature_version,
                    )
                )
            elif confidence is not None and float(confidence) < 0.5:
                uncertain.append(
                    FeatureUncertainty(
                        feature_name=name,
                        reason="Recorded feature confidence is below 0.5.",
                        feature_value=numeric_values[name],
                        confidence=float(confidence),
                        feature_version=feature_version,
                    )
                )
            elif metadata and not evidence_references[name]:
                uncertain.append(
                    FeatureUncertainty(
                        feature_name=name,
                        reason="No evidence provenance is recorded for this derived feature.",
                        feature_value=numeric_values[name],
                        confidence=float(confidence) if confidence is not None else None,
                        feature_version=feature_version,
                    )
                )
            elif not metadata:
                uncertain.append(
                    FeatureUncertainty(
                        feature_name=name,
                        reason="The input snapshot has no feature provenance or confidence metadata.",
                        feature_value=numeric_values[name],
                        feature_version=feature_version,
                    )
                )

        contributions: dict[str, float] = {}
        base_value = 0.5
        contribution_unit = "model_output"
        attribution_method = ""
        unavailable_reason: str | None = None
        explanation_available = not missing

        if missing:
            unavailable_reason = "Required feature values are missing from the saved input snapshot."
        elif model.architecture == ModelArchitecture.LOGISTIC_REGRESSION:
            weights = model.coefficients_or_weights.get("weights", [])
            if len(weights) < len(model.feature_names):
                explanation_available = False
                unavailable_reason = "Registered logistic-regression artifact has incomplete coefficients."
            else:
                base_value = 1.0 / (1.0 + math.exp(-max(min(model.intercept, 35.0), -35.0)))
                contributions = {
                    name: float(weights[index]) * numeric_values[name]
                    for index, name in enumerate(model.feature_names)
                }
                contribution_unit = "log_odds"
                attribution_method = "linear_coefficient_times_input_value"
        elif model.architecture == ModelArchitecture.RANDOM_FOREST:
            try:
                contributions, base_value = cls._random_forest_contributions(model, numeric_values)
                contribution_unit = "probability"
                attribution_method = "tree_path_delta_from_equal_leaf_mean"
            except (KeyError, TypeError, ValueError) as exc:
                explanation_available = False
                unavailable_reason = str(exc)
        elif model.architecture == ModelArchitecture.GRADIENT_BOOSTING:
            try:
                contributions, base_value = cls._gradient_boosting_contributions(model, numeric_values)
                contribution_unit = "log_odds"
                attribution_method = "boosting_stump_delta_from_mean_branch_value"
            except (KeyError, TypeError, ValueError) as exc:
                explanation_available = False
                unavailable_reason = str(exc)
        else:
            explanation_available = False
            unavailable_reason = f"Explanation is unsupported for model architecture '{model.architecture}'."

        importances = model.coefficients_or_weights.get("feature_importances", {})
        if not isinstance(importances, dict):
            importances = {}
        importance_total = sum(max(0.0, float(value)) for value in importances.values()) or 1.0
        attributions: list[FeatureAttribution] = []
        if explanation_available:
            for index, name in enumerate(model.feature_names):
                contribution = contributions.get(name, 0.0)
                direction: Literal["POSITIVE", "NEGATIVE", "NEUTRAL"]
                if contribution > near_zero_tolerance:
                    direction = "POSITIVE"
                elif contribution < -near_zero_tolerance:
                    direction = "NEGATIVE"
                else:
                    direction = "NEUTRAL"
                    uncertain.append(
                        FeatureUncertainty(
                            feature_name=name,
                            reason="Instance-specific model contribution is within the near-zero direction tolerance.",
                            feature_value=numeric_values[name],
                            feature_version=feature_version,
                        )
                    )
                attribution = FeatureAttribution(
                    feature_name=name,
                    feature_value=numeric_values[name],
                    importance_weight=round(
                        max(0.0, float(importances.get(str(index), importances.get(index, 0.0))))
                        / importance_total,
                        4,
                    ),
                    attribution_score=round(contribution, 6),
                    directional_impact=direction,
                    explanation=f"Instance-specific model contribution: {contribution:+.6f} {contribution_unit}.",
                    feature_version=feature_version,
                    contribution_unit=contribution_unit,
                )
                attributions.append(attribution)

        top_drivers = sorted(attributions, key=lambda item: abs(item.attribution_score), reverse=True)
        positive = [item for item in top_drivers if item.directional_impact == "POSITIVE"]
        negative = [item for item in top_drivers if item.directional_impact == "NEGATIVE"]
        narrative = (
            f"MODEL EXPLANATION for {entity_id} from {model.name}:{model.version}; "
            "feature contributions describe model behavior and are not scientific evidence."
        )
        if unavailable_reason:
            narrative += f" Explanation unavailable: {unavailable_reason}"

        return PredictionExplanation(
            prediction_id=prediction_id,
            entity_id=entity_id,
            asset_id=asset_id or snapshot.get("asset_id"),
            model_name=model.name,
            model_version=model.version,
            feature_version=feature_version or str(snapshot.get("feature_version", "")),
            explanation_type="MODEL_EXPLANATION",
            attribution_method=attribution_method,
            input_snapshot=snapshot,
            feature_evidence_references=evidence_references,
            explanation_available=explanation_available,
            unavailable_reason=unavailable_reason,
            predicted_probability=round(predicted_probability, 4),
            base_value=round(base_value, 6),
            top_drivers=top_drivers,
            positive_contributors=positive,
            negative_contributors=negative,
            uncertain_features=uncertain,
            missing_features=sorted(set(missing + recorded_missing)),
            summary_narrative=narrative,
        )

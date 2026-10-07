"""
Explainability Engine for Interpretable ML.

Computes feature attributions, directional impacts, and clinical/commercial narratives
for any prediction made by baseline models (Logistic Regression, Random Forest, Gradient Boosting).
"""

from __future__ import annotations

import math
from typing import Dict, List
from uuid import UUID

from .models import (
    FeatureAttribution,
    ModelArchitecture,
    ModelArtifact,
    PredictionExplanation,
)


class ExplainabilityEngine:
    """
    Interpretable attribution engine providing transparent local feature attributions
    and narrative summaries without opaque black-box approximations.
    """

    @classmethod
    def explain_prediction(
        cls,
        model: ModelArtifact,
        features: Dict[str, float],
        predicted_probability: float,
        entity_id: str,
        prediction_id: UUID,
    ) -> PredictionExplanation:
        feature_names = model.feature_names
        attributions: List[FeatureAttribution] = []

        if model.architecture == ModelArchitecture.LOGISTIC_REGRESSION:
            weights = model.coefficients_or_weights.get("weights", [])
            intercept = model.intercept
            base_value = 1.0 / (1.0 + math.exp(-max(min(intercept, 35.0), -35.0)))
            total_abs_w = sum(abs(w) for w in weights) or 1.0

            for i, name in enumerate(feature_names):
                w = weights[i] if i < len(weights) else 0.0
                val = features.get(name, 0.0)
                # Linear contribution to log-odds
                contrib = w * val
                importance = abs(w) / total_abs_w

                if contrib > 0.01:
                    direction = "POSITIVE"
                    narrative = f"{name.replace('_', ' ').title()} ({val:.1f}) actively elevates pursuit score (+{contrib:.2f})."
                elif contrib < -0.01:
                    direction = "NEGATIVE"
                    narrative = f"{name.replace('_', ' ').title()} ({val:.1f}) depresses pursuit probability ({contrib:.2f})."
                else:
                    direction = "NEUTRAL"
                    narrative = f"{name.replace('_', ' ').title()} has neutral marginal impact."

                attributions.append(
                    FeatureAttribution(
                        feature_name=name,
                        feature_value=round(val, 2),
                        importance_weight=round(importance, 4),
                        attribution_score=round(contrib, 4),
                        directional_impact=direction,
                        explanation=narrative,
                    )
                )

        else:
            # Tree-based baseline (Random Forest or Gradient Boosting)
            raw_importances = model.coefficients_or_weights.get("feature_importances", {})
            base_value = 0.5

            total_gain = sum(float(v) for v in raw_importances.values()) or 1.0

            for i, name in enumerate(feature_names):
                val = features.get(name, 0.0)
                imp = float(raw_importances.get(str(i), raw_importances.get(i, 0.0))) / total_gain
                # Normalized directional score relative to median feature midpoint (50.0)
                deviation = (val - 50.0) / 50.0
                contrib = imp * deviation

                if contrib > 0.01:
                    direction = "POSITIVE"
                    narrative = f"High {name.replace('_', ' ')} ({val:.1f}) provides positive evidence support."
                elif contrib < -0.01:
                    direction = "NEGATIVE"
                    narrative = f"Lower {name.replace('_', ' ')} ({val:.1f}) reduces model confidence."
                else:
                    direction = "NEUTRAL"
                    narrative = f"{name.replace('_', ' ')} is near baseline."

                attributions.append(
                    FeatureAttribution(
                        feature_name=name,
                        feature_value=round(val, 2),
                        importance_weight=round(imp, 4),
                        attribution_score=round(contrib, 4),
                        directional_impact=direction,
                        explanation=narrative,
                    )
                )

        # Sort top drivers by absolute attribution score
        top_drivers = sorted(attributions, key=lambda a: abs(a.attribution_score), reverse=True)

        # Generate clinical/commercial summary narrative
        pos_drivers = [d.feature_name.replace("_", " ") for d in top_drivers if d.directional_impact == "POSITIVE"][:2]
        neg_drivers = [d.feature_name.replace("_", " ") for d in top_drivers if d.directional_impact == "NEGATIVE"][:2]

        narrative_parts = [
            f"Asset {entity_id} received a predicted success probability of {predicted_probability:.1%}."
        ]
        if pos_drivers:
            narrative_parts.append(f"Key positive drivers include {', '.join(pos_drivers)}.")
        if neg_drivers:
            narrative_parts.append(f"Primary risk headwinds include {', '.join(neg_drivers)}.")
        if not pos_drivers and not neg_drivers:
            narrative_parts.append("Features are aligned near baseline expectation.")

        summary_narrative = " ".join(narrative_parts)

        return PredictionExplanation(
            prediction_id=prediction_id,
            entity_id=entity_id,
            model_version=model.version,
            predicted_probability=round(predicted_probability, 4),
            base_value=round(base_value, 4),
            top_drivers=top_drivers,
            summary_narrative=summary_narrative,
        )

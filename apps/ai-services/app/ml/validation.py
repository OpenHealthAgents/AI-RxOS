"""
AI Output Validation Module

Validates AI-generated recommendations and outputs against typed schemas and business constraints.
Prevents unvalidated model output from becoming authoritative canonical facts or recommendations.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID


class ValidationError(ValueError):
    """Raised when AI output fails validation."""
    pass


class RecommendationValidator:
    """Validates AI-generated recommendation outputs."""

    VALID_ACTIONS = {
        "PURSUE",
        "INVESTIGATE",
        "PARTNER",
        "LICENSE",
        "MONITOR",
        "AVOID",
        "INSUFFICIENT_EVIDENCE",
    }

    @classmethod
    def validate_recommendation(cls, output: dict[str, Any]) -> dict[str, Any]:
        """
        Validates a recommendation output structure.

        Args:
            output: Raw AI model output

        Returns:
            Validated and normalized output

        Raises:
            ValidationError: If output is malformed or contains invalid values
        """
        if not isinstance(output, dict):
            raise ValidationError("Recommendation output must be a dictionary")

        # Validate action
        action = output.get("action")
        if action is None:
            raise ValidationError("Recommendation must include 'action' field")
        if not isinstance(action, str):
            raise ValidationError("Action must be a string")
        if action not in cls.VALID_ACTIONS:
            raise ValidationError(f"Invalid action '{action}'. Must be one of: {cls.VALID_ACTIONS}")

        # Validate score
        score = output.get("score")
        if score is not None:
            try:
                score = float(score)
            except (ValueError, TypeError):
                raise ValidationError("Score must be a number")
            if not (0 <= score <= 100):
                raise ValidationError("Score must be between 0 and 100")

        # Validate confidence
        confidence = output.get("confidence")
        if confidence is not None:
            try:
                confidence = float(confidence)
            except (ValueError, TypeError):
                raise ValidationError("Confidence must be a number")
            if not (0 <= confidence <= 1):
                raise ValidationError("Confidence must be between 0 and 1")

        # Validate asset_id if present
        asset_id = output.get("asset_id")
        if asset_id is not None:
            try:
                UUID(str(asset_id))
            except (ValueError, AttributeError):
                raise ValidationError("asset_id must be a valid UUID")

        # Validate evidence_refs if present
        evidence_refs = output.get("evidence_refs")
        if evidence_refs is not None:
            if not isinstance(evidence_refs, list):
                raise ValidationError("evidence_refs must be a list")
            for ref in evidence_refs:
                if not isinstance(ref, dict):
                    raise ValidationError("Each evidence reference must be a dictionary")

        # Return validated output (normalized)
        return {
            "action": action,
            "score": float(score) if score is not None else None,
            "confidence": float(confidence) if confidence is not None else None,
            "asset_id": str(asset_id) if asset_id else None,
            "evidence_refs": evidence_refs or [],
            "rationale": output.get("rationale", ""),
            "model_version": output.get("model_version"),
            "feature_version": output.get("feature_version"),
            "evidence_version": output.get("evidence_version"),
        }

    @classmethod
    def validate_prediction(cls, output: dict[str, Any]) -> dict[str, Any]:
        """
        Validates a prediction output structure.

        Args:
            output: Raw AI model output

        Returns:
            Validated and normalized output

        Raises:
            ValidationError: If output is malformed
        """
        if not isinstance(output, dict):
            raise ValidationError("Prediction output must be a dictionary")

        # Validate prediction value
        prediction = output.get("prediction")
        if prediction is None:
            raise ValidationError("Prediction must include 'prediction' field")

        # Validate probability if present
        probability = output.get("probability")
        if probability is not None:
            try:
                probability = float(probability)
            except (ValueError, TypeError):
                raise ValidationError("Probability must be a number")
            if not (0 <= probability <= 1):
                raise ValidationError("Probability must be between 0 and 1")

        return {
            "prediction": prediction,
            "probability": float(probability) if probability is not None else None,
            "model_version": output.get("model_version"),
            "feature_version": output.get("feature_version"),
        }

    @classmethod
    def validate_evidence_classification(cls, output: dict[str, Any]) -> dict[str, Any]:
        """
        Validates evidence classification output.

        Args:
            output: Raw AI model output

        Returns:
            Validated and normalized output

        Raises:
            ValidationError: If output is malformed
        """
        if not isinstance(output, dict):
            raise ValidationError("Evidence classification output must be a dictionary")

        classification = output.get("classification")
        if classification is None:
            raise ValidationError("Evidence classification must include 'classification' field")
        if not isinstance(classification, str):
            raise ValidationError("Classification must be a string")

        quality = output.get("quality")
        if quality is not None:
            valid_qualities = {"high", "moderate", "low", "insufficient"}
            if quality.lower() not in valid_qualities:
                raise ValidationError(f"Invalid quality '{quality}'. Must be one of: {valid_qualities}")

        return {
            "classification": classification,
            "quality": quality.lower() if quality else None,
            "confidence": output.get("confidence"),
            "rationale": output.get("rationale", ""),
        }

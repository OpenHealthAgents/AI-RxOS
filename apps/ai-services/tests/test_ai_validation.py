"""
Tests for AI Output Validation Module
"""

import pytest

from app.ml.validation import RecommendationValidator, ValidationError


def test_validate_recommendation_valid_output():
    """Test validation of a valid recommendation."""
    output = {
        "action": "PURSUE",
        "score": 85.5,
        "confidence": 0.88,
        "asset_id": "123e4567-e89b-12d3-a456-426614174000",
        "rationale": "Strong clinical evidence",
    }
    validated = RecommendationValidator.validate_recommendation(output)
    assert validated["action"] == "PURSUE"
    assert validated["score"] == 85.5
    assert validated["confidence"] == 0.88
    assert validated["asset_id"] == "123e4567-e89b-12d3-a456-426614174000"


def test_validate_recommendation_missing_action():
    """Test that missing action raises ValidationError."""
    output = {"score": 85.5, "confidence": 0.88}
    with pytest.raises(ValidationError, match="must include 'action'"):
        RecommendationValidator.validate_recommendation(output)


def test_validate_recommendation_invalid_action():
    """Test that invalid action raises ValidationError."""
    output = {"action": "INVALID_ACTION", "score": 85.5}
    with pytest.raises(ValidationError, match="Invalid action"):
        RecommendationValidator.validate_recommendation(output)


def test_validate_recommendation_score_out_of_range():
    """Test that score out of range raises ValidationError."""
    output = {"action": "PURSUE", "score": 150}
    with pytest.raises(ValidationError, match="Score must be between 0 and 100"):
        RecommendationValidator.validate_recommendation(output)


def test_validate_recommendation_confidence_out_of_range():
    """Test that confidence out of range raises ValidationError."""
    output = {"action": "PURSUE", "confidence": 1.5}
    with pytest.raises(ValidationError, match="Confidence must be between 0 and 1"):
        RecommendationValidator.validate_recommendation(output)


def test_validate_recommendation_invalid_asset_id():
    """Test that invalid asset_id raises ValidationError."""
    output = {"action": "PURSUE", "asset_id": "not-a-uuid"}
    with pytest.raises(ValidationError, match="asset_id must be a valid UUID"):
        RecommendationValidator.validate_recommendation(output)


def test_validate_recommendation_invalid_evidence_refs():
    """Test that invalid evidence_refs raises ValidationError."""
    output = {"action": "PURSUE", "evidence_refs": "not-a-list"}
    with pytest.raises(ValidationError, match="evidence_refs must be a list"):
        RecommendationValidator.validate_recommendation(output)


def test_validate_recommendation_non_dict_output():
    """Test that non-dict output raises ValidationError."""
    with pytest.raises(ValidationError, match="must be a dictionary"):
        RecommendationValidator.validate_recommendation("not-a-dict")


def test_validate_prediction_valid_output():
    """Test validation of a valid prediction."""
    output = {
        "prediction": "positive",
        "probability": 0.92,
        "model_version": "v1",
    }
    validated = RecommendationValidator.validate_prediction(output)
    assert validated["prediction"] == "positive"
    assert validated["probability"] == 0.92
    assert validated["model_version"] == "v1"


def test_validate_prediction_missing_prediction():
    """Test that missing prediction raises ValidationError."""
    output = {"probability": 0.92}
    with pytest.raises(ValidationError, match="must include 'prediction'"):
        RecommendationValidator.validate_prediction(output)


def test_validate_prediction_probability_out_of_range():
    """Test that probability out of range raises ValidationError."""
    output = {"prediction": "positive", "probability": 1.5}
    with pytest.raises(ValidationError, match="Probability must be between 0 and 1"):
        RecommendationValidator.validate_prediction(output)


def test_validate_evidence_classification_valid_output():
    """Test validation of valid evidence classification."""
    output = {
        "classification": "HIGH_PRIORITY",
        "quality": "high",
        "rationale": "Strong evidence",
    }
    validated = RecommendationValidator.validate_evidence_classification(output)
    assert validated["classification"] == "HIGH_PRIORITY"
    assert validated["quality"] == "high"
    assert validated["rationale"] == "Strong evidence"


def test_validate_evidence_classification_invalid_quality():
    """Test that invalid quality raises ValidationError."""
    output = {"classification": "HIGH_PRIORITY", "quality": "invalid"}
    with pytest.raises(ValidationError, match="Invalid quality"):
        RecommendationValidator.validate_evidence_classification(output)


def test_validate_evidence_classification_missing_classification():
    """Test that missing classification raises ValidationError."""
    output = {"quality": "high"}
    with pytest.raises(ValidationError, match="must include 'classification'"):
        RecommendationValidator.validate_evidence_classification(output)


def test_validate_recommendation_normalizes_types():
    """Test that validation normalizes numeric types."""
    output = {
        "action": "PURSUE",
        "score": "85",  # String that should be converted
        "confidence": 0.88,
    }
    validated = RecommendationValidator.validate_recommendation(output)
    assert isinstance(validated["score"], float)
    assert validated["score"] == 85.0


def test_validate_recommendation_optional_fields():
    """Test that optional fields can be omitted."""
    output = {"action": "MONITOR"}
    validated = RecommendationValidator.validate_recommendation(output)
    assert validated["action"] == "MONITOR"
    assert validated["score"] is None
    assert validated["confidence"] is None
    assert validated["asset_id"] is None

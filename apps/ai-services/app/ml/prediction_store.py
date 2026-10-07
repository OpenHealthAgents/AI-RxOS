"""
Prediction Store for ML Inferences and Ground Truth Tracking.

Persists model inference records, features used, explanations, and delayed actual outcomes
for auditing, model calibration tracking, and drift detection.
"""

from __future__ import annotations

from datetime import date, timezone, datetime
from typing import Dict, List, Optional
from uuid import UUID

from .models import StoredPrediction


class PredictionStore:
    """
    In-memory and persistent storage for serving predictions and observed outcomes.
    """

    def __init__(self) -> None:
        self._predictions: Dict[str, StoredPrediction] = {}

    def save_prediction(self, prediction: StoredPrediction) -> StoredPrediction:
        """Stores an inference prediction record."""
        self._predictions[str(prediction.prediction_id)] = prediction
        return prediction

    def get_prediction(self, prediction_id: UUID | str) -> Optional[StoredPrediction]:
        """Retrieves a single prediction by ID."""
        return self._predictions.get(str(prediction_id))

    def list_predictions(
        self,
        entity_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[StoredPrediction]:
        """Returns predictions filtered optionally by entity_id."""
        records = list(self._predictions.values())
        if entity_id:
            records = [r for r in records if r.entity_id.lower() == entity_id.lower()]
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records[:limit]

    def record_outcome(
        self,
        prediction_id: UUID | str,
        actual_outcome: float,
        observed_date: Optional[date] = None,
    ) -> StoredPrediction:
        """Records ground truth actual outcome when clinical/regulatory event resolves."""
        key = str(prediction_id)
        if key not in self._predictions:
            raise KeyError(f"Prediction '{prediction_id}' not found in prediction store.")

        existing = self._predictions[key]
        obs_date = observed_date or date.today()
        updated = existing.model_copy(
            update={
                "actual_outcome": actual_outcome,
                "outcome_observed_date": obs_date,
            }
        )
        self._predictions[key] = updated
        return updated

    def get_evaluated_predictions(self) -> List[StoredPrediction]:
        """Returns predictions with recorded actual outcomes."""
        return [r for r in self._predictions.values() if r.actual_outcome is not None]

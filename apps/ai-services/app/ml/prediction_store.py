"""
Prediction Store for ML Inferences and Ground Truth Tracking.

Persists model inference records, features used, explanations, and delayed actual outcomes
for auditing, model calibration tracking, and drift detection.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from .models import ModelMonitoringReport, PredictionFailure, StoredPrediction


class PredictionStore:
    """
    In-memory and persistent storage for serving predictions and observed outcomes.
    """

    def __init__(self) -> None:
        self._predictions: dict[str, StoredPrediction] = {}
        self._failures: dict[str, PredictionFailure] = {}
        self._monitoring_reports: dict[str, ModelMonitoringReport] = {}

    def save_prediction(self, prediction: StoredPrediction) -> StoredPrediction:
        """Stores an immutable inference record without replacing an existing prediction."""
        key = str(prediction.prediction_id)
        if key in self._predictions:
            raise ValueError(f"Prediction '{prediction.prediction_id}' already exists.")
        self._predictions[key] = prediction
        return prediction

    def get_prediction(
        self,
        prediction_id: UUID | str,
        tenant_id: str | None = None,
    ) -> StoredPrediction | None:
        """Retrieves a prediction only within its exact tenant scope."""
        prediction = self._predictions.get(str(prediction_id))
        if prediction is None or prediction.tenant_id != tenant_id:
            return None
        return prediction

    def list_predictions(
        self,
        entity_id: str | None = None,
        limit: int = 50,
        *,
        tenant_id: str | None = None,
        model_version: str | None = None,
        feature_version: str | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> list[StoredPrediction]:
        """Returns predictions within exact tenant, version, and timestamp filters."""
        records = [r for r in self._predictions.values() if r.tenant_id == tenant_id]
        if entity_id:
            records = [r for r in records if r.entity_id.lower() == entity_id.lower()]
        if model_version is not None:
            records = [r for r in records if r.model_version == model_version]
        if feature_version is not None:
            records = [r for r in records if r.feature_version == feature_version]
        if window_start is not None:
            records = [r for r in records if r.prediction_timestamp >= window_start]
        if window_end is not None:
            records = [r for r in records if r.prediction_timestamp <= window_end]
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records[:limit]

    def record_failure(self, failure: PredictionFailure) -> PredictionFailure:
        """Records a failed prediction attempt under its tenant and requested version."""
        key = str(failure.failure_id)
        if key in self._failures:
            raise ValueError(f"Prediction failure '{failure.failure_id}' already exists.")
        self._failures[key] = failure
        return failure

    def list_failures(
        self,
        *,
        tenant_id: str | None = None,
        model_version: str | None = None,
        feature_version: str | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> list[PredictionFailure]:
        """Returns failure events within exact tenant, version, and timestamp filters."""
        records = [failure for failure in self._failures.values() if failure.tenant_id == tenant_id]
        if model_version is not None:
            records = [failure for failure in records if failure.model_version == model_version]
        if feature_version is not None:
            records = [failure for failure in records if failure.feature_version == feature_version]
        if window_start is not None:
            records = [failure for failure in records if failure.failed_at >= window_start]
        if window_end is not None:
            records = [failure for failure in records if failure.failed_at <= window_end]
        return sorted(records, key=lambda failure: failure.failed_at, reverse=True)

    def save_monitoring_report(
        self,
        report: ModelMonitoringReport,
    ) -> ModelMonitoringReport:
        """Persists an immutable tenant-scoped monitoring report."""
        key = str(report.report_id)
        if key in self._monitoring_reports:
            raise ValueError(f"Monitoring report '{report.report_id}' already exists.")
        self._monitoring_reports[key] = report
        return report

    def get_monitoring_report(
        self,
        report_id: UUID | str,
        tenant_id: str | None = None,
    ) -> ModelMonitoringReport | None:
        """Retrieves a monitoring report only within its exact tenant scope."""
        report = self._monitoring_reports.get(str(report_id))
        if report is None or report.tenant_id != tenant_id:
            return None
        return report

    def record_outcome(
        self,
        prediction_id: UUID | str,
        actual_outcome: float,
        observed_date: date | None = None,
        *,
        tenant_id: str | None = None,
    ) -> StoredPrediction:
        """Records ground truth actual outcome when clinical/regulatory event resolves."""
        key = str(prediction_id)
        existing = self.get_prediction(key, tenant_id=tenant_id)
        if existing is None:
            raise KeyError(f"Prediction '{prediction_id}' not found in prediction store.")

        obs_date = observed_date or datetime.now(timezone.utc).date()
        updated = existing.model_copy(
            update={
                "actual_outcome": actual_outcome,
                "outcome_observed_date": obs_date,
            }
        )
        self._predictions[key] = updated
        return updated

    def get_evaluated_predictions(
        self,
        tenant_id: str | None = None,
    ) -> list[StoredPrediction]:
        """Returns predictions with recorded actual outcomes."""
        return [
            r for r in self._predictions.values()
            if r.tenant_id == tenant_id and r.actual_outcome is not None
        ]

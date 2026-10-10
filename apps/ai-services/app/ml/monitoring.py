"""Version- and tenant-scoped prediction, drift, performance, and calibration monitoring."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date, datetime, timezone
from typing import Literal, Protocol
from uuid import uuid4

from .models import (
    DriftReport,
    DriftStatus,
    FeatureDriftMetric,
    ModelArtifact,
    ModelMonitoringReport,
    MonitoringAlert,
    MonitoringStatus,
    PredictionFailure,
    StoredPrediction,
)
from .pipeline import ValidationPipeline


class DriftDetector(Protocol):
    """Extensible contract for comparing a reference and production feature sample."""

    name: str

    def calculate(self, baseline: list[float], current: list[float]) -> float | None:
        """Return a drift statistic, or None when the populations cannot be compared."""


class PopulationStabilityIndexDetector:
    """Default detector, retaining the ML subsystem's existing PSI convention."""

    name = "psi"

    def calculate(self, baseline: list[float], current: list[float]) -> float | None:
        return DriftDetectionEngine.calculate_psi(baseline, current)


class DriftDetectionEngine:
    """Compares observed data against an explicit model-version training reference."""

    @classmethod
    def calculate_psi(
        cls,
        baseline_values: list[float],
        current_values: list[float],
        num_bins: int = 5,
    ) -> float | None:
        """Calculate PSI, returning None when either comparison population is absent."""
        if not baseline_values or not current_values:
            return None
        if num_bins < 1:
            raise ValueError("num_bins must be at least 1.")
        if any(not math.isfinite(value) for value in baseline_values + current_values):
            raise ValueError("PSI inputs must contain only finite values.")

        minimum = min(baseline_values)
        maximum = max(baseline_values)
        if minimum == maximum:
            baseline_counts = [len(baseline_values)]
            current_counts = [sum(minimum <= value <= maximum for value in current_values),
                              sum(value < minimum or value > maximum for value in current_values)]
            baseline_counts = [baseline_counts[0], 0]
            bin_count = 2
        else:
            step = (maximum - minimum) / num_bins
            baseline_counts = [0] * num_bins
            current_counts = [0] * num_bins
            for value in baseline_values:
                index = min(int((value - minimum) / step), num_bins - 1)
                baseline_counts[index] += 1
            for value in current_values:
                if value < minimum:
                    current_counts[0] += 1
                elif value > maximum:
                    current_counts[-1] += 1
                else:
                    index = min(int((value - minimum) / step), num_bins - 1)
                    current_counts[index] += 1
            bin_count = num_bins

        epsilon = 1e-4
        baseline_total = len(baseline_values)
        current_total = len(current_values)
        psi = 0.0
        for index in range(bin_count):
            baseline_fraction = max(baseline_counts[index] / baseline_total, epsilon)
            current_fraction = max(current_counts[index] / current_total, epsilon)
            psi += (current_fraction - baseline_fraction) * math.log(current_fraction / baseline_fraction)
        return round(max(0.0, psi), 4)

    @classmethod
    def evaluate_drift(
        cls,
        model_version: str,
        baseline_features: dict[str, list[float]],
        current_features: dict[str, list[float]],
        window_start: date | None = None,
        window_end: date | None = None,
    ) -> DriftReport:
        """Legacy PSI report; absent populations are explicitly insufficient."""
        feature_drifts: dict[str, FeatureDriftMetric] = {}
        has_severe = False
        has_moderate = False
        has_insufficient = False
        total_current = 0

        for feature_name, baseline_values in baseline_features.items():
            current_values = current_features.get(feature_name, [])
            total_current = max(total_current, len(current_values))
            psi = cls.calculate_psi(baseline_values, current_values)
            if psi is None:
                status = DriftStatus.INSUFFICIENT_DATA
                flagged = False
                has_insufficient = True
            elif psi >= 0.25:
                status = DriftStatus.SEVERE_DRIFT
                flagged = True
                has_severe = True
            elif psi >= 0.10:
                status = DriftStatus.MODERATE_DRIFT
                flagged = True
                has_moderate = True
            else:
                status = DriftStatus.NO_DRIFT
                flagged = False

            feature_drifts[feature_name] = FeatureDriftMetric(
                feature_name=feature_name,
                baseline_mean=(sum(baseline_values) / len(baseline_values)) if baseline_values else None,
                current_mean=(sum(current_values) / len(current_values)) if current_values else None,
                psi=psi,
                drift_status=status,
                flagged=flagged,
                baseline_count=len(baseline_values),
                current_count=len(current_values),
            )

        if has_severe:
            overall_status = DriftStatus.SEVERE_DRIFT
            alert_triggered = True
            recommendation = "Severe distribution drift detected. Review affected features and model suitability."
        elif has_moderate:
            overall_status = DriftStatus.MODERATE_DRIFT
            alert_triggered = False
            recommendation = "Moderate distribution shift detected. Increase monitoring frequency."
        elif has_insufficient or not feature_drifts:
            overall_status = DriftStatus.INSUFFICIENT_DATA
            alert_triggered = False
            recommendation = "Insufficient reference or current data for a drift comparison."
        else:
            overall_status = DriftStatus.NO_DRIFT
            alert_triggered = False
            recommendation = "Compared distributions are stable within configured PSI thresholds."

        today = datetime.now(timezone.utc).date()
        start_date = window_start or today
        end_date = window_end or today
        return DriftReport(
            report_id=uuid4(),
            model_version=model_version,
            evaluation_window_start=start_date,
            evaluation_window_end=end_date,
            total_inferences_evaluated=total_current,
            overall_drift_status=overall_status,
            feature_drifts=feature_drifts,
            drift_alert_triggered=alert_triggered,
            recommended_action=recommendation,
        )

    @classmethod
    def evaluate_model(
        cls,
        model: ModelArtifact,
        predictions: Sequence[StoredPrediction],
        failures: Sequence[PredictionFailure] = (),
        *,
        window_start: datetime,
        window_end: datetime,
        tenant_id: str | None = None,
        feature_version: str | None = None,
        psi_warning_threshold: float = 0.10,
        psi_critical_threshold: float = 0.25,
        missing_rate_delta_threshold: float = 0.10,
        performance_drop_threshold: float = 0.10,
        calibration_error_threshold: float = 0.05,
        min_outcomes: int = 5,
        drift_detector: DriftDetector | None = None,
    ) -> ModelMonitoringReport:
        """Build a scoped monitoring report from saved prediction/outcome snapshots."""
        if window_start.tzinfo is None or window_end.tzinfo is None:
            raise ValueError("Monitoring window timestamps must be timezone-aware.")
        if window_end < window_start:
            raise ValueError("Monitoring window_end must be on or after window_start.")
        if not (0 <= psi_warning_threshold < psi_critical_threshold):
            raise ValueError("PSI thresholds must satisfy 0 <= warning < critical.")
        if min_outcomes < 1:
            raise ValueError("min_outcomes must be at least 1.")
        if model.tenant_id is not None and model.tenant_id != tenant_id:
            raise ValueError("Monitoring tenant must exactly match the registered model tenant.")
        if feature_version is None:
            if len(model.feature_versions) != 1:
                raise ValueError("feature_version is required to monitor a model with multiple feature versions.")
            feature_version = model.feature_versions[0]
        if feature_version not in model.feature_versions:
            raise ValueError(f"Feature version '{feature_version}' is not registered for this model.")
        detector = drift_detector or PopulationStabilityIndexDetector()

        selected_predictions = [
            prediction for prediction in predictions
            if prediction.model_id == model.model_id
            and prediction.model_version == model.version
            and prediction.feature_version == feature_version
            and prediction.tenant_id == tenant_id
            and window_start <= prediction.prediction_timestamp <= window_end
        ]
        selected_failures = [
            failure for failure in failures
            if failure.model_version == model.version
            and failure.feature_version == feature_version
            and failure.tenant_id == tenant_id
            and window_start <= failure.failed_at <= window_end
            and (failure.model_name is None or failure.model_name == model.name)
        ]
        report_id = uuid4()
        alerts: list[MonitoringAlert] = []
        signals: dict[str, object] = {
            "prediction_count": len(selected_predictions),
            "failure_count": len(selected_failures),
            "model_version": model.version,
            "feature_version": feature_version,
        }
        reference_distributions = model.monitoring_reference.get("feature_distributions", {})
        reference_missing_rates = model.monitoring_reference.get("feature_missing_rates", {})
        if not isinstance(reference_distributions, dict):
            reference_distributions = {}
        if not isinstance(reference_missing_rates, dict):
            reference_missing_rates = {}
        feature_drifts: dict[str, FeatureDriftMetric] = {}
        missing_reasons: list[str] = []
        has_drift = False
        has_warning = False
        has_degradation = False
        total_attempts = len(selected_predictions) + len(selected_failures)

        for feature_name in model.feature_names:
            baseline = reference_distributions.get(feature_name, [])
            if not isinstance(baseline, list):
                baseline = []
            baseline_values = [float(value) for value in baseline if isinstance(value, (int, float))]
            current_values: list[float] = []
            missing_count = 0
            for prediction in selected_predictions:
                values = prediction.input_snapshot.get("feature_values", {})
                if isinstance(values, dict) and isinstance(values.get(feature_name), (int, float)):
                    current_values.append(float(values[feature_name]))
                else:
                    missing_count += 1
            missing_count += sum(feature_name in failure.missing_features for failure in selected_failures)
            raw_baseline_missing = reference_missing_rates.get(feature_name)
            baseline_missing_rate = (
                float(raw_baseline_missing)
                if isinstance(raw_baseline_missing, (int, float))
                else None
            )
            current_missing_rate = missing_count / total_attempts if total_attempts else None
            missing_delta = (
                current_missing_rate - baseline_missing_rate
                if current_missing_rate is not None and baseline_missing_rate is not None
                else None
            )
            psi = detector.calculate(baseline_values, current_values)
            psi_status = (
                DriftStatus.INSUFFICIENT_DATA if psi is None
                else DriftStatus.SEVERE_DRIFT if psi >= psi_critical_threshold
                else DriftStatus.MODERATE_DRIFT if psi >= psi_warning_threshold
                else DriftStatus.NO_DRIFT
            )
            flagged = psi_status in (DriftStatus.SEVERE_DRIFT, DriftStatus.MODERATE_DRIFT)
            if psi is None:
                missing_reasons.append(f"No baseline or current numeric population for feature '{feature_name}'.")
            if flagged:
                severity: Literal["warning", "critical"] = (
                    "critical" if psi_status == DriftStatus.SEVERE_DRIFT else "warning"
                )
                alerts.append(
                    MonitoringAlert(
                        tenant_id=tenant_id,
                        model_name=model.name,
                        model_version=model.version,
                        feature_version=feature_version,
                        metric=f"feature_{detector.name}:{feature_name}",
                        baseline_value=0.0,
                        current_value=psi,
                        threshold=psi_critical_threshold if severity == "critical" else psi_warning_threshold,
                        severity=severity,
                        window_start=window_start,
                        window_end=window_end,
                    )
                )
                has_drift = has_drift or severity == "critical"
                has_warning = has_warning or severity == "warning"

            if missing_delta is not None and missing_delta >= missing_rate_delta_threshold:
                alerts.append(
                    MonitoringAlert(
                        tenant_id=tenant_id,
                        model_name=model.name,
                        model_version=model.version,
                        feature_version=feature_version,
                        metric=f"missing_rate_delta:{feature_name}",
                        baseline_value=baseline_missing_rate,
                        current_value=current_missing_rate,
                        threshold=missing_rate_delta_threshold,
                        severity="critical" if missing_delta >= 2 * missing_rate_delta_threshold else "warning",
                        window_start=window_start,
                        window_end=window_end,
                    )
                )
                has_drift = has_drift or missing_delta >= 2 * missing_rate_delta_threshold
                has_warning = has_warning or missing_delta < 2 * missing_rate_delta_threshold

            feature_drifts[feature_name] = FeatureDriftMetric(
                feature_name=feature_name,
                baseline_mean=sum(baseline_values) / len(baseline_values) if baseline_values else None,
                current_mean=sum(current_values) / len(current_values) if current_values else None,
                psi=psi,
                drift_status=(
                    DriftStatus.MODERATE_DRIFT
                    if missing_delta is not None and missing_delta >= missing_rate_delta_threshold and psi_status == DriftStatus.NO_DRIFT
                    else psi_status
                ),
                flagged=flagged or (missing_delta is not None and missing_delta >= missing_rate_delta_threshold),
                feature_version=feature_version,
                baseline_dataset_version=model.dataset_version,
                baseline_count=len(baseline_values),
                current_count=len(current_values),
                baseline_missing_rate=baseline_missing_rate,
                current_missing_rate=current_missing_rate,
                missing_rate_delta=missing_delta,
            )

        outcomes = [
            prediction for prediction in selected_predictions
            if prediction.actual_outcome is not None
            and prediction.outcome_observed_date is not None
            and window_start.date() <= prediction.outcome_observed_date <= window_end.date()
            and prediction.outcome_observed_date >= prediction.prediction_timestamp.date()
        ]
        performance_metrics: dict[str, float | None] = {}
        calibration_metrics: dict[str, float | None] = {
            "reference_brier_score": model.metrics.brier_score,
            "production_brier_score": None,
            "brier_score_delta": None,
        }
        if len(outcomes) >= min_outcomes:
            y_true = [float(item.actual_outcome) for item in outcomes if item.actual_outcome is not None]
            probabilities = [item.probability for item in outcomes if item.probability is not None]
            if len(probabilities) == len(outcomes):
                measured = ValidationPipeline.evaluate(y_true, probabilities)
                performance_metrics = measured.model_dump()
                production_brier = measured.brier_score
                calibration_metrics["production_brier_score"] = production_brier
                if model.metrics.brier_score is not None and production_brier is not None:
                    delta = production_brier - model.metrics.brier_score
                    calibration_metrics["brier_score_delta"] = delta
                    if delta >= calibration_error_threshold:
                        alerts.append(
                            MonitoringAlert(
                                tenant_id=tenant_id,
                                model_name=model.name,
                                model_version=model.version,
                                feature_version=feature_version,
                                metric="calibration_brier_score_delta",
                                baseline_value=model.metrics.brier_score,
                                current_value=production_brier,
                                threshold=calibration_error_threshold,
                                severity="critical" if delta >= 2 * calibration_error_threshold else "warning",
                                window_start=window_start,
                                window_end=window_end,
                            )
                        )
                        has_degradation = True
        else:
            missing_reasons.append(
                f"At least {min_outcomes} outcomes are required for performance and calibration evaluation; found {len(outcomes)}."
            )

        baseline_accuracy = model.metrics.accuracy
        current_accuracy = performance_metrics.get("accuracy")
        if baseline_accuracy is not None and isinstance(current_accuracy, (int, float)):
            performance_delta = baseline_accuracy - current_accuracy
            signals["performance_drop"] = performance_delta
            if performance_delta >= performance_drop_threshold:
                alerts.append(
                    MonitoringAlert(
                        tenant_id=tenant_id,
                        model_name=model.name,
                        model_version=model.version,
                        feature_version=feature_version,
                        metric="accuracy_drop",
                        baseline_value=baseline_accuracy,
                        current_value=current_accuracy,
                        threshold=performance_drop_threshold,
                        severity="critical" if performance_delta >= 2 * performance_drop_threshold else "warning",
                        window_start=window_start,
                        window_end=window_end,
                    )
                )
                has_degradation = True

        probabilities = [
            float(item.probability)
            for item in selected_predictions
            if item.probability is not None
        ]
        confidences = [
            float(item.confidence)
            for item in selected_predictions
            if item.confidence is not None
        ]
        latencies = [item.latency_ms for item in selected_predictions]
        class_counts: dict[str, int] = {}
        for item in selected_predictions:
            if item.prediction is not None:
                key = str(item.prediction)
                class_counts[key] = class_counts.get(key, 0) + 1
        signals["prediction_class_counts"] = class_counts
        failure_types: dict[str, int] = {}
        for failure in selected_failures:
            failure_types[failure.error_type] = failure_types.get(failure.error_type, 0) + 1
        signals["failure_types"] = failure_types
        signals["probability_count"] = len(probabilities)
        signals["confidence_count"] = len(confidences)
        signals["feature_missingness"] = {
            name: metric.current_missing_rate for name, metric in feature_drifts.items()
        }
        comparable_features = sum(metric.psi is not None for metric in feature_drifts.values())
        signals["data_drift_status"] = (
            DriftStatus.SEVERE_DRIFT.value if has_drift
            else DriftStatus.MODERATE_DRIFT.value if has_warning
            else DriftStatus.NO_DRIFT.value if comparable_features
            else DriftStatus.INSUFFICIENT_DATA.value
        )

        if not selected_predictions or comparable_features == 0:
            status = MonitoringStatus.INSUFFICIENT_DATA
            if not selected_predictions:
                missing_reasons.append("No successful predictions occurred in this model/version/window.")
            if comparable_features == 0:
                missing_reasons.append("No feature had both training-reference and production values to compare.")
        elif has_degradation:
            status = MonitoringStatus.DEGRADED
        elif has_drift:
            status = MonitoringStatus.DRIFT_DETECTED
        elif has_warning:
            status = MonitoringStatus.WARNING
        else:
            status = MonitoringStatus.HEALTHY

        return ModelMonitoringReport(
            report_id=report_id,
            tenant_id=tenant_id,
            model_name=model.name,
            model_version=model.version,
            feature_versions=[feature_version],
            dataset_version=model.dataset_version,
            window_start=window_start,
            window_end=window_end,
            status=status,
            prediction_count=len(selected_predictions),
            failure_count=len(selected_failures),
            failure_types=failure_types,
            mean_latency_ms=sum(latencies) / len(latencies) if latencies else None,
            prediction_class_counts=class_counts,
            probability_mean=sum(probabilities) / len(probabilities) if probabilities else None,
            probability_min=min(probabilities) if probabilities else None,
            probability_max=max(probabilities) if probabilities else None,
            confidence_mean=sum(confidences) / len(confidences) if confidences else None,
            feature_drifts=feature_drifts,
            performance_metrics=performance_metrics,
            calibration_metrics=calibration_metrics,
            outcome_count=len(outcomes),
            signals=signals,
            alerts=alerts,
            insufficient_data_reasons=missing_reasons,
        )

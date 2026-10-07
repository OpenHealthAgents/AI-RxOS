"""
Monitoring and Drift Detection Subsystem.

Calculates Population Stability Index (PSI) and statistical distributional shifts
between baseline training distributions and real-time serving distributions.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

from .models import DriftReport, DriftStatus, FeatureDriftMetric


class DriftDetectionEngine:
    """
    Automated data and concept drift detection using Population Stability Index (PSI).
    Monitors feature stability to preempt silent model degradation.
    """

    @classmethod
    def calculate_psi(
        cls,
        baseline_values: List[float],
        current_values: List[float],
        num_bins: int = 5,
    ) -> float:
        """
        Calculates the Population Stability Index (PSI) between baseline and current distributions.
        PSI = sum((actual% - expected%) * ln(actual% / expected%))
        """
        if not baseline_values or not current_values:
            return 0.0

        min_val = min(baseline_values)
        max_val = max(baseline_values)

        if min_val == max_val:
            # Constant feature distribution
            return 0.0

        # Create uniform bin edges
        step = (max_val - min_val) / num_bins
        bin_edges = [min_val + i * step for i in range(num_bins + 1)]
        bin_edges[-1] = max_val + 1e-6  # Include upper edge

        n_base = len(baseline_values)
        n_curr = len(current_values)

        base_counts = [0] * num_bins
        curr_counts = [0] * num_bins

        for val in baseline_values:
            idx = min(int((val - min_val) / step), num_bins - 1)
            base_counts[idx] += 1

        for val in current_values:
            # Handle out-of-range current values
            clamped = min(max(val, min_val), max_val)
            idx = min(int((clamped - min_val) / step), num_bins - 1)
            curr_counts[idx] += 1

        eps = 1e-4
        psi = 0.0

        for b_count, c_count in zip(base_counts, curr_counts):
            # Fractions with epsilon smoothing
            p_base = max(b_count / n_base, eps)
            p_curr = max(c_count / n_curr, eps)

            psi += (p_curr - p_base) * math.log(p_curr / p_base)

        return round(max(0.0, psi), 4)

    @classmethod
    def evaluate_drift(
        cls,
        model_version: str,
        baseline_features: Dict[str, List[float]],
        current_features: Dict[str, List[float]],
        window_start: Optional[date] = None,
        window_end: Optional[date] = None,
    ) -> DriftReport:
        """Evaluates feature distribution drift across all features."""
        feature_drifts: Dict[str, FeatureDriftMetric] = {}
        has_severe = False
        has_moderate = False
        total_curr = 0

        for feat_name, base_vals in baseline_features.items():
            curr_vals = current_features.get(feat_name, [])
            total_curr = max(total_curr, len(curr_vals))

            base_mean = sum(base_vals) / len(base_vals) if base_vals else 0.0
            curr_mean = sum(curr_vals) / len(curr_vals) if curr_vals else 0.0

            psi = cls.calculate_psi(base_vals, curr_vals)

            if psi >= 0.25:
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

            feature_drifts[feat_name] = FeatureDriftMetric(
                feature_name=feat_name,
                baseline_mean=round(base_mean, 2),
                current_mean=round(curr_mean, 2),
                psi=psi,
                drift_status=status,
                flagged=flagged,
            )

        # Dataset-level drift determination
        if has_severe:
            overall_status = DriftStatus.SEVERE_DRIFT
            alert_triggered = True
            recommendation = "Severe distribution drift detected in key clinical features. Trigger automated retraining."
        elif has_moderate:
            overall_status = DriftStatus.MODERATE_DRIFT
            alert_triggered = False
            recommendation = "Moderate shift observed. Increase monitoring frequency on flagged features."
        else:
            overall_status = DriftStatus.NO_DRIFT
            alert_triggered = False
            recommendation = "Distributions are stable within statistical confidence limits."

        w_start = window_start or date.today()
        w_end = window_end or date.today()

        return DriftReport(
            report_id=uuid4(),
            model_version=model_version,
            evaluation_window_start=w_start,
            evaluation_window_end=w_end,
            total_inferences_evaluated=total_curr,
            overall_drift_status=overall_status,
            feature_drifts=feature_drifts,
            drift_alert_triggered=alert_triggered,
            recommended_action=recommendation,
        )

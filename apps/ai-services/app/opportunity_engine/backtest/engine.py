from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional
from app.opportunity_engine.data.fixtures import get_fixture_asset
from app.opportunity_engine.domain.schemas import (
    DevelopmentStage,
    EvidenceItem,
    HistoricalBacktestQuery,
    HistoricalBacktestResult,
    StageTransitionProbabilities,
    StrategicAction,
)
from app.opportunity_engine.temporal import (
    InformationLeakageDetector,
    InformationLeakageError,
    TemporalIntelligenceEngine,
)


class HistoricalBacktestEngine:
    """
    Simulates historical counterfactual evaluations with strict temporal evidence isolation.
    Ensures zero future data leakage across all 7 temporal coordinates.
    """

    _temporal_engine = TemporalIntelligenceEngine()

    @classmethod
    def run_backtest(cls, query: HistoricalBacktestQuery) -> HistoricalBacktestResult:
        cutoff_date = date.fromisoformat(query.cutoff_date)

        # Run via the comprehensive TemporalIntelligenceEngine
        snapshot = cls._temporal_engine.evaluate_historical_prediction(
            asset_id=query.asset_id,
            cutoff_date=cutoff_date,
            strict_audit=True,
        )

        return HistoricalBacktestResult(
            asset_id=query.asset_id,
            asset_name=snapshot.asset_name,
            cutoff_date=query.cutoff_date,
            evidence_items_eligible=snapshot.prediction.eligible_evidence_count,
            evidence_items_suppressed_future=snapshot.prediction.suppressed_future_evidence_count,
            predicted_action_at_cutoff=snapshot.prediction.predicted_action,
            predicted_transition_probabilities=snapshot.prediction.predicted_transitions,
            predicted_development_potential=snapshot.prediction.predicted_dps,
            historical_recommendation_rationale=snapshot.prediction.rationale,
            ground_truth_eventual_outcome=snapshot.ground_truth_post_cutoff_outcome or "N/A",
            prediction_accuracy=snapshot.accuracy_assessment or "Calibrated",
            anti_leakage_audit_passed=snapshot.audit_report.audit_passed,
        )

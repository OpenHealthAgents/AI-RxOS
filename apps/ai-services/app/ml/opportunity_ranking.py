"""Prompt 43 opportunity ranking contracts and safe unavailable-state handling."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import MLDataset

EpistemicClass = Literal[
    "FACT",
    "DERIVED_FEATURE",
    "ML_PREDICTION",
    "AI_INFERENCE",
    "HYPOTHESIS",
    "UNKNOWN",
]


class OpportunitySignalInput(BaseModel):
    """Typed upstream signal; unclassified source values are never ranking inputs."""

    epistemic_class: EpistemicClass = "UNKNOWN"
    available: bool = False
    value: float | None = None
    unclassified_value: float | None = None
    reason: str | None = None
    unavailable_reason: str | None = None
    feature_version: str | None = None
    observation_date: str | None = None
    prediction_cutoff: str | None = None
    evidence_references: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class OpportunityRankingResult(BaseModel):
    """A ranking result that never represents absent model evidence as a numeric score."""

    model_config = ConfigDict(from_attributes=True)

    entity_id: str
    opportunity_score: float | None = None
    rank: int | None = None
    confidence: float | None = None
    feature_contributions: list[dict[str, Any]] = Field(default_factory=list)
    model_name: str = "opportunity_ranking"
    model_version: str | None = None
    feature_version: str | None = None
    prediction_cutoff: date | None = None
    prediction_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tenant_id: str | None = None
    input_snapshot: dict[str, Any] = Field(default_factory=dict)
    upstream_signals: dict[str, dict[str, OpportunitySignalInput]] = Field(
        default_factory=dict
    )
    evidence_references: list[str] = Field(default_factory=list)
    ranking_status: Literal["unavailable_insufficient_history"] = (
        "unavailable_insufficient_history"
    )
    explanation_status: str = "unavailable_no_model_explanation"
    monitoring_status: str = "unavailable_no_model_predictions"


class OpportunityRankingEngine:
    """Produces explicit unavailable ranking records until a valid model exists."""

    def rank_dataset(self, dataset: MLDataset) -> list[OpportunityRankingResult]:
        """Return metadata-preserving unavailable outputs; never synthesize scores or ranks."""
        if dataset.metadata.get("dataset_family") != "prompt_43_opportunity_ranking":
            raise ValueError("OpportunityRankingEngine requires a Prompt 43 ranking dataset.")

        training_available = dataset.metadata.get("training_available") is True
        if training_available:
            raise ValueError(
                "Historical labels are sufficient; train and register a fitted ranking model "
                "before producing opportunity scores."
            )
        prediction_cutoff = dataset.metadata.get("prediction_cutoff")
        if isinstance(prediction_cutoff, str):
            prediction_cutoff = datetime.fromisoformat(prediction_cutoff).date()
        if prediction_cutoff is None:
            prediction_cutoff = dataset.cutoff_date

        results: list[OpportunityRankingResult] = []
        for record in dataset.train_records:
            upstream_signals = record.metadata.get("upstream_signals", {})
            evidence_references = sorted(
                {
                    reference
                    for signal_members in upstream_signals.values()
                    for signal in signal_members.values()
                    if signal.get("available") is True
                    for reference in signal.get("evidence_references", [])
                }
            )
            snapshot = {
                "dataset_id": str(dataset.dataset_id),
                "dataset_name": dataset.name,
                "dataset_version": dataset.version,
                "feature_versions": list(dataset.feature_versions),
                "label_versions": list(dataset.label_versions),
                "feature_cutoff": record.metadata.get("feature_cutoff"),
                "dataset_cutoff": record.metadata.get("dataset_cutoff"),
                "prediction_cutoff": (
                    prediction_cutoff.isoformat() if prediction_cutoff else None
                ),
                "tenant_id": record.metadata.get("tenant_id"),
                "upstream_signals": upstream_signals,
                "numeric_features": record.features,
            }
            results.append(
                OpportunityRankingResult(
                    entity_id=record.entity_id,
                    opportunity_score=None,
                    rank=None,
                    confidence=None,
                    feature_contributions=[],
                    model_version=None,
                    feature_version=(
                        dataset.feature_versions[0] if len(dataset.feature_versions) == 1 else None
                    ),
                    prediction_cutoff=prediction_cutoff,
                    tenant_id=record.metadata.get("tenant_id"),
                    input_snapshot=snapshot,
                    upstream_signals=upstream_signals,
                    evidence_references=evidence_references,
                    ranking_status="unavailable_insufficient_history",
                )
            )
        return results

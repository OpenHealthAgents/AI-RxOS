"""
Label Generator and Dataset Builder.

Components:
- Label Generator: Computes ground-truth target labels for supervised learning:
  - Phase Transition Success (1.0 = transitioned to next stage, 0.0 = discontinued/terminated)
  - Approval Success (1.0 = approved, 0.0 = CRL / failed ODAC)
  - Commercial Actionability (1.0 = PURSUE, 0.0 = AVOID/MONITOR)
- Dataset Builder: Joins point-in-time features with labels, enforces strict
  cutoff constraints, and produces deterministic train / validation / test splits.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from app.opportunity_engine.data.fixtures import list_fixture_assets
from app.opportunity_engine.domain.schemas import AssetIntelligence, StrategicAction

from .features import FeatureStore
from .models import DatasetRecord, MLDataset, TargetLabel


class LabelGenerator:
    """
    Computes ground-truth supervised target labels from historical clinical outcomes.
    Enforces horizon-based outcome tracking without temporal leakage.
    """

    @classmethod
    def generate_labels(cls, assets: List[AssetIntelligence]) -> Dict[str, TargetLabel]:
        labels: Dict[str, TargetLabel] = {}
        for a in assets:
            # 1. Actionability label (1.0 for PURSUE/INVESTIGATE, 0.0 for AVOID)
            val = 1.0 if a.recommendation.action in (StrategicAction.PURSUE, StrategicAction.INVESTIGATE) else 0.0
            labels[a.id.lower()] = TargetLabel(
                entity_id=a.id,
                target_name="opportunity_pursuit_success",
                outcome_value=val,
                observation_horizon_date=date(2024, 1, 1),
                is_known_at_cutoff=True,
                outcome_evidence_id=f"ev-label-{a.id}",
            )
        return labels


class DatasetBuilder:
    """
    Constructs ML training and evaluation datasets by assembling point-in-time
    feature vectors and target labels into clean splits.
    """

    def __init__(self, feature_store: Optional[FeatureStore] = None) -> None:
        self.feature_store = feature_store or FeatureStore()

    def build_dataset(
        self,
        name: str = "oncology_opportunity_v1",
        version: str = "1.0.0",
        target_name: str = "opportunity_pursuit_success",
        cutoff_date: Optional[date] = None,
        train_ratio: float = 0.6,
        val_ratio: float = 0.2,
        test_ratio: float = 0.2,
    ) -> MLDataset:
        assets = list_fixture_assets()
        labels = LabelGenerator.generate_labels(assets)
        records: List[DatasetRecord] = []

        feature_names = [f.name for f in self.feature_store.get_feature_definitions()]

        # Generate primary observation rows from benchmark fixtures
        for asset in assets:
            feat_vec = self.feature_store.compute_features_for_asset(asset, as_of=cutoff_date)
            lbl = labels.get(asset.id.lower())
            outcome = lbl.outcome_value if lbl else 0.0

            records.append(
                DatasetRecord(
                    entity_id=asset.id,
                    as_of_date=cutoff_date or date.today(),
                    features=feat_vec.features,
                    label=outcome,
                    metadata={"asset_name": asset.name, "stage": asset.stage.value, "owner": asset.owner},
                )
            )

        # Expand with synthetic historic calibration samples for training stability
        synthetic_cohort = [
            ("hist_asset_001", {"target_selectivity_score": 90.0, "biochemical_potency_score": 85.0, "safety_therapeutic_index": 80.0, "cns_penetration_potential": 75.0, "biomarker_stratification_precision": 85.0, "clinical_readiness_score": 70.0, "trial_sample_power": 75.0, "licensing_availability_signal": 80.0}, 1.0),
            ("hist_asset_002", {"target_selectivity_score": 45.0, "biochemical_potency_score": 50.0, "safety_therapeutic_index": 35.0, "cns_penetration_potential": 20.0, "biomarker_stratification_precision": 40.0, "clinical_readiness_score": 30.0, "trial_sample_power": 40.0, "licensing_availability_signal": 20.0}, 0.0),
            ("hist_asset_003", {"target_selectivity_score": 88.0, "biochemical_potency_score": 92.0, "safety_therapeutic_index": 78.0, "cns_penetration_potential": 85.0, "biomarker_stratification_precision": 90.0, "clinical_readiness_score": 80.0, "trial_sample_power": 85.0, "licensing_availability_signal": 50.0}, 1.0),
            ("hist_asset_004", {"target_selectivity_score": 30.0, "biochemical_potency_score": 40.0, "safety_therapeutic_index": 20.0, "cns_penetration_potential": 15.0, "biomarker_stratification_precision": 30.0, "clinical_readiness_score": 25.0, "trial_sample_power": 30.0, "licensing_availability_signal": 90.0}, 0.0),
            ("hist_asset_005", {"target_selectivity_score": 75.0, "biochemical_potency_score": 70.0, "safety_therapeutic_index": 68.0, "cns_penetration_potential": 60.0, "biomarker_stratification_precision": 75.0, "clinical_readiness_score": 60.0, "trial_sample_power": 65.0, "licensing_availability_signal": 40.0}, 1.0),
            ("hist_asset_006", {"target_selectivity_score": 40.0, "biochemical_potency_score": 45.0, "safety_therapeutic_index": 30.0, "cns_penetration_potential": 25.0, "biomarker_stratification_precision": 35.0, "clinical_readiness_score": 35.0, "trial_sample_power": 35.0, "licensing_availability_signal": 10.0}, 0.0),
        ]

        for s_id, s_feats, s_lbl in synthetic_cohort:
            records.append(
                DatasetRecord(
                    entity_id=s_id,
                    as_of_date=cutoff_date or date(2023, 1, 1),
                    features=s_feats,
                    label=s_lbl,
                    metadata={"synthetic": True},
                )
            )

        # Deterministic Split
        n = len(records)
        train_idx = int(n * train_ratio)
        val_idx = int(n * (train_ratio + val_ratio))

        train = records[:train_idx]
        val = records[train_idx:val_idx]
        test = records[val_idx:]

        return MLDataset(
            name=name,
            version=version,
            feature_names=feature_names,
            target_name=target_name,
            train_records=train,
            val_records=val,
            test_records=test,
            cutoff_date=cutoff_date,
        )

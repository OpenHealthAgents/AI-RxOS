"""
Feature Engineering and Feature Store.

Manages:
- Canonical feature definitions across 4 feature groups:
  1. Biology & Target Selectivity
  2. Clinical Pharmacology & CNS Activity
  3. Trial Development & Sample Scale
  4. Commercial & Licensing Rigor
- Point-in-time feature extraction for drug assets
- Feature store registration, retrieval, and point-in-time consistency
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.opportunity_engine.data.fixtures import list_fixture_assets
from app.opportunity_engine.domain.schemas import AssetIntelligence

from .models import FeatureDataType, FeatureDefinition, FeatureVector


class FeatureStore:
    """
    Centralized, point-in-time Feature Store for oncology opportunity modeling.
    Extracts features deterministically from structured asset intelligence.
    """

    CANONICAL_FEATURES: List[FeatureDefinition] = [
        # Group 1: Biology & Selectivity
        FeatureDefinition(
            name="target_selectivity_score",
            feature_group="biology",
            data_type=FeatureDataType.FLOAT,
            description="Normalized fold selectivity for oncogenic mutant over wild-type (0-100)",
            min_value=0.0,
            max_value=100.0,
        ),
        FeatureDefinition(
            name="biochemical_potency_score",
            feature_group="biology",
            data_type=FeatureDataType.FLOAT,
            description="Biochemical potency metric (IC50 inverse scale, 0-100)",
            min_value=0.0,
            max_value=100.0,
        ),
        FeatureDefinition(
            name="safety_therapeutic_index",
            feature_group="biology",
            data_type=FeatureDataType.FLOAT,
            description="Calculated therapeutic window sparing wild-type tissues (0-100)",
            min_value=0.0,
            max_value=100.0,
        ),
        # Group 2: Pharmacology & CNS
        FeatureDefinition(
            name="cns_penetration_potential",
            feature_group="pharmacology",
            data_type=FeatureDataType.FLOAT,
            description="Blood-brain barrier partition and intracranial efficacy score (0-100)",
            min_value=0.0,
            max_value=100.0,
        ),
        FeatureDefinition(
            name="biomarker_stratification_precision",
            feature_group="pharmacology",
            data_type=FeatureDataType.FLOAT,
            description="Degree to which indication relies on genomic biomarker stratification (0-100)",
            min_value=0.0,
            max_value=100.0,
        ),
        # Group 3: Clinical Development Scale
        FeatureDefinition(
            name="clinical_readiness_score",
            feature_group="clinical",
            data_type=FeatureDataType.FLOAT,
            description="Development stage maturity and trial execution score (0-100)",
            min_value=0.0,
            max_value=100.0,
        ),
        FeatureDefinition(
            name="trial_sample_power",
            feature_group="clinical",
            data_type=FeatureDataType.FLOAT,
            description="Statistical cohort power based on total human enrollment (log10 scaled)",
            min_value=0.0,
            max_value=100.0,
        ),
        # Group 4: Commercial & IP
        FeatureDefinition(
            name="licensing_availability_signal",
            feature_group="commercial",
            data_type=FeatureDataType.FLOAT,
            description="Signal indicator: 100 for available, 50 for partnered, 0 for internal",
            min_value=0.0,
            max_value=100.0,
        ),
    ]

    def __init__(self) -> None:
        self._definitions: Dict[str, FeatureDefinition] = {
            f.name: f for f in self.CANONICAL_FEATURES
        }
        self._store: Dict[str, FeatureVector] = {}
        self._bootstrap_features()

    def get_feature_definitions(self) -> List[FeatureDefinition]:
        return list(self._definitions.values())

    def compute_features_for_asset(
        self,
        asset: AssetIntelligence,
        as_of: Optional[date] = None,
    ) -> FeatureVector:
        """Engineers the canonical feature vector for an asset."""
        ref_date = as_of or date.today()

        # Group 1: Biology
        bio = asset.biology_profile
        sel = float(bio.target_selectivity)
        pot = float(bio.potency)
        ti = float(bio.safety_ti)

        # Group 2: Pharmacology & CNS
        cns = float(bio.cns_potential)
        bio_strat = float(bio.biomarker_strategy)

        # Group 3: Clinical readiness & Sample size
        readiness = float(bio.clinical_readiness)
        sample_power = 65.0  # Default moderate cohort power
        if "Phase III" in asset.stage.value or "Approved" in asset.stage.value:
            sample_power = 95.0
        elif "Phase II" in asset.stage.value:
            sample_power = 75.0
        elif "Phase I" in asset.stage.value:
            sample_power = 50.0

        # Group 4: Commercial
        lic_val = 25.0
        if " Hanmi" in asset.owner or "Spectrum" in asset.owner:
            lic_val = 90.0  # Available licensing signal
        elif "Pfizer" in asset.owner or "Puma" in asset.owner:
            lic_val = 50.0  # Partnered

        features: Dict[str, float] = {
            "target_selectivity_score": round(sel, 2),
            "biochemical_potency_score": round(pot, 2),
            "safety_therapeutic_index": round(ti, 2),
            "cns_penetration_potential": round(cns, 2),
            "biomarker_stratification_precision": round(bio_strat, 2),
            "clinical_readiness_score": round(readiness, 2),
            "trial_sample_power": round(sample_power, 2),
            "licensing_availability_signal": round(lic_val, 2),
        }

        return FeatureVector(
            entity_id=asset.id,
            as_of_date=ref_date,
            features=features,
        )

    def get_features(
        self,
        entity_id: str,
        as_of: Optional[date] = None,
        as_of_date: Optional[date] = None,
    ) -> FeatureVector:
        ref_date = as_of_date or as_of or date.today()
        key = entity_id.lower()
        if as_of is None and as_of_date is None and key in self._store:
            return self._store[key]

        # Check if it corresponds to an asset in fixtures
        for asset in list_fixture_assets():
            if asset.id.lower() == key:
                vec = self.compute_features_for_asset(asset, as_of=ref_date)
                self.save_features(vec)
                return vec

        # Fallback default feature vector
        default_feats = {f.name: f.default_value for f in self.CANONICAL_FEATURES}
        vec = FeatureVector(entity_id=entity_id, as_of_date=ref_date, features=default_feats)
        self.save_features(vec)
        return vec

    def extract_batch(self, as_of: Optional[date] = None) -> List[FeatureVector]:
        """Returns feature vectors for all known benchmark oncology assets."""
        vectors: List[FeatureVector] = []
        for asset in list_fixture_assets():
            vectors.append(self.compute_features_for_asset(asset, as_of=as_of))
        return vectors

    def save_features(self, vector: FeatureVector) -> None:
        self._store[vector.entity_id.lower()] = vector

    def _bootstrap_features(self) -> None:
        for asset in list_fixture_assets():
            vec = self.compute_features_for_asset(asset)
            self.save_features(vec)

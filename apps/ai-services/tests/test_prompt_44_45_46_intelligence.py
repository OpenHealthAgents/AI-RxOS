from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.ml.features import FeatureStore
from app.ml.models import FeatureRecord
from app.ml.registry import ModelRegistry
from app.opportunity_engine.biology.engine import BiologyIntelligenceEngine
from app.opportunity_engine.biology.models import (
    BiologyObservationType,
    RawBiologicalObservation,
)
from app.opportunity_engine.biology.router import get_asset_biology_intelligence
from app.opportunity_engine.clinical.engine import ClinicalDevelopmentIntelligenceEngine
from app.opportunity_engine.clinical.models import (
    ClinicalStage,
    EndpointReviewType,
    ObservedClinicalOutcome,
)
from app.opportunity_engine.clinical.router import get_asset_clinical_intelligence
from app.opportunity_engine.cns.engine import CNSIntelligenceEngine
from app.opportunity_engine.cns.models import (
    CNSEvidenceLevel,
    CNSParameterType,
    CNSSpecies,
    RawCNSObservation,
)
from app.opportunity_engine.cns.router import get_asset_cns_intelligence
from app.opportunity_engine.data.fixtures import list_fixture_assets
from app.opportunity_engine.intelligence import (
    EpistemicClass,
    IntelligenceValueStatus,
)
from app.opportunity_engine.kg.engine import OncologyKnowledgeGraphEngine

CUTOFF = date(2025, 1, 1)


def _biology_observation(
    asset_id: str,
    observation_type: BiologyObservationType,
    parameter_name: str,
    value: float,
    *,
    observed: date | None = CUTOFF,
    tenant_id: str | None = None,
    confidence: float = 0.8,
) -> RawBiologicalObservation:
    return RawBiologicalObservation(
        asset_id=asset_id,
        tenant_id=tenant_id,
        parameter_name=parameter_name,
        observation_type=observation_type,
        raw_text_value=f"Observed {parameter_name}: {value}",
        normalized_value=value,
        unit="nM" if "IC50" in observation_type.value else "ratio",
        source_citation=f"source:{parameter_name}",
        pmid=f"PMID-{parameter_name}",
        confidence=confidence,
        observation_date=observed,
    )


def _clinical_outcome(
    asset_id: str,
    *,
    reported: date | None = CUTOFF,
    tenant_id: str | None = None,
) -> ObservedClinicalOutcome:
    return ObservedClinicalOutcome(
        trial_id=f"NCT-{asset_id}",
        tenant_id=tenant_id,
        trial_title="Dated clinical report",
        phase=ClinicalStage.PHASE_II,
        sample_size=120,
        population="Documented study population",
        biomarker_status="Documented biomarker",
        orr_pct=42.0,
        source_citation="Dated clinical report, source reference",
        pmid="12345678",
        reported_date=reported,
        endpoint_review=EndpointReviewType.BLINDED_INDEPENDENT_CENTRAL_REVIEW,
    )


def _cns_observation(
    asset_id: str,
    parameter: CNSParameterType,
    value: float,
    *,
    observed: date | None = CUTOFF,
    tenant_id: str | None = None,
    confidence: float = 0.75,
    level: CNSEvidenceLevel = CNSEvidenceLevel.DIRECT_MEASUREMENT,
) -> RawCNSObservation:
    return RawCNSObservation(
        asset_id=asset_id,
        tenant_id=tenant_id,
        parameter_type=parameter,
        evidence_level=level,
        species=CNSSpecies.HUMAN,
        experimental_condition="prospective_dated_measurement",
        raw_text_value=f"Measured {parameter.value}: {value}",
        normalized_value=value,
        normalized_unit="ratio",
        source_citation=f"source:{parameter.value}",
        pmid=f"PMID-{parameter.value}",
        confidence=confidence,
        observation_date=observed,
    )


def test_biology_intelligence_integrates_dated_evidence_rules_and_kg():
    asset_id = "tucatinib"
    observations = [
        _biology_observation(asset_id, BiologyObservationType.IC50_BIOCHEMICAL, "ic50_bio", 5.0),
        _biology_observation(asset_id, BiologyObservationType.SELECTIVITY_RATIO, "selectivity", 18.0),
        _biology_observation(asset_id, BiologyObservationType.ON_TARGET_ENGAGEMENT, "target_engagement", 2.4),
        _biology_observation(asset_id, BiologyObservationType.MECHANISTIC_RATIONALE, "mechanism", 1.0),
        _biology_observation(asset_id, BiologyObservationType.BIOMARKER_STRATEGY, "biomarker", 1.0),
        _biology_observation(asset_id, BiologyObservationType.ANIMAL_EFFICACY, "animal_efficacy", 55.0),
        _biology_observation(asset_id, BiologyObservationType.TARGET_VALIDITY, "target_validity", 1.0),
        _biology_observation(asset_id, BiologyObservationType.FUNCTIONAL_EVIDENCE, "functional", 4.0),
    ]
    graph = OncologyKnowledgeGraphEngine()
    result = BiologyIntelligenceEngine().evaluate_intelligence(
        asset_id,
        datetime.now(timezone.utc).date(),
        custom_observations=observations,
        knowledge_graph=graph,
    )

    assert result.biology_validation.status == IntelligenceValueStatus.AVAILABLE
    assert result.potency.status == IntelligenceValueStatus.AVAILABLE
    assert result.selectivity.status == IntelligenceValueStatus.AVAILABLE
    assert result.mechanistic_confidence.status == IntelligenceValueStatus.AVAILABLE
    assert result.biomarker_strength.status == IntelligenceValueStatus.AVAILABLE
    assert result.translational_readiness.status == IntelligenceValueStatus.AVAILABLE
    assert all(
        metric.epistemic_class == EpistemicClass.DERIVED_FEATURE
        for metric in (
            result.potency,
            result.selectivity,
            result.mechanistic_confidence,
            result.biomarker_strength,
            result.translational_readiness,
        )
    )
    assert all(metric.confidence == pytest.approx(0.8) for metric in (
        result.potency,
        result.selectivity,
        result.mechanistic_confidence,
        result.biomarker_strength,
        result.translational_readiness,
    ))
    assert result.evidence
    assert result.knowledge_graph_evidence
    assert result.rule_findings
    assert result.ml_component.available is False
    assert result.ml_component.reason
    assert all(metric.supporting_evidence for metric in (
        result.biology_validation,
        result.potency,
        result.selectivity,
        result.mechanistic_confidence,
        result.biomarker_strength,
        result.translational_readiness,
    ))


def test_biology_unknowns_do_not_turn_into_zero_and_future_evidence_is_excluded():
    asset_id = "tucatinib"
    inputs = [
        _biology_observation(
            asset_id,
            BiologyObservationType.IC50_BIOCHEMICAL,
            "future_potency",
            0.1,
            observed=CUTOFF + timedelta(days=1),
        ),
        _biology_observation(
            asset_id,
            BiologyObservationType.SELECTIVITY_RATIO,
            "undated_selectivity",
            30.0,
            observed=None,
        ),
    ]
    result = BiologyIntelligenceEngine().evaluate_intelligence(
        asset_id,
        CUTOFF,
        custom_observations=inputs,
    )

    assert result.potency.value is None
    assert result.potency.status == IntelligenceValueStatus.UNKNOWN
    assert result.selectivity.value is None
    assert result.selectivity.status == IntelligenceValueStatus.UNKNOWN
    assert result.evidence == []
    excluded_ids = {item.evidence_id for item in result.excluded_undated_evidence}
    assert {str(item.id) for item in inputs}.issubset(excluded_ids)


def test_biology_tenant_mismatch_is_rejected_and_output_is_reproducible():
    engine = BiologyIntelligenceEngine()
    obs = _biology_observation(
        "tucatinib",
        BiologyObservationType.IC50_CELLULAR,
        "ic50_cell",
        12.0,
        tenant_id="tenant-a",
    )
    with pytest.raises(ValueError, match="asset and tenant"):
        engine.evaluate_intelligence(
            "tucatinib",
            CUTOFF,
            tenant_id="tenant-b",
            custom_observations=[obs],
        )

    first = engine.evaluate_intelligence(
        "tucatinib", CUTOFF, tenant_id="tenant-a", custom_observations=[obs]
    )
    second = engine.evaluate_intelligence(
        "tucatinib", CUTOFF, tenant_id="tenant-a", custom_observations=[obs]
    )
    assert first.potency.model_dump() == second.potency.model_dump()
    assert first.rule_findings == second.rule_findings


def test_clinical_intelligence_uses_dated_trial_facts_but_not_fabricated_probability():
    outcome = _clinical_outcome("custom")
    result = ClinicalDevelopmentIntelligenceEngine().evaluate_intelligence(
        "custom",
        CUTOFF,
        tenant_id="tenant-clinical",
        custom_outcomes=[outcome],
    )

    assert result.evidence
    assert result.evidence[0].epistemic_class == EpistemicClass.FACT
    assert result.evidence[0].source_reference == outcome.trial_id
    assert result.clinical_readiness.status == IntelligenceValueStatus.AVAILABLE
    assert result.clinical_readiness.value["dated_outcome_count"] == 1
    assert result.evidence_maturity.status == IntelligenceValueStatus.AVAILABLE
    assert result.evidence_maturity.confidence is None
    assert result.clinical_success_probability.value is None
    assert result.clinical_success_probability.status == IntelligenceValueStatus.UNAVAILABLE
    assert result.development_risk.value is None
    assert result.ml_component.available is False


def test_clinical_temporal_cutoff_excludes_future_and_undated_outcomes():
    engine = ClinicalDevelopmentIntelligenceEngine()
    future = _clinical_outcome("custom", reported=CUTOFF + timedelta(days=1))
    undated = _clinical_outcome("custom-undated", reported=None)
    result = engine.evaluate_intelligence(
        "custom",
        CUTOFF,
        custom_outcomes=[future, undated],
    )

    assert result.evidence == []
    assert len(result.excluded_undated_evidence) == 2
    assert result.evidence_maturity.value is None
    assert result.evidence_maturity.status == IntelligenceValueStatus.INSUFFICIENT_EVIDENCE
    assert result.clinical_success_probability.value is None


def test_clinical_tenant_isolation_and_canonical_outcome_cutoff():
    engine = ClinicalDevelopmentIntelligenceEngine()
    with pytest.raises(ValueError, match="requested tenant"):
        engine.evaluate_intelligence(
            "tucatinib",
            datetime.now(timezone.utc).date(),
            tenant_id="tenant-b",
            custom_outcomes=[_clinical_outcome("tucatinib", tenant_id="tenant-a")],
        )

    snapshot = engine.evaluate_intelligence(
        "tucatinib", datetime.now(timezone.utc).date(), tenant_id="tenant-b"
    )
    assert snapshot.evidence == []
    assert snapshot.excluded_undated_evidence
    assert snapshot.ml_component.available is False


def test_cns_intelligence_separates_measured_exposure_activity_and_brain_mets():
    asset_id = "custom-cns"
    observations = [
        _cns_observation(asset_id, CNSParameterType.KP_UU, 0.42),
        _cns_observation(
            asset_id,
            CNSParameterType.INTRACRANIAL_RESPONSE,
            45.0,
            level=CNSEvidenceLevel.CLINICAL_CNS_EVIDENCE,
        ),
        _cns_observation(
            asset_id,
            CNSParameterType.BRAIN_METASTASIS_RESPONSE,
            36.0,
            level=CNSEvidenceLevel.CLINICAL_CNS_EVIDENCE,
        ),
    ]
    result = CNSIntelligenceEngine().evaluate_intelligence(
        asset_id,
        CUTOFF,
        custom_observations=observations,
    )

    assert result.cns_exposure.value[0]["value"] == 0.42
    assert result.cns_exposure.epistemic_class == EpistemicClass.FACT
    assert result.cns_activity.value[0]["value"] == 45.0
    assert result.brain_metastasis_relevance.value[0]["value"] == 36.0
    assert result.confidence.value == pytest.approx(0.75)
    assert result.predicted_cns_activity.value is None
    assert result.predicted_cns_activity.status == IntelligenceValueStatus.UNAVAILABLE
    assert result.ml_component.available is False
    assert result.evidence


def test_cns_predicted_potential_never_becomes_measured_activity():
    store = FeatureStore()
    asset_id = list_fixture_assets()[0].id
    store.record_feature(
        FeatureRecord(
            feature_name="cns_penetration_potential",
            value=72.0,
            unit="score",
            asset=asset_id,
            tenant_id="tenant-cns",
            evidence_references=["model-feature-reference"],
            observation_date=CUTOFF,
            prediction_cutoff=CUTOFF,
            feature_version="v1",
            extraction_method="test_injected_prediction",
            confidence=0.65,
            provenance={"epistemic_class": "AI_INFERENCE", "model_version": "potential-v1"},
        )
    )
    result = CNSIntelligenceEngine().evaluate_intelligence(
        asset_id,
        CUTOFF,
        tenant_id="tenant-cns",
        feature_store=store,
    )

    assert result.predicted_cns_potential.value == 72.0
    assert result.predicted_cns_potential.epistemic_class == EpistemicClass.AI_INFERENCE
    assert result.cns_activity.value is None
    assert result.cns_activity.status == IntelligenceValueStatus.UNKNOWN
    assert result.predicted_cns_activity.value is None


def test_cns_undated_and_future_observations_stay_unknown_and_tenant_scoped():
    asset_id = "custom-cns"
    observations = [
        _cns_observation(
            asset_id,
            CNSParameterType.KP_UU,
            0.5,
            observed=CUTOFF + timedelta(days=2),
            tenant_id="tenant-cns",
        ),
        _cns_observation(
            asset_id,
            CNSParameterType.INTRACRANIAL_RESPONSE,
            50.0,
            observed=None,
            tenant_id="tenant-cns",
        ),
    ]
    engine = CNSIntelligenceEngine()
    result = engine.evaluate_intelligence(
        asset_id,
        CUTOFF,
        tenant_id="tenant-cns",
        custom_observations=observations,
    )
    assert result.cns_exposure.value is None
    assert result.cns_activity.value is None
    assert result.brain_metastasis_relevance.value is None
    assert len(result.excluded_undated_evidence) == 2

    with pytest.raises(ValueError, match="asset and tenant"):
        engine.evaluate_intelligence(
            asset_id,
            CUTOFF,
            tenant_id="other-tenant",
            custom_observations=observations,
        )


def test_default_benchmark_observations_remain_excluded_when_undated():
    asset_id = "tucatinib"
    cutoff = datetime.now(timezone.utc).date()
    biology = BiologyIntelligenceEngine().evaluate_intelligence(asset_id, cutoff)
    clinical = ClinicalDevelopmentIntelligenceEngine().evaluate_intelligence(asset_id, cutoff)
    cns = CNSIntelligenceEngine().evaluate_intelligence(asset_id, cutoff)

    assert biology.potency.value is None
    assert biology.excluded_undated_evidence
    assert clinical.clinical_success_probability.value is None
    assert clinical.clinical_readiness.status == IntelligenceValueStatus.INSUFFICIENT_EVIDENCE
    assert clinical.evidence_maturity.status == IntelligenceValueStatus.INSUFFICIENT_EVIDENCE
    assert clinical.excluded_undated_evidence
    assert cns.cns_exposure.value is None
    assert cns.cns_activity.value is None
    assert cns.excluded_undated_evidence


def test_ml_models_are_explicitly_unavailable_without_registered_artifacts():
    registry = ModelRegistry()
    store = FeatureStore()
    assert BiologyIntelligenceEngine().evaluate_intelligence(
        "tucatinib", CUTOFF, feature_store=store, model_registry=registry
    ).ml_component.available is False
    assert ClinicalDevelopmentIntelligenceEngine().evaluate_intelligence(
        "tucatinib", CUTOFF, feature_store=store, model_registry=registry
    ).ml_component.available is False
    assert CNSIntelligenceEngine().evaluate_intelligence(
        "tucatinib", CUTOFF, feature_store=store, model_registry=registry
    ).ml_component.available is False


def test_intelligence_routes_use_shared_ml_services(monkeypatch):
    registry = ModelRegistry()
    store = FeatureStore()
    monkeypatch.setattr(
        "app.ml.router.get_shared_ml_services",
        lambda: (store, registry),
    )

    biology = get_asset_biology_intelligence("tucatinib", CUTOFF, "tenant-a")
    clinical = get_asset_clinical_intelligence("tucatinib", CUTOFF, "tenant-a")
    cns = get_asset_cns_intelligence("tucatinib", CUTOFF, "tenant-a")

    assert biology.ml_component.reason == (
        "No tenant-visible registered 'biology_translational' model is available."
    )
    assert clinical.ml_component.reason == (
        "No tenant-visible registered 'clinical_success' model is available."
    )
    assert cns.ml_component.reason == "No tenant-visible registered 'cns' model is available."

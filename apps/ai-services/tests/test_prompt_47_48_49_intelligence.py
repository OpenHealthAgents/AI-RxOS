from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.ml.features import FeatureStore
from app.ml.models import (
    FeatureRecord,
    ModelArchitecture,
    ModelArtifact,
    ModelEvaluationMetrics,
)
from app.ml.registry import ModelRegistry
from app.opportunity_engine.biology.engine import BiologyIntelligenceEngine
from app.opportunity_engine.biology.models import (
    BiologyObservationType,
    RawBiologicalObservation,
)
from app.opportunity_engine.clinical.engine import ClinicalDevelopmentIntelligenceEngine
from app.opportunity_engine.clinical.models import (
    ClinicalStage,
    ObservedClinicalOutcome,
)
from app.opportunity_engine.combination.engine import CombinationIntelligenceEngine
from app.opportunity_engine.intelligence import (
    EpistemicClass,
    IntelligenceEvidence,
    IntelligenceValueStatus,
)
from app.opportunity_engine.intelligence_47_49 import (
    CombinationValidationClass,
    DatedResistanceObservation,
    ResistanceEvidenceClass,
)
from app.opportunity_engine.kg.engine import OncologyKnowledgeGraphEngine
from app.opportunity_engine.kg.models import (
    EdgeEvidenceProvenance,
    KGNodeType,
    KGRelationshipType,
)
from app.opportunity_engine.patient_match.engine import PatientMatchEngine
from app.opportunity_engine.resistance.engine import ResistanceIntelligenceEngine

CUTOFF = date(2025, 1, 1)


def _biology_observation(
    *,
    observation_type: BiologyObservationType,
    parameter_name: str,
    observation_date: date | None = CUTOFF,
    tenant_id: str | None = None,
) -> RawBiologicalObservation:
    return RawBiologicalObservation(
        asset_id="tucatinib",
        tenant_id=tenant_id,
        parameter_name=parameter_name,
        observation_type=observation_type,
        raw_text_value=f"Observed {parameter_name}",
        normalized_value=4.0,
        unit="score",
        source_citation=f"citation:{parameter_name}",
        pmid=f"PMID:{parameter_name}",
        confidence=0.8,
        observation_date=observation_date,
    )


def _resistance_observation(
    *,
    evidence_id: str = "resistance-1",
    date_observed: date | None = CUTOFF,
    tenant_id: str | None = "tenant-a",
    evidence_class: ResistanceEvidenceClass = ResistanceEvidenceClass.CLINICAL_RESISTANCE,
) -> DatedResistanceObservation:
    return DatedResistanceObservation(
        evidence_id=evidence_id,
        asset_id="tucatinib",
        mechanism_name="HER2 kinase-domain mutation",
        category="target mutation",
        evidence_class=evidence_class,
        observation_date=date_observed,
        tenant_id=tenant_id,
        source_type="clinical_post_progression_observation",
        source_reference="NCT-123",
        citation="Dated clinical resistance observation",
        confidence=0.75,
        provenance={"observation_id": evidence_id},
    )


def _graph_with_resistance_and_combination(
    *,
    evidence_date: date = date(2024, 6, 1),
    combination_properties: dict | None = None,
) -> OncologyKnowledgeGraphEngine:
    graph = OncologyKnowledgeGraphEngine()
    asset = graph.get_node_by_external_id("ASSET:TUCATINIB")
    assert asset is not None
    mechanism = graph.add_node(
        KGNodeType.RESISTANCE_MECHANISM,
        "TEST:RESISTANCE:TUCATINIB",
        "HER2 kinase-domain mutation",
        "HER2 kinase-domain mutation",
    )
    partner = graph.add_node(
        KGNodeType.COMBINATION,
        "TEST:COMBINATION:TUCATINIB",
        "Tucatinib + Partner-X",
        "Tucatinib + Partner-X",
    )
    source = EdgeEvidenceProvenance(
        evidence_type="PRECLINICAL",
        source_citation="Dated preclinical source",
        source_document_id="PMID:KG-1",
        confidence=0.7,
        created_at=datetime(
            evidence_date.year,
            evidence_date.month,
            evidence_date.day,
            tzinfo=timezone.utc,
        ),
    )
    graph.add_edge(
        asset.id,
        KGRelationshipType.ACQUIRES_RESISTANCE,
        mechanism.id,
        evidence=[source],
    )
    graph.add_edge(
        asset.id,
        KGRelationshipType.OVERCOMES_RESISTANCE_VIA,
        partner.id,
        properties={
            "resistance_mechanism": "HER2 kinase-domain mutation",
            "validation_status": "preclinical",
            **(combination_properties or {}),
        },
        evidence=[source.model_copy(deep=True)],
    )
    return graph


def _empty_upstream_profile(*, evidence: list[IntelligenceEvidence]):
    return SimpleNamespace(
        evidence=evidence,
        knowledge_graph_evidence=[],
        excluded_undated_evidence=[],
    )


def test_patient_match_combines_biology_and_clinical_evidence_but_does_not_rank_without_ml():
    biology = BiologyIntelligenceEngine().evaluate_intelligence(
        "tucatinib",
        CUTOFF,
        tenant_id="tenant-a",
        custom_observations=[
            _biology_observation(
                observation_type=BiologyObservationType.BIOMARKER_STRATEGY,
                parameter_name="HER2 amplification",
            )
        ],
    )
    clinical = ClinicalDevelopmentIntelligenceEngine().evaluate_intelligence(
        "tucatinib",
        CUTOFF,
        tenant_id="tenant-a",
        custom_outcomes=[
            ObservedClinicalOutcome(
                trial_id="NCT-TEST",
                tenant_id="tenant-a",
                trial_title="Dated test cohort record",
                phase=ClinicalStage.PHASE_II,
                sample_size=20,
                population="Documented test population",
                biomarker_status="HER2 positive",
                source_citation="Dated test source",
                reported_date=CUTOFF,
            )
        ],
    )
    result = PatientMatchEngine().evaluate_intelligence(
        "tucatinib",
        CUTOFF,
        tenant_id="tenant-a",
        feature_store=FeatureStore(),
        model_registry=ModelRegistry(),
        biology_intelligence=biology,
        clinical_intelligence=clinical,
    )

    assert result.evidence
    assert result.evidence[0].epistemic_class in EpistemicClass
    assert result.primary_population.status == IntelligenceValueStatus.INSUFFICIENT_EVIDENCE
    assert result.secondary_population.status == IntelligenceValueStatus.INSUFFICIENT_EVIDENCE
    assert result.low_likelihood_population.status == IntelligenceValueStatus.INSUFFICIENT_EVIDENCE
    assert result.patient_match_score.status == IntelligenceValueStatus.UNAVAILABLE
    assert result.confidence.value is None
    assert result.biomarker_strategy.epistemic_class == EpistemicClass.HYPOTHESIS
    assert (
        result.biomarker_strategy.value["patient_response"] == "UNKNOWN"
    )
    assert any(item.source_type == "clinical_trial_outcome" for item in result.evidence)
    assert result.ml_component.model_name == "patient_response"


def test_patient_match_does_not_use_future_biology_features_or_undated_clinical_outcomes():
    biology = BiologyIntelligenceEngine().evaluate_intelligence(
        "tucatinib",
        CUTOFF,
        custom_observations=[
            _biology_observation(
                observation_type=BiologyObservationType.BIOMARKER_STRATEGY,
                parameter_name="future biomarker",
                observation_date=date(2025, 1, 2),
            ),
            _biology_observation(
                observation_type=BiologyObservationType.BIOMARKER_STRATEGY,
                parameter_name="undated biomarker",
                observation_date=None,
            ),
        ],
    )
    result = PatientMatchEngine().evaluate_intelligence(
        "tucatinib",
        CUTOFF,
        biology_intelligence=biology,
        feature_store=FeatureStore(),
        model_registry=ModelRegistry(),
    )

    assert result.evidence == []
    assert len(result.excluded_undated_evidence) >= 2
    assert result.biomarker_strategy.status == IntelligenceValueStatus.INSUFFICIENT_EVIDENCE


def test_patient_match_rejects_cross_tenant_upstream_data():
    evidence = IntelligenceEvidence(
        evidence_id="tenant-evidence",
        source_type="biology",
        source_reference="PMID:1",
        observed_at=CUTOFF,
        confidence=0.8,
        provenance={"tenant_id": "tenant-a"},
    )
    result = PatientMatchEngine().evaluate_intelligence(
        "tucatinib",
        CUTOFF,
        tenant_id="tenant-b",
        feature_store=FeatureStore(),
        model_registry=ModelRegistry(),
        biology_intelligence=_empty_upstream_profile(evidence=[evidence]),
    )
    assert result.evidence == []


def test_patient_match_refuses_test_only_prompt_39_model_artifact():
    store = FeatureStore()
    registry = ModelRegistry()
    feature_names = [item.name for item in FeatureStore.PATIENT_RESPONSE_FEATURES]
    artifact = ModelArtifact(
        name="patient_response",
        version="test-only",
        architecture=ModelArchitecture.LOGISTIC_REGRESSION,
        feature_names=feature_names,
        metrics=ModelEvaluationMetrics(),
        dataset_version="test-only",
        feature_versions=["v1"],
        training_cutoff=CUTOFF,
        tenant_id="tenant-a",
        lineage={
            "dataset_metadata": {
                "test_only": True,
                "test_fixture_scientific_evidence": False,
            }
        },
    )
    registry.register(artifact)
    for feature_name in feature_names:
        store.record_feature(
            FeatureRecord(
                feature_name=feature_name,
                value=1.0,
                asset="tucatinib",
                tenant_id="tenant-a",
                evidence_references=[f"test-only:tucatinib:{feature_name}"],
                observation_date=CUTOFF,
                prediction_cutoff=CUTOFF,
                feature_version="v1",
                provenance={"test_only": True, "scientific_evidence": False},
            )
        )

    result = PatientMatchEngine().evaluate_intelligence(
        "tucatinib",
        CUTOFF,
        tenant_id="tenant-a",
        feature_store=store,
        model_registry=registry,
    )
    assert result.patient_match_score.status == IntelligenceValueStatus.UNAVAILABLE
    assert "Test-only" in (result.ml_component.reason or "")


def test_resistance_intelligence_uses_dated_evidence_and_classifies_kg_sources():
    graph = _graph_with_resistance_and_combination()
    result = ResistanceIntelligenceEngine().evaluate_intelligence(
        "tucatinib",
        CUTOFF,
        tenant_id="tenant-a",
        custom_observations=[_resistance_observation()],
        knowledge_graph=graph,
        feature_store=FeatureStore(),
        model_registry=ModelRegistry(),
    )
    classes = {item.classification for item in result.top_escape_mechanisms}
    assert ResistanceEvidenceClass.CLINICAL_RESISTANCE in classes
    assert ResistanceEvidenceClass.PRECLINICAL_RESISTANCE in classes
    assert result.predicted_resistance_risk.status == IntelligenceValueStatus.UNAVAILABLE
    assert result.top_escape_mechanisms
    assert all(item.supporting_evidence for item in result.top_escape_mechanisms)
    assert result.confidence.value == 0.7
    assert all(
        item.epistemic_class != EpistemicClass.ML_PREDICTION
        for item in result.evidence
    )


def test_resistance_intelligence_excludes_future_and_undated_records_and_keeps_unknown():
    result = ResistanceIntelligenceEngine().evaluate_intelligence(
        "tucatinib",
        CUTOFF,
        tenant_id="tenant-a",
        custom_observations=[
            _resistance_observation(evidence_id="future", date_observed=date(2025, 1, 2)),
            _resistance_observation(evidence_id="undated", date_observed=None),
        ],
        feature_store=FeatureStore(),
        model_registry=ModelRegistry(),
    )
    assert result.top_escape_mechanisms == []
    assert result.evidence == []
    assert len(result.excluded_undated_evidence) >= 2
    assert result.confidence.status == IntelligenceValueStatus.UNKNOWN
    assert result.predicted_resistance_risk.value is None


def test_resistance_intelligence_enforces_tenant_scope():
    with pytest.raises(ValueError, match="asset and tenant"):
        ResistanceIntelligenceEngine().evaluate_intelligence(
            "tucatinib",
            CUTOFF,
            tenant_id="tenant-b",
            custom_observations=[_resistance_observation(tenant_id="tenant-a")],
            feature_store=FeatureStore(),
            model_registry=ModelRegistry(),
        )


def test_resistance_intelligence_excludes_post_cutoff_kg_evidence():
    graph = _graph_with_resistance_and_combination(evidence_date=date(2025, 1, 2))
    result = ResistanceIntelligenceEngine().evaluate_intelligence(
        "tucatinib",
        CUTOFF,
        knowledge_graph=graph,
        feature_store=FeatureStore(),
        model_registry=ModelRegistry(),
    )
    assert result.top_escape_mechanisms == []
    assert len(result.excluded_undated_evidence) >= 1


def test_combination_intelligence_classifies_only_dated_mechanism_linked_candidates():
    graph = _graph_with_resistance_and_combination()
    resistance = ResistanceIntelligenceEngine().evaluate_intelligence(
        "tucatinib",
        CUTOFF,
        tenant_id="tenant-a",
        custom_observations=[_resistance_observation()],
        knowledge_graph=graph,
        feature_store=FeatureStore(),
        model_registry=ModelRegistry(),
    )
    result = CombinationIntelligenceEngine().evaluate_intelligence(
        "tucatinib",
        CUTOFF,
        tenant_id="tenant-a",
        resistance_intelligence=resistance,
        knowledge_graph=graph,
    )
    matched = next(
        item
        for item in result.mechanism_evaluations
        if item.resistance_mechanism == "HER2 kinase-domain mutation"
    )
    assert len(matched.candidates) == 1
    candidate = matched.candidates[0]
    assert candidate.classification == CombinationValidationClass.PRECLINICAL
    assert candidate.mechanistic_complementarity.value is None
    assert candidate.toxicity_overlap.status == IntelligenceValueStatus.UNKNOWN
    assert candidate.development_feasibility.status == IntelligenceValueStatus.UNKNOWN
    assert candidate.evidence_strength.value == {"cutoff_valid_source_count": 1}


def test_combination_intelligence_does_not_promote_mechanistic_rationale_to_clinical_validation():
    graph = _graph_with_resistance_and_combination(
        combination_properties={
            "validation_status": "clinically validated",
            "mechanistic_rationale": "Evidence-linked mechanism statement",
        }
    )
    resistance = ResistanceIntelligenceEngine().evaluate_intelligence(
        "tucatinib",
        CUTOFF,
        tenant_id="tenant-a",
        custom_observations=[_resistance_observation()],
        knowledge_graph=graph,
        feature_store=FeatureStore(),
        model_registry=ModelRegistry(),
    )
    result = CombinationIntelligenceEngine().evaluate_intelligence(
        "tucatinib",
        CUTOFF,
        resistance_intelligence=resistance,
        knowledge_graph=graph,
    )
    candidate = next(
        candidate
        for mechanism in result.mechanism_evaluations
        for candidate in mechanism.candidates
    )
    assert candidate.classification == CombinationValidationClass.PRECLINICAL
    assert candidate.mechanistic_complementarity.status == IntelligenceValueStatus.AVAILABLE
    assert candidate.toxicity_overlap.value is None


def test_combination_intelligence_requires_cutoff_valid_resistance_before_generation():
    resistance = ResistanceIntelligenceEngine().evaluate_intelligence(
        "tucatinib",
        CUTOFF,
        feature_store=FeatureStore(),
        model_registry=ModelRegistry(),
    )
    result = CombinationIntelligenceEngine().evaluate_intelligence(
        "tucatinib",
        CUTOFF,
        resistance_intelligence=resistance,
        knowledge_graph=_graph_with_resistance_and_combination(),
    )
    assert result.mechanism_evaluations == []
    assert result.evidence == []


def test_combination_intelligence_excludes_future_kg_support():
    graph = _graph_with_resistance_and_combination(evidence_date=date(2025, 1, 2))
    resistance = ResistanceIntelligenceEngine().evaluate_intelligence(
        "tucatinib",
        CUTOFF,
        tenant_id="tenant-a",
        custom_observations=[_resistance_observation()],
        knowledge_graph=graph,
        feature_store=FeatureStore(),
        model_registry=ModelRegistry(),
    )
    result = CombinationIntelligenceEngine().evaluate_intelligence(
        "tucatinib",
        CUTOFF,
        resistance_intelligence=resistance,
        knowledge_graph=graph,
    )
    assert all(not item.candidates for item in result.mechanism_evaluations)
    assert result.excluded_undated_evidence


@pytest.mark.parametrize(
    ("validation_status", "evidence_type", "expected"),
    [
        (
            "clinically validated",
            "CLINICAL_TRIAL",
            CombinationValidationClass.CLINICALLY_VALIDATED,
        ),
        (
            "clinical hypothesis",
            "CLINICAL_TRIAL",
            CombinationValidationClass.CLINICAL_HYPOTHESIS,
        ),
        ("preclinical", "PRECLINICAL", CombinationValidationClass.PRECLINICAL),
        ("mechanistic", "LITERATURE", CombinationValidationClass.MECHANISTIC),
        (
            "AI-generated hypothesis",
            "AI_GENERATED_HYPOTHESIS",
            CombinationValidationClass.AI_GENERATED_HYPOTHESIS,
        ),
    ],
)
def test_combination_classifications_require_explicit_provenance(
    validation_status, evidence_type, expected
):
    from app.opportunity_engine.intelligence_47_49 import _combination_classification

    relationship = SimpleNamespace(
        properties={"validation_status": validation_status, "clinical_evidence": False}
    )
    source = SimpleNamespace(evidence_type=evidence_type)
    assert _combination_classification(relationship, source) == expected


def test_existing_routes_expose_synthesis_contracts():
    from app.main import app

    paths = {route.path for route in app.routes}
    assert "/api/v1/patient-match/intelligence/{asset_id}" in paths
    assert "/api/v1/resistance/intelligence/{asset_id}" in paths
    assert "/api/v1/combination/intelligence/{asset_id}" in paths

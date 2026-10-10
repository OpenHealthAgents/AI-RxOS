from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.ml.dataset import DatasetBuilder
from app.ml.features import FeatureStore
from app.ml.models import FeatureRecord
from app.ml.opportunity_ranking import OpportunityRankingEngine
from app.ml.registry import ModelRegistry
from app.opportunity_engine.data.fixtures import list_fixture_assets

PREDICTION_CUTOFF = date(2024, 1, 1)
DATASET_CUTOFF = date(2025, 1, 1)


def _record(
    asset_id: str,
    feature_name: str,
    value: float | None,
    *,
    tenant_id: str = "tenant-43",
    observed: date = PREDICTION_CUTOFF,
    cutoff: date = PREDICTION_CUTOFF,
    epistemic_class: str | None = "FACT",
    provenance: dict | None = None,
) -> FeatureRecord:
    details = dict(provenance or {})
    if epistemic_class is not None:
        details["epistemic_class"] = epistemic_class
    return FeatureRecord(
        feature_name=feature_name,
        value=value,
        unit="source-defined",
        asset=asset_id,
        tenant_id=tenant_id,
        evidence_references=[f"evidence:{asset_id}:{feature_name}"],
        observation_date=observed,
        prediction_cutoff=cutoff,
        feature_version="v1",
        extraction_method="prompt_43_test_source",
        confidence=0.8,
        provenance=details,
    )


def _build(store: FeatureStore, tenant_id: str = "tenant-43"):
    return DatasetBuilder(store).build_opportunity_ranking_dataset(
        cutoff_date=DATASET_CUTOFF,
        prediction_cutoff=PREDICTION_CUTOFF,
        tenant_id=tenant_id,
    )


def test_opportunity_dataset_reports_insufficient_real_historical_labels():
    dataset = _build(FeatureStore())

    assert dataset.metadata["dataset_family"] == "prompt_43_opportunity_ranking"
    assert dataset.metadata["model_name"] == "opportunity_ranking"
    assert dataset.metadata["training_available"] is False
    assert dataset.metadata["model_status"] == "insufficient_historical_labels"
    assert dataset.metadata["labelled_rows"] == 0
    assert dataset.metadata["class_counts"] == {"0": 0, "1": 0}
    assert dataset.metadata["synthetic_data_used"] is False
    assert dataset.metadata["legacy_synthetic_opportunity_cohort_used"] is False
    assert dataset.label_versions == []
    assert all(record.label is None for record in dataset.train_records)


def test_opportunity_builder_ignores_legacy_synthetic_cohort_labels():
    dataset = _build(FeatureStore())

    assert {record.entity_id for record in dataset.train_records} == {
        asset.id for asset in list_fixture_assets()
    }
    assert not any(record.metadata.get("synthetic") for record in dataset.train_records)
    assert all(record.label is None for record in dataset.train_records)


def test_global_bootstrap_feature_values_without_epistemic_lineage_remain_unknown():
    store = FeatureStore()
    asset_id = list_fixture_assets()[0].id
    bootstrap_record = store.get_feature_record(asset_id, "biochemical_potency_score", "v1")
    assert bootstrap_record is not None
    today = bootstrap_record.observation_date
    dataset = DatasetBuilder(store).build_opportunity_ranking_dataset(
        cutoff_date=today,
        prediction_cutoff=today,
    )
    row = next(
        record
        for record in dataset.train_records
        if record.entity_id == asset_id
    )
    signal = row.metadata["upstream_signals"]["biology"]["biochemical_potency_score"]

    assert signal["epistemic_class"] == "UNKNOWN"
    assert signal["available"] is False
    assert signal["value"] is None
    assert signal["unclassified_value"] is not None
    assert row.features["biochemical_potency_score"] is None


def test_opportunity_input_contract_preserves_unknowns_and_classifies_signals():
    store = FeatureStore()
    asset_id = list_fixture_assets()[0].id
    store.record_feature(
        _record(
            asset_id,
            "biochemical_potency_score",
            72.5,
            epistemic_class="DERIVED_FEATURE",
            provenance={"feature_version": "bio-v3"},
        )
    )
    store.record_feature(_record(asset_id, "patient_match_score", 80.0))
    store.record_feature(
        _record(asset_id, "cns_clinical_efficacy_probability", None, epistemic_class="UNKNOWN")
    )
    store.record_feature(
        _record(
            asset_id,
            "grade_ge_3_ae_probability",
            0.3,
            epistemic_class="ML_PREDICTION",
            provenance={"model_name": "safety", "model_version": "safety-v1"},
        )
    )
    store.record_feature(
        _record(
            asset_id,
            "phase_II_success_probability",
            0.65,
            epistemic_class="ML_PREDICTION",
            provenance={"model_name": "clinical_success", "model_version": "clinical-v1"},
        )
    )
    store.record_feature(
        _record(
            asset_id,
            "licensing_availability_signal",
            40.0,
            epistemic_class="FACT",
        )
    )
    store.record_feature(
        _record(
            asset_id,
            "competition_intensity",
            0.6,
            epistemic_class=None,
        )
    )

    dataset = _build(store)
    row = next(record for record in dataset.train_records if record.entity_id == asset_id)
    signals = row.metadata["upstream_signals"]
    assert row.features["biochemical_potency_score"] == 72.5
    assert signals["biology"]["biochemical_potency_score"]["epistemic_class"] == "DERIVED_FEATURE"
    assert signals["patient_match"]["patient_match_score"]["value"] == 80.0
    assert signals["safety"]["grade_ge_3_ae_probability"]["epistemic_class"] == "ML_PREDICTION"
    assert signals["safety"]["grade_ge_3_ae_probability"]["provenance"]["model_version"] == "safety-v1"
    assert signals["clinical_probability"]["phase_II_success_probability"][
        "provenance"
    ]["model_name"] == "clinical_success"
    assert signals["licensing_signals"]["licensing_availability_signal"]["value"] == 40.0
    assert row.features["cns_clinical_efficacy_probability"] is None
    assert signals["cns"]["cns_clinical_efficacy_probability"]["available"] is False
    assert row.features["competition_intensity"] is None
    assert signals["competition"]["competition_intensity"]["epistemic_class"] == "UNKNOWN"
    assert signals["competition"]["competition_intensity"]["unclassified_value"] == 0.6


def test_unavailable_cns_and_resistance_remain_unknown_not_zero():
    dataset = _build(FeatureStore())
    row = dataset.train_records[0]
    signals = row.metadata["upstream_signals"]

    cns = signals["cns"]["cns_clinical_efficacy_probability"]
    resistance_related = signals["resistance"]["resistance_mechanism_probability"]
    assert cns == {
        "epistemic_class": "UNKNOWN",
        "available": False,
        "value": None,
        "reason": "No tenant-visible feature record at the prediction cutoff.",
    }
    assert resistance_related["value"] is None
    assert resistance_related["available"] is False
    assert set(signals["resistance"]) == {
        "resistance_mechanism_probability",
        "resistance_risk_probability",
        "predicted_resistance_probability",
    }
    assert dataset.metadata["training_available"] is False


def test_future_test_only_and_cross_tenant_signals_are_excluded():
    store = FeatureStore()
    asset_id = list_fixture_assets()[0].id
    store.record_feature(
        _record(
            asset_id,
            "commercial_opportunity_score",
            80.0,
            tenant_id="tenant-43",
            observed=PREDICTION_CUTOFF + timedelta(days=1),
            cutoff=PREDICTION_CUTOFF,
        )
    )
    store.record_feature(
        _record(
            asset_id,
            "commercial_opportunity_score",
            80.0,
            tenant_id="tenant-43",
            cutoff=PREDICTION_CUTOFF + timedelta(days=1),
        )
    )
    store.record_feature(
        _record(
            asset_id,
            "commercial_opportunity_score",
            80.0,
            tenant_id="tenant-43",
            provenance={"test_only": True, "scientific_evidence": False},
        )
    )
    store.record_feature(
        _record(
            asset_id,
            "commercial_opportunity_score",
            90.0,
            tenant_id="other-tenant",
        )
    )

    dataset = _build(store)
    row = next(record for record in dataset.train_records if record.entity_id == asset_id)
    assert row.features["commercial_opportunity_score"] is None
    assert row.metadata["upstream_signals"]["commercial_opportunity"][
        "commercial_opportunity_score"
    ]["available"] is False


def test_explicit_opportunity_label_must_be_real_and_observed_after_feature_cutoff():
    store = FeatureStore()
    asset_id = list_fixture_assets()[0].id
    store.record_feature(
        _record(
            asset_id,
            "label_opportunity_success",
            1.0,
            observed=DATASET_CUTOFF,
            cutoff=DATASET_CUTOFF,
            provenance={
                "record_type": "observed_outcome_label",
                "target_name": "opportunity_success",
                "test_only": True,
                "scientific_evidence": False,
            },
        )
    )
    dataset = _build(store)
    row = next(record for record in dataset.train_records if record.entity_id == asset_id)

    assert row.label is None
    assert row.metadata["label_status"] == "unknown_without_observed_opportunity_success_outcome"
    assert dataset.metadata["training_available"] is False
    assert dataset.label_versions == []


def test_unavailable_rankings_have_no_score_rank_confidence_or_fake_explanation():
    store = FeatureStore()
    asset_id = list_fixture_assets()[0].id
    store.record_feature(
        _record(
            asset_id,
            "biochemical_potency_score",
            72.5,
            epistemic_class="FACT",
        )
    )
    dataset = _build(store)
    outputs = OpportunityRankingEngine().rank_dataset(dataset)

    assert len(outputs) == len(dataset.train_records)
    for output, record in zip(outputs, dataset.train_records, strict=True):
        assert output.entity_id == record.entity_id
        assert output.opportunity_score is None
        assert output.rank is None
        assert output.confidence is None
        assert output.feature_contributions == []
        assert output.model_name == "opportunity_ranking"
        assert output.model_version is None
        assert output.feature_version == "v1"
        assert output.prediction_cutoff == PREDICTION_CUTOFF
        assert output.tenant_id == "tenant-43"
        assert output.ranking_status == "unavailable_insufficient_history"
        assert output.explanation_status == "unavailable_no_model_explanation"
        assert output.monitoring_status == "unavailable_no_model_predictions"
        assert output.input_snapshot["dataset_version"] == dataset.version
        assert output.input_snapshot["prediction_cutoff"] == PREDICTION_CUTOFF.isoformat()
        assert output.input_snapshot["tenant_id"] == "tenant-43"
        assert output.prediction_timestamp.tzinfo is not None
    first_asset = next(output for output in outputs if output.entity_id == asset_id)
    assert first_asset.evidence_references == [
        f"evidence:{asset_id}:biochemical_potency_score"
    ]
    assert (
        first_asset.upstream_signals["biology"]["biochemical_potency_score"].value
        == 72.5
    )


def test_tenant_isolation_and_reproducibility_for_unavailable_results():
    store = FeatureStore()
    asset_id = list_fixture_assets()[0].id
    store.record_feature(
        _record(asset_id, "biochemical_potency_score", 20.0, tenant_id="tenant-a")
    )
    store.record_feature(
        _record(asset_id, "biochemical_potency_score", 99.0, tenant_id="tenant-b")
    )

    dataset_a = _build(store, "tenant-a")
    dataset_b = _build(store, "tenant-b")
    row_a = next(row for row in dataset_a.train_records if row.entity_id == asset_id)
    row_b = next(row for row in dataset_b.train_records if row.entity_id == asset_id)
    assert row_a.features["biochemical_potency_score"] == 20.0
    assert row_b.features["biochemical_potency_score"] == 99.0

    engine = OpportunityRankingEngine()
    outputs_a = engine.rank_dataset(dataset_a)
    outputs_a_repeat = engine.rank_dataset(dataset_a)
    outputs_b = engine.rank_dataset(dataset_b)
    result_a = next(output for output in outputs_a if output.entity_id == asset_id)
    result_a_repeat = next(output for output in outputs_a_repeat if output.entity_id == asset_id)
    result_b = next(output for output in outputs_b if output.entity_id == asset_id)
    assert result_a.opportunity_score == result_a_repeat.opportunity_score is None
    assert result_a.rank == result_a_repeat.rank is None
    assert result_a.input_snapshot["numeric_features"] == result_a_repeat.input_snapshot["numeric_features"]
    assert result_a.tenant_id == "tenant-a"
    assert result_b.tenant_id == "tenant-b"
    assert result_a.input_snapshot["numeric_features"]["biochemical_potency_score"] == 20.0
    assert result_b.input_snapshot["numeric_features"]["biochemical_potency_score"] == 99.0


def test_unavailable_opportunity_model_is_not_registered_or_served():
    registry = ModelRegistry()
    dataset = _build(FeatureStore())
    assert dataset.metadata["training_available"] is False
    assert registry.get_model_by_version("opportunity_ranking", "v1") is None
    assert registry.get_production_model("opportunity_ranking") is None


def test_sufficient_labels_cannot_emit_scores_without_a_registered_fitted_model():
    dataset = _build(FeatureStore())
    dataset = dataset.model_copy(update={"metadata": {**dataset.metadata, "training_available": True}})
    with pytest.raises(ValueError, match="train and register a fitted ranking model"):
        OpportunityRankingEngine().rank_dataset(dataset)

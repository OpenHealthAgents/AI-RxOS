"""Cutoff-aware synthesis contracts for PatientMatch, Resistance, and Combination."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.opportunity_engine.intelligence import (
    EpistemicClass,
    IntelligenceEvidence,
    IntelligenceModelComponent,
    IntelligenceProfileBase,
    IntelligenceValue,
    IntelligenceValueStatus,
    evidence_confidence,
    registered_model_prediction,
    unknown_value,
)


class PatientMatchIntelligence(IntelligenceProfileBase):
    """Population-level match synthesis; UNKNOWN populations are intentionally retained."""

    primary_population: IntelligenceValue
    secondary_population: IntelligenceValue
    low_likelihood_population: IntelligenceValue
    biomarker_strategy: IntelligenceValue
    patient_match_score: IntelligenceValue
    confidence: IntelligenceValue


class ResistanceEvidenceClass(StrEnum):
    OBSERVED_RESISTANCE = "observed resistance"
    PRECLINICAL_RESISTANCE = "preclinical resistance"
    CLINICAL_RESISTANCE = "clinical resistance"
    MECHANISTIC_INFERENCE = "mechanistic inference"


class DatedResistanceObservation(BaseModel):
    """Tenant-scoped resistance evidence with an explicit date and evidence class."""

    model_config = ConfigDict(from_attributes=True)

    evidence_id: str
    asset_id: str
    mechanism_name: str
    category: str
    evidence_class: ResistanceEvidenceClass
    observation_date: date | None = None
    tenant_id: str | None = None
    source_type: str
    source_reference: str
    citation: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    provenance: dict[str, Any] = Field(default_factory=dict)


class ResistanceMechanismIntelligence(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    mechanism_name: str
    category: str
    classification: ResistanceEvidenceClass
    epistemic_class: EpistemicClass
    supporting_evidence: list[IntelligenceEvidence] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class ResistanceIntelligence(IntelligenceProfileBase):
    """Resistance mechanisms supported by cutoff-valid evidence only."""

    top_escape_mechanisms: list[ResistanceMechanismIntelligence] = Field(
        default_factory=list
    )
    predicted_resistance_risk: IntelligenceValue
    confidence: IntelligenceValue


class CombinationValidationClass(StrEnum):
    CLINICALLY_VALIDATED = "clinically validated"
    CLINICAL_HYPOTHESIS = "clinical hypothesis"
    PRECLINICAL = "preclinical"
    MECHANISTIC = "mechanistic"
    AI_GENERATED_HYPOTHESIS = "AI-generated hypothesis"


class CombinationCandidateIntelligence(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    partner: str
    resistance_mechanism: str
    classification: CombinationValidationClass
    mechanistic_complementarity: IntelligenceValue
    toxicity_overlap: IntelligenceValue
    development_feasibility: IntelligenceValue
    evidence_strength: IntelligenceValue
    supporting_evidence: list[IntelligenceEvidence] = Field(default_factory=list)


class CombinationMechanismEvaluation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    resistance_mechanism: str
    candidates: list[CombinationCandidateIntelligence] = Field(default_factory=list)
    status: IntelligenceValueStatus
    reason: str | None = None
    supporting_evidence: list[IntelligenceEvidence] = Field(default_factory=list)


class CombinationIntelligence(IntelligenceProfileBase):
    """Combinations linked to cutoff-valid resistance and KG evidence."""

    mechanism_evaluations: list[CombinationMechanismEvaluation] = Field(
        default_factory=list
    )
    evidence: list[IntelligenceEvidence] = Field(default_factory=list)
    excluded_undated_evidence: list[IntelligenceEvidence] = Field(default_factory=list)


def _feature_evidence(record: Any, *, source_type: str) -> list[IntelligenceEvidence]:
    references = [
        reference
        for reference in record.evidence_references
        if not str(reference).lower().startswith("test-only:")
    ]
    if not references:
        return []
    confidence = (
        record.confidence if "confidence" in record.model_fields_set else None
    )
    return [
        IntelligenceEvidence(
            evidence_id=f"feature:{record.feature_name}:{reference}",
            source_type=source_type,
            source_reference=str(reference),
            observed_at=record.observation_date,
            confidence=confidence,
            epistemic_class=EpistemicClass.DERIVED_FEATURE,
            provenance={
                **record.provenance,
                "feature_name": record.feature_name,
                "feature_version": record.feature_version,
                "prediction_cutoff": record.prediction_cutoff.isoformat(),
            },
        )
        for reference in references
    ]


def _upstream_evidence(
    *,
    tenant_id: str | None,
    profiles: tuple[Any | None, ...],
) -> list[IntelligenceEvidence]:
    result: list[IntelligenceEvidence] = []
    for profile in profiles:
        if profile is None or getattr(profile, "tenant_id", None) not in (
            None,
            tenant_id,
        ):
            continue
        result.extend(profile.evidence)
        result.extend(profile.knowledge_graph_evidence)
    deduplicated: dict[str, IntelligenceEvidence] = {}
    for item in result:
        evidence_tenant = item.provenance.get("tenant_id")
        if evidence_tenant not in (None, tenant_id):
            continue
        deduplicated[item.evidence_id] = item
    return list(deduplicated.values())


def synthesize_patient_match(
    *,
    asset_id: str,
    asset_name: str,
    prediction_cutoff: date,
    tenant_id: str | None,
    feature_store: Any | None,
    model_registry: Any | None,
    biology_intelligence: Any | None,
    clinical_intelligence: Any | None,
) -> PatientMatchIntelligence:
    upstream = _upstream_evidence(
        tenant_id=tenant_id,
        profiles=(biology_intelligence, clinical_intelligence),
    )
    excluded = [
        item
        for profile in (biology_intelligence, clinical_intelligence)
        if profile is not None
        and getattr(profile, "tenant_id", None) in (None, tenant_id)
        for item in profile.excluded_undated_evidence
        if item.provenance.get("tenant_id") in (None, tenant_id)
    ]
    records: list[Any] = []
    if feature_store is not None:
        records = feature_store.get_feature_records_for_asset(
            asset_id, tenant_id=tenant_id
        )
    admissible = [
        record
        for record in records
        if record.feature_name in {"mutation", "expression", "amplification", "biomarker",
                                   "subtype", "prior_treatment", "line_of_therapy",
                                   "resistance", "CNS", "mechanism"}
        and record.value is not None
        and record.observation_date <= prediction_cutoff
        and record.prediction_cutoff <= prediction_cutoff
        and not record.provenance.get("test_only")
        and record.provenance.get("scientific_evidence") is not False
        and record.provenance.get("source_count") != 0
    ]
    feature_evidence = [
        evidence
        for record in admissible
        for evidence in _feature_evidence(
            record, source_type="patient_match_input_feature"
        )
    ]
    evidence = list(
        {
            item.evidence_id: item
            for item in [*upstream, *feature_evidence]
        }.values()
    )
    model_component, prediction = registered_model_prediction(
        model_name="patient_response",
        asset_id=asset_id,
        prediction_cutoff=prediction_cutoff,
        tenant_id=tenant_id,
        registry=model_registry,
        feature_store=feature_store,
        require_scientific_evidence=True,
    )
    if prediction is not None and prediction.probability is not None:
        score = IntelligenceValue(
            name="patient_match_score",
            value=round(float(prediction.probability) * 100.0, 6),
            status=IntelligenceValueStatus.AVAILABLE,
            epistemic_class=EpistemicClass.ML_PREDICTION,
            confidence=prediction.confidence,
            supporting_evidence=[
                item
                for item in evidence
                if item.source_type == "patient_match_input_feature"
                and item.provenance.get("feature_name")
                in prediction.input_snapshot.get("observation_dates", {})
            ],
            provenance={
                "model_name": prediction.model_name,
                "model_version": prediction.model_version,
                "feature_version": prediction.feature_version,
                "prediction_cutoff": prediction_cutoff.isoformat(),
                "prediction_timestamp": prediction.prediction_timestamp.isoformat(),
                "input_snapshot": prediction.input_snapshot,
                "meaning": "Model response probability scaled to a 0-100 population-match score.",
            },
        )
        confidence = IntelligenceValue(
            name="confidence",
            value=prediction.confidence,
            status=(
                IntelligenceValueStatus.AVAILABLE
                if prediction.confidence is not None
                else IntelligenceValueStatus.UNKNOWN
            ),
            epistemic_class=EpistemicClass.ML_PREDICTION,
            confidence=prediction.confidence,
            supporting_evidence=score.supporting_evidence,
            reason=(
                None
                if prediction.confidence is not None
                else "Patient-response serving did not supply calibrated confidence."
            ),
        )
    else:
        score = unknown_value(
            "patient_match_score",
            model_component.reason or "Patient-response ML is unavailable.",
            status=IntelligenceValueStatus.UNAVAILABLE,
        )
        confidence = unknown_value(
            "confidence",
            "No eligible patient-response model confidence is available.",
            status=IntelligenceValueStatus.UNAVAILABLE,
        )

    biomarker_records = [
        item for item in admissible if item.feature_name == "biomarker"
    ]
    biomarker_evidence = [
        evidence
        for item in biomarker_records
        for evidence in _feature_evidence(item, source_type="biomarker_feature")
    ]
    biomarker_strategy = unknown_value(
        "biomarker_strategy",
        "No cutoff-valid biomarker feature with non-test scientific provenance is available.",
        status=IntelligenceValueStatus.INSUFFICIENT_EVIDENCE,
    )
    if biomarker_records and biomarker_evidence:
        biomarker_strategy = IntelligenceValue(
            name="biomarker_strategy",
            value={
                "documented_feature_values": [
                    {
                        "value": item.value,
                        "unit": item.unit,
                        "provenance": item.provenance,
                    }
                    for item in biomarker_records
                ],
                "interpretation": (
                    "Biological/feature support only; not evidence of patient response "
                    "or a clinically validated companion diagnostic."
                ),
            },
            status=IntelligenceValueStatus.AVAILABLE,
            epistemic_class=EpistemicClass.DERIVED_FEATURE,
            confidence=evidence_confidence(biomarker_evidence),
            supporting_evidence=biomarker_evidence,
            provenance={"prediction_cutoff": prediction_cutoff.isoformat()},
        )
    elif (
        (biological_biomarker := getattr(
            biology_intelligence, "biomarker_strength", None
        ))
        is not None
        and biological_biomarker.status == IntelligenceValueStatus.AVAILABLE
        and biological_biomarker.supporting_evidence
    ):
        biomarker_strategy = IntelligenceValue(
            name="biomarker_strategy",
            value={
                "biological_biomarker_strength": biological_biomarker.value,
                "patient_response": "UNKNOWN",
                "interpretation": (
                    "Biological evidence may support a biomarker hypothesis; "
                    "it is not observed patient response or a validated diagnostic strategy."
                ),
            },
            status=IntelligenceValueStatus.AVAILABLE,
            epistemic_class=EpistemicClass.HYPOTHESIS,
            confidence=biological_biomarker.confidence,
            supporting_evidence=biological_biomarker.supporting_evidence,
            provenance={
                "prediction_cutoff": prediction_cutoff.isoformat(),
                "derived_from": "Biology Intelligence biomarker strength",
            },
        )

    unknown_populations = [
        unknown_value(
            name,
            "No eligible patient-level response evidence supports ranking this population.",
            status=IntelligenceValueStatus.INSUFFICIENT_EVIDENCE,
        )
        for name in (
            "primary_population",
            "secondary_population",
            "low_likelihood_population",
        )
    ]
    return PatientMatchIntelligence(
        asset_id=asset_id,
        asset_name=asset_name,
        tenant_id=tenant_id,
        prediction_cutoff=prediction_cutoff,
        primary_population=unknown_populations[0],
        secondary_population=unknown_populations[1],
        low_likelihood_population=unknown_populations[2],
        biomarker_strategy=biomarker_strategy,
        patient_match_score=score,
        confidence=confidence,
        evidence=evidence,
        excluded_undated_evidence=excluded,
        ml_component=model_component,
    )


def _resistance_epistemic(
    evidence_class: ResistanceEvidenceClass,
) -> EpistemicClass:
    return (
        EpistemicClass.FACT
        if evidence_class
        in {
            ResistanceEvidenceClass.OBSERVED_RESISTANCE,
            ResistanceEvidenceClass.PRECLINICAL_RESISTANCE,
            ResistanceEvidenceClass.CLINICAL_RESISTANCE,
        }
        else EpistemicClass.HYPOTHESIS
    )


def _kg_resistance(
    *,
    asset_id: str,
    cutoff: date,
    knowledge_graph: Any | None,
) -> tuple[list[tuple[str, str, ResistanceEvidenceClass, IntelligenceEvidence]],
           list[IntelligenceEvidence]]:
    if knowledge_graph is None:
        return [], []
    node = knowledge_graph.get_node_by_external_id(f"ASSET:{asset_id.upper()}")
    if node is None:
        return [], []
    graph = knowledge_graph.get_asset_opportunity_graph(node.id)
    mechanisms: list[tuple[str, str, ResistanceEvidenceClass, IntelligenceEvidence]] = []
    excluded: list[IntelligenceEvidence] = []
    for relationship in graph.relationships_by_category.get("resistance", []):
        mechanism_name = relationship.target_node.name
        for source in relationship.evidence_lineage:
            reference = source.source_document_id or str(source.evidence_id)
            if source.created_at.date() > cutoff:
                excluded.append(
                    IntelligenceEvidence(
                        evidence_id=str(source.evidence_id),
                        source_type="knowledge_graph_resistance_excluded",
                        source_reference=reference,
                        citation=source.source_citation,
                        confidence=None,
                        epistemic_class=EpistemicClass.FACT,
                        provenance={
                            "exclusion_reason": "evidence_created_after_prediction_cutoff",
                            "available_at": source.created_at.isoformat(),
                            "prediction_cutoff": cutoff.isoformat(),
                        },
                    )
                )
                continue
            raw_class = str(
                relationship.properties.get(
                    "resistance_class",
                    relationship.properties.get("evidence_class", ""),
                )
            ).casefold()
            evidence_type = source.evidence_type.casefold()
            if raw_class in {"clinical resistance", "clinical_resistance"} or "clinical_resistance" in evidence_type:
                evidence_class = ResistanceEvidenceClass.CLINICAL_RESISTANCE
            elif raw_class in {"preclinical resistance", "preclinical_resistance"} or "preclinical" in evidence_type:
                evidence_class = ResistanceEvidenceClass.PRECLINICAL_RESISTANCE
            elif raw_class in {"observed resistance", "observed_resistance"} or "observed_resistance" in evidence_type:
                evidence_class = ResistanceEvidenceClass.OBSERVED_RESISTANCE
            else:
                evidence_class = ResistanceEvidenceClass.MECHANISTIC_INFERENCE
            evidence = IntelligenceEvidence(
                evidence_id=str(source.evidence_id),
                source_type=f"knowledge_graph_resistance:{source.evidence_type}",
                source_reference=reference,
                citation=source.source_citation,
                confidence=(
                    source.confidence
                    if "confidence" in source.model_fields_set
                    else None
                ),
                epistemic_class=_resistance_epistemic(evidence_class),
                provenance={
                    "relationship_category": relationship.relationship_category,
                    "relationship_type": relationship.relationship_type.value,
                    "edge_id": str(relationship.edge_id),
                    "available_at": source.created_at.isoformat(),
                    **relationship.properties,
                },
            )
            mechanisms.append(
                (
                    mechanism_name,
                    raw_class or "resistance",
                    evidence_class,
                    evidence,
                )
            )
    return mechanisms, excluded


def synthesize_resistance(
    *,
    asset_id: str,
    asset_name: str,
    prediction_cutoff: date,
    tenant_id: str | None,
    observations: list[DatedResistanceObservation],
    knowledge_graph: Any | None,
    feature_store: Any | None,
    model_registry: Any | None,
    undated_canonical_mechanisms: list[Any] | None = None,
) -> ResistanceIntelligence:
    if any(
        item.asset_id.casefold() != asset_id.casefold()
        or item.tenant_id not in (None, tenant_id)
        for item in observations
    ):
        raise ValueError(
            "Resistance observations must belong to the requested asset and tenant."
        )
    admissible = [
        item
        for item in observations
        if item.observation_date is not None
        and item.observation_date <= prediction_cutoff
        and item.tenant_id in (None, tenant_id)
    ]
    excluded = [
        IntelligenceEvidence(
            evidence_id=item.evidence_id,
            source_type=f"{item.source_type}_excluded",
            source_reference=item.source_reference,
            citation=item.citation,
            observed_at=item.observation_date,
            confidence=None,
            epistemic_class=_resistance_epistemic(item.evidence_class),
            provenance={
                **item.provenance,
                "exclusion_reason": (
                    "observation_date_missing"
                    if item.observation_date is None
                    else "observation_after_prediction_cutoff"
                ),
                "prediction_cutoff": prediction_cutoff.isoformat(),
            },
        )
        for item in observations
        if item not in admissible
    ]
    records: list[
        tuple[str, str, ResistanceEvidenceClass, IntelligenceEvidence]
    ] = []
    for item in admissible:
        evidence = IntelligenceEvidence(
            evidence_id=item.evidence_id,
            source_type=item.source_type,
            source_reference=item.source_reference,
            citation=item.citation,
            observed_at=item.observation_date,
            confidence=item.confidence,
            epistemic_class=_resistance_epistemic(item.evidence_class),
            provenance=item.provenance,
        )
        records.append(
            (item.mechanism_name, item.category, item.evidence_class, evidence)
        )
    kg_records, kg_excluded = _kg_resistance(
        asset_id=asset_id,
        cutoff=prediction_cutoff,
        knowledge_graph=knowledge_graph,
    )
    records.extend(kg_records)
    excluded.extend(kg_excluded)
    for mechanism in undated_canonical_mechanisms or []:
        citations = mechanism.evidence_citations or []
        excluded.append(
            IntelligenceEvidence(
                evidence_id=f"legacy_resistance:{mechanism.id}",
                source_type="canonical_resistance_profile_excluded",
                source_reference=(
                    str(citations[0].get("pmid") or citations[0].get("nct_id"))
                    if citations
                    and (citations[0].get("pmid") or citations[0].get("nct_id"))
                    else str(mechanism.id)
                ),
                citation=(
                    str(citations[0].get("citation"))
                    if citations and citations[0].get("citation")
                    else None
                ),
                confidence=None,
                epistemic_class=EpistemicClass.UNKNOWN,
                provenance={
                    "mechanism_name": mechanism.mechanism_name,
                    "exclusion_reason": "canonical_resistance_record_has_no_observation_date",
                    "prediction_cutoff": prediction_cutoff.isoformat(),
                },
            )
        )

    grouped: dict[
        tuple[str, ResistanceEvidenceClass],
        list[tuple[str, str, ResistanceEvidenceClass, IntelligenceEvidence]],
    ] = {}
    for record in records:
        grouped.setdefault((record[0].casefold(), record[2]), []).append(record)
    findings = [
        ResistanceMechanismIntelligence(
            mechanism_name=items[0][0],
            category=items[0][1],
            classification=evidence_class,
            epistemic_class=_resistance_epistemic(evidence_class),
            supporting_evidence=[item[3] for item in items],
            confidence=evidence_confidence([item[3] for item in items]),
        )
        for (_, evidence_class), items in grouped.items()
    ]
    findings.sort(
        key=lambda item: (
            item.confidence is not None,
            item.confidence if item.confidence is not None else -1.0,
            len(item.supporting_evidence),
        ),
        reverse=True,
    )
    model_component, prediction = registered_model_prediction(
        model_name="resistance",
        asset_id=asset_id,
        prediction_cutoff=prediction_cutoff,
        tenant_id=tenant_id,
        registry=model_registry,
        feature_store=feature_store,
        require_scientific_evidence=True,
    )
    if prediction is not None and prediction.probability is not None:
        predicted_risk = IntelligenceValue(
            name="predicted_resistance_risk",
            value=prediction.probability,
            status=IntelligenceValueStatus.AVAILABLE,
            epistemic_class=EpistemicClass.ML_PREDICTION,
            confidence=prediction.confidence,
            provenance={
                "model_name": prediction.model_name,
                "model_version": prediction.model_version,
                "feature_version": prediction.feature_version,
                "prediction_cutoff": prediction_cutoff.isoformat(),
                "prediction_timestamp": prediction.prediction_timestamp.isoformat(),
                "input_snapshot": prediction.input_snapshot,
                "mechanism_names_not_inferred_from_scalar_risk": True,
            },
        )
    else:
        predicted_risk = unknown_value(
            "predicted_resistance_risk",
            model_component.reason or "Resistance ML is unavailable.",
            status=IntelligenceValueStatus.UNAVAILABLE,
        )
    evidence = [item[3] for item in records]
    evidence_conf = evidence_confidence(evidence)
    confidence = (
        IntelligenceValue(
            name="confidence",
            value=evidence_conf,
            status=IntelligenceValueStatus.AVAILABLE,
            epistemic_class=EpistemicClass.DERIVED_FEATURE,
            confidence=evidence_conf,
            supporting_evidence=evidence,
            provenance={"aggregation": "minimum explicit source confidence"},
        )
        if evidence_conf is not None
        else unknown_value(
            "confidence",
            "No cutoff-valid resistance source reports confidence.",
        )
    )
    return ResistanceIntelligence(
        asset_id=asset_id,
        asset_name=asset_name,
        tenant_id=tenant_id,
        prediction_cutoff=prediction_cutoff,
        top_escape_mechanisms=findings,
        predicted_resistance_risk=predicted_risk,
        confidence=confidence,
        evidence=evidence,
        excluded_undated_evidence=excluded,
        ml_component=model_component,
    )


def _combination_classification(
    relationship: Any, source: Any
) -> CombinationValidationClass:
    explicit = str(relationship.properties.get("validation_status", "")).casefold()
    evidence_type = source.evidence_type.casefold()
    if explicit == CombinationValidationClass.CLINICALLY_VALIDATED.value.casefold() and (
        (
            evidence_type.startswith("clinical")
            and not evidence_type.startswith("preclinical")
        )
        or relationship.properties.get("clinical_evidence") is True
    ):
        return CombinationValidationClass.CLINICALLY_VALIDATED
    if explicit == CombinationValidationClass.CLINICAL_HYPOTHESIS.value.casefold() or (
        "clinical_trial" in evidence_type
    ):
        return CombinationValidationClass.CLINICAL_HYPOTHESIS
    if (
        explicit == CombinationValidationClass.PRECLINICAL.value.casefold()
        or "preclinical" in evidence_type
    ):
        return CombinationValidationClass.PRECLINICAL
    if (
        explicit
        == CombinationValidationClass.AI_GENERATED_HYPOTHESIS.value.casefold()
    ):
        return CombinationValidationClass.AI_GENERATED_HYPOTHESIS
    return CombinationValidationClass.MECHANISTIC


def synthesize_combinations(
    *,
    asset_id: str,
    asset_name: str,
    prediction_cutoff: date,
    tenant_id: str | None,
    resistance_intelligence: ResistanceIntelligence,
    knowledge_graph: Any | None,
) -> CombinationIntelligence:
    graph = None
    if knowledge_graph is not None:
        node = knowledge_graph.get_node_by_external_id(f"ASSET:{asset_id.upper()}")
        if node is not None:
            graph = knowledge_graph.get_asset_opportunity_graph(node.id)
    relationships = (
        graph.relationships_by_category.get("combination", []) if graph else []
    )
    evaluations: list[CombinationMechanismEvaluation] = []
    all_evidence: dict[str, IntelligenceEvidence] = {}
    excluded: list[IntelligenceEvidence] = []
    for mechanism in resistance_intelligence.top_escape_mechanisms:
        candidates: list[CombinationCandidateIntelligence] = []
        mechanism_evidence = mechanism.supporting_evidence
        for relationship in relationships:
            declared_mechanism = str(
                relationship.properties.get("resistance_mechanism", "")
            ).casefold()
            if declared_mechanism != mechanism.mechanism_name.casefold():
                continue
            source_evidence: list[IntelligenceEvidence] = []
            eligible_sources: list[Any] = []
            for source in relationship.evidence_lineage:
                if source.created_at.date() > prediction_cutoff:
                    excluded.append(
                        IntelligenceEvidence(
                            evidence_id=str(source.evidence_id),
                            source_type="knowledge_graph_combination_excluded",
                            source_reference=source.source_document_id or str(source.evidence_id),
                            citation=source.source_citation,
                            confidence=None,
                            epistemic_class=EpistemicClass.FACT,
                            provenance={
                                "exclusion_reason": "evidence_created_after_prediction_cutoff",
                                "available_at": source.created_at.isoformat(),
                                "prediction_cutoff": prediction_cutoff.isoformat(),
                            },
                        )
                    )
                    continue
                source_evidence.append(
                    IntelligenceEvidence(
                        evidence_id=str(source.evidence_id),
                        source_type=f"knowledge_graph_combination:{source.evidence_type}",
                        source_reference=source.source_document_id or str(source.evidence_id),
                        citation=source.source_citation,
                        confidence=(
                            source.confidence
                            if "confidence" in source.model_fields_set
                            else None
                        ),
                        epistemic_class=EpistemicClass.FACT,
                        provenance={
                            "relationship_type": relationship.relationship_type.value,
                            "edge_id": str(relationship.edge_id),
                            "available_at": source.created_at.isoformat(),
                            **relationship.properties,
                        },
                    )
                )
                eligible_sources.append(source)
            if not source_evidence:
                continue
            classified = _combination_classification(
                relationship, eligible_sources[0]
            )
            epistemic_class = (
                EpistemicClass.HYPOTHESIS
                if classified
                in {
                    CombinationValidationClass.CLINICAL_HYPOTHESIS,
                    CombinationValidationClass.MECHANISTIC,
                    CombinationValidationClass.AI_GENERATED_HYPOTHESIS,
                }
                else EpistemicClass.FACT
            )
            source_evidence = [
                item.model_copy(update={"epistemic_class": epistemic_class})
                for item in source_evidence
            ]
            rationale = relationship.properties.get("mechanistic_rationale")
            if rationale:
                complementarity = IntelligenceValue(
                    name="mechanistic_complementarity",
                    value={
                        "documented_relationship": relationship.relationship_type.value,
                        "rationale": rationale,
                    },
                    status=IntelligenceValueStatus.AVAILABLE,
                    epistemic_class=EpistemicClass.FACT,
                    confidence=evidence_confidence(source_evidence),
                    supporting_evidence=source_evidence,
                    provenance={"source": "provenance-backed knowledge graph"},
                )
            else:
                complementarity = unknown_value(
                    "mechanistic_complementarity",
                    "The KG relation has no sourced mechanistic rationale.",
                )
            candidates.append(
                CombinationCandidateIntelligence(
                    partner=relationship.target_node.name,
                    resistance_mechanism=mechanism.mechanism_name,
                    classification=classified,
                    mechanistic_complementarity=complementarity,
                    toxicity_overlap=unknown_value(
                        "toxicity_overlap",
                        "No cutoff-valid partner-specific safety evidence was supplied.",
                    ),
                    development_feasibility=unknown_value(
                        "development_feasibility",
                        "No cutoff-valid development feasibility evidence was supplied.",
                    ),
                    evidence_strength=IntelligenceValue(
                        name="evidence_strength",
                        value={"cutoff_valid_source_count": len(source_evidence)},
                        status=IntelligenceValueStatus.AVAILABLE,
                        epistemic_class=EpistemicClass.DERIVED_FEATURE,
                        confidence=evidence_confidence(source_evidence),
                        supporting_evidence=source_evidence,
                        provenance={
                            "count_is_not_a_scientific_quality_score": True,
                            "prediction_cutoff": prediction_cutoff.isoformat(),
                        },
                    ),
                    supporting_evidence=source_evidence,
                )
            )
            all_evidence.update({item.evidence_id: item for item in source_evidence})
        evaluations.append(
            CombinationMechanismEvaluation(
                resistance_mechanism=mechanism.mechanism_name,
                candidates=candidates,
                status=(
                    IntelligenceValueStatus.AVAILABLE
                    if candidates
                    else IntelligenceValueStatus.INSUFFICIENT_EVIDENCE
                ),
                reason=(
                    None
                    if candidates
                    else "No cutoff-valid KG combination relationship explicitly addresses this mechanism."
                ),
                supporting_evidence=mechanism_evidence,
            )
        )
        all_evidence.update(
            {item.evidence_id: item for item in mechanism_evidence}
        )
    return CombinationIntelligence(
        asset_id=asset_id,
        asset_name=asset_name,
        tenant_id=tenant_id,
        prediction_cutoff=prediction_cutoff,
        ml_component=IntelligenceModelComponent(
            model_name="combination_intelligence",
            prediction_cutoff=prediction_cutoff,
            reason="No combination ML model is defined; combinations require sourced evidence.",
        ),
        mechanism_evaluations=evaluations,
        evidence=list(all_evidence.values()),
        excluded_undated_evidence=excluded,
    )

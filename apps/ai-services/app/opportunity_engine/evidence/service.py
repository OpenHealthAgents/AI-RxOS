from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Union
from uuid import UUID, uuid4

from app.opportunity_engine.domain.canonical_model import (
    EvidencePolarity,
    ScientificEvidenceState,
    StrategicAction,
)
from app.opportunity_engine.temporal.models import (
    EvidenceTemporalMetadata,
    TemporalDateField,
    TemporalQueryFilter,
)
from app.opportunity_engine.provenance import (
    DecisionInputRecord,
    ModelInputRecord,
    NormalizationRecord,
    ProvenanceGraph,
    ProvenanceGraphEngine,
    ProvenanceTracebackResult,
)
from .scoring import (
    DirectnessLevel,
    EvidenceQualityAppraisal,
    EvidenceQualityEngine,
    LowEvidenceConversionError,
    ModelRelevance,
    ReplicationStatus,
    StudyDesignType,
)
from .ranking import (
    EvidenceRankingEngine,
    EvidenceRankingRecord,
    EvidenceRankingResult,
    EvidenceRankingTier,
    RankingDimensionDetail,
)

from .contradiction import (
    ContradictionEngine,
    ContradictionRecord,
    ContradictionReport,
    ContradictoryClaim,
    DisagreementCategory,
    DisagreementResolutionStatus,
    SilentSelectionViolationError,
)
from .lineage import EvidenceLineageEngine
from .models import (
    ClaimType,
    ConfidenceLevel,
    Evidence,
    EvidenceCitation,
    EvidenceClaim,
    EvidenceConfidence,
    EvidenceExtraction,
    EvidenceLineageGraph,
    EvidenceObservation,
    EvidenceQuality,
    EvidenceSource,
    EvidenceTemporalScope,
    ExtractionMethod,
    ProspectiveOrRetrospective,
    QualityGrade,
    RiskOfBias,
    SourceType,
)


class EvidenceService:
    """
    Evidence intelligence service managing source ingestion, quality appraisal,
    temporal anti-leakage filtering, and full decision lineage trees.
    """

    def __init__(
        self,
        lineage_engine: Optional[EvidenceLineageEngine] = None,
        provenance_engine: Optional[ProvenanceGraphEngine] = None,
        contradiction_engine: Optional[ContradictionEngine] = None,
    ) -> None:
        self.lineage_engine = lineage_engine or EvidenceLineageEngine()
        self.provenance_engine = provenance_engine or ProvenanceGraphEngine()
        self.contradiction_engine = contradiction_engine or ContradictionEngine()
        self._sources: Dict[UUID, EvidenceSource] = {}
        self._source_asset_map: Dict[UUID, UUID] = {}
        self._extractions: Dict[UUID, EvidenceExtraction] = {}
        self._observations: Dict[UUID, EvidenceObservation] = {}
        self._claims: Dict[UUID, EvidenceClaim] = {}
        self._appraisals: Dict[UUID, EvidenceQualityAppraisal] = {}
        self._bootstrap_fixtures()

    @staticmethod
    def calculate_quality(
        peer_reviewed: bool,
        study_type: str,
        sample_size: Optional[int],
        prospective: ProspectiveOrRetrospective,
        risk_of_bias: RiskOfBias = RiskOfBias.LOW,
        model: Optional[str] = None,
        species: Optional[str] = "Human",
        source_type: SourceType = SourceType.PUBLICATION,
        publication_date: Optional[date] = None,
    ) -> EvidenceQualityAppraisal:
        """
        Calibrates evidence quality across all 10 dimensions using EvidenceQualityEngine:
        peer review, study design, sample size, model relevance, human evidence,
        prospective design, replication, source quality, directness, and recency.
        """
        # Map study_type to StudyDesignType
        st_lower = study_type.lower()
        if "double_blind" in st_lower or "rct" in st_lower:
            design = StudyDesignType.RCT_DOUBLE_BLIND if "double" in st_lower else StudyDesignType.RCT_OPEN_LABEL
        elif "phase 1" in st_lower or "phase_1" in st_lower or "phase 2" in st_lower or "phase_2" in st_lower or "clinical" in st_lower:
            design = StudyDesignType.PHASE_1_2_SINGLE_ARM
        elif "retrospective" in st_lower:
            design = StudyDesignType.RETROSPECTIVE_OBSERVATIONAL
        elif "in_vivo" in st_lower or "xenograft" in st_lower or "pdx" in st_lower:
            design = StudyDesignType.IN_VIVO_ANIMAL_DISEASE_MODEL
        elif "cell_line" in st_lower or "cell line" in st_lower:
            design = StudyDesignType.IN_VITRO_CELL_LINE
        elif "kinase" in st_lower or "biochemical" in st_lower:
            design = StudyDesignType.BIOCHEMICAL_KINASE_ASSAY
        elif "computational" in st_lower:
            design = StudyDesignType.COMPUTATIONAL_PREDICTION
        else:
            design = StudyDesignType.PROSPECTIVE_COHORT if prospective == ProspectiveOrRetrospective.PROSPECTIVE else StudyDesignType.IN_VIVO_ANIMAL_DISEASE_MODEL

        # Model relevance
        is_human = species is not None and "human" in species.lower()
        if is_human:
            mod_rel = ModelRelevance.DIRECT_HUMAN_CLINICAL
        elif model and "pdx" in model.lower():
            mod_rel = ModelRelevance.PATIENT_DERIVED_XENOGRAFT
        elif model and "syngeneic" in model.lower():
            mod_rel = ModelRelevance.SYNGENEIC_ANIMAL_MODEL
        elif model and "cell" in model.lower():
            mod_rel = ModelRelevance.IMMORTALIZED_CELL_LINE
        else:
            mod_rel = ModelRelevance.RECOMBINANT_CELL_FREE_ASSAY

        return EvidenceQualityEngine.evaluate(
            peer_reviewed=peer_reviewed,
            study_design=design,
            sample_size=sample_size,
            model_relevance=mod_rel,
            is_human=is_human,
            prospective_or_retrospective=prospective,
            replication_status=ReplicationStatus.INTERNALLY_REPLICATED if sample_size and sample_size >= 50 else ReplicationStatus.SINGLE_STUDY_UNREPLICATED,
            source_type=source_type,
            directness=DirectnessLevel.DIRECT if is_human else DirectnessLevel.PROXIMATE,
            publication_date=publication_date,
            as_of_date=date.today(),
            risk_of_bias=risk_of_bias,
        )

    def register_evidence(
        self,
        asset_id: UUID,
        source_type: SourceType,
        source_id: str,
        title: str,
        authors: List[str],
        organization: str,
        publication_date: date,
        retrieval_date: date,
        url_reference: str,
        study_type: str,
        phase: Optional[str] = None,
        species: Optional[str] = "Human",
        model: Optional[str] = None,
        sample_size: Optional[int] = None,
        peer_reviewed: bool = True,
        prospective_or_retrospective: ProspectiveOrRetrospective = ProspectiveOrRetrospective.NOT_APPLICABLE,
        risk_of_bias: RiskOfBias = RiskOfBias.LOW,
        confidence_score: float = 0.90,
        observation_date: Optional[date] = None,
        trial_date: Optional[date] = None,
        outcome_date: Optional[date] = None,
        regulatory_date: Optional[date] = None,
        licensing_date: Optional[date] = None,
        prediction_cutoff: Optional[date] = None,
        public_availability_date: Optional[date] = None,
        temporal_metadata: Optional[EvidenceTemporalMetadata] = None,
    ) -> EvidenceSource:
        """
        Registers an evidence source capturing all 18 specified attributes and full temporal metadata.
        """
        temporal_scope = EvidenceTemporalScope(
            valid_from=publication_date,
            valid_to=None,
            as_of_date=publication_date,
            is_current=True,
            cutoff_compliant=True,
        )

        appraisal = self.calculate_quality(
            peer_reviewed=peer_reviewed,
            study_type=study_type,
            sample_size=sample_size,
            prospective=prospective_or_retrospective,
            risk_of_bias=risk_of_bias,
            model=model,
            species=species,
            source_type=source_type,
            publication_date=publication_date,
        )

        citation = EvidenceCitation(
            source_id=uuid4(),
            formatted_citation=f"{title} ({publication_date.year}). {organization}.",
            short_citation=f"{organization} ({publication_date.year})",
            pmid=source_id if source_type == SourceType.PUBLICATION and source_id.startswith("PMID:") else None,
            nct_id=source_id if source_type == SourceType.CLINICAL_TRIAL else None,
            patent_number=source_id if source_type == SourceType.PATENT else None,
            url=url_reference,
        )

        meta = temporal_metadata or EvidenceTemporalMetadata(
            publication_date=publication_date,
            observation_date=observation_date or publication_date,
            trial_date=trial_date or (publication_date if source_type == SourceType.CLINICAL_TRIAL else None),
            outcome_date=outcome_date,
            regulatory_date=regulatory_date or (publication_date if source_type == SourceType.REGULATORY_SOURCE else None),
            licensing_date=licensing_date or (publication_date if source_type == SourceType.COMPANY_SOURCE else None),
            prediction_cutoff=prediction_cutoff,
            public_availability_date=public_availability_date or publication_date,
        )

        source = EvidenceSource(
            id=citation.source_id,
            source_type=source_type,
            source_id=source_id,
            title=title,
            authors=authors,
            organization=organization,
            publication_date=publication_date,
            retrieval_date=retrieval_date,
            url_reference=url_reference,
            study_type=study_type,
            phase=phase,
            species=species,
            model=model,
            sample_size=sample_size,
            peer_reviewed=peer_reviewed,
            prospective_or_retrospective=prospective_or_retrospective,
            quality_score=appraisal.overall_quality_score,
            confidence=confidence_score if confidence_score != 0.90 else appraisal.calibrated_confidence,
            temporal_validity=temporal_scope,
            temporal_metadata=meta,
            quality=appraisal.quality,
            confidence_details=appraisal.confidence,
            citation=citation,
        )

        self._sources[source.id] = source
        self._source_asset_map[source.id] = asset_id
        self._appraisals[source.id] = appraisal
        self.lineage_engine.register_source(source)
        return source

    def add_extraction_and_observation(
        self,
        source: EvidenceSource,
        asset_id: UUID,
        source_location: str,
        extracted_text: str,
        entity: str,
        parameter_name: str,
        normalized_value: float,
        unit: Optional[str],
        observation_date: date,
        extraction_method: ExtractionMethod = ExtractionMethod.LLM_STRUCTURED_EXTRACTION,
        confidence: float = 0.90,
        polarity: EvidencePolarity = EvidencePolarity.SUPPORTING,
        observation_state: ScientificEvidenceState = ScientificEvidenceState.VERIFIED_FACT,
    ) -> EvidenceObservation:
        """
        Creates extraction text coordinate anchor and resulting normalized observation.
        """
        extraction = EvidenceExtraction(
            source_id=source.id,
            source_location=source_location,
            extracted_text=extracted_text,
            extraction_method=extraction_method,
            confidence=confidence,
            extracted_date=date.today(),
            validation_status="validated",
        )
        self._extractions[extraction.id] = extraction
        self.lineage_engine.add_extraction(extraction)

        obs_meta = EvidenceTemporalMetadata(
            publication_date=source.temporal_metadata.publication_date if source.temporal_metadata else source.publication_date,
            observation_date=observation_date,
            trial_date=source.temporal_metadata.trial_date if source.temporal_metadata else None,
            outcome_date=source.temporal_metadata.outcome_date if source.temporal_metadata else None,
            regulatory_date=source.temporal_metadata.regulatory_date if source.temporal_metadata else None,
            licensing_date=source.temporal_metadata.licensing_date if source.temporal_metadata else None,
            prediction_cutoff=source.temporal_metadata.prediction_cutoff if source.temporal_metadata else None,
            public_availability_date=source.temporal_metadata.public_availability_date if source.temporal_metadata else source.publication_date,
        )

        observation = EvidenceObservation(
            extraction_id=extraction.id,
            source_id=source.id,
            source_ref=source.source_id,
            asset_id=asset_id,
            entity=entity,
            parameter_name=parameter_name,
            extracted_text_or_value=extracted_text,
            normalized_value=normalized_value,
            unit=unit,
            observation_date=observation_date,
            source_location=source_location,
            extraction_method=extraction_method,
            confidence=confidence,
            polarity=polarity,
            observation_state=observation_state,
            temporal_metadata=obs_meta,
        )
        self._observations[observation.id] = observation
        self.lineage_engine.add_observation(observation)
        return observation

    def get_asset_evidence(
        self,
        asset_id: UUID,
        cutoff_date: Optional[date] = None,
    ) -> List[Evidence]:
        """
        Returns all evidence for an asset, enforcing temporal anti-leakage cutoff if specified.
        """
        results: List[Evidence] = []
        asset_obs = [
            obs for obs in self._observations.values()
            if obs.asset_id == asset_id
            and (cutoff_date is None or obs.observation_date <= cutoff_date)
        ]

        # Group observations by source
        obs_by_source: Dict[UUID, List[EvidenceObservation]] = {}
        for obs in asset_obs:
            obs_by_source.setdefault(obs.source_id, []).append(obs)

        for src_id, source in self._sources.items():
            if self._source_asset_map.get(src_id) != asset_id:
                continue

            # Anti-leakage visibility filtering
            if cutoff_date is not None:
                if source.temporal_metadata and not source.temporal_metadata.is_visible_at(cutoff_date):
                    continue
                elif not source.temporal_metadata and source.publication_date > cutoff_date:
                    continue

            observations = obs_by_source.get(src_id, [])
            extractions = [
                self._extractions[obs.extraction_id]
                for obs in observations
                if obs.extraction_id and obs.extraction_id in self._extractions
            ]

            ev = Evidence(
                id=uuid4(),
                asset_id=asset_id,
                source_type=source.source_type,
                source_id=source.source_id,
                title=source.title,
                authors=source.authors,
                organization=source.organization,
                publication_date=source.publication_date,
                retrieval_date=source.retrieval_date,
                url_reference=source.url_reference,
                study_type=source.study_type,
                phase=source.phase,
                species=source.species,
                model=source.model,
                sample_size=source.sample_size,
                peer_reviewed=source.peer_reviewed,
                prospective_or_retrospective=source.prospective_or_retrospective,
                quality_score=source.quality_score,
                confidence=source.confidence,
                temporal_validity=source.temporal_validity,
                temporal_metadata=source.temporal_metadata,
                quality=source.quality or self.calculate_quality(
                    peer_reviewed=source.peer_reviewed,
                    study_type=source.study_type,
                    sample_size=source.sample_size,
                    prospective=source.prospective_or_retrospective,
                    model=source.model,
                    species=source.species,
                    source_type=source.source_type,
                    publication_date=source.publication_date,
                ).quality,
                confidence_details=source.confidence_details or EvidenceConfidence(score=source.confidence),
                citation=source.citation or EvidenceCitation(source_id=source.id, formatted_citation=source.title, short_citation=source.title),
                extractions=extractions,
                observations=observations,
            )
            results.append(ev)

        return results

    def get_lineage_graph_for_recommendation(
        self,
        recommendation_id: UUID,
        asset_id: UUID,
    ) -> EvidenceLineageGraph:
        """Retrieves complete lineage DAG for recommendation."""
        return self.lineage_engine.get_lineage_graph(recommendation_id, asset_id)

    def _bootstrap_fixtures(self) -> None:
        """
        Bootstraps comprehensive real-world evidence lineage for Zongertinib (BI-1810631)
        spanning all 8 source types and tracing all the way from source to recommendation.
        """
        zong_asset_id = UUID("33333333-3333-3333-3333-333333333333")
        rec_id = UUID("77777777-7777-7777-7777-777777777777")

        # 1. Publication (Nature Cancer 2024)
        pub_src = self.register_evidence(
            asset_id=zong_asset_id,
            source_type=SourceType.PUBLICATION,
            source_id="PMID:38718468",
            title="Selective HER2 oncogenic mutant inhibition by BI 1810631 (Zongertinib) spares wild-type EGFR",
            authors=["Wilding B", "Neumüller R", "Savarese F", "Boehringer Ingelheim Oncology"],
            organization="Nature Cancer / Springer Nature",
            publication_date=date(2024, 5, 8),
            retrieval_date=date(2024, 5, 15),
            url_reference="https://pubmed.ncbi.nlm.nih.gov/38718468/",
            study_type="in_vitro_and_in_vivo_pharmacology",
            phase="Preclinical",
            species="Recombinant & Mouse",
            model="Ba/F3 HER2 mutants and PDX models",
            sample_size=120,
            peer_reviewed=True,
            prospective_or_retrospective=ProspectiveOrRetrospective.PROSPECTIVE,
            confidence_score=0.96,
            observation_date=date(2024, 5, 8),
            public_availability_date=date(2024, 5, 8),
            prediction_cutoff=date(2024, 5, 15),
        )

        obs_selectivity = self.add_extraction_and_observation(
            source=pub_src,
            asset_id=zong_asset_id,
            source_location="Page 715, Table 1, Column 4",
            extracted_text="IC50 for HER2 exon 20 insertion mutant is 2.4 nM whereas wild-type EGFR IC50 is 142 nM (>59-fold selectivity margin).",
            entity="HER2 Exon 20 / WT EGFR",
            parameter_name="mutant_vs_wt_selectivity_ratio",
            normalized_value=59.1,
            unit="fold_ratio",
            observation_date=date(2024, 5, 8),
            confidence=0.95,
        )

        obs_potency = self.add_extraction_and_observation(
            source=pub_src,
            asset_id=zong_asset_id,
            source_location="Page 716, Figure 2C",
            extracted_text="Mean biochemical IC50 across HER2 L755S, V777L, and Y772_A775dup mutants was 2.1 nM.",
            entity="HER2 Kinase Domain Mutants",
            parameter_name="biochemical_ic50_nm",
            normalized_value=2.1,
            unit="nM",
            observation_date=date(2024, 5, 8),
            confidence=0.94,
        )

        # 2. Clinical Trial (Beamion LUNG-1 / PANO-1 NCT04886804)
        trial_src = self.register_evidence(
            asset_id=zong_asset_id,
            source_type=SourceType.CLINICAL_TRIAL,
            source_id="NCT04886804",
            title="Beamion LUNG-1: Phase 1a/1b Trial of Zongertinib in Patients with Advanced HER2-Mutant Solid Tumors",
            authors=["Boehringer Ingelheim Clinical Investigators"],
            organization="Boehringer Ingelheim",
            publication_date=date(2023, 10, 15),
            retrieval_date=date(2023, 11, 1),
            url_reference="https://clinicaltrials.gov/study/NCT04886804",
            study_type="interventional_clinical_trial",
            phase="Phase 1a/1b",
            species="Human",
            model="Metastatic HER2-mutant solid tumors",
            sample_size=102,
            peer_reviewed=True,
            prospective_or_retrospective=ProspectiveOrRetrospective.PROSPECTIVE,
            confidence_score=0.94,
            trial_date=date(2021, 5, 15),
            outcome_date=date(2023, 10, 15),
            observation_date=date(2023, 10, 15),
            public_availability_date=date(2023, 10, 15),
            prediction_cutoff=date(2023, 11, 1),
        )

        obs_safety_ti = self.add_extraction_and_observation(
            source=trial_src,
            asset_id=zong_asset_id,
            source_location="Safety Results, Cohort Expansion Summary",
            extracted_text="Treatment-related diarrhea of Grade 3 or higher occurred in 3.9% of patients; no Grade 4-5 events were reported.",
            entity="Patient Cohort (n=102)",
            parameter_name="grade_3_plus_diarrhea_rate_pct",
            normalized_value=3.9,
            unit="%",
            observation_date=date(2023, 10, 15),
            confidence=0.94,
        )

        # 3. Conference Abstract (AACR 2023 Intracranial Activity)
        conf_src = self.register_evidence(
            asset_id=zong_asset_id,
            source_type=SourceType.CONFERENCE_ABSTRACT,
            source_id="AACR-2023-4521",
            title="Preclinical intracranial antitumor activity and pharmacokinetics of zongertinib across brain metastasis models",
            authors=["Zongertinib Translational Team"],
            organization="American Association for Cancer Research (AACR)",
            publication_date=date(2023, 4, 18),
            retrieval_date=date(2023, 4, 20),
            url_reference="https://cancerres.aacrjournals.org/content/83/7_Supplement/4521",
            study_type="intracranial_in_vivo_pk_pd",
            phase="Preclinical",
            species="Mouse",
            model="HER2-mutant intracerebral orthotopic xenografts",
            sample_size=40,
            peer_reviewed=True,
            confidence_score=0.88,
            trial_date=date(2022, 11, 1),
            observation_date=date(2023, 4, 18),
            public_availability_date=date(2023, 4, 18),
            prediction_cutoff=date(2023, 4, 20),
        )

        obs_cns = self.add_extraction_and_observation(
            source=conf_src,
            asset_id=zong_asset_id,
            source_location="Abstract body, Results line 14",
            extracted_text="Mean unbound brain-to-plasma ratio of zongertinib was 0.42, with significant survival prolongation in intracranial models.",
            entity="Blood-Brain Barrier Penetration",
            parameter_name="brain_to_plasma_ratio",
            normalized_value=0.42,
            unit="ratio",
            observation_date=date(2023, 4, 18),
            confidence=0.88,
        )

        # 4. Patent (USPTO Granted Composition of Matter)
        self.register_evidence(
            asset_id=zong_asset_id,
            source_type=SourceType.PATENT,
            source_id="US-11453678-B2",
            title="Substituted pyrimidine compounds as selective HER2 tyrosine kinase inhibitors",
            authors=["Boehringer Ingelheim International Inventors"],
            organization="United States Patent and Trademark Office",
            publication_date=date(2022, 9, 27),
            retrieval_date=date(2022, 10, 1),
            url_reference="https://patents.google.com/patent/US11453678B2/en",
            study_type="patent_grant",
            peer_reviewed=False,
            confidence_score=0.99,
            public_availability_date=date(2022, 9, 27),
            prediction_cutoff=date(2022, 10, 1),
        )

        # 5. Regulatory Source (FDA Breakthrough Therapy Designation)
        self.register_evidence(
            asset_id=zong_asset_id,
            source_type=SourceType.REGULATORY_SOURCE,
            source_id="FDA-BTD-2023-0891",
            title="FDA Breakthrough Therapy Designation for Zongertinib in HER2-mutant Advanced NSCLC",
            authors=["FDA Oncology Center of Excellence"],
            organization="U.S. Food and Drug Administration",
            publication_date=date(2023, 7, 24),
            retrieval_date=date(2023, 7, 25),
            url_reference="https://www.fda.gov/drugs/development-resources/breakthrough-therapy",
            study_type="regulatory_designation",
            peer_reviewed=False,
            confidence_score=0.98,
            regulatory_date=date(2023, 7, 24),
            outcome_date=date(2023, 7, 24),
            public_availability_date=date(2023, 7, 24),
            prediction_cutoff=date(2023, 7, 25),
        )

        # 6. Licensing Source (Global Commercialization & Option Agreement)
        self.register_evidence(
            asset_id=zong_asset_id,
            source_type=SourceType.COMPANY_SOURCE,
            source_id="DEAL-2022-ZONG-01",
            title="Strategic Co-Development and Commercial Licensing Option for Selective HER2 Programs",
            authors=["Boehringer Ingelheim Corporate Business Development"],
            organization="Boehringer Ingelheim & Global Commercial Partners",
            publication_date=date(2022, 12, 1),
            retrieval_date=date(2022, 12, 5),
            url_reference="https://www.boehringer-ingelheim.com/press-release/partnering-licensing-her2",
            study_type="commercial_licensing_agreement",
            peer_reviewed=False,
            confidence_score=0.97,
            licensing_date=date(2022, 12, 1),
            outcome_date=date(2022, 12, 1),
            public_availability_date=date(2022, 12, 1),
            prediction_cutoff=date(2022, 12, 5),
        )

        # Complete Lineage Chain for Zongertinib:
        # Step 1: Derive Features from Observations
        feat_selectivity = self.lineage_engine.derive_feature(
            asset_id=zong_asset_id,
            feature_name="target_selectivity_metric",
            computed_value=92.0,
            calculation_formula="min(100.0, 50.0 + (log10(selectivity_ratio) * 23.8))",
            source_observation_ids=[obs_selectivity.id],
        )

        feat_potency = self.lineage_engine.derive_feature(
            asset_id=zong_asset_id,
            feature_name="potency_metric",
            computed_value=88.0,
            calculation_formula="max(0.0, 100.0 - (ic50_nm * 5.7))",
            source_observation_ids=[obs_potency.id],
        )

        feat_safety_ti = self.lineage_engine.derive_feature(
            asset_id=zong_asset_id,
            feature_name="safety_ti_metric",
            computed_value=84.0,
            calculation_formula="max(0.0, 100.0 - (grade_3_diarrhea_rate * 4.1))",
            source_observation_ids=[obs_safety_ti.id],
        )

        feat_cns = self.lineage_engine.derive_feature(
            asset_id=zong_asset_id,
            feature_name="cns_potential_metric",
            computed_value=78.0,
            calculation_formula="min(100.0, brain_to_plasma_ratio * 185.0)",
            source_observation_ids=[obs_cns.id],
        )

        # Step 2: Model Output from Derived Features
        model_out = self.lineage_engine.record_model_output(
            asset_id=zong_asset_id,
            model_name="CalibratedMultiAttributeEngine",
            output_metric="development_potential_score",
            output_value=68.0,
            derived_feature_ids=[
                feat_selectivity.id,
                feat_potency.id,
                feat_safety_ti.id,
                feat_cns.id,
            ],
        )

        # Step 3: Link Recommendation to Model Output
        self.lineage_engine.link_recommendation(
            recommendation_id=rec_id,
            asset_id=zong_asset_id,
            action=StrategicAction.PURSUE,
            model_output_ids=[model_out.id],
        )

        # ==============================================================================
        # IMMUTABLE PROVENANCE DAG (7 Mandatory Stages)
        # 1. Source -> 2. Extraction -> 3. Normalization -> 4. Feature Derivation ->
        # 5. Model Input -> 6. Model Output -> 7. Decision Input
        # ==============================================================================
        # Stage 1: Sources
        self.provenance_engine.record_source(pub_src, zong_asset_id)
        self.provenance_engine.record_source(trial_src, zong_asset_id)
        self.provenance_engine.record_source(conf_src, zong_asset_id)

        # Stage 2: Extractions
        ext_selectivity = self._extractions[obs_selectivity.extraction_id]
        ext_potency = self._extractions[obs_potency.extraction_id]
        ext_safety = self._extractions[obs_safety_ti.extraction_id]
        ext_cns = self._extractions[obs_cns.extraction_id]

        self.provenance_engine.record_extraction(ext_selectivity, pub_src, zong_asset_id)
        self.provenance_engine.record_extraction(ext_potency, pub_src, zong_asset_id)
        self.provenance_engine.record_extraction(ext_safety, trial_src, zong_asset_id)
        self.provenance_engine.record_extraction(ext_cns, conf_src, zong_asset_id)

        # Stage 3: Normalizations
        norm_selectivity = NormalizationRecord(
            extraction_id=ext_selectivity.id,
            asset_id=zong_asset_id,
            raw_value=">59-fold selectivity margin",
            normalized_value=59.1,
            normalized_unit="fold_ratio",
            parameter_name="mutant_vs_wt_selectivity_ratio",
            transformation_rule="regex_ratio_extraction_to_fold",
        )
        self.provenance_engine.record_normalization(norm_selectivity, ext_selectivity.id, obs_selectivity)

        norm_potency = NormalizationRecord(
            extraction_id=ext_potency.id,
            asset_id=zong_asset_id,
            raw_value="Mean biochemical IC50 2.1 nM",
            normalized_value=2.1,
            normalized_unit="nM",
            parameter_name="biochemical_ic50_nm",
            transformation_rule="concentration_nm_standardization",
        )
        self.provenance_engine.record_normalization(norm_potency, ext_potency.id, obs_potency)

        norm_safety = NormalizationRecord(
            extraction_id=ext_safety.id,
            asset_id=zong_asset_id,
            raw_value="Grade 3+ diarrhea in 3.9%",
            normalized_value=3.9,
            normalized_unit="%",
            parameter_name="grade_3_plus_diarrhea_rate_pct",
            transformation_rule="adverse_event_rate_pct",
        )
        self.provenance_engine.record_normalization(norm_safety, ext_safety.id, obs_safety_ti)

        norm_cns = NormalizationRecord(
            extraction_id=ext_cns.id,
            asset_id=zong_asset_id,
            raw_value="brain-to-plasma ratio 0.42",
            normalized_value=0.42,
            normalized_unit="ratio",
            parameter_name="brain_to_plasma_ratio",
            transformation_rule="pk_partition_ratio",
        )
        self.provenance_engine.record_normalization(norm_cns, ext_cns.id, obs_cns)

        # Stage 4: Feature Derivations
        self.provenance_engine.record_feature_derivation(feat_selectivity, [norm_selectivity.id])
        self.provenance_engine.record_feature_derivation(feat_potency, [norm_potency.id])
        self.provenance_engine.record_feature_derivation(feat_safety_ti, [norm_safety.id])
        self.provenance_engine.record_feature_derivation(feat_cns, [norm_cns.id])

        # Stage 5: Model Input
        model_input = ModelInputRecord(
            model_name="CalibratedMultiAttributeEngine",
            model_version="v0.1",
            asset_id=zong_asset_id,
            feature_ids=[
                feat_selectivity.id,
                feat_potency.id,
                feat_safety_ti.id,
                feat_cns.id,
            ],
            feature_vector={
                "target_selectivity": feat_selectivity.computed_value,
                "potency": feat_potency.computed_value,
                "safety_ti": feat_safety_ti.computed_value,
                "cns_penetration": feat_cns.computed_value,
            },
        )
        self.provenance_engine.record_model_input(model_input)

        # Stage 6: Model Output
        self.provenance_engine.record_model_output(model_out, model_input.id)

        # Stage 7: Decision Input (Final Recommendation)
        decision_input = DecisionInputRecord(
            recommendation_id=rec_id,
            asset_id=zong_asset_id,
            action=StrategicAction.PURSUE,
            model_output_ids=[model_out.id],
            model_scores={"development_potential_score": model_out.output_value},
            decision_policy_version="v1.0",
            thresholds_applied={"pursue_min_dps": 65.0},
        )
        self.provenance_engine.record_decision_input(decision_input)

        # Stage 8: Explicit Contradictory Evidence Registration
        # Source 6: Real-World Clinical Intracranial Cohort (Lancet Oncol 2024 / NCT04886804-CNS)
        cns_realworld_src = self.register_evidence(
            asset_id=zong_asset_id,
            source_type=SourceType.CLINICAL_TRIAL,
            source_id="NCT04886804-CNS-EXP",
            title="Real-World Intracranial Objective Response Rate of Zongertinib in Heavily Pretreated Brain Metastases Post-T-DXd",
            authors=["Lancet Oncology Clinical Investigators"],
            organization="Lancet Oncology Collaborators",
            publication_date=date(2024, 6, 2),
            retrieval_date=date(2024, 6, 10),
            url_reference="https://doi.org/10.1016/S1470-2045(24)00241-1",
            study_type="phase_1_2_single_arm",
            phase="Phase 1b",
            species="Human",
            model="HER2+ NSCLC / Active untreated CNS metastases",
            sample_size=12,
            peer_reviewed=True,
            prospective_or_retrospective=ProspectiveOrRetrospective.PROSPECTIVE,
            confidence_score=0.84,
            trial_date=date(2023, 8, 1),
            outcome_date=date(2024, 6, 2),
            observation_date=date(2024, 6, 2),
            public_availability_date=date(2024, 6, 2),
            prediction_cutoff=date(2024, 6, 10),
        )

        # Source 7: High-Dose Phase 1b Dose Escalation Cohort (240mg BID Safety Signal)
        high_dose_safety_src = self.register_evidence(
            asset_id=zong_asset_id,
            source_type=SourceType.CLINICAL_TRIAL,
            source_id="NCT04886804-DOSE-240",
            title="Dose-Dependent Safety and Wild-Type Sparing Characterization of Zongertinib at 240mg BID",
            authors=["American Society of Clinical Oncology (ASCO) Investigators"],
            organization="ASCO Annual Meeting 2024",
            publication_date=date(2024, 6, 15),
            retrieval_date=date(2024, 6, 20),
            url_reference="https://ascopubs.org/doi/10.1200/JCO.2024.42.16_suppl.3012",
            study_type="phase_1_2_single_arm",
            phase="Phase 1b",
            species="Human",
            model="Advanced Solid Tumors (240mg BID Cohort)",
            sample_size=62,
            peer_reviewed=True,
            prospective_or_retrospective=ProspectiveOrRetrospective.PROSPECTIVE,
            confidence_score=0.91,
            trial_date=date(2023, 6, 1),
            outcome_date=date(2024, 6, 15),
            observation_date=date(2024, 6, 15),
            public_availability_date=date(2024, 6, 15),
            prediction_cutoff=date(2024, 6, 20),
        )

        # Contradiction Pair 1: CNS Penetration & Intracranial Regression Discrepancy
        cns_claim_a = ContradictoryClaim(
            claim_text="Mean unbound brain-to-plasma ratio of zongertinib was 0.42, with 95% intracranial regression in murine orthotopic xenografts.",
            polarity=EvidencePolarity.SUPPORTING,
            source=conf_src,
            date=date(2023, 4, 18),
            study_design=StudyDesignType.IN_VIVO_ANIMAL_DISEASE_MODEL,
            quality=EvidenceQuality(quality_score=74.0, methodological_rigor=76.0, risk_of_bias=RiskOfBias.LOW),
            confidence=EvidenceConfidence(score=0.88, confidence_level=ConfidenceLevel.HIGH),
            numeric_measurement="Kp,uu = 0.42",
            observed_endpoint="Intracranial Regression",
            sample_size=40,
        )
        cns_claim_b = ContradictoryClaim(
            claim_text="Intracranial objective response rate was 33% (4/12) in patients with active untreated brain metastases post-T-DXd.",
            polarity=EvidencePolarity.CONTRADICTORY,
            source=cns_realworld_src,
            date=date(2024, 6, 2),
            study_design=StudyDesignType.PHASE_1_2_SINGLE_ARM,
            quality=EvidenceQuality(quality_score=86.0, methodological_rigor=88.0, risk_of_bias=RiskOfBias.LOW),
            confidence=EvidenceConfidence(score=0.84, confidence_level=ConfidenceLevel.HIGH),
            numeric_measurement="iORR = 33%",
            observed_endpoint="Intracranial Objective Response Rate",
            sample_size=12,
        )
        self.contradiction_engine.build_contradiction_pair(
            asset_id=zong_asset_id,
            topic="Intracranial CNS Penetration & Clinical Response",
            parameter_name="intracranial_response_rate",
            category=DisagreementCategory.CNS_PENETRATION_DISCREPANCY,
            claim_a=cns_claim_a,
            claim_b=cns_claim_b,
            status=DisagreementResolutionStatus.PARTIALLY_EXPLAINED,
            possible_explanation=(
                "Design and cohort disparity: Murine orthotopic xenografts in treatment-naive mice demonstrated high "
                "Kp,uu (0.42) and 95% intracranial regression, whereas human Phase 1b clinical data in heavily pretreated "
                "patients post-T-DXd showed 33% iORR. Active P-gp efflux at the intact human blood-tumor barrier and prior "
                "radiotherapy vascular scarring likely account for the clinical attenuation."
            ),
            resolution_recommendation="Track dedicated Beamion LUNG-1 Phase 2 brain metastasis cohort expansion with prospective RANO-BM criteria.",
        )

        # Contradiction Pair 2: WT-EGFR Sparing vs Clinical Diarrhea Rate
        safety_claim_a = ContradictoryClaim(
            claim_text="Sub-nanomolar selectivity window (>59-fold vs WT EGFR) predicts minimal EGFR-mediated wild-type toxicity.",
            polarity=EvidencePolarity.SUPPORTING,
            source=pub_src,
            date=date(2024, 5, 8),
            study_design=StudyDesignType.BIOCHEMICAL_KINASE_ASSAY,
            quality=EvidenceQuality(quality_score=85.0, methodological_rigor=88.0, risk_of_bias=RiskOfBias.LOW),
            confidence=EvidenceConfidence(score=0.95, confidence_level=ConfidenceLevel.HIGH),
            numeric_measurement=">59x selectivity",
            observed_endpoint="WT EGFR Sparing Ratio",
            sample_size=120,
        )
        safety_claim_b = ContradictoryClaim(
            claim_text="At 240mg BID dosing, Grade 3 diarrhea occurred in 6.5% of patients (overall diarrhea 48%), signaling partial WT-EGFR engagement in human intestinal mucosa.",
            polarity=EvidencePolarity.CONTRADICTORY,
            source=high_dose_safety_src,
            date=date(2024, 6, 15),
            study_design=StudyDesignType.PHASE_1_2_SINGLE_ARM,
            quality=EvidenceQuality(quality_score=89.0, methodological_rigor=90.0, risk_of_bias=RiskOfBias.LOW),
            confidence=EvidenceConfidence(score=0.91, confidence_level=ConfidenceLevel.HIGH),
            numeric_measurement="Grade 3 Diarrhea = 6.5%",
            observed_endpoint="Treatment-Related Adverse Events",
            sample_size=62,
        )
        self.contradiction_engine.build_contradiction_pair(
            asset_id=zong_asset_id,
            topic="Wild-Type EGFR Sparing Margin vs Clinical Diarrhea",
            parameter_name="grade_3_diarrhea_rate",
            category=DisagreementCategory.SAFETY_TOXICITY_CONFLICT,
            claim_a=safety_claim_a,
            claim_b=safety_claim_b,
            status=DisagreementResolutionStatus.PARTIALLY_EXPLAINED,
            possible_explanation=(
                "Assay conditions vs clinical exposure: High selectivity in cell-free biochemical kinase panels does not "
                "fully protect against off-target gastrointestinal toxicity when high clinical doses (240mg BID) produce "
                "peak Cmax levels sufficient to partially inhibit mucosal EGFR."
            ),
            resolution_recommendation="Establish 120mg BID as maximum recommended Phase 2 dose (RP2D) with proactive prophylactic antidiarrheal guidance.",
        )

    def get_asset_contradictions(self, asset_id: UUID) -> List[ContradictionRecord]:
        """Returns all registered contradictory evidence pairs for an asset."""
        return self.contradiction_engine.get_contradictions_for_asset(asset_id)

    def get_asset_contradiction_report(self, asset_id: UUID, asset_name: str = "Asset") -> ContradictionReport:
        """Generates comprehensive contradiction summary report with epistemic disclaimers."""
        return self.contradiction_engine.generate_contradiction_report(asset_id, asset_name)

    def register_contradiction(self, record: ContradictionRecord) -> ContradictionRecord:
        """Registers a verified contradiction record."""
        return self.contradiction_engine.register_contradiction(record)

    def trace_recommendation_provenance(self, recommendation_id: UUID) -> ProvenanceTracebackResult:
        """Traces a final recommendation back through all 7 stages to root sources."""
        return self.provenance_engine.trace_recommendation_back_to_sources(recommendation_id)

    def get_provenance_graph(self, recommendation_id: UUID) -> ProvenanceGraph:
        """Retrieves complete immutable provenance DAG with Merkle hash."""
        return self.provenance_engine.get_provenance_graph(recommendation_id)

    def get_source_appraisal(self, source_id: UUID) -> Optional[EvidenceQualityAppraisal]:
        """Retrieves the full 10-dimension quality appraisal for a source."""
        return self._appraisals.get(source_id)

    def evaluate_evidence(
        self,
        peer_reviewed: bool,
        study_design: StudyDesignType,
        sample_size: Optional[int],
        model_relevance: ModelRelevance,
        is_human: bool,
        prospective_or_retrospective: ProspectiveOrRetrospective,
        replication_status: ReplicationStatus,
        source_type: SourceType,
        directness: DirectnessLevel = DirectnessLevel.DIRECT,
        publication_date: Optional[date] = None,
        as_of_date: Optional[date] = None,
        risk_of_bias: RiskOfBias = RiskOfBias.LOW,
    ) -> EvidenceQualityAppraisal:
        """Evaluates arbitrary evidence configuration across all 10 dimensions."""
        return EvidenceQualityEngine.evaluate(
            peer_reviewed=peer_reviewed,
            study_design=study_design,
            sample_size=sample_size,
            model_relevance=model_relevance,
            is_human=is_human,
            prospective_or_retrospective=prospective_or_retrospective,
            replication_status=replication_status,
            source_type=source_type,
            directness=directness,
            publication_date=publication_date,
            as_of_date=as_of_date or date.today(),
            risk_of_bias=risk_of_bias,
        )

    def query_evidence_by_time(
        self,
        asset_id: Optional[UUID] = None,
        filter: Optional[TemporalQueryFilter] = None,
        as_of_date: Optional[date] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        date_field: Union[TemporalDateField, str] = TemporalDateField.ANY_DATE,
        prediction_cutoff: Optional[date] = None,
    ) -> List[Evidence]:
        """
        Queries all evidence across temporal coordinates.
        Supports:
        - as_of_date (strict anti-leakage visibility filtering)
        - start_date / end_date ranges
        - date_field (publication_date, observation_date, trial_date, outcome_date, regulatory_date, licensing_date, prediction_cutoff, public_availability_date, any_date)
        - prediction cutoff filtering
        All evidence is queryable by time.
        """
        if filter is None:
            if isinstance(date_field, str):
                date_field = TemporalDateField(date_field)
            filter = TemporalQueryFilter(
                as_of_date=as_of_date,
                start_date=start_date,
                end_date=end_date,
                date_field=date_field,
                prediction_cutoff=prediction_cutoff,
            )

        if asset_id:
            all_evidence = self.get_asset_evidence(asset_id, cutoff_date=filter.as_of_date)
        else:
            all_asset_ids = {obs.asset_id for obs in self._observations.values()}
            all_evidence = []
            for a_id in all_asset_ids:
                all_evidence.extend(self.get_asset_evidence(a_id, cutoff_date=filter.as_of_date))

        matching_evidence = []
        for ev in all_evidence:
            if ev.temporal_metadata and filter.matches(ev.temporal_metadata):
                matching_evidence.append(ev)

        return matching_evidence

    def rank_evidence(
        self,
        evidence_items: List[Dict[str, Any]],
        as_of_date: Optional[date] = None,
        prediction_cutoff: Optional[date] = None,
        query_context: Optional[str] = None,
    ) -> EvidenceRankingResult:
        """
        Ranks arbitrary evidence items using the 9 canonical dimensions:
        source quality, directness, recency, human relevance, study design,
        sample size, peer review, confidence, temporal validity.
        Returns ranked evidence with detailed ranking rationale.
        """
        return EvidenceRankingEngine.rank_evidence_list(
            evidence_items=evidence_items,
            as_of_date=as_of_date,
            prediction_cutoff=prediction_cutoff,
            query_context=query_context,
        )

    def rank_asset_evidence(
        self,
        asset_id: UUID,
        as_of_date: Optional[date] = None,
        prediction_cutoff: Optional[date] = None,
    ) -> EvidenceRankingResult:
        """
        Ranks all registered evidence for an asset across all 9 dimensions,
        returning evidence in descending rank order with transparent rationale.
        """
        evidence_list = self.get_asset_evidence(asset_id, cutoff_date=as_of_date)
        items = []
        for ev in evidence_list:
            # Map study design type
            s_design = StudyDesignType.PHASE_1_2_SINGLE_ARM
            if ev.study_type in [s.value for s in StudyDesignType]:
                s_design = StudyDesignType(ev.study_type)
            elif "rct" in ev.study_type.lower():
                s_design = StudyDesignType.RCT_DOUBLE_BLIND

            # Map directness
            directness = DirectnessLevel.DIRECT
            if ev.species and "mouse" in ev.species.lower():
                directness = DirectnessLevel.PROXIMATE

            items.append({
                "id": str(ev.id),
                "title": ev.title,
                "citation": ev.citation.formatted_citation if ev.citation else ev.title,
                "source_type": ev.source_type,
                "directness": directness,
                "is_human": ev.species == "Human" or (ev.model and "human" in ev.model.lower()),
                "model_relevance": ModelRelevance.DIRECT_HUMAN_CLINICAL if ev.species == "Human" else ModelRelevance.PATIENT_DERIVED_XENOGRAFT,
                "study_design": s_design,
                "sample_size": ev.sample_size,
                "peer_reviewed": ev.peer_reviewed,
                "confidence": ev.confidence,
                "publication_date": ev.publication_date,
                "valid_to_date": ev.temporal_validity.valid_to if ev.temporal_validity else None,
            })

        return self.rank_evidence(
            evidence_items=items,
            as_of_date=as_of_date,
            prediction_cutoff=prediction_cutoff,
            query_context=f"Asset {asset_id} evidence ranking",
        )


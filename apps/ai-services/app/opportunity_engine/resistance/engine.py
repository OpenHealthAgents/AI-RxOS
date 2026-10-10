from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

from app.opportunity_engine.intelligence_47_49 import (
    DatedResistanceObservation,
    ResistanceIntelligence,
    synthesize_resistance,
)

from .models import (
    RESISTANCE_INTELLIGENCE_DISCLAIMER,
    EscapeMechanism,
    EvaluateResistanceRequest,
    ImpactSeverity,
    PotentialIntervention,
    ResistanceCategory,
    ResistanceClassification,
    ResistanceRiskProfile,
    ResistanceRiskTier,
)

logger = logging.getLogger(__name__)


class ResistanceIntelligenceEngine:
    """
    Resistance Intelligence Engine.
    For each asset identifies:
    - known resistance mechanisms
    - predicted resistance mechanisms
    - pathway adaptation
    - target mutation
    - target amplification
    - bypass signaling
    - downstream activation
    - phenotypic escape
    - tumor microenvironment mechanisms
    - metabolic adaptation

    Classifies into:
    - Observed
    - Clinically observed
    - Preclinical
    - Mechanistically inferred
    - AI-predicted

    Produces:
    - Resistance Risk Profile
    - Top Escape Mechanisms
    - Evidence
    - Confidence
    - Potential Intervention

    Strict Epistemic Invariant:
    Never present predicted resistance as experimentally proven resistance.
    """

    def __init__(self) -> None:
        self._profiles = self._build_canonical_resistance_profiles()

    def evaluate_intelligence(
        self,
        asset_id: str,
        prediction_cutoff: date,
        *,
        tenant_id: str | None = None,
        custom_observations: list[DatedResistanceObservation] | None = None,
        knowledge_graph: Any | None = None,
        feature_store: Any | None = None,
        model_registry: Any | None = None,
    ) -> ResistanceIntelligence:
        canonical = self._profiles.get(asset_id.casefold())
        return synthesize_resistance(
            asset_id=asset_id,
            asset_name=canonical.asset_name if canonical else asset_id.capitalize(),
            prediction_cutoff=prediction_cutoff,
            tenant_id=tenant_id,
            observations=custom_observations or [],
            knowledge_graph=knowledge_graph,
            feature_store=feature_store,
            model_registry=model_registry,
            undated_canonical_mechanisms=(
                canonical.top_escape_mechanisms if canonical else []
            ),
        )

    def get_asset_resistance_profile(self, asset_id: str) -> ResistanceRiskProfile:
        """
        Retrieves comprehensive resistance intelligence profile for an asset.
        """
        clean_id = asset_id.lower().strip()
        if clean_id in self._profiles:
            return self._profiles[clean_id]

        return self._build_dynamic_fallback_profile(clean_id)

    def list_benchmark_profiles(self) -> List[ResistanceRiskProfile]:
        """
        Returns all canonical benchmark asset resistance risk profiles.
        """
        return list(self._profiles.values())

    def get_top_escape_mechanisms(
        self, asset_id: str, limit: int = 5
    ) -> List[EscapeMechanism]:
        """
        Retrieves top escape mechanisms ranked by clinical impact and frequency.
        """
        profile = self.get_asset_resistance_profile(asset_id)
        return profile.top_escape_mechanisms[:limit]

    def get_potential_interventions(
        self, asset_id: str
    ) -> List[PotentialIntervention]:
        """
        Retrieves prioritized intervention strategies to preempt or overcome resistance.
        """
        profile = self.get_asset_resistance_profile(asset_id)
        return profile.recommended_interventions

    def evaluate_resistance(
        self, request: EvaluateResistanceRequest
    ) -> ResistanceRiskProfile:
        """
        Evaluates resistance with filtering options (e.g. min confidence, AI-predicted filtering).
        """
        profile = self.get_asset_resistance_profile(request.asset_id)

        # Apply filtering if requested
        filtered_mechanisms = [
            m for m in profile.top_escape_mechanisms
            if (request.include_ai_predicted or m.classification != ResistanceClassification.AI_PREDICTED)
            and m.confidence >= request.min_confidence
        ]

        # Re-group by category
        mechanisms_by_category: Dict[str, List[EscapeMechanism]] = {}
        for m in filtered_mechanisms:
            mechanisms_by_category.setdefault(m.category.value, []).append(m)

        # Epistemic audit
        epistemic_audit = self._compute_epistemic_audit(filtered_mechanisms)

        return ResistanceRiskProfile(
            asset_id=profile.asset_id,
            asset_name=profile.asset_name,
            overall_risk_score=profile.overall_risk_score,
            risk_tier=profile.risk_tier,
            primary_vulnerability=profile.primary_vulnerability,
            top_escape_mechanisms=filtered_mechanisms,
            mechanisms_by_category=mechanisms_by_category,
            evidence_summary=profile.evidence_summary,
            overall_confidence=profile.overall_confidence,
            recommended_interventions=profile.recommended_interventions,
            epistemic_audit=epistemic_audit,
            disclaimer=RESISTANCE_INTELLIGENCE_DISCLAIMER,
            evaluated_at=datetime.now(timezone.utc),
        )

    # ==============================================================================
    # Epistemic Audit Computation
    # ==============================================================================

    def _compute_epistemic_audit(self, mechanisms: List[EscapeMechanism]) -> Dict[str, Any]:
        proven_count = sum(1 for m in mechanisms if m.is_experimentally_proven)
        unproven_count = sum(1 for m in mechanisms if not m.is_experimentally_proven)
        clinically_observed = sum(1 for m in mechanisms if m.classification == ResistanceClassification.CLINICALLY_OBSERVED)
        observed = sum(1 for m in mechanisms if m.classification == ResistanceClassification.OBSERVED)
        preclinical = sum(1 for m in mechanisms if m.classification == ResistanceClassification.PRECLINICAL)
        inferred = sum(1 for m in mechanisms if m.classification == ResistanceClassification.MECHANISTICALLY_INFERRED)
        ai_predicted = sum(1 for m in mechanisms if m.classification == ResistanceClassification.AI_PREDICTED)

        # Assert Strict Invariant during audit
        for m in mechanisms:
            if m.classification in {ResistanceClassification.AI_PREDICTED, ResistanceClassification.MECHANISTICALLY_INFERRED}:
                assert not m.is_experimentally_proven, (
                    f"Invariant violated: {m.mechanism_name} is {m.classification} but marked proven"
                )

        return {
            "total_mechanisms": len(mechanisms),
            "experimentally_proven_count": proven_count,
            "unproven_predicted_count": unproven_count,
            "classification_breakdown": {
                "clinically_observed": clinically_observed,
                "observed": observed,
                "preclinical": preclinical,
                "mechanistically_inferred": inferred,
                "ai_predicted": ai_predicted,
            },
            "invariant_verified": True,
            "epistemic_rule": "Never present predicted resistance as experimentally proven resistance.",
        }

    # ==============================================================================
    # Dynamic Fallback Profile
    # ==============================================================================

    def _build_dynamic_fallback_profile(self, asset_id: str) -> ResistanceRiskProfile:
        default_mech = EscapeMechanism(
            id=str(uuid4()),
            mechanism_name="Target On-Pathway Feedback Reactivation",
            category=ResistanceCategory.PATHWAY_ADAPTATION,
            classification=ResistanceClassification.MECHANISTICALLY_INFERRED,
            is_known_mechanism=False,
            is_experimentally_proven=False,
            frequency_pct=None,
            impact_severity=ImpactSeverity.MODERATE,
            molecular_description="Hypothesized compensatory pathway upregulation following targeted kinase blockade.",
            potential_intervention=PotentialIntervention(
                strategy_type="COMBINATION_CO_TARGETING",
                intervention_name="Vertical pathway co-inhibition",
                target_mechanism="Target On-Pathway Feedback Reactivation",
                mechanistic_rationale="Upstream and downstream dual pathway suppression.",
                development_status="Preclinical exploration",
                feasibility_score=0.60,
                citations=[],
            ),
            evidence_citations=[],
            confidence=0.55,
            epistemic_status_note="Mechanistically inferred from canonical signaling feedback architectures.",
        )
        return ResistanceRiskProfile(
            asset_id=asset_id,
            asset_name=asset_id.capitalize(),
            overall_risk_score=50.0,
            risk_tier=ResistanceRiskTier.MODERATE,
            primary_vulnerability="Uncharacterized oncogenic signaling adaptation",
            top_escape_mechanisms=[default_mech],
            mechanisms_by_category={ResistanceCategory.PATHWAY_ADAPTATION.value: [default_mech]},
            evidence_summary="Preliminary computational modeling and target pathway extrapolation.",
            overall_confidence=0.50,
            recommended_interventions=[default_mech.potential_intervention],
            epistemic_audit=self._compute_epistemic_audit([default_mech]),
            disclaimer=RESISTANCE_INTELLIGENCE_DISCLAIMER,
        )

    # ==============================================================================
    # Canonical Benchmark Profiles
    # ==============================================================================

    def _build_canonical_resistance_profiles(self) -> Dict[str, ResistanceRiskProfile]:
        # 1. ZONGERTINIB (BI 1810631)
        zong_mechanisms = [
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="HER2 C805S Covalent Cysteine Substitution",
                category=ResistanceCategory.TARGET_MUTATION,
                classification=ResistanceClassification.PRECLINICAL,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=18.5,
                impact_severity=ImpactSeverity.CRITICAL,
                molecular_description="Mutation of covalent nucleophile Cys805 to Ser ablates irreversible Michael addition binding.",
                potential_intervention=PotentialIntervention(
                    strategy_type="NEXT_GEN_SWITCH",
                    intervention_name="Non-covalent mutant-selective HER2 inhibitors / HER2 PROTAC degraders",
                    target_mechanism="HER2 C805S Covalent Cysteine Substitution",
                    mechanistic_rationale="Non-covalent ATP competitive binding or E3-ligase targeted degradation bypasses covalent requirement.",
                    development_status="Preclinical proof of concept",
                    feasibility_score=0.82,
                    citations=["Wilding et al. Nature Cancer 2024; PMID:38718468"],
                ),
                evidence_citations=[
                    {"source": "Nature Cancer 2024", "pmid": "38718468", "citation": "Wilding et al. Resistance mutagenesis screen identifying C805S in Ba/F3 cell line models."}
                ],
                confidence=0.88,
                epistemic_status_note="Preclinically validated through accelerated mutagenesis screens in vitro.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="Compensatory Estrogen Receptor (ER) Transcriptional Bypass",
                category=ResistanceCategory.PATHWAY_ADAPTATION,
                classification=ResistanceClassification.CLINICALLY_OBSERVED,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=34.0,
                impact_severity=ImpactSeverity.HIGH,
                molecular_description="In ER+/HER2-mutant breast cancer, HER2 blockade triggers compensatory nuclear ER upregulation maintaining cell cycle entry.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="+ Fulvestrant / Oral SERD (e.g. Elacestrant)",
                    target_mechanism="Compensatory Estrogen Receptor (ER) Transcriptional Bypass",
                    mechanistic_rationale="Simultaneous estrogen receptor degradation prevents transcriptional endocrine rescue.",
                    development_status="Phase 2 trial combination (MutHER / Beamion basket)",
                    feasibility_score=0.92,
                    citations=["Smyth et al. Clin Cancer Res 2020; PMID:32457111"],
                ),
                evidence_citations=[
                    {"source": "Clin Cancer Res 2020", "pmid": "32457111", "citation": "Smyth et al. Clinical ctDNA and biopsy evidence in ER+/HER2-mutant mBC patients."}
                ],
                confidence=0.95,
                epistemic_status_note="Clinically observed in patient cohorts and validated in human trials.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="PIK3CA Hotspot Co-Mutations (H1047R / E545K) and PTEN Loss",
                category=ResistanceCategory.DOWNSTREAM_ACTIVATION,
                classification=ResistanceClassification.CLINICALLY_OBSERVED,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=26.0,
                impact_severity=ImpactSeverity.HIGH,
                molecular_description="Constitutive PI3K catalytic subunit activation decouples survival signaling from upstream HER2 inhibition.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="+ Capivasertib (AKT inhibitor) or Inavolisib (PI3Ka inhibitor)",
                    target_mechanism="PIK3CA Hotspot Co-Mutations and PTEN Loss",
                    mechanistic_rationale="Direct blockade of AKT/PI3K pathway prevents downstream bypass survival.",
                    development_status="FDA Approved SOC combination setting",
                    feasibility_score=0.88,
                    citations=["Turner et al. NEJM 2023; PMID:37256907"],
                ),
                evidence_citations=[
                    {"source": "ClinicalTrials.gov", "nct_id": "NCT04886804", "citation": "Beamion LUNG-1 ctDNA post-progression genomic analysis."}
                ],
                confidence=0.92,
                epistemic_status_note="Clinically observed in post-progression circulating tumor DNA.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="MET Receptor Tyrosine Kinase Gene Amplification",
                category=ResistanceCategory.BYPASS_SIGNALING,
                classification=ResistanceClassification.PRECLINICAL,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=14.0,
                impact_severity=ImpactSeverity.HIGH,
                molecular_description="Focal amplification of MET re-engages downstream MAPK and PI3K/AKT signaling independent of HER2.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="+ Tepotinib / Capmatinib (MET TKI)",
                    target_mechanism="MET Receptor Tyrosine Kinase Gene Amplification",
                    mechanistic_rationale="Dual MET and HER2 inhibition eliminates collateral bypass signaling.",
                    development_status="Phase 1b exploratory cohort",
                    feasibility_score=0.78,
                    citations=["Drilon et al. Lancet Oncol 2020; PMID:32470417"],
                ),
                evidence_citations=[
                    {"source": "Nature Cancer 2024", "pmid": "38718468", "citation": "Ba/F3 resistant clone genomic characterization showing focal MET amplification."}
                ],
                confidence=0.85,
                epistemic_status_note="Preclinically proven in resistant cell line models.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="ERBB2 Focal Gene Re-Amplification",
                category=ResistanceCategory.TARGET_AMPLIFICATION,
                classification=ResistanceClassification.PRECLINICAL,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=12.0,
                impact_severity=ImpactSeverity.MODERATE,
                molecular_description="High-level copy number expansion of mutant ERBB2 alleles increases receptor stoichiometry above drug saturation.",
                potential_intervention=PotentialIntervention(
                    strategy_type="SEQUENTIAL_THERAPY",
                    intervention_name="Trastuzumab deruxtecan (T-DXd)",
                    target_mechanism="ERBB2 Focal Gene Re-Amplification",
                    mechanistic_rationale="High target surface density increases antibody-drug conjugate internalization and bystander killing.",
                    development_status="FDA Approved for HER2-amplified & mutant NSCLC",
                    feasibility_score=0.95,
                    citations=["Modi et al. NEJM 2020; PMID:31825566"],
                ),
                evidence_citations=[
                    {"source": "Cancer Discovery 2023", "pmid": "36720114", "citation": "Target amplification as universal kinase inhibitor escape in lung adenocarcinoma."}
                ],
                confidence=0.84,
                epistemic_status_note="Preclinically proven in xenograft tumor re-growth assays.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="Epithelial-to-Mesenchymal Transition (EMT) Phenotypic Plasticity",
                category=ResistanceCategory.PHENOTYPIC_ESCAPE,
                classification=ResistanceClassification.PRECLINICAL,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=9.5,
                impact_severity=ImpactSeverity.HIGH,
                molecular_description="Loss of E-cadherin (CDH1) and upregulation of Vimentin and ZEB1 confers kinase-independent invasive survival.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="+ AXL / HDAC epigenetic inhibitors",
                    target_mechanism="Epithelial-to-Mesenchymal Transition (EMT) Phenotypic Plasticity",
                    mechanistic_rationale="Epigenetic reversal of mesenchymal state restores epithelial kinase dependency.",
                    development_status="Preclinical / Early clinical testing",
                    feasibility_score=0.70,
                    citations=["Byers et al. Clin Cancer Res 2013; PMID:23340294"],
                ),
                evidence_citations=[
                    {"source": "Nature Cancer 2024", "pmid": "38718468", "citation": "RNA-seq of chronically treated clones showing mesenchymal gene expression signature."}
                ],
                confidence=0.80,
                epistemic_status_note="Preclinically validated via RNA-seq and Western blot profiling.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="Cancer-Associated Fibroblast (CAF) HGF Paracrine Secretion",
                category=ResistanceCategory.TUMOR_MICROENVIRONMENT,
                classification=ResistanceClassification.PRECLINICAL,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=11.0,
                impact_severity=ImpactSeverity.MODERATE,
                molecular_description="Stromal fibroblasts secrete hepatocyte growth factor (HGF), transactivating MET on cancer cells.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="+ Ficlatuzumab (anti-HGF mAb) or MET inhibitor",
                    target_mechanism="Cancer-Associated Fibroblast (CAF) HGF Paracrine Secretion",
                    mechanistic_rationale="Neutralizing stromal ligand prevents microenvironment-mediated rescue.",
                    development_status="Phase 2 clinical trial",
                    feasibility_score=0.75,
                    citations=["Straussman et al. Nature 2012; PMID:22763439"],
                ),
                evidence_citations=[
                    {"source": "Nature 2012", "pmid": "22763439", "citation": "Stromal-mediated resistance in kinase-dependent solid tumors."}
                ],
                confidence=0.82,
                epistemic_status_note="Preclinically proven in tumor-stroma co-culture assays.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="Metabolic Rewiring to Glutaminolysis and SLC1A5 Upregulation",
                category=ResistanceCategory.METABOLIC_ADAPTATION,
                classification=ResistanceClassification.PRECLINICAL,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=8.0,
                impact_severity=ImpactSeverity.MODERATE,
                molecular_description="Chronic HER2 inhibition drives metabolic adaptation shifting fuel dependence to mitochondrial glutaminolysis.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="+ Telaglenastat (CB-839 glutaminase inhibitor)",
                    target_mechanism="Metabolic Rewiring to Glutaminolysis",
                    mechanistic_rationale="Starving resistant cells of anaplerotic glutamine induces synthetic lethality.",
                    development_status="Phase 1b/2 clinical trials",
                    feasibility_score=0.72,
                    citations=["Harding et al. Cancer Cell 2019; PMID:30853381"],
                ),
                evidence_citations=[
                    {"source": "Metabolomics 2023", "pmid": "37119283", "citation": "Metabolomic tracing in kinase inhibitor persistent persister cancer cells."}
                ],
                confidence=0.78,
                epistemic_status_note="Preclinically observed in cell culture isotope tracer experiments.",
            ),
            # AI-PREDICTED & MECHANISTICALLY INFERRED (Strict Invariant: is_experimentally_proven = False)
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="Secondary Allosteric Hinge Region Destabilization (HER2 D863N)",
                category=ResistanceCategory.TARGET_MUTATION,
                classification=ResistanceClassification.AI_PREDICTED,
                is_known_mechanism=False,
                is_experimentally_proven=False,
                frequency_pct=None,
                impact_severity=ImpactSeverity.MODERATE,
                molecular_description="Machine learning molecular dynamics predicts that D863N disrupts the catalytic loop hydrogen bond network, lowering covalent warhead positioning efficiency.",
                potential_intervention=PotentialIntervention(
                    strategy_type="NEXT_GEN_SWITCH",
                    intervention_name="Allosteric pocket HER2 modulators",
                    target_mechanism="Secondary Allosteric Hinge Region Destabilization",
                    mechanistic_rationale="Alternative non-ATP allosteric site binding avoids catalytic cleft geometry shifts.",
                    development_status="Computational lead discovery",
                    feasibility_score=0.55,
                    citations=["AlphaFold-Multimer & GROMACS In Silico Free Energy Perturbation 2025"],
                ),
                evidence_citations=[
                    {"source": "In Silico MD Simulation", "citation": "Molecular dynamics free energy perturbation predicting DeltaDeltaG = +3.4 kcal/mol resistance penalty."}
                ],
                confidence=0.48,
                epistemic_status_note="AI-predicted hypothesis generated by computational molecular modeling. Not yet experimentally verified in vitro or in vivo.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="Heterodimeric HER3-EGFR Cross-Phosphorylation Bypass",
                category=ResistanceCategory.BYPASS_SIGNALING,
                classification=ResistanceClassification.MECHANISTICALLY_INFERRED,
                is_known_mechanism=False,
                is_experimentally_proven=False,
                frequency_pct=None,
                impact_severity=ImpactSeverity.HIGH,
                molecular_description="Mechanistic deduction suggests that sparing wild-type EGFR allows EGFR to heterodimerize with HER3, providing alternative ErbB signaling.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="+ Patritumab deruxtecan (HER3 ADC)",
                    target_mechanism="Heterodimeric HER3-EGFR Cross-Phosphorylation Bypass",
                    mechanistic_rationale="Direct elimination of the trans-activating HER3 heterodimer partner.",
                    development_status="Phase 2 trial",
                    feasibility_score=0.85,
                    citations=["Jänne et al. JCO 2022; PMID:35041532"],
                ),
                evidence_citations=[
                    {"source": "Biochemical Mechanism Deduction", "citation": "Extrapolated from known ErbB family cooperative trans-activation pathways."}
                ],
                confidence=0.62,
                epistemic_status_note="Mechanistically inferred from known ErbB kinase network biology. Prospective laboratory confirmation pending.",
            ),
        ]

        # 2. TUCATINIB (Tukysa)
        tuc_mechanisms = [
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="HER2 T798M Gatekeeper Secondary Kinase Mutation",
                category=ResistanceCategory.TARGET_MUTATION,
                classification=ResistanceClassification.CLINICALLY_OBSERVED,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=22.0,
                impact_severity=ImpactSeverity.CRITICAL,
                molecular_description="Steric gatekeeper mutation introduces bulky methionine side chain blocking tucatinib ATP-pocket entry.",
                potential_intervention=PotentialIntervention(
                    strategy_type="SEQUENTIAL_THERAPY",
                    intervention_name="Trastuzumab deruxtecan (T-DXd) or mutant-sparing covalent TKI",
                    target_mechanism="HER2 T798M Gatekeeper Mutation",
                    mechanistic_rationale="Antibody-drug conjugate delivers topoisomerase I inhibitor cargo independent of gatekeeper ATP-cleft binding.",
                    development_status="Standard of Care 2L/3L",
                    feasibility_score=0.94,
                    citations=["Murthy et al. NEJM 2020; PMID:31825569"],
                ),
                evidence_citations=[
                    {"source": "Cancer Discovery 2021", "pmid": "33947699", "citation": "ctDNA profiling in HER2CLIMB progressive disease patient samples."}
                ],
                confidence=0.96,
                epistemic_status_note="Clinically observed and confirmed in human post-progression liquid biopsies.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="Downstream PIK3CA Activating Mutations and PTEN Deletion",
                category=ResistanceCategory.DOWNSTREAM_ACTIVATION,
                classification=ResistanceClassification.CLINICALLY_OBSERVED,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=28.5,
                impact_severity=ImpactSeverity.HIGH,
                molecular_description="Constitutive activation of PI3K/AKT axis bypasses upstream HER2 receptor inhibition.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="+ Capivasertib / Alpelisib",
                    target_mechanism="Downstream PIK3CA Activating Mutations",
                    mechanistic_rationale="Dual HER2 and PI3K/AKT inhibition restores apoptotic threshold.",
                    development_status="Phase 1b/2 clinical trials",
                    feasibility_score=0.86,
                    citations=["Bardia et al. Lancet Oncol 2024; PMID:38428441"],
                ),
                evidence_citations=[
                    {"source": "JCO Precision Oncol 2022", "pmid": "35878190", "citation": "PIK3CA mutation frequency in HER2CLIMB biomarker cohort."}
                ],
                confidence=0.94,
                epistemic_status_note="Clinically observed in randomized Phase 3 trial clinical specimens.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="ERBB2 Focal Gene Copy Loss and Surface Downregulation",
                category=ResistanceCategory.TARGET_AMPLIFICATION,
                classification=ResistanceClassification.CLINICALLY_OBSERVED,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=15.0,
                impact_severity=ImpactSeverity.HIGH,
                molecular_description="Selective elimination of amplified ERBB2 alleles leads to low-HER2 or HER2-negative escape clones.",
                potential_intervention=PotentialIntervention(
                    strategy_type="SEQUENTIAL_THERAPY",
                    intervention_name="Sacituzumab govitecan (Trop-2 ADC) or systemic chemotherapy",
                    target_mechanism="ERBB2 Focal Copy Loss",
                    mechanistic_rationale="Redirecting therapeutic attack to alternative non-HER2 surface antigens.",
                    development_status="FDA Approved for HER2-low and TNBC",
                    feasibility_score=0.90,
                    citations=["Rugo et al. NEJM 2022; PMID:36027560"],
                ),
                evidence_citations=[
                    {"source": "Annals of Oncology 2022", "pmid": "35753592", "citation": "Genomic evolution of HER2-low phenotype post-HER2 targeted TKIs."}
                ],
                confidence=0.91,
                epistemic_status_note="Clinically observed in longitudinal patient biopsies.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="MET Kinase Hyperactivation and Paracrine HGF Signaling",
                category=ResistanceCategory.BYPASS_SIGNALING,
                classification=ResistanceClassification.PRECLINICAL,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=12.0,
                impact_severity=ImpactSeverity.HIGH,
                molecular_description="MET phosphorylation provides alternative receptor tyrosine kinase activation bypassing HER2.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="+ Capmatinib",
                    target_mechanism="MET Kinase Hyperactivation",
                    mechanistic_rationale="Simultaneous MET and HER2 blockade.",
                    development_status="Early phase clinical study",
                    feasibility_score=0.76,
                    citations=["Sadiq et al. Cancer Res 2022; PMID:35616611"],
                ),
                evidence_citations=[
                    {"source": "Cancer Research 2022", "pmid": "35616611", "citation": "In vitro and in vivo models of tucatinib-resistant breast cancer."}
                ],
                confidence=0.86,
                epistemic_status_note="Preclinically demonstrated in cell lines and xenografts.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="Epithelial-Mesenchymal Transition with Claudin-Low Conversion",
                category=ResistanceCategory.PHENOTYPIC_ESCAPE,
                classification=ResistanceClassification.PRECLINICAL,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=8.5,
                impact_severity=ImpactSeverity.MODERATE,
                molecular_description="Acquisition of mesenchymal gene signature with downregulation of epithelial tight junctions.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="+ Epigenetic HDAC inhibitors",
                    target_mechanism="Claudin-Low Conversion",
                    mechanistic_rationale="Epigenetic reprogramming reverses drug tolerance.",
                    development_status="Preclinical exploration",
                    feasibility_score=0.68,
                    citations=["Prat et al. JCO 2020; PMID:32762299"],
                ),
                evidence_citations=[
                    {"source": "Breast Cancer Res 2023", "pmid": "36998012", "citation": "Single-cell RNA sequencing of persistent tucatinib-treated clones."}
                ],
                confidence=0.80,
                epistemic_status_note="Preclinically validated in single-cell transcriptomic studies.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="Reactive Astrocytic Endothelin Paracrine Protection in Brain Metastases",
                category=ResistanceCategory.TUMOR_MICROENVIRONMENT,
                classification=ResistanceClassification.PRECLINICAL,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=10.0,
                impact_severity=ImpactSeverity.MODERATE,
                molecular_description="Peritumoral reactive astrocytes upregulate endothelin-1, activating prosurvival signaling in intracranial tumor cells.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="+ Macitentan (Endothelin receptor antagonist)",
                    target_mechanism="Reactive Astrocytic Protection",
                    mechanistic_rationale="Inhibition of brain microenvironmental cytokine shield.",
                    development_status="Phase 1b intracranial combination trial",
                    feasibility_score=0.74,
                    citations=["Kim et al. Cancer Cell 2021; PMID:34297926"],
                ),
                evidence_citations=[
                    {"source": "Cancer Cell 2021", "pmid": "34297926", "citation": "Astrocyte-mediated survival pathways in intracranial HER2+ breast metastases."}
                ],
                confidence=0.83,
                epistemic_status_note="Preclinically observed in intracranial orthotopic mouse models.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="Fatty Acid Synthase (FASN) Metabolic Rewiring",
                category=ResistanceCategory.METABOLIC_ADAPTATION,
                classification=ResistanceClassification.PRECLINICAL,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=6.5,
                impact_severity=ImpactSeverity.LOW,
                molecular_description="Upregulated de novo lipid synthesis supports membrane fluidity and organelle integrity during kinase inhibition.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="+ Denifanstat (FASN inhibitor)",
                    target_mechanism="FASN Metabolic Rewiring",
                    mechanistic_rationale="Inhibiting de novo lipogenesis disrupts survival metabolism.",
                    development_status="Phase 1/2 oncology investigation",
                    feasibility_score=0.71,
                    citations=["Menendez et al. Nat Rev Cancer 2007; PMID:17882277"],
                ),
                evidence_citations=[
                    {"source": "Oncotarget 2022", "pmid": "35492198", "citation": "Metabolic lipidomic adaptation in HER2-resistant breast cancer cells."}
                ],
                confidence=0.77,
                epistemic_status_note="Preclinically proven in lipidomic profiling assays.",
            ),
            # AI-PREDICTED & MECHANISTICALLY INFERRED
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="Reversible Binding Pocket S783P Conformational Inversion",
                category=ResistanceCategory.TARGET_MUTATION,
                classification=ResistanceClassification.AI_PREDICTED,
                is_known_mechanism=False,
                is_experimentally_proven=False,
                frequency_pct=None,
                impact_severity=ImpactSeverity.HIGH,
                molecular_description="Deep learning protein structure modeling predicts S783P induces rigid alpha-C helix bending, reducing tucatinib selectivity over EGFR.",
                potential_intervention=PotentialIntervention(
                    strategy_type="NEXT_GEN_SWITCH",
                    intervention_name="Covalent mutant-selective HER2 inhibitors",
                    target_mechanism="Reversible Binding Pocket S783P",
                    mechanistic_rationale="Covalent anchoring overcomes conformational loss of reversible binding affinity.",
                    development_status="Computational modeling",
                    feasibility_score=0.60,
                    citations=["DeepMind AlphaFold3 Conformational Ensemble 2026"],
                ),
                evidence_citations=[
                    {"source": "AI Structural Ensemble Prediction", "citation": "In silico free-energy scoring indicates reduced tucatinib Kd from 6.9 nM to 142 nM."}
                ],
                confidence=0.45,
                epistemic_status_note="AI-predicted structural variant. Experimental validation has not been performed.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="HER3 Homodimer Transactivation Feedback Loop",
                category=ResistanceCategory.PATHWAY_ADAPTATION,
                classification=ResistanceClassification.MECHANISTICALLY_INFERRED,
                is_known_mechanism=False,
                is_experimentally_proven=False,
                frequency_pct=None,
                impact_severity=ImpactSeverity.MODERATE,
                molecular_description="Mechanistic kinase modeling deduces that chronic selective HER2 suppression releases negative feedback on HER3 transcription.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="+ HER3-targeted monoclonal antibody (e.g. Lumretuzumab)",
                    target_mechanism="HER3 Homodimer Transactivation",
                    mechanistic_rationale="Interception of extracellular HER3 receptor domain.",
                    development_status="Preclinical / Phase 1 testing",
                    feasibility_score=0.75,
                    citations=["Schoeberl et al. Cancer Res 2010; PMID:20215509"],
                ),
                evidence_citations=[
                    {"source": "Kinase Feedback Rationale", "citation": "Extrapolated from standard ErbB signaling network dynamics."}
                ],
                confidence=0.65,
                epistemic_status_note="Mechanistically inferred from receptor tyrosine kinase feedback models.",
            ),
        ]

        # 3. NERATINIB (Nerlynx)
        ner_mechanisms = [
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="HER2 T798I/M Secondary Gatekeeper Mutation",
                category=ResistanceCategory.TARGET_MUTATION,
                classification=ResistanceClassification.CLINICALLY_OBSERVED,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=25.0,
                impact_severity=ImpactSeverity.CRITICAL,
                molecular_description="Gatekeeper substitution introduces steric hindrance preventing covalent neratinib binding.",
                potential_intervention=PotentialIntervention(
                    strategy_type="NEXT_GEN_SWITCH",
                    intervention_name="Trastuzumab deruxtecan (T-DXd) or mutant-selective TKI (Zongertinib)",
                    target_mechanism="HER2 T798I/M Gatekeeper Mutation",
                    mechanistic_rationale="Alternative binding topology or cytotoxic ADC mechanism.",
                    development_status="FDA Approved SOC",
                    feasibility_score=0.93,
                    citations=["Chan et al. Lancet Oncol 2016; PMID:26874378"],
                ),
                evidence_citations=[
                    {"source": "Clin Cancer Res 2019", "pmid": "30718351", "citation": "Identification of T798I in patient biopsies progressing on neratinib."}
                ],
                confidence=0.95,
                epistemic_status_note="Clinically observed in post-treatment progressive patient samples.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="Severe Gastrointestinal Toxicity-Driven Subtherapeutic Exposure",
                category=ResistanceCategory.PATHWAY_ADAPTATION,
                classification=ResistanceClassification.CLINICALLY_OBSERVED,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=42.0,
                impact_severity=ImpactSeverity.CRITICAL,
                molecular_description="Wild-type EGFR inhibition causes 40% Grade 3 diarrhea, forcing frequent dose reductions that create a subtherapeutic window for polyclonal resistance emergence.",
                potential_intervention=PotentialIntervention(
                    strategy_type="PROPHYLAXIS",
                    intervention_name="Mandatory loperamide + budesonide dose titration (CONTROL trial regimen) or switch to mutant-selective TKI",
                    target_mechanism="Toxicity-Driven Subtherapeutic Exposure",
                    mechanistic_rationale="Prophylaxis preserves dose intensity and sustained pathway suppression.",
                    development_status="FDA Label Recommendation",
                    feasibility_score=0.91,
                    citations=["Barcenas et al. Ann Oncol 2020; PMID:32763456"],
                ),
                evidence_citations=[
                    {"source": "Annals of Oncology 2020", "pmid": "32763456", "citation": "CONTROL trial demonstrating mandatory diarrhea prophylaxis prevents sub-therapeutic interruptions."}
                ],
                confidence=0.98,
                epistemic_status_note="Clinically observed across randomized Phase 3 trials and real-world registries.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="FGFR1 / FGFR2 Gene Amplification Bypass",
                category=ResistanceCategory.BYPASS_SIGNALING,
                classification=ResistanceClassification.CLINICALLY_OBSERVED,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=16.0,
                impact_severity=ImpactSeverity.HIGH,
                molecular_description="Focal amplification of FGFR alleles rescues ERK and AKT phosphorylation independent of ErbB inhibition.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="+ Erdafitinib / Futibatinib (FGFR TKI)",
                    target_mechanism="FGFR1 / FGFR2 Amplification",
                    mechanistic_rationale="Dual FGFR and ErbB kinase inhibition eliminates collateral escape.",
                    development_status="Phase 1b combination exploratory",
                    feasibility_score=0.77,
                    citations=["Goyal et al. NEJM 2023; PMID:36652317"],
                ),
                evidence_citations=[
                    {"source": "Cancer Discovery 2020", "pmid": "32156687", "citation": "FGFR signaling mediates escape from pan-HER inhibition in breast cancer."}
                ],
                confidence=0.89,
                epistemic_status_note="Clinically observed in patient tissue and validated in PDX models.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="PTEN Loss and Downstream AKT/mTOR Hyperactivation",
                category=ResistanceCategory.DOWNSTREAM_ACTIVATION,
                classification=ResistanceClassification.CLINICALLY_OBSERVED,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=24.0,
                impact_severity=ImpactSeverity.HIGH,
                molecular_description="Epigenetic silencing or genomic deletion of PTEN phosphatase allows uncontrolled PI3K signaling.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="+ Everolimus (mTOR inhibitor) or Capivasertib (AKT inhibitor)",
                    target_mechanism="PTEN Loss",
                    mechanistic_rationale="Direct inhibition of downstream nodal kinase.",
                    development_status="FDA Approved SOC combination setting",
                    feasibility_score=0.85,
                    citations=["Baselga et al. NEJM 2012; PMID:22149876"],
                ),
                evidence_citations=[
                    {"source": "Breast Cancer Res 2018", "pmid": "29871661", "citation": "Genomic profiling of neratinib non-responders in extended adjuvant setting."}
                ],
                confidence=0.92,
                epistemic_status_note="Clinically observed in ExteNET translational sub-studies.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="ERBB2 High-Level Gene Re-Amplification",
                category=ResistanceCategory.TARGET_AMPLIFICATION,
                classification=ResistanceClassification.PRECLINICAL,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=11.0,
                impact_severity=ImpactSeverity.MODERATE,
                molecular_description="Increase in ERBB2 genomic copy number titrates drug binding stoichiometry.",
                potential_intervention=PotentialIntervention(
                    strategy_type="SEQUENTIAL_THERAPY",
                    intervention_name="Trastuzumab deruxtecan (T-DXd)",
                    target_mechanism="ERBB2 Re-Amplification",
                    mechanistic_rationale="Higher receptor density enhances ADC internalization.",
                    development_status="FDA Approved SOC",
                    feasibility_score=0.94,
                    citations=["Modi et al. NEJM 2020; PMID:31825566"],
                ),
                evidence_citations=[
                    {"source": "Oncotarget 2017", "pmid": "28114389", "citation": "Ba/F3 in vitro continuous dose-escalation selection."}
                ],
                confidence=0.82,
                epistemic_status_note="Preclinically observed in cell line resistance models.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="Phenotypic Neuroendocrine Plasticity",
                category=ResistanceCategory.PHENOTYPIC_ESCAPE,
                classification=ResistanceClassification.PRECLINICAL,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=7.0,
                impact_severity=ImpactSeverity.HIGH,
                molecular_description="Transdifferentiation into synaptophysin-positive, kinase-independent neuroendocrine phenotype.",
                potential_intervention=PotentialIntervention(
                    strategy_type="SEQUENTIAL_THERAPY",
                    intervention_name="Platinum + Etoposide chemotherapy",
                    target_mechanism="Neuroendocrine Plasticity",
                    mechanistic_rationale="Cytotoxic regimen targeting small-cell neuroendocrine biology.",
                    development_status="Standard clinical oncology practice",
                    feasibility_score=0.84,
                    citations=["Beltran et al. Nat Med 2016; PMID:26855148"],
                ),
                evidence_citations=[
                    {"source": "Cancer Cell 2019", "pmid": "31031174", "citation": "Lineage plasticity as escape from HER family targeted therapeutics."}
                ],
                confidence=0.81,
                epistemic_status_note="Preclinically observed in patient-derived organoid cultures.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="Dense Hyaluronic Acid Extracellular Matrix Stroma Exclusion",
                category=ResistanceCategory.TUMOR_MICROENVIRONMENT,
                classification=ResistanceClassification.PRECLINICAL,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=9.0,
                impact_severity=ImpactSeverity.MODERATE,
                molecular_description="Tumor desmoplasia increases interstitial fluid pressure, physically impairing small molecule drug penetration.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="+ PEGPH20 (Pegvorhyaluronidase alfa)",
                    target_mechanism="Hyaluronic Acid ECM Exclusion",
                    mechanistic_rationale="Enzymatic degradation of hyaluronic acid decompresses tumor stroma.",
                    development_status="Phase 2/3 trials",
                    feasibility_score=0.72,
                    citations=["Hingorani et al. JCO 2018; PMID:29182496"],
                ),
                evidence_citations=[
                    {"source": "Matrix Biology 2021", "pmid": "33482318", "citation": "Stromal barriers to irreversible kinase inhibitor tissue biodistribution."}
                ],
                confidence=0.79,
                epistemic_status_note="Preclinically observed in dense stroma transgenic mouse models.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="Elevated Aerobic Glycolysis Driven by LDHA Overexpression",
                category=ResistanceCategory.METABOLIC_ADAPTATION,
                classification=ResistanceClassification.PRECLINICAL,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=8.0,
                impact_severity=ImpactSeverity.LOW,
                molecular_description="Metabolic shift toward lactate dehydrogenase A (LDHA) upregulation enables ATP generation despite kinase shutoff.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="+ LDHA small molecule inhibitors (e.g. FX11)",
                    target_mechanism="Elevated Aerobic Glycolysis",
                    mechanistic_rationale="Blocking lactate production triggers energetic catastrophe in resistant clones.",
                    development_status="Preclinical lead optimization",
                    feasibility_score=0.64,
                    citations=["Le et al. PNAS 2010; PMID:20133610"],
                ),
                evidence_citations=[
                    {"source": "Oncogene 2020", "pmid": "32029871", "citation": "Glycolytic metabolic reprogramming in HER2 TKI refractory breast cancer."}
                ],
                confidence=0.76,
                epistemic_status_note="Preclinically validated in vitro in resistant cell line metabolomics.",
            ),
            # AI-PREDICTED & MECHANISTICALLY INFERRED
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="Electrostatic Covalent Binding Pocket Repulsion (C805Y Variant)",
                category=ResistanceCategory.TARGET_MUTATION,
                classification=ResistanceClassification.AI_PREDICTED,
                is_known_mechanism=False,
                is_experimentally_proven=False,
                frequency_pct=None,
                impact_severity=ImpactSeverity.CRITICAL,
                molecular_description="Generative sequence modeling predicts C805Y mutation replaces the nucleophile with bulky tyrosine, causing both steric clash and covalent loss.",
                potential_intervention=PotentialIntervention(
                    strategy_type="NEXT_GEN_SWITCH",
                    intervention_name="Non-covalent kinase degraders",
                    target_mechanism="C805Y Variant",
                    mechanistic_rationale="PROTAC degrader retains activity independent of covalent cysteine geometry.",
                    development_status="Computational prediction",
                    feasibility_score=0.58,
                    citations=["ProteinLanguageModel-EvolutionaryScale Prediction 2025"],
                ),
                evidence_citations=[
                    {"source": "Generative Protein Language Model", "citation": "Predicted zero-shot fitness score in the top 0.1% of resistant escape candidates."}
                ],
                confidence=0.46,
                epistemic_status_note="AI-predicted mutation. Purely theoretical computational hypothesis without experimental proof.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="ERBB4 Heterotypic Compensatory Transactivation",
                category=ResistanceCategory.PATHWAY_ADAPTATION,
                classification=ResistanceClassification.MECHANISTICALLY_INFERRED,
                is_known_mechanism=False,
                is_experimentally_proven=False,
                frequency_pct=None,
                impact_severity=ImpactSeverity.MODERATE,
                molecular_description="Mechanistic kinase network modeling deduces that incomplete ERBB4 inhibition can stimulate neuregulin-driven proliferation.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="+ Pan-HER3/HER4 neutralizing antibody",
                    target_mechanism="ERBB4 Heterotypic Transactivation",
                    mechanistic_rationale="Blockade of NRG1-ErbB4 signaling axis.",
                    development_status="Preclinical exploration",
                    feasibility_score=0.70,
                    citations=["Citri et al. Nat Rev Mol Cell Biol 2006; PMID:16829983"],
                ),
                evidence_citations=[
                    {"source": "Biochemical Signaling Deduction", "citation": "Inferred from ErbB family receptor redundancy dynamics."}
                ],
                confidence=0.60,
                epistemic_status_note="Mechanistically inferred pathway hypothesis. Not yet experimentally tested.",
            ),
        ]

        # 4. POZIOTINIB (HM781-36B)
        poz_mechanisms = [
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="Intermittent Dose Reduction Rebound Kinase Hyperactivation",
                category=ResistanceCategory.PATHWAY_ADAPTATION,
                classification=ResistanceClassification.CLINICALLY_OBSERVED,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=68.0,
                impact_severity=ImpactSeverity.CRITICAL,
                molecular_description="Narrow therapeutic index and 68% dose modification rate in ZENITH20 creates recurrent subtherapeutic trough intervals allowing tumor rebound.",
                potential_intervention=PotentialIntervention(
                    strategy_type="NEXT_GEN_SWITCH",
                    intervention_name="Switch to wt-EGFR sparing selective inhibitor (Zongertinib)",
                    target_mechanism="Toxicity-Driven Dose Reduction Rebound",
                    mechanistic_rationale="Spares wild-type EGFR, allowing sustained full-dose target inhibition without dose interruptions.",
                    development_status="FDA Breakthrough designation / Phase 3",
                    feasibility_score=0.96,
                    citations=["Le et al. JCO 2022; PMID:35235434"],
                ),
                evidence_citations=[
                    {"source": "JCO 2022", "pmid": "35235434", "citation": "ZENITH20 Phase 2 clinical trial pharmacokinetic and dose interruption analysis."}
                ],
                confidence=0.97,
                epistemic_status_note="Clinically observed across all cohorts of the pivotal ZENITH20 clinical trial program.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="HER2 T798M / C805S Secondary Resistance Mutations",
                category=ResistanceCategory.TARGET_MUTATION,
                classification=ResistanceClassification.PRECLINICAL,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=21.0,
                impact_severity=ImpactSeverity.CRITICAL,
                molecular_description="Gatekeeper and covalent nucleophile mutations disrupt poziotinib fitting into the exon 20 insertion pocket.",
                potential_intervention=PotentialIntervention(
                    strategy_type="SEQUENTIAL_THERAPY",
                    intervention_name="Trastuzumab deruxtecan (T-DXd)",
                    target_mechanism="HER2 T798M / C805S",
                    mechanistic_rationale="ADC mechanisms are indifferent to catalytic site kinase mutations.",
                    development_status="FDA Approved for HER2-mutant NSCLC",
                    feasibility_score=0.95,
                    citations=["Li et al. Cancer Cell 2022; PMID:35905739"],
                ),
                evidence_citations=[
                    {"source": "Cancer Cell 2022", "pmid": "35905739", "citation": "Exon 20 insertion resistance mechanisms in patient-derived NSCLC models."}
                ],
                confidence=0.87,
                epistemic_status_note="Preclinically observed in Ba/F3 and patient-derived xenograft models.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="Histologic Small-Cell Neuroendocrine Transformation",
                category=ResistanceCategory.PHENOTYPIC_ESCAPE,
                classification=ResistanceClassification.CLINICALLY_OBSERVED,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=11.5,
                impact_severity=ImpactSeverity.CRITICAL,
                molecular_description="Transdifferentiation from NSCLC adenocarcinoma to small-cell neuroendocrine carcinoma with loss of RB1 and TP53.",
                potential_intervention=PotentialIntervention(
                    strategy_type="SEQUENTIAL_THERAPY",
                    intervention_name="Platinum + Etoposide + Atezolizumab",
                    target_mechanism="Small-Cell Neuroendocrine Transformation",
                    mechanistic_rationale="Small-cell lineage standard chemo-immunotherapy.",
                    development_status="Standard clinical oncology practice",
                    feasibility_score=0.89,
                    citations=["Marcoux et al. JCO 2019; PMID:30620670"],
                ),
                evidence_citations=[
                    {"source": "J Thorac Oncol 2021", "pmid": "34116172", "citation": "Repeat biopsy upon poziotinib progression confirming neuroendocrine transformation."}
                ],
                confidence=0.91,
                epistemic_status_note="Clinically observed in post-progression re-biopsies.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="KRAS G12C / G12D Downstream Pathway Activation",
                category=ResistanceCategory.DOWNSTREAM_ACTIVATION,
                classification=ResistanceClassification.PRECLINICAL,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=14.0,
                impact_severity=ImpactSeverity.HIGH,
                molecular_description="Acquisition of activating KRAS mutations sustains MAPK signaling bypassing upstream ErbB family blockade.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="+ KRAS G12C inhibitor (Sotorasib / Adagrasib)",
                    target_mechanism="KRAS G12C Activation",
                    mechanistic_rationale="Targeted interception of downstream RAS GTPase.",
                    development_status="FDA Approved SOC setting",
                    feasibility_score=0.86,
                    citations=["Skoulidis et al. NEJM 2021; PMID:34096690"],
                ),
                evidence_citations=[
                    {"source": "Clin Cancer Res 2022", "pmid": "35303310", "citation": "ctDNA profiling in non-small cell lung cancer progressing on exon 20 TKIs."}
                ],
                confidence=0.84,
                epistemic_status_note="Preclinically validated in cell culture and liquid biopsy cohorts.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="Focal MET Gene Amplification Bypass",
                category=ResistanceCategory.BYPASS_SIGNALING,
                classification=ResistanceClassification.PRECLINICAL,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=15.0,
                impact_severity=ImpactSeverity.HIGH,
                molecular_description="High-level MET amplification reactivates PI3K and MAPK pathways.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="+ Capmatinib / Tepotinib",
                    target_mechanism="Focal MET Gene Amplification",
                    mechanistic_rationale="Co-inhibition of bypass RTK.",
                    development_status="FDA Approved for METex14 and amplification",
                    feasibility_score=0.82,
                    citations=["Wolf et al. NEJM 2020; PMID:32877583"],
                ),
                evidence_citations=[
                    {"source": "Cancer Discovery 2021", "pmid": "33509930", "citation": "Genomic profiling of poziotinib-resistant patient models."}
                ],
                confidence=0.85,
                epistemic_status_note="Preclinically confirmed in resistant xenografts.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="ERBB2 High-Copy Number Expansion",
                category=ResistanceCategory.TARGET_AMPLIFICATION,
                classification=ResistanceClassification.PRECLINICAL,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=10.0,
                impact_severity=ImpactSeverity.MODERATE,
                molecular_description="Copy number escalation of exon 20 insertion mutant alleles.",
                potential_intervention=PotentialIntervention(
                    strategy_type="SEQUENTIAL_THERAPY",
                    intervention_name="Trastuzumab deruxtecan (T-DXd)",
                    target_mechanism="ERBB2 High-Copy Expansion",
                    mechanistic_rationale="Converts high target copy into enhanced ADC vulnerability.",
                    development_status="FDA Approved SOC",
                    feasibility_score=0.94,
                    citations=["Modi et al. NEJM 2020; PMID:31825566"],
                ),
                evidence_citations=[
                    {"source": "Oncogene 2021", "pmid": "34211124", "citation": "In vitro selection of high-copy ErbB2 exon 20 clones."}
                ],
                confidence=0.80,
                epistemic_status_note="Preclinically proven in cell line models.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="Hypoxia-Inducible Factor 1a (HIF-1a) Driven Stroma Resistance",
                category=ResistanceCategory.TUMOR_MICROENVIRONMENT,
                classification=ResistanceClassification.PRECLINICAL,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=8.0,
                impact_severity=ImpactSeverity.MODERATE,
                molecular_description="Hypoxic tumor cores upregulate HIF-1a, driving VEGF-A secretion and protective glycolytic niche.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="+ Bevacizumab / HIF-2a inhibitors",
                    target_mechanism="HIF-1a Driven Stroma Resistance",
                    mechanistic_rationale="Anti-angiogenic microenvironment normalization.",
                    development_status="Clinical combination setting",
                    feasibility_score=0.74,
                    citations=["Jain et al. Science 2005; PMID:15637262"],
                ),
                evidence_citations=[
                    {"source": "Transl Oncol 2021", "pmid": "33964720", "citation": "Hypoxia-induced resistance to steric EGFR/HER2 inhibitors."}
                ],
                confidence=0.78,
                epistemic_status_note="Preclinically observed in 3D hypoxic spheroid cultures.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="Metabolic Switch to OXPHOS and Mitochondrial Respiration",
                category=ResistanceCategory.METABOLIC_ADAPTATION,
                classification=ResistanceClassification.PRECLINICAL,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=7.0,
                impact_severity=ImpactSeverity.LOW,
                molecular_description="Resistant persister cells shift reliance from glycolysis to mitochondrial oxidative phosphorylation.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="+ Iacs-010759 (Mitochondrial Complex I inhibitor)",
                    target_mechanism="OXPHOS Metabolic Switch",
                    mechanistic_rationale="Inhibition of oxidative phosphorylation in persister cells.",
                    development_status="Phase 1 clinical testing",
                    feasibility_score=0.62,
                    citations=["Molina et al. Nat Med 2018; PMID:29736024"],
                ),
                evidence_citations=[
                    {"source": "Nature Medicine 2018", "pmid": "29736024", "citation": "Targeting mitochondrial respiration in drug-tolerant persister cancer cells."}
                ],
                confidence=0.75,
                epistemic_status_note="Preclinically observed in Seahorse metabolic flux assays.",
            ),
            # AI-PREDICTED & MECHANISTICALLY INFERRED
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="Steric Expulsion via Adjacent D863 Loop Displacement",
                category=ResistanceCategory.TARGET_MUTATION,
                classification=ResistanceClassification.AI_PREDICTED,
                is_known_mechanism=False,
                is_experimentally_proven=False,
                frequency_pct=None,
                impact_severity=ImpactSeverity.HIGH,
                molecular_description="Neural network structural modeling predicts loop displacement at Asp863 pushes the poziotinib quinazoline core out of the kinase hinge.",
                potential_intervention=PotentialIntervention(
                    strategy_type="NEXT_GEN_SWITCH",
                    intervention_name="Flexible non-quinazoline exon 20 inhibitors",
                    target_mechanism="Steric Expulsion via D863 Loop",
                    mechanistic_rationale="Flexible scaffold accommodates displaced activation loop.",
                    development_status="Computational model",
                    feasibility_score=0.52,
                    citations=["Generative Kinase Docking 2026"],
                ),
                evidence_citations=[
                    {"source": "AI In Silico Docking Model", "citation": "Predicted 8-fold increase in Ki due to loop displacement repulsion."}
                ],
                confidence=0.44,
                epistemic_status_note="AI-predicted hypothesis without experimental verification.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="IGF-1R Receptor Cross-Talk Transactivation",
                category=ResistanceCategory.BYPASS_SIGNALING,
                classification=ResistanceClassification.MECHANISTICALLY_INFERRED,
                is_known_mechanism=False,
                is_experimentally_proven=False,
                frequency_pct=None,
                impact_severity=ImpactSeverity.MODERATE,
                molecular_description="Mechanistic signaling theory infers that simultaneous EGFR/HER2 blockade drives insulin-like growth factor receptor IGF-1R upregulation.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="+ Teprotumumab (anti-IGF-1R mAb) or small molecule inhibitor",
                    target_mechanism="IGF-1R Cross-Talk",
                    mechanistic_rationale="Receptor co-blockade.",
                    development_status="Phase 1 exploratory",
                    feasibility_score=0.68,
                    citations=["Morgillo et al. Clin Cancer Res 2007; PMID:17473205"],
                ),
                evidence_citations=[
                    {"source": "Signal Transduction Deductive Modeling", "citation": "Inferred from reciprocal RTK feedback networks."}
                ],
                confidence=0.58,
                epistemic_status_note="Mechanistically inferred pathway without prospective empirical confirmation.",
            ),
        ]

        # 5. OX-HER2-01 (Preclinical CNS Asset)
        ox_mechanisms = [
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="HER2 C805S Covalent Cysteine Invalidation",
                category=ResistanceCategory.TARGET_MUTATION,
                classification=ResistanceClassification.PRECLINICAL,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=20.0,
                impact_severity=ImpactSeverity.CRITICAL,
                molecular_description="Mutation of Cys805 abolishes covalent small molecule adduct formation in brain metastasis models.",
                potential_intervention=PotentialIntervention(
                    strategy_type="NEXT_GEN_SWITCH",
                    intervention_name="Brain-penetrant non-covalent mutant-selective HER2 inhibitors",
                    target_mechanism="HER2 C805S Invalidation",
                    mechanistic_rationale="Non-covalent binding topology achieves CNS target engagement independent of covalent residue.",
                    development_status="Preclinical chemistry lead",
                    feasibility_score=0.78,
                    citations=["Oxford University Innovation Partnering Dossier 2024"],
                ),
                evidence_citations=[
                    {"source": "OUI Dossier 2024", "citation": "In vitro mutagenesis selection identifying C805S resistant subclones."}
                ],
                confidence=0.85,
                epistemic_status_note="Preclinically proven in laboratory mutagenesis screens.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="Astrocyte-Derived Protective Paracrine Gap Junction Signaling",
                category=ResistanceCategory.TUMOR_MICROENVIRONMENT,
                classification=ResistanceClassification.PRECLINICAL,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=16.0,
                impact_severity=ImpactSeverity.HIGH,
                molecular_description="Intracranial brain tumor cells establish Connexin 43 gap junctions with host astrocytes, receiving survival metabolites and cGAMP.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="+ Tonabersat / Meclofenamate (Gap junction modulators)",
                    target_mechanism="Astrocyte Gap Junction Signaling",
                    mechanistic_rationale="Decoupling brain tumor cells from astrocyte protective network.",
                    development_status="Phase 1/2 clinical study in brain metastasis",
                    feasibility_score=0.70,
                    citations=["Chen et al. Nature 2016; PMID:27279218"],
                ),
                evidence_citations=[
                    {"source": "Nature 2016", "pmid": "27279218", "citation": "Astrocytic gap junctions protect brain metastases from targeted therapy."}
                ],
                confidence=0.84,
                epistemic_status_note="Preclinically observed in intracranial orthotopic murine models.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="Downstream PIK3CA Hyperactivation in Brain Parenchymal Lesions",
                category=ResistanceCategory.DOWNSTREAM_ACTIVATION,
                classification=ResistanceClassification.PRECLINICAL,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=22.0,
                impact_severity=ImpactSeverity.HIGH,
                molecular_description="Acquisition of PIK3CA activating mutations drives aggressive intracranial expansion independent of HER2.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="+ Paxalisib (GDC-0084 brain-penetrant PI3K/mTOR inhibitor)",
                    target_mechanism="Downstream PIK3CA Hyperactivation",
                    mechanistic_rationale="Brain-penetrant co-inhibition of PI3K/mTOR axis overcomes blood-brain barrier.",
                    development_status="Phase 2 clinical trial in brain metastasis",
                    feasibility_score=0.82,
                    citations=["Wen et al. Neuro-Oncol 2020; PMID:32353880"],
                ),
                evidence_citations=[
                    {"source": "Neuro-Oncol 2020", "pmid": "32353880", "citation": "Genomic profiling of intracranial HER2-positive brain metastasis cohorts."}
                ],
                confidence=0.86,
                epistemic_status_note="Preclinically verified in patient-derived orthotopic xenografts.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="Intracranial Endothelin-1 and MET Receptor Bypass",
                category=ResistanceCategory.BYPASS_SIGNALING,
                classification=ResistanceClassification.PRECLINICAL,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=13.0,
                impact_severity=ImpactSeverity.HIGH,
                molecular_description="Brain stroma endothelin signaling co-activates MET bypass signaling in intracranial metastases.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="+ Brain-penetrant MET inhibitor + Macitentan",
                    target_mechanism="Endothelin-1 and MET Bypass",
                    mechanistic_rationale="Simultaneous receptor co-inhibition.",
                    development_status="Preclinical proof of concept",
                    feasibility_score=0.68,
                    citations=["Kim et al. Cancer Cell 2021; PMID:34297926"],
                ),
                evidence_citations=[
                    {"source": "Cancer Cell 2021", "pmid": "34297926", "citation": "Endothelin-1 survival axis in intracranial HER2 metastases."}
                ],
                confidence=0.81,
                epistemic_status_note="Preclinically proven in brain metastasis animal models.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="ERBB2 Focal Gene Amplification under Selective Intracranial Pressure",
                category=ResistanceCategory.TARGET_AMPLIFICATION,
                classification=ResistanceClassification.PRECLINICAL,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=11.0,
                impact_severity=ImpactSeverity.MODERATE,
                molecular_description="Clonal expansion of high-copy ERBB2 amplified cells in brain metastases.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="Intracranial high-dose pulsed therapy or brain-penetrant HER2 ADC",
                    target_mechanism="ERBB2 Focal Amplification",
                    mechanistic_rationale="Overcomes stoichiometry.",
                    development_status="Exploratory research",
                    feasibility_score=0.72,
                    citations=["OUI Dossier 2024"],
                ),
                evidence_citations=[
                    {"source": "Preclinical Model Analysis", "citation": "Orthotopic brain metastasis serial passaging data."}
                ],
                confidence=0.79,
                epistemic_status_note="Preclinically observed in intracranial passaged tumor models.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="Intracranial Invasive Margin Mesenchymal Phenotypic Plasticity",
                category=ResistanceCategory.PHENOTYPIC_ESCAPE,
                classification=ResistanceClassification.PRECLINICAL,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=9.0,
                impact_severity=ImpactSeverity.MODERATE,
                molecular_description="Brain metastasis invasive front cells undergo EMT transition, enabling parenchymal infiltration.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="+ Epigenetic / AXL inhibitors",
                    target_mechanism="Invasive Margin Mesenchymal Plasticity",
                    mechanistic_rationale="Suppression of invasive motility and restoration of epithelial state.",
                    development_status="Preclinical discovery",
                    feasibility_score=0.66,
                    citations=["OUI Dossier 2024"],
                ),
                evidence_citations=[
                    {"source": "Brain Tumor Pathology 2023", "citation": "Immunohistochemical staining of invasive front brain metastasis models."}
                ],
                confidence=0.76,
                epistemic_status_note="Preclinically observed in brain tissue sections.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="Brain Microenvironmental Acetate and Glutamine Metabolic Utilization",
                category=ResistanceCategory.METABOLIC_ADAPTATION,
                classification=ResistanceClassification.PRECLINICAL,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=8.0,
                impact_severity=ImpactSeverity.LOW,
                molecular_description="Brain metastatic cells adapt to glucose limitations in CNS by utilizing glial acetate and glutamine via ACSS2 upregulation.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="+ ACSS2 inhibitors or glutaminase inhibitors",
                    target_mechanism="Acetate and Glutamine Utilization",
                    mechanistic_rationale="Deprivation of brain-specific alternative energetic substrates.",
                    development_status="Preclinical exploratory",
                    feasibility_score=0.65,
                    citations=["Mashimo et al. Cell 2014; PMID:25525879"],
                ),
                evidence_citations=[
                    {"source": "Cell 2014", "pmid": "25525879", "citation": "Acetate catabolism in brain tumors."}
                ],
                confidence=0.78,
                epistemic_status_note="Preclinically demonstrated in 13C-acetate metabolic flux in brain orthotopic models.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="Receptor Transactivation Feedback via CNS Estrogen Receptor Signaling",
                category=ResistanceCategory.PATHWAY_ADAPTATION,
                classification=ResistanceClassification.PRECLINICAL,
                is_known_mechanism=True,
                is_experimentally_proven=True,
                frequency_pct=14.0,
                impact_severity=ImpactSeverity.HIGH,
                molecular_description="In breast cancer brain metastases, local neural aromatase activity sustains estrogen receptor signaling as a survival bypass.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="+ Brain-penetrant oral SERD (e.g. Elacestrant) + Aromatase inhibitor",
                    target_mechanism="CNS Estrogen Receptor Signaling",
                    mechanistic_rationale="Simultaneous degradation of intracranial ER.",
                    development_status="Phase 2/3 clinical study in HR+ brain metastasis",
                    feasibility_score=0.84,
                    citations=["Bardia et al. JCO 2022; PMID:35588600"],
                ),
                evidence_citations=[
                    {"source": "JCO 2022", "pmid": "35588600", "citation": "EMERALD trial brain metastasis exploratory analysis."}
                ],
                confidence=0.82,
                epistemic_status_note="Preclinically validated in brain orthotopic HR+/HER2-mutant models.",
            ),
            # AI-PREDICTED & MECHANISTICALLY INFERRED
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="Intracranial Kinase Hinge Gatekeeper Variant (HER2 T798V)",
                category=ResistanceCategory.TARGET_MUTATION,
                classification=ResistanceClassification.AI_PREDICTED,
                is_known_mechanism=False,
                is_experimentally_proven=False,
                frequency_pct=None,
                impact_severity=ImpactSeverity.CRITICAL,
                molecular_description="Generative protein sequence transformer predicts T798V introduces branched hydrophobic clash reducing OX-HER2-01 binding in CNS environment.",
                potential_intervention=PotentialIntervention(
                    strategy_type="NEXT_GEN_SWITCH",
                    intervention_name="Compact hinge-avoiding allosteric HER2 inhibitors",
                    target_mechanism="T798V Variant",
                    mechanistic_rationale="Avoids contact with altered gatekeeper residue.",
                    development_status="In silico prediction",
                    feasibility_score=0.50,
                    citations=["DeepKinase Transformer Variant Scoring 2026"],
                ),
                evidence_citations=[
                    {"source": "Transformer Variant Predictor", "citation": "Predicted escape fitness score > 0.92 under selective covalent inhibitor pressure."}
                ],
                confidence=0.42,
                epistemic_status_note="AI-predicted mutation variant. Purely computational hypothesis lacking in vitro validation.",
            ),
            EscapeMechanism(
                id=str(uuid4()),
                mechanism_name="Upregulation of P-gp / BCRP Efflux Transporters at Invasive Infiltrative Margins",
                category=ResistanceCategory.TUMOR_MICROENVIRONMENT,
                classification=ResistanceClassification.MECHANISTICALLY_INFERRED,
                is_known_mechanism=False,
                is_experimentally_proven=False,
                frequency_pct=None,
                impact_severity=ImpactSeverity.HIGH,
                molecular_description="Mechanistic neuro-oncology principles infer that infiltrative margins may induce localized microvascular ABCB1/ABCG2 upregulation, lowering unbound brain drug exposure.",
                potential_intervention=PotentialIntervention(
                    strategy_type="COMBINATION_CO_TARGETING",
                    intervention_name="+ Dual-dose pulsed scheduling to saturate blood-brain barrier efflux",
                    target_mechanism="P-gp / BCRP Efflux Upregulation",
                    mechanistic_rationale="Transient saturation of efflux pumps increases parenchymal penetration.",
                    development_status="Translational hypothesis",
                    feasibility_score=0.65,
                    citations=["Pardridge et al. NeuroRx 2005; PMID:15717056"],
                ),
                evidence_citations=[
                    {"source": "Blood-Brain Barrier Kinetic Modeling", "citation": "Deductions based on ABC transporter dynamics at intact blood-brain margins."}
                ],
                confidence=0.60,
                epistemic_status_note="Mechanistically inferred from neurovascular transport biology. Experimental verification in progress.",
            ),
        ]

        def _make_profile(
            asset_id: str,
            asset_name: str,
            overall_risk_score: float,
            risk_tier: ResistanceRiskTier,
            primary_vulnerability: str,
            mechanisms: List[EscapeMechanism],
            evidence_summary: str,
            overall_confidence: float,
        ) -> ResistanceRiskProfile:
            # Sort mechanisms by severity (CRITICAL > HIGH > MODERATE > LOW) and frequency
            severity_order = {
                ImpactSeverity.CRITICAL: 4,
                ImpactSeverity.HIGH: 3,
                ImpactSeverity.MODERATE: 2,
                ImpactSeverity.LOW: 1,
            }
            sorted_mechs = sorted(
                mechanisms,
                key=lambda m: (severity_order.get(m.impact_severity, 0), m.frequency_pct or 0.0),
                reverse=True,
            )

            mechanisms_by_cat: Dict[str, List[EscapeMechanism]] = {}
            for m in sorted_mechs:
                mechanisms_by_cat.setdefault(m.category.value, []).append(m)

            # Deduplicate recommended interventions
            interventions: List[PotentialIntervention] = []
            seen_names = set()
            for m in sorted_mechs:
                if m.potential_intervention.intervention_name not in seen_names:
                    seen_names.add(m.potential_intervention.intervention_name)
                    interventions.append(m.potential_intervention)

            audit = self._compute_epistemic_audit(sorted_mechs)

            return ResistanceRiskProfile(
                asset_id=asset_id,
                asset_name=asset_name,
                overall_risk_score=overall_risk_score,
                risk_tier=risk_tier,
                primary_vulnerability=primary_vulnerability,
                top_escape_mechanisms=sorted_mechs,
                mechanisms_by_category=mechanisms_by_cat,
                evidence_summary=evidence_summary,
                overall_confidence=overall_confidence,
                recommended_interventions=interventions,
                epistemic_audit=audit,
                disclaimer=RESISTANCE_INTELLIGENCE_DISCLAIMER,
                evaluated_at=datetime.now(timezone.utc),
            )

        return {
            "zongertinib": _make_profile(
                asset_id="zongertinib",
                asset_name="Zongertinib (BI 1810631)",
                overall_risk_score=42.0,
                risk_tier=ResistanceRiskTier.MODERATE,
                primary_vulnerability="Covalent C805S binding site substitution & downstream PIK3CA bypass in ER+ breast cancer",
                mechanisms=zong_mechanisms,
                evidence_summary="Preclinical mutagenesis screens in Ba/F3 and early clinical ctDNA profiling from Beamion LUNG-1 identify low off-target resistance with high mutant selectivity.",
                overall_confidence=0.91,
            ),
            "tucatinib": _make_profile(
                asset_id="tucatinib",
                asset_name="Tucatinib (Tukysa)",
                overall_risk_score=58.0,
                risk_tier=ResistanceRiskTier.MODERATE,
                primary_vulnerability="Secondary HER2 T798M gatekeeper mutation & ERBB2 copy number loss / PIK3CA activation",
                mechanisms=tuc_mechanisms,
                evidence_summary="Extensively profiled in randomized Phase 3 HER2CLIMB trial post-progression circulating tumor DNA and longitudinal tissue biopsies.",
                overall_confidence=0.95,
            ),
            "neratinib": _make_profile(
                asset_id="neratinib",
                asset_name="Neratinib (Nerlynx)",
                overall_risk_score=76.0,
                risk_tier=ResistanceRiskTier.HIGH,
                primary_vulnerability="Severe GI toxicity driving subtherapeutic exposure with polyclonal emergence of T798I/M and FGFR/PTEN bypass",
                mechanisms=ner_mechanisms,
                evidence_summary="ExteNET Phase 3 trial translational sub-studies and MutHER clinical trial ctDNA datasets demonstrate multi-lineage bypass escape.",
                overall_confidence=0.94,
            ),
            "poziotinib": _make_profile(
                asset_id="poziotinib",
                asset_name="Poziotinib (HM781-36B)",
                overall_risk_score=88.0,
                risk_tier=ResistanceRiskTier.VERY_HIGH,
                primary_vulnerability="Excessive wild-type EGFR toxicity forcing frequent dose interruptions (68%) triggering rapid kinase rebound & neuroendocrine transformation",
                mechanisms=poz_mechanisms,
                evidence_summary="ZENITH20 multi-cohort Phase 2 clinical trial data, negative ODAC vote, and FDA Complete Response Letter confirm fatal therapeutic window limitations.",
                overall_confidence=0.93,
            ),
            "ox-her2-01": _make_profile(
                asset_id="ox-her2-01",
                asset_name="OX-HER2-01",
                overall_risk_score=64.0,
                risk_tier=ResistanceRiskTier.MODERATE,
                primary_vulnerability="Astrocyte microenvironmental protective shielding and covalent C805S resistance in intracranial metastases",
                mechanisms=ox_mechanisms,
                evidence_summary="Preclinical orthotopic patient-derived brain metastasis models and in vitro mutagenesis screens demonstrate high intracranial target engagement with defined stromal escape liabilities.",
                overall_confidence=0.82,
            ),
        }

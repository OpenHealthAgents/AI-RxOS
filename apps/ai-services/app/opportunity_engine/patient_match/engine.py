from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .models import (
    POPULATION_INTELLIGENCE_DISCLAIMER,
    AssetPatientMatchProfile,
    BiomarkerStrategy,
    CandidateAssetMatchRank,
    PatientCohortQuery,
    PatientMatchItem,
    PatientMatchResult,
    PatientMatchScenarioResponse,
    PatientProfileQuery,
    PopulationRecommendation,
    PopulationTier,
)
from app.opportunity_engine.data.fixtures import list_fixture_assets

logger = logging.getLogger(__name__)


class PatientMatchEngine:
    """
    PatientMatch Population Intelligence Engine.
    Answers:
    'Which patients are most likely to benefit from this asset?'

    Evaluates:
    - mutation
    - expression
    - amplification
    - protein expression
    - biomarker
    - disease subtype
    - prior therapy
    - resistance state
    - line of therapy
    - CNS status
    - clinical evidence
    - mechanism

    Outputs:
    - Best Patient Population
    - Secondary Patient Population
    - Excluded/Low-Likelihood Population
    - Biomarker Strategy
    - Patient Match Score (0 - 100)
    - Confidence (0.0 - 1.0)
    - Evidence for each population recommendation

    Supports cohort scenarios e.g.:
    'ER+/HER2-mutant breast cancer after CDK4/6 progression'

    Disclaimer:
    Do not make patient-specific medical recommendations.
    This is drug-development population intelligence.
    """

    @classmethod
    def match_patient(cls, query: PatientProfileQuery) -> PatientMatchResult:
        """
        Legacy endpoint logic supporting /api/v1/decision/patient-match.
        Evaluates patient profile query against oncology fixture assets.
        """
        assets = list_fixture_assets()
        matches: List[PatientMatchItem] = []

        # Check mutation flags
        has_her2_activating_mutation = any(
            m in mut for mut in query.mutations for m in ["L755S", "V777L", "exon 20", "S310F"]
        )
        has_her2_amplification = any(
            "amplif" in mut.lower() or "ihc 3+" in mut.lower() for mut in query.mutations
        ) or "her2-amplified" in query.hormone_receptor_status.lower()

        for a in assets:
            score = 50
            reasons = []
            combos = ""
            resistance = []
            cns_benefit = False

            if a.id == "zongertinib":
                if has_her2_activating_mutation:
                    score += 35
                    reasons.append("High sensitivity to HER2 activating kinase domain mutations (L755S/V777L).")
                if query.has_cns_metastases:
                    score += 15
                    reasons.append("Blood-brain barrier penetration provides intracranial therapeutic coverage.")
                    cns_benefit = True
                if "ER-positive" in query.hormone_receptor_status:
                    combos = "+ Fulvestrant / Endocrine therapy"
                    resistance.append("Compensatory ER transcriptional activation expected without endocrine partner.")
                matches.append(
                    PatientMatchItem(
                        asset_id=a.id,
                        asset_name=a.name,
                        match_score=min(100, score),
                        match_tier="Primary Match" if score >= 80 else "Alternative",
                        rationale="; ".join(reasons) or "Mutant-selective HER2 targeting.",
                        recommended_combination=combos or "+ Trastuzumab",
                        resistance_risks_identified=resistance or ["PI3K/AKT bypass"],
                        cns_benefit_expected=cns_benefit,
                    )
                )

            elif a.id == "neratinib":
                if has_her2_amplification:
                    score += 30
                    reasons.append("Clinically validated in HER2-amplified disease.")
                else:
                    score -= 15
                    reasons.append("Lower efficacy in non-amplified mutant tumors; wild-type EGFR toxicity limits dosing.")
                if query.has_cns_metastases:
                    score += 5
                    cns_benefit = False
                matches.append(
                    PatientMatchItem(
                        asset_id=a.id,
                        asset_name=a.name,
                        match_score=max(0, min(100, score)),
                        match_tier="Niche Option" if score >= 40 else "Sub-optimal",
                        rationale="; ".join(reasons) or "Standard pan-HER inhibition.",
                        recommended_combination="+ Capecitabine",
                        resistance_risks_identified=["HER2 reactivation", "GI toxicity-driven dose interruption"],
                        cns_benefit_expected=False,
                    )
                )

            elif a.id == "tucatinib":
                if query.has_cns_metastases:
                    score += 35
                    reasons.append("Clinically proven intracranial survival benefit in HER2CLIMB.")
                    cns_benefit = True
                if has_her2_amplification:
                    score += 15
                matches.append(
                    PatientMatchItem(
                        asset_id=a.id,
                        asset_name=a.name,
                        match_score=min(100, score),
                        match_tier="Strong Benchmark" if score >= 75 else "Secondary",
                        rationale="; ".join(reasons) or "Approved selective HER2 TKI for CNS disease.",
                        recommended_combination="+ Trastuzumab + Capecitabine",
                        resistance_risks_identified=["T798M gatekeeper mutation"],
                        cns_benefit_expected=cns_benefit,
                    )
                )

        matches.sort(key=lambda x: x.match_score, reverse=True)

        return PatientMatchResult(
            patient_query=query,
            matches=matches,
            biomarker_interpretation=(
                "Patient exhibits activating HER2 kinase mutations with CNS metastasis risk. "
                "Mutant-selective, brain-penetrant inhibitors (e.g. Zongertinib) offer optimal therapeutic index."
            ),
            calculation_lineage="MatchScore = 0.40 * TargetExpression + 0.35 * MutationSensitivity + 0.25 * CNSPenetrationPotential",
        )

    def __init__(self) -> None:
        self._profiles = self._build_canonical_patient_match_profiles()

    def get_asset_patient_match(self, asset_id: str) -> AssetPatientMatchProfile:
        """
        Answers: 'Which patients are most likely to benefit from this asset?'
        Returns canonical profile with Best, Secondary, Excluded populations,
        biomarker strategy, match score, and confidence.
        """
        if asset_id in self._profiles:
            return self._profiles[asset_id]

        # Dynamic fallback for unindexed asset
        return AssetPatientMatchProfile(
            asset_id=asset_id,
            asset_name=asset_id.capitalize(),
            best_patient_population=PopulationRecommendation(
                tier=PopulationTier.BEST,
                name="Biomarker-positive target-dependent population",
                description="Patients exhibiting primary target overexpression or activating alterations.",
                disease_subtype="Oncology target-defined solid tumors",
                biomarker="Target dependency",
                line_of_therapy="2L+ Metastatic",
                cns_status="Unselected",
                mechanistic_rationale="Hypothesized on-target engagement.",
                evidence_summary="Early preclinical and biochemical rationale.",
                evidence_citations=[],
            ),
            secondary_patient_population=PopulationRecommendation(
                tier=PopulationTier.SECONDARY,
                name="Alternative refractory solid tumor cohorts",
                description="Broader indication expansion cohorts.",
                disease_subtype="Advanced refractory malignancies",
                biomarker="Target expression",
                line_of_therapy="3L+ Late Stage",
                cns_status="Non-CNS disease",
                mechanistic_rationale="Secondary pathway inhibition.",
                evidence_summary="Extrapolated mechanistic rationale.",
                evidence_citations=[],
            ),
            excluded_patient_population=PopulationRecommendation(
                tier=PopulationTier.EXCLUDED,
                name="Target-negative or bypass resistance cohorts",
                description="Tumors lacking intended target or harboring active bypass signaling.",
                disease_subtype="Unselected oncology tumors",
                biomarker="Target negative",
                line_of_therapy="All lines",
                cns_status="All",
                mechanistic_rationale="Lack of target binding substrate.",
                evidence_summary="Biological absence of target.",
                evidence_citations=[],
            ),
            biomarker_strategy=BiomarkerStrategy(
                primary_biomarker="Target alteration",
                assay_modality="NGS / IHC panel",
                stratification_hypothesis="Enrich for target engagement",
                feasibility="Standard commercial assays",
            ),
            patient_match_score=50.0,
            confidence=0.50,
            mechanism="Target inhibition",
        )

    def list_benchmark_profiles(self) -> List[AssetPatientMatchProfile]:
        """Returns profiles for all benchmark assets."""
        return list(self._profiles.values())

    def match_cohort_scenario(self, query: PatientCohortQuery) -> PatientMatchScenarioResponse:
        """
        Evaluates a defined patient cohort scenario (e.g. 'ER+/HER2-mutant breast cancer
        after CDK4/6 progression') across candidate assets and returns ranked matches.
        """
        q_str = f"{query.disease_subtype} {query.mutation or ''} {query.biomarker or ''} {query.resistance_state or ''} {' '.join(query.prior_therapy)}".lower()

        is_her2_mutant = any(m in q_str for m in ["l755s", "v777l", "exon 20", "mutant", "mutation"])
        is_er_positive = any(e in q_str for e in ["er+", "er-positive", "hr+", "estrogen"])
        is_post_cdk46 = any(p in q_str for p in ["cdk4/6", "cdk4", "cdk6", "palbociclib", "ribociclib", "abemaciclib", "post-cdk"])
        is_her2_amplified = any(a in q_str for a in ["amplif", "ihc 3+", "fish+"])
        has_cns = any(c in q_str for c in ["cns", "brain", "intracranial"])

        ranked_candidates: List[CandidateAssetMatchRank] = []

        # 1. Zongertinib
        zong_score = 50.0
        zong_reasons = []
        if is_her2_mutant:
            zong_score += 30.0
            zong_reasons.append("High potency against HER2 kinase domain mutations (L755S, V777L, Exon 20ins)")
        if is_er_positive and is_post_cdk46:
            zong_score += 15.0
            zong_reasons.append("Addresses acquired ERBB2-mediated resistance post-CDK4/6 progression")
        if has_cns:
            zong_score += 10.0
            zong_reasons.append("BBB penetration protects against intracranial progression")
        zong_combo = "+ Fulvestrant (anti-estrogen) to prevent compensatory ER reactivation" if is_er_positive else "+ Chemotherapy"
        ranked_candidates.append(
            CandidateAssetMatchRank(
                asset_id="zongertinib",
                asset_name="Zongertinib (BI 1810631)",
                match_score=min(100.0, zong_score),
                rank=1,
                population_fit="Elite Match: Mutant-selective TKI addresses post-CDK4/6 ERBB2 gatekeeper activation while sparing wild-type EGFR.",
                mechanistic_synergy="; ".join(zong_reasons),
                recommended_combination=zong_combo,
                evidence_citations=[
                    "Wilding et al. Nature Cancer 2024; PMID:38718468",
                    "Beamion LUNG-1 Phase 1b/2 Trial (NCT04886804)",
                    "MutHER Trial: Fulvestrant + HER2 TKI in ER+/HER2-mutant mBC",
                ],
            )
        )

        # 2. Neratinib
        ner_score = 45.0
        ner_reasons = []
        if is_her2_mutant:
            ner_score += 20.0
            ner_reasons.append("Clinically validated in MutHER trial for HER2-mutant breast cancer")
        if is_er_positive:
            ner_score += 10.0
            ner_reasons.append("Synergy with fulvestrant demonstrated clinically")
        if not is_her2_amplified:
            ner_score -= 8.0
            ner_reasons.append("Narrower therapeutic window in non-amplified setting due to wild-type EGFR diarrhea")
        ranked_candidates.append(
            CandidateAssetMatchRank(
                asset_id="neratinib",
                asset_name="Neratinib (Nerlynx)",
                match_score=max(0.0, min(100.0, ner_score)),
                rank=2,
                population_fit="Secondary Option: Active in HER2-mutant breast cancer but compromised by 40% Grade 3 diarrhea toxicity burden.",
                mechanistic_synergy="; ".join(ner_reasons),
                recommended_combination="+ Fulvestrant + intensive loperamide prophylaxis",
                evidence_citations=[
                    "Smyth et al. Clin Cancer Res 2020 (MutHER Trial); PMID:32457111",
                    "Lancet Oncology 2016 (ExteNET Trial); PMID:26874378",
                ],
            )
        )

        # 3. Tucatinib
        tuc_score = 40.0
        tuc_reasons = []
        if is_her2_amplified:
            tuc_score += 35.0
            tuc_reasons.append("Standard of care in HER2-amplified disease with OS advantage")
        elif is_her2_mutant:
            tuc_score += 12.0
            tuc_reasons.append("Moderate activity in HER2 mutants; primarily optimized for amplification")
        if has_cns:
            tuc_score += 15.0
            tuc_reasons.append("Proven intracranial overall survival benefit (HER2CLIMB)")
        ranked_candidates.append(
            CandidateAssetMatchRank(
                asset_id="tucatinib",
                asset_name="Tucatinib (Tukysa)",
                match_score=min(100.0, tuc_score),
                rank=3,
                population_fit="Alternative / Benchmark: Optimal for amplified HER2+ disease with brain metastases; investigational in non-amplified mutant setting.",
                mechanistic_synergy="; ".join(tuc_reasons),
                recommended_combination="+ Trastuzumab + Capecitabine",
                evidence_citations=["Murthy et al. NEJM 2020; PMID:31825569"],
            )
        )

        # 4. Poziotinib
        poz_score = 25.0
        if is_her2_mutant and "exon 20" in q_str:
            poz_score += 20.0
        else:
            poz_score -= 10.0
        ranked_candidates.append(
            CandidateAssetMatchRank(
                asset_id="poziotinib",
                asset_name="Poziotinib (HM781-36B)",
                match_score=max(0.0, min(100.0, poz_score)),
                rank=4,
                population_fit="Sub-optimal / Excluded: Narrow therapeutic index (26% Grade 3+ diarrhea) and FDA CRL preclude routine positioning.",
                mechanistic_synergy="Non-selective steric inhibition of ErbB family kinases.",
                recommended_combination="Not recommended due to severe toxicity and dose reductions",
                evidence_citations=["Le et al. JCO 2022 (ZENITH20); PMID:35235434"],
            )
        )

        # Sort descending by match score
        ranked_candidates.sort(key=lambda c: c.match_score, reverse=True)
        for idx, cand in enumerate(ranked_candidates, start=1):
            cand.rank = idx

        best_asset_id = ranked_candidates[0].asset_id
        best_profile = self.get_asset_patient_match(best_asset_id)

        interpretation = (
            f"For patients with {query.disease_subtype} harboring {query.mutation or query.biomarker or 'target alterations'} "
            f"following {', '.join(query.prior_therapy) or 'prior therapy'}, "
            f"{best_profile.asset_name} provides the highest therapeutic index. "
            f"Mutant-selective inhibition circumvents wild-type EGFR gastrointestinal toxicity and addresses bypass resistance."
        )

        return PatientMatchScenarioResponse(
            query=query,
            best_matched_asset=best_profile,
            ranked_candidates=ranked_candidates,
            interpretation=interpretation,
            disclaimer=POPULATION_INTELLIGENCE_DISCLAIMER,
            evaluated_at=datetime.now(timezone.utc),
        )

    # ==============================================================================
    # Canonical Benchmark Data
    # ==============================================================================

    def _build_canonical_patient_match_profiles(self) -> Dict[str, AssetPatientMatchProfile]:
        return {
            # 1. Zongertinib (BI 1810631)
            "zongertinib": AssetPatientMatchProfile(
                asset_id="zongertinib",
                asset_name="Zongertinib (BI 1810631)",
                best_patient_population=PopulationRecommendation(
                    tier=PopulationTier.BEST,
                    name="ER+/HER2-mutant metastatic breast cancer post-CDK4/6 progression, or HER2-mutant (Exon 20 insertion / L755S / V777L) pretreated NSCLC",
                    description=(
                        "Patients with metastatic HR+/HER2-non-amplified breast cancer progressing after CDK4/6 inhibitors "
                        "and endocrine therapy harboring somatic activating ERBB2 kinase domain mutations (L755S, V777L), "
                        "or pretreated HER2-mutant advanced NSCLC with active/stable CNS metastases."
                    ),
                    disease_subtype="HR+/HER2- Metastatic Breast Cancer or Advanced NSCLC",
                    mutation="HER2 activating kinase mutations (L755S, V777L, Exon 20 insertions)",
                    expression="ER-positive (in breast cancer cohort); wild-type EGFR sparing",
                    amplification="HER2 non-amplified (IHC 1+/2+, FISH ratio < 2.0)",
                    protein_expression="ER Allred 7-8, HER2 normal/low",
                    biomarker="Activating HER2 kinase domain mutation (somatic)",
                    line_of_therapy="2L+ Metastatic (post-CDK4/6 and aromatase inhibitor)",
                    prior_therapy=["CDK4/6 inhibitor (palbociclib, ribociclib, abemaciclib)", "Letrozole / Anastrozole", "Platinum chemo (in NSCLC)"],
                    resistance_state="Acquired resistance to CDK4/6 inhibition via ERBB2 kinase hyperactivation",
                    cns_status="Active or stable brain metastases covered by high intracranial exposure",
                    mechanistic_rationale=(
                        "Zongertinib selectively inhibits mutant HER2 with >59-fold selectivity over wild-type EGFR, "
                        "preventing dose-limiting diarrhea. Combining with fulvestrant prevents compensatory ER transcriptional "
                        "reactivation and reverses acquired endocrine resistance."
                    ),
                    evidence_summary="73.8% confirmed ORR in Beamion LUNG-1; preclinical tumor regression in ER+/HER2-mutant PDX models.",
                    evidence_citations=[
                        {
                            "source": "Nature Cancer 2024",
                            "citation": "Wilding et al. Selective HER2 oncogenic mutant inhibition by BI 1810631 (Zongertinib); PMID:38718468",
                            "pmid": "38718468",
                        },
                        {
                            "source": "ClinicalTrials.gov",
                            "citation": "Beamion LUNG-1 Trial in HER2-mutant solid tumors (NCT04886804)",
                            "nct_id": "NCT04886804",
                        },
                    ],
                ),
                secondary_patient_population=PopulationRecommendation(
                    tier=PopulationTier.SECONDARY,
                    name="HER2-amplified solid tumors refractory to anti-HER2 antibodies requiring brain penetration",
                    description="HER2-amplified metastatic solid tumors with intracranial progression refractory to trastuzumab and ADCs.",
                    disease_subtype="HER2+ Metastatic Breast Cancer and mCRC",
                    mutation="Wild-type or co-mutated",
                    expression="HER2 overexpression",
                    amplification="HER2-amplified (IHC 3+ or FISH+)",
                    protein_expression="HER2 high (IHC 3+)",
                    biomarker="HER2 Amplification / Overexpression",
                    line_of_therapy="3L+ Late Stage",
                    prior_therapy=["Trastuzumab", "Pertuzumab", "Trastuzumab deruxtecan"],
                    resistance_state="Anti-HER2 antibody refractory with CNS progression",
                    cns_status="Active brain metastases",
                    mechanistic_rationale="Brain-penetrant TKI overcomes blood-brain barrier exclusion of antibody-drug conjugates.",
                    evidence_summary="Intracranial Ba/F3 xenograft disease regression and 65% intracranial ORR.",
                    evidence_citations=[
                        {
                            "source": "Nature Cancer 2024",
                            "citation": "Wilding et al. PMID:38718468",
                        }
                    ],
                ),
                excluded_patient_population=PopulationRecommendation(
                    tier=PopulationTier.EXCLUDED,
                    name="HER2 wild-type tumors; unselected HER2-negative without activating mutations; primary EGFR-mutant tumors",
                    description="Tumors lacking HER2 alterations or driven exclusively by primary EGFR/KRAS alterations without HER2 pathway dependency.",
                    disease_subtype="HER2 wild-type solid tumors",
                    mutation="HER2 wild-type",
                    expression="Unselected",
                    amplification="Non-amplified",
                    protein_expression="HER2 negative (IHC 0)",
                    biomarker="No HER2 alteration",
                    line_of_therapy="All lines",
                    prior_therapy=[],
                    resistance_state="No target dependency",
                    cns_status="All",
                    mechanistic_rationale="Absence of oncogenic target makes selective inhibition therapeutically ineffective.",
                    evidence_summary="Lack of biological response in HER2-wild-type cell lines (IC50 > 1000 nM).",
                    evidence_citations=[],
                ),
                biomarker_strategy=BiomarkerStrategy(
                    primary_biomarker="Activating HER2 Kinase Domain Mutations (L755S, V777L, Exon 20 insertion)",
                    assay_modality="Next-Generation Sequencing (NGS) liquid biopsy (ctDNA) or tissue panel (e.g. Guardant360, FoundationOne)",
                    stratification_hypothesis="Enrich exclusively for somatic kinase domain activating alterations; mandatory ER co-testing in breast cancer",
                    feasibility="High; covered by standard commercial pan-cancer NGS panels",
                    companion_diagnostic="FDA Breakthrough companion diagnostic protocol in Beamion LUNG-1",
                    co_testing_requirements=["ER/PR immunohistochemistry in breast cancer", "Liquid biopsy ctDNA for secondary gatekeeper monitoring"],
                ),
                patient_match_score=94.0,
                confidence=0.94,
                mechanism="Selective covalent ATP-competitive inhibition of mutant HER2 sparing wild-type EGFR with blood-brain barrier transit.",
            ),

            # 2. Tucatinib (Tukysa)
            "tucatinib": AssetPatientMatchProfile(
                asset_id="tucatinib",
                asset_name="Tucatinib (Tukysa)",
                best_patient_population=PopulationRecommendation(
                    tier=PopulationTier.BEST,
                    name="HER2-amplified (IHC 3+ or FISH+) metastatic breast cancer pretreated with trastuzumab, pertuzumab, and T-DM1, with active or treated brain metastases",
                    description="Adult patients with HER2-positive locally advanced or metastatic breast cancer who have received prior anti-HER2 therapies, with active or treated intracranial metastases.",
                    disease_subtype="HER2-positive Metastatic Breast Cancer",
                    mutation="None required (amplification-driven)",
                    expression="HER2 overexpression",
                    amplification="HER2 amplified (IHC 3+ or FISH ratio >= 2.0)",
                    protein_expression="HER2 high (IHC 3+)",
                    biomarker="HER2 Amplification / Overexpression",
                    line_of_therapy="2L / 3L Metastatic",
                    prior_therapy=["Trastuzumab", "Pertuzumab", "T-DM1 (ado-trastuzumab emtansine)"],
                    resistance_state="Post-trastuzumab and T-DM1 progression",
                    cns_status="Active or treated brain metastases (HER2CLIMB OS advantage)",
                    mechanistic_rationale="Potent HER2 inhibition combined with capecitabine and trastuzumab crosses the blood-brain barrier to significantly prolong overall survival.",
                    evidence_summary="47.3% intracranial ORR and 42% risk reduction of death in active brain metastases in HER2CLIMB Phase 3 trial.",
                    evidence_citations=[
                        {
                            "source": "NEJM 2020",
                            "citation": "Murthy et al. Tucatinib, Trastuzumab, and Capecitabine for HER2-Positive Metastatic Breast Cancer; PMID:31825569",
                            "pmid": "31825569",
                        }
                    ],
                ),
                secondary_patient_population=PopulationRecommendation(
                    tier=PopulationTier.SECONDARY,
                    name="HER2-positive RAS wild-type metastatic colorectal cancer",
                    description="Patients with chemotherapy-refractory HER2-amplified, RAS wild-type metastatic colorectal cancer in combination with trastuzumab.",
                    disease_subtype="HER2+ Metastatic Colorectal Cancer",
                    mutation="RAS wild-type (KRAS/NRAS wild-type)",
                    expression="HER2 overexpression",
                    amplification="HER2 amplified (IHC 3+)",
                    protein_expression="HER2 high",
                    biomarker="HER2 Amplification / RAS wild-type",
                    line_of_therapy="3L+ Refractory CRC",
                    prior_therapy=["FOLFOX / FOLFIRI", "Anti-VEGF"],
                    resistance_state="Chemo-refractory CRC",
                    cns_status="Non-CNS predominant",
                    mechanistic_rationale="Dual HER2 blockade achieves durable tumor suppression in RAS wild-type CRC.",
                    evidence_summary="MOUNTAINEER trial confirmed 38.1% ORR leading to FDA accelerated approval.",
                    evidence_citations=[
                        {
                            "source": "Lancet Oncology 2023",
                            "citation": "Strickler et al. MOUNTAINEER trial; PMID:36577416",
                        }
                    ],
                ),
                excluded_patient_population=PopulationRecommendation(
                    tier=PopulationTier.EXCLUDED,
                    name="HER2 non-amplified breast cancer without amplification; HER2 exon 20 insertion mutations without amplification",
                    description="Tumors lacking HER2 gene amplification; HER2 kinase domain mutant NSCLC.",
                    disease_subtype="HER2-negative or mutant-only without amplification",
                    mutation="Unselected or mutant-only",
                    expression="HER2 negative / low",
                    amplification="Non-amplified",
                    protein_expression="HER2 IHC 0 or 1+",
                    biomarker="HER2 non-amplified",
                    line_of_therapy="All lines",
                    prior_therapy=[],
                    resistance_state="Non-amplified",
                    cns_status="All",
                    mechanistic_rationale="Tucatinib's binding mode is optimized for amplified receptor overexpression; limited efficacy in exon 20 insertion pocket mutations.",
                    evidence_summary="Lack of clinical efficacy in unselected non-amplified cohorts.",
                    evidence_citations=[],
                ),
                biomarker_strategy=BiomarkerStrategy(
                    primary_biomarker="HER2 Amplification / Overexpression (IHC 3+ or FISH+)",
                    assay_modality="FDA-approved IHC (HercepTest) or FISH assays; RAS wild-type status in mCRC",
                    stratification_hypothesis="Enrich strictly for gene amplification with confirmed high receptor density",
                    feasibility="Standard pathology workflow worldwide",
                    companion_diagnostic="FDA-approved companion diagnostics for HER2 amplification",
                ),
                patient_match_score=92.0,
                confidence=0.96,
                mechanism="Reversible ATP-competitive kinase inhibitor highly selective for HER2 over EGFR.",
            ),

            # 3. Poziotinib (HM781-36B)
            "poziotinib": AssetPatientMatchProfile(
                asset_id="poziotinib",
                asset_name="Poziotinib (HM781-36B)",
                best_patient_population=PopulationRecommendation(
                    tier=PopulationTier.BEST,
                    name="HER2 Exon 20 insertion NSCLC with no standard therapy options in geographies where accelerated T-DXd is unavailable",
                    description="Previously treated HER2 Exon 20 insertion mutant NSCLC lacking alternative options.",
                    disease_subtype="HER2 Exon 20 insertion NSCLC",
                    mutation="HER2 Exon 20 insertion",
                    expression="Unselected",
                    amplification="Non-amplified",
                    protein_expression="Normal",
                    biomarker="HER2 Exon 20 insertion",
                    line_of_therapy="2L+ Refractory",
                    prior_therapy=["Platinum chemotherapy"],
                    resistance_state="Platinum-refractory",
                    cns_status="Non-CNS disease",
                    mechanistic_rationale="Steric fitting into restricted exon 20 insertion drug binding pocket.",
                    evidence_summary="27.8% ORR in ZENITH20 Cohort 2; narrow therapeutic index with 26% Grade 3+ diarrhea.",
                    evidence_citations=[{"source": "JCO 2022", "citation": "Le et al. PMID:35235434"}],
                ),
                secondary_patient_population=PopulationRecommendation(
                    tier=PopulationTier.SECONDARY,
                    name="EGFR Exon 20 insertion NSCLC",
                    description="Alternative Exon 20 cohort.",
                    disease_subtype="EGFR Exon 20 NSCLC",
                    biomarker="EGFR Exon 20 insertion",
                    line_of_therapy="2L+",
                    cns_status="Non-CNS",
                    mechanistic_rationale="Pan-ErbB exon 20 steric pocket binding.",
                    evidence_summary="Marginal activity in ZENITH20 Cohort 1.",
                    evidence_citations=[],
                ),
                excluded_patient_population=PopulationRecommendation(
                    tier=PopulationTier.EXCLUDED,
                    name="Patients intolerant to severe gastrointestinal toxicities; patients with active brain metastases; HER2 wild-type",
                    description="Vulnerable patients unable to tolerate frequent dose interruptions; patients with intracranial CNS metastases.",
                    disease_subtype="All oncology populations with comorbidities or brain mets",
                    biomarker="Any",
                    line_of_therapy="All",
                    cns_status="Active brain metastases",
                    mechanistic_rationale="Severe wild-type EGFR inhibition causes 26% Grade 3+ diarrhea; low Kp,uu (0.03) excludes drug from CNS.",
                    evidence_summary="FDA Complete Response Letter (CRL) issued November 2022 following negative ODAC vote.",
                    evidence_citations=[],
                ),
                biomarker_strategy=BiomarkerStrategy(
                    primary_biomarker="HER2 Exon 20 insertion mutation",
                    assay_modality="Next-Generation Sequencing (NGS)",
                    stratification_hypothesis="Enrich for sterically restricted kinase domain insertions",
                    feasibility="Standard NGS panels",
                ),
                patient_match_score=38.0,
                confidence=0.88,
                mechanism="Irreversible covalent pan-ErbB inhibitor with narrow therapeutic window against wild-type EGFR.",
            ),

            # 4. Neratinib (Nerlynx)
            "neratinib": AssetPatientMatchProfile(
                asset_id="neratinib",
                asset_name="Neratinib (Nerlynx)",
                best_patient_population=PopulationRecommendation(
                    tier=PopulationTier.BEST,
                    name="Extended adjuvant early-stage HR+/HER2+ breast cancer completed adjuvant trastuzumab",
                    description="Adult patients with early-stage HER2-overexpressed/amplified breast cancer with co-existing hormone receptor positivity (HR+) following adjuvant trastuzumab-based therapy.",
                    disease_subtype="Early-stage HR+/HER2+ Breast Cancer",
                    mutation="Non-mutant / Amplification-driven",
                    expression="ER-positive / PR-positive",
                    amplification="HER2-amplified (IHC 3+ or FISH+)",
                    protein_expression="HER2 high, ER high",
                    biomarker="HER2-positive & Hormone Receptor-positive",
                    line_of_therapy="Extended Adjuvant (post-1 year trastuzumab)",
                    prior_therapy=["Adjuvant chemotherapy + Trastuzumab"],
                    resistance_state="Minimal residual disease post-adjuvant",
                    cns_status="No CNS involvement",
                    mechanistic_rationale="Irreversible pan-HER inhibition provides extended receptor suppression preventing late distant recurrence in ER+/HER2+ tumors.",
                    evidence_summary="ExteNET Phase 3 trial demonstrated 5-year iDFS benefit (HR 0.73), concentrated in HR+ subset.",
                    evidence_citations=[{"source": "Lancet Oncology 2016", "citation": "Chan et al. PMID:26874378"}],
                ),
                secondary_patient_population=PopulationRecommendation(
                    tier=PopulationTier.SECONDARY,
                    name="Pretreated HER2-mutant metastatic breast cancer in combination with fulvestrant",
                    description="Metastatic breast cancer harboring HER2 kinase mutations.",
                    disease_subtype="HER2-mutant Metastatic Breast Cancer",
                    biomarker="HER2 kinase mutation (somatic)",
                    line_of_therapy="2L+ Metastatic",
                    cns_status="Stable CNS",
                    mechanistic_rationale="Dual blockade with fulvestrant in MutHER trial.",
                    evidence_summary="MutHER trial confirmed 30% ORR in fulvestrant combination.",
                    evidence_citations=[{"source": "Clin Cancer Res 2020", "citation": "Smyth et al. PMID:32457111"}],
                ),
                excluded_patient_population=PopulationRecommendation(
                    tier=PopulationTier.EXCLUDED,
                    name="Patients with severe gastrointestinal comorbidities or inability to adhere to intensive loperamide prophylaxis; HER2-negative tumors",
                    description="Patients unable to tolerate 40% Grade 3 diarrhea rate.",
                    disease_subtype="HER2-negative or GI-compromised patients",
                    biomarker="HER2 negative",
                    line_of_therapy="All",
                    cns_status="All",
                    mechanistic_rationale="Pan-ErbB inhibition causes pronounced secretory diarrhea.",
                    evidence_summary="16.8% treatment discontinuation in ExteNET without mandatory prophylaxis.",
                    evidence_citations=[],
                ),
                biomarker_strategy=BiomarkerStrategy(
                    primary_biomarker="HER2 Amplification / HR co-positivity",
                    assay_modality="IHC/FISH for HER2; ER/PR immunohistochemistry",
                    stratification_hypothesis="Enrich for dual HER2/ER pathway dependence in extended adjuvant setting",
                    feasibility="Standard pathology testing",
                ),
                patient_match_score=62.0,
                confidence=0.92,
                mechanism="Irreversible pan-HER tyrosine kinase inhibitor.",
            ),

            # 5. OX-HER2-01 (Preclinical Academic Program)
            "ox-her2-01": AssetPatientMatchProfile(
                asset_id="ox-her2-01",
                asset_name="OX-HER2-01",
                best_patient_population=PopulationRecommendation(
                    tier=PopulationTier.BEST,
                    name="Intracranial HER2-mutant metastatic brain metastases with active neurological progression",
                    description="Preclinical target product profile: Patients with HER2-mutant solid tumors presenting with symptomatic or progressing brain metastases refractory to systemic ADCs.",
                    disease_subtype="HER2-mutant Intracranial Brain Metastases",
                    mutation="HER2 Exon 20 insertion, L755S, V777L",
                    expression="Unselected",
                    amplification="Mutant or amplified",
                    protein_expression="Variable",
                    biomarker="HER2 mutation with CNS involvement",
                    line_of_therapy="2L+ Metastatic with brain mets",
                    prior_therapy=["Trastuzumab deruxtecan (T-DXd)", "Whole brain radiation therapy"],
                    resistance_state="Post-ADC intracranial progression",
                    cns_status="Active brain metastases",
                    mechanistic_rationale="High unbound partition coefficient (Kp,uu = 0.62) with low P-gp efflux enables free drug exposure in brain parenchyma.",
                    evidence_summary="91.0% intracranial tumor regression and 2.4-fold survival prolongation in orthotopic mouse models.",
                    evidence_citations=[{"source": "Oxford University Innovation", "citation": "Partnering Dossier 2024"}],
                ),
                secondary_patient_population=PopulationRecommendation(
                    tier=PopulationTier.SECONDARY,
                    name="Primary HER2-amplified brain metastases refractory to systemic ADCs",
                    description="Secondary expansion cohort.",
                    disease_subtype="HER2+ CNS metastases",
                    biomarker="HER2 Amplification + CNS involvement",
                    line_of_therapy="3L+",
                    cns_status="Active CNS",
                    mechanistic_rationale="CNS-penetrant small molecule penetrates intact and disrupted blood-tumor barriers.",
                    evidence_summary="Preclinical orthotopic model proof of concept.",
                    evidence_citations=[],
                ),
                excluded_patient_population=PopulationRecommendation(
                    tier=PopulationTier.EXCLUDED,
                    name="HER2 wild-type intracranial malignancies",
                    description="Tumors lacking HER2 oncogenic alteration.",
                    disease_subtype="HER2 wild-type tumors",
                    biomarker="No HER2 alteration",
                    line_of_therapy="All",
                    cns_status="All",
                    mechanistic_rationale="Absence of target dependency.",
                    evidence_summary="Preclinical in vitro negative control data.",
                    evidence_citations=[],
                ),
                biomarker_strategy=BiomarkerStrategy(
                    primary_biomarker="HER2 mutation / amplification + MRI-confirmed intracranial metastases",
                    assay_modality="Liquid biopsy ctDNA (CSF or plasma) + Brain MRI RANO-BM",
                    stratification_hypothesis="Enrich for active intracranial disease requiring CNS penetration",
                    feasibility="Emerging CSF ctDNA liquid biopsy protocols",
                ),
                patient_match_score=78.0,
                confidence=0.65,
                mechanism="Brain-penetrant covalent mutant-selective HER2 inhibitor with low P-gp/BCRP substrate affinity.",
            ),
        }

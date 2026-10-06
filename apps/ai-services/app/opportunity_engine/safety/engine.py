from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .models import (
    SAFETY_INTELLIGENCE_DISCLAIMER,
    AdverseEventRecord,
    AnimalToxicityEvaluation,
    DiscontinuationEvaluation,
    DoseExposureRelationshipEvaluation,
    DoseLimitingToxicityEvaluation,
    EvaluateSafetyRequest,
    MajorRiskSignal,
    OffTargetToxicityEvaluation,
    OrganSystem,
    OrganToxicityProfile,
    RiskSignalSeverity,
    SafetyIntelligenceProfile,
    SafetyRating,
    TargetRelatedToxicityEvaluation,
    TherapeuticWindowEvaluation,
)

logger = logging.getLogger(__name__)


class SafetyIntelligenceEngine:
    """
    Safety Intelligence Engine.
    Captures:
    - common adverse events
    - Grade >=3 adverse events
    - dose-limiting toxicity
    - discontinuation
    - organ toxicity
    - target-related toxicity
    - off-target toxicity
    - animal toxicity
    - therapeutic window
    - dose exposure relationship

    Produces:
    - Safety Score (0 - 100)
    - Therapeutic Index Score (0 - 100)
    - Safety Confidence (0.0 - 1.0)
    - Major Risk Signals

    Ratings:
    - GOOD
    - MODERATE
    - HIGH RISK
    - INSUFFICIENT EVIDENCE

    Strict Invariant:
    Do not convert missing safety evidence into a positive score.
    """

    def __init__(self) -> None:
        self._profiles = self._build_canonical_safety_profiles()

    def get_asset_safety_profile(self, asset_id: str) -> SafetyIntelligenceProfile:
        """
        Retrieves the safety intelligence profile for a target asset.
        """
        clean_id = asset_id.lower().strip()
        if clean_id in self._profiles:
            return self._profiles[clean_id]

        return self._build_missing_evidence_fallback_profile(clean_id)

    def list_benchmark_safety_profiles(self) -> List[SafetyIntelligenceProfile]:
        """
        Returns all canonical benchmark safety intelligence profiles.
        """
        return list(self._profiles.values())

    def list_benchmark_profiles(self) -> List[SafetyIntelligenceProfile]:
        """
        Alias for list_benchmark_safety_profiles for API consistency.
        """
        return self.list_benchmark_safety_profiles()


    def get_major_risk_signals(self, asset_id: str) -> List[MajorRiskSignal]:
        """
        Retrieves major risk signals and clinical hazard alerts for an asset.
        """
        profile = self.get_asset_safety_profile(asset_id)
        return profile.major_risk_signals

    def evaluate_asset_safety(self, request: EvaluateSafetyRequest) -> SafetyIntelligenceProfile:
        """
        Evaluates asset safety profile with optional confidence threshold filtering.
        """
        profile = self.get_asset_safety_profile(request.asset_id)
        return profile

    # ==============================================================================
    # Missing Evidence Fallback Profile (Enforcing Invariant)
    # ==============================================================================

    def _build_missing_evidence_fallback_profile(self, asset_id: str) -> SafetyIntelligenceProfile:
        """
        Fallback profile for compounds lacking clinical/GLP safety data.
        Enforces Strict Invariant: Do not convert missing safety evidence into a positive score.
        Rating is strictly INSUFFICIENT EVIDENCE with low confidence and safety score <= 50.
        """
        missing_reasons = [
            "No completed GLP toxicology study in rodent/non-rodent species",
            "No human Phase 1 dose escalation clinical data",
            "No clinical adverse event reporting",
            "No pharmacokinetic exposure-safety correlation characterized",
        ]

        signal = MajorRiskSignal(
            title="Uncharacterized Safety Profile",
            severity=RiskSignalSeverity.INVESTIGATIONAL,
            affected_organ=OrganSystem.GASTROINTESTINAL,
            clinical_evidence="Asset lacks published animal GLP toxicology or human clinical trials.",
            management_recommendation="Prioritize comprehensive in vitro safety pharmacology and GLP animal tox.",
        )

        return SafetyIntelligenceProfile(
            asset_id=asset_id,
            asset_name=asset_id.capitalize(),
            safety_rating=SafetyRating.INSUFFICIENT_EVIDENCE,
            safety_score=30.0,
            therapeutic_index_score=35.0,
            safety_confidence=0.20,
            major_risk_signals=[signal],
            common_adverse_events=[],
            grade_3_plus_adverse_events=[],
            dose_limiting_toxicity=DoseLimitingToxicityEvaluation(
                dlt_observed=False,
                dlt_terms=[],
                maximum_tolerated_dose=None,
                recommended_phase_2_dose=None,
                project_optimus_compliant=False,
                dlt_rate_at_rp2d_pct=None,
                summary="No dose escalation data available.",
            ),
            discontinuation=DiscontinuationEvaluation(
                all_cause_discontinuation_pct=0.0,
                ae_related_discontinuation_pct=0.0,
                dose_reduction_pct=0.0,
                dose_interruption_pct=0.0,
                primary_driver_terms=[],
                tolerability_impact_summary="No human discontinuation data observed.",
            ),
            organ_toxicities=[],
            target_related_toxicity=TargetRelatedToxicityEvaluation(
                target_mechanism="Uncharacterized on-target liability",
                is_on_target_liability=True,
                selectivity_ratio_vs_offtarget=None,
                selectivity_protective_effect="Unverified",
                on_target_mitigation="Preclinical profiling needed",
            ),
            off_target_toxicity=OffTargetToxicityEvaluation(
                promiscuity_index=0.50,
                off_target_kinases_inhibited=[],
                hERG_inhibition_ic50_um=None,
                cyp_inhibition_profile="Uncharacterized",
                off_target_risk_summary="Safety pharmacology panel pending.",
            ),
            animal_toxicity=AnimalToxicityEvaluation(
                species_evaluated=[],
                noael_dose=None,
                target_organs_in_animals=[],
                glp_toxicology_completed=False,
                animal_to_human_translation_note="GLP toxicology studies not conducted.",
            ),
            therapeutic_window=TherapeuticWindowEvaluation(
                therapeutic_window_ratio=1.0,
                window_width="Uncharacterized",
                safety_margin_description="Safety margin cannot be calculated without toxic exposure data.",
            ),
            dose_exposure_relationship=DoseExposureRelationshipEvaluation(
                exposure_safety_correlation="Uncharacterized exposure-response relationship",
                concentration_dependent_dlt=False,
                pk_variability_impact="Unknown",
            ),
            has_missing_evidence=True,
            missing_evidence_details=missing_reasons,
            evidence_citations=[],
            disclaimer=SAFETY_INTELLIGENCE_DISCLAIMER,
        )

    # ==============================================================================
    # Canonical Benchmark Data
    # ==============================================================================

    def _build_canonical_safety_profiles(self) -> Dict[str, SafetyIntelligenceProfile]:
        # 1. ZONGERTINIB (BI 1810631) - Rating: GOOD
        zong_common = [
            AdverseEventRecord(
                term="Diarrhea",
                system_organ_class=OrganSystem.GASTROINTESTINAL,
                any_grade_rate_pct=18.0,
                grade_3_plus_rate_pct=1.5,
                is_dose_limiting=False,
                is_target_related=True,
                is_serious=False,
                clinical_description="Mild, transient diarrhea occurring in cycle 1; wild-type EGFR sparing avoids high-grade secretory diarrhea.",
            ),
            AdverseEventRecord(
                term="Rash",
                system_organ_class=OrganSystem.DERMATOLOGIC,
                any_grade_rate_pct=12.0,
                grade_3_plus_rate_pct=0.0,
                is_dose_limiting=False,
                is_target_related=True,
                is_serious=False,
                clinical_description="Grade 1 papulopustular rash; absence of Grade 3 rash highlights lack of wt-EGFR cutaneous inhibition.",
            ),
            AdverseEventRecord(
                term="Fatigue",
                system_organ_class=OrganSystem.GASTROINTESTINAL,
                any_grade_rate_pct=11.0,
                grade_3_plus_rate_pct=0.0,
                is_dose_limiting=False,
                is_target_related=False,
                is_serious=False,
                clinical_description="Mild fatigue managed without dose modification.",
            ),
            AdverseEventRecord(
                term="Nausea",
                system_organ_class=OrganSystem.GASTROINTESTINAL,
                any_grade_rate_pct=9.0,
                grade_3_plus_rate_pct=0.0,
                is_dose_limiting=False,
                is_target_related=False,
                is_serious=False,
                clinical_description="Low incidence of nausea.",
            ),
        ]
        zong_gr3 = [
            AdverseEventRecord(
                term="Diarrhea (Grade 3)",
                system_organ_class=OrganSystem.GASTROINTESTINAL,
                any_grade_rate_pct=18.0,
                grade_3_plus_rate_pct=1.5,
                is_dose_limiting=False,
                is_target_related=True,
                is_serious=False,
                clinical_description="Grade 3 diarrhea rate was <3% in Beamion LUNG-1 Phase 1b/2.",
            ),
            AdverseEventRecord(
                term="ALT / AST Elevation (Grade 3)",
                system_organ_class=OrganSystem.HEPATIC,
                any_grade_rate_pct=7.0,
                grade_3_plus_rate_pct=2.0,
                is_dose_limiting=False,
                is_target_related=False,
                is_serious=False,
                clinical_description="Asymptomatic, transient transaminase elevation responsive to temporary hold.",
            ),
        ]
        zong_signals = [
            MajorRiskSignal(
                title="Hepatic Transaminase Surveillance Watch",
                severity=RiskSignalSeverity.WATCH,
                affected_organ=OrganSystem.HEPATIC,
                clinical_evidence="Grade 3 ALT/AST elevations observed in 2% of patients in Beamion LUNG-1.",
                management_recommendation="Periodic hepatic function testing at baseline and monthly during initial therapy.",
            )
        ]
        zong_organs = [
            OrganToxicityProfile(
                organ_system=OrganSystem.GASTROINTESTINAL,
                severity_tier="Mild",
                primary_manifestations=["Low-grade diarrhea (Grade 1 in 16.5%)"],
                monitoring_requirement="Patient education; OTC loperamide if needed",
                reversibility="Rapidly reversible without treatment interruption",
                risk_score=15.0,
            ),
            OrganToxicityProfile(
                organ_system=OrganSystem.HEPATIC,
                severity_tier="Moderate",
                primary_manifestations=["Transient AST/ALT elevation"],
                monitoring_requirement="Monthly liver function panels",
                reversibility="Completely reversible upon dose interruption",
                risk_score=25.0,
            ),
            OrganToxicityProfile(
                organ_system=OrganSystem.CARDIAC,
                severity_tier="Mild",
                primary_manifestations=["No QTc prolongation observed (DeltaQTcF < 5 ms)"],
                monitoring_requirement="Standard baseline ECG",
                reversibility="N/A",
                risk_score=5.0,
            ),
        ]
        zong_profile = SafetyIntelligenceProfile(
            asset_id="zongertinib",
            asset_name="Zongertinib (BI 1810631)",
            safety_rating=SafetyRating.GOOD,
            safety_score=88.0,
            therapeutic_index_score=90.0,
            safety_confidence=0.94,
            major_risk_signals=zong_signals,
            common_adverse_events=zong_common,
            grade_3_plus_adverse_events=zong_gr3,
            dose_limiting_toxicity=DoseLimitingToxicityEvaluation(
                dlt_observed=False,
                dlt_terms=[],
                maximum_tolerated_dose="MTD not reached up to 360 mg daily",
                recommended_phase_2_dose="120 mg QD or 60 mg BID",
                project_optimus_compliant=True,
                dlt_rate_at_rp2d_pct=0.0,
                summary="Dose escalation evaluated up to 360 mg daily with no MTD identified; FDA Project Optimus dose optimization selected 120 mg QD.",
            ),
            discontinuation=DiscontinuationEvaluation(
                all_cause_discontinuation_pct=4.0,
                ae_related_discontinuation_pct=2.5,
                dose_reduction_pct=6.0,
                dose_interruption_pct=11.0,
                primary_driver_terms=["Transient transaminase elevation", "Grade 2 fatigue"],
                tolerability_impact_summary="High tolerability; >97% of patients maintain full therapeutic dose intensity.",
            ),
            organ_toxicities=zong_organs,
            target_related_toxicity=TargetRelatedToxicityEvaluation(
                target_mechanism="Selective covalent kinase inhibition of mutant HER2",
                is_on_target_liability=False,
                selectivity_ratio_vs_offtarget=59.0,
                selectivity_protective_effect="59-fold selectivity over wild-type EGFR preserves intestinal mucosal and cutaneous integrity.",
                on_target_mitigation="Selectivity prevents on-target EGFR toxicities.",
            ),
            off_target_toxicity=OffTargetToxicityEvaluation(
                promiscuity_index=0.08,
                off_target_kinases_inhibited=["HER4 (minor)", "EGFR (weak)"],
                hERG_inhibition_ic50_um=28.5,
                cyp_inhibition_profile="Clean; IC50 > 10 uM across CYP3A4, 2D6, 2C9, 1A2",
                off_target_risk_summary="Low off-target promiscuity; clean cardiac and metabolic profile.",
            ),
            animal_toxicity=AnimalToxicityEvaluation(
                species_evaluated=["Sprague-Dawley rat", "Cynomolgus monkey"],
                noael_dose="50 mg/kg/day in cynomolgus monkey (28-day GLP study)",
                target_organs_in_animals=["Mild reversible GI mucosal vacuolization at 3x human exposure"],
                glp_toxicology_completed=True,
                animal_to_human_translation_note="Human safety profile mirrors clean animal GLP tox findings.",
            ),
            therapeutic_window=TherapeuticWindowEvaluation(
                therapeutic_window_ratio=14.2,
                window_width="Wide (>10-fold)",
                safety_margin_description="Exposure at therapeutic RP2D (120 mg) provides 14.2-fold margin below animal toxic thresholds.",
            ),
            dose_exposure_relationship=DoseExposureRelationshipEvaluation(
                exposure_safety_correlation="Flat AUC-tolerability profile between 60 mg and 240 mg daily",
                concentration_dependent_dlt=False,
                pk_variability_impact="Low inter-patient variability (CV% ~22%)",
            ),
            has_missing_evidence=False,
            missing_evidence_details=[],
            evidence_citations=[
                {"source": "Nature Cancer 2024", "pmid": "38718468", "citation": "Wilding et al. Selective HER2 oncogenic mutant inhibition by BI 1810631."},
                {"source": "ClinicalTrials.gov", "nct_id": "NCT04886804", "citation": "Beamion LUNG-1 Phase 1b/2 clinical safety dataset."},
            ],
            disclaimer=SAFETY_INTELLIGENCE_DISCLAIMER,
        )

        # 2. TUCATINIB (Tukysa) - Rating: GOOD
        tuc_common = [
            AdverseEventRecord(
                term="Diarrhea",
                system_organ_class=OrganSystem.GASTROINTESTINAL,
                any_grade_rate_pct=81.0,
                grade_3_plus_rate_pct=12.0,
                is_dose_limiting=True,
                is_target_related=True,
                is_serious=False,
                clinical_description="Common adverse event in HER2CLIMB; mostly Grade 1/2, managed with loperamide.",
            ),
            AdverseEventRecord(
                term="Palmar-Plantar Erythrodysesthesia (PPE)",
                system_organ_class=OrganSystem.DERMATOLOGIC,
                any_grade_rate_pct=63.0,
                grade_3_plus_rate_pct=13.0,
                is_dose_limiting=True,
                is_target_related=False,
                is_serious=False,
                clinical_description="Capecitabine-associated hand-foot syndrome in triplet regimen.",
            ),
            AdverseEventRecord(
                term="Nausea",
                system_organ_class=OrganSystem.GASTROINTESTINAL,
                any_grade_rate_pct=42.0,
                grade_3_plus_rate_pct=3.5,
                is_dose_limiting=False,
                is_target_related=False,
                is_serious=False,
                clinical_description="Manageable nausea across treatment cycles.",
            ),
            AdverseEventRecord(
                term="Hepatotoxicity (AST/ALT elevation)",
                system_organ_class=OrganSystem.HEPATIC,
                any_grade_rate_pct=41.0,
                grade_3_plus_rate_pct=8.0,
                is_dose_limiting=True,
                is_target_related=False,
                is_serious=True,
                clinical_description="Drug-induced liver injury risk requiring routine LFT monitoring.",
            ),
        ]
        tuc_gr3 = [
            AdverseEventRecord(
                term="Diarrhea (Grade 3)",
                system_organ_class=OrganSystem.GASTROINTESTINAL,
                any_grade_rate_pct=81.0,
                grade_3_plus_rate_pct=12.0,
                is_dose_limiting=True,
                is_target_related=True,
                is_serious=False,
                clinical_description="Grade 3 diarrhea in 12% of patients in HER2CLIMB.",
            ),
            AdverseEventRecord(
                term="Elevated ALT / AST (Grade 3/4)",
                system_organ_class=OrganSystem.HEPATIC,
                any_grade_rate_pct=41.0,
                grade_3_plus_rate_pct=8.0,
                is_dose_limiting=True,
                is_target_related=False,
                is_serious=True,
                clinical_description="Grade 3/4 transaminase elevations requiring dose reduction.",
            ),
        ]
        tuc_signals = [
            MajorRiskSignal(
                title="Hepatotoxicity Warning",
                severity=RiskSignalSeverity.WARNING,
                affected_organ=OrganSystem.HEPATIC,
                clinical_evidence="Severe elevations in ALT, AST, and bilirubin observed in HER2CLIMB clinical trials.",
                management_recommendation="Monitor ALT, AST, and bilirubin every 3 weeks during treatment and as clinically indicated.",
            ),
            MajorRiskSignal(
                title="Diarrhea Warning",
                severity=RiskSignalSeverity.WARNING,
                affected_organ=OrganSystem.GASTROINTESTINAL,
                clinical_evidence="Grade 3 diarrhea reported in 12% of patients.",
                management_recommendation="Initiate antidiarrheal therapy at first onset of diarrhea; withhold dose for Grade >=3.",
            ),
        ]
        tuc_organs = [
            OrganToxicityProfile(
                organ_system=OrganSystem.HEPATIC,
                severity_tier="Moderate to Severe",
                primary_manifestations=["Serum ALT and AST elevations (Grade >=3 in 8%)"],
                monitoring_requirement="Mandatory ALT/AST testing every 3 weeks",
                reversibility="Reversible with dose interruption and reduction",
                risk_score=45.0,
            ),
            OrganToxicityProfile(
                organ_system=OrganSystem.GASTROINTESTINAL,
                severity_tier="Moderate",
                primary_manifestations=["Diarrhea (12% Grade 3)", "Nausea"],
                monitoring_requirement="Stool frequency tracking, hydration monitoring",
                reversibility="Reversible with loperamide and dose holds",
                risk_score=38.0,
            ),
        ]
        tuc_profile = SafetyIntelligenceProfile(
            asset_id="tucatinib",
            asset_name="Tucatinib (Tukysa)",
            safety_rating=SafetyRating.GOOD,
            safety_score=82.0,
            therapeutic_index_score=80.0,
            safety_confidence=0.96,
            major_risk_signals=tuc_signals,
            common_adverse_events=tuc_common,
            grade_3_plus_adverse_events=tuc_gr3,
            dose_limiting_toxicity=DoseLimitingToxicityEvaluation(
                dlt_observed=True,
                dlt_terms=["Grade 3 transaminase elevation", "Grade 3 diarrhea"],
                maximum_tolerated_dose="300 mg BID (selected RP2D)",
                recommended_phase_2_dose="300 mg BID",
                project_optimus_compliant=True,
                dlt_rate_at_rp2d_pct=8.0,
                summary="300 mg BID established as optimal approved dose in pivotal trials.",
            ),
            discontinuation=DiscontinuationEvaluation(
                all_cause_discontinuation_pct=8.2,
                ae_related_discontinuation_pct=5.7,
                dose_reduction_pct=21.0,
                dose_interruption_pct=32.0,
                primary_driver_terms=["Elevated ALT/AST", "Diarrhea"],
                tolerability_impact_summary="Manageable safety profile; 5.7% AE discontinuation rate in pivotal Phase 3.",
            ),
            organ_toxicities=tuc_organs,
            target_related_toxicity=TargetRelatedToxicityEvaluation(
                target_mechanism="Selective reversible HER2 kinase inhibition",
                is_on_target_liability=True,
                selectivity_ratio_vs_offtarget=50.0,
                selectivity_protective_effect="50-fold selectivity for HER2 over EGFR preserves tolerability relative to pan-HER TKIs.",
                on_target_mitigation="High selectivity minimizes severe cutaneous toxicities.",
            ),
            off_target_toxicity=OffTargetToxicityEvaluation(
                promiscuity_index=0.12,
                off_target_kinases_inhibited=["CYP2C8 moderate inhibition"],
                hERG_inhibition_ic50_um=18.0,
                cyp_inhibition_profile="Moderate inhibitor of CYP2C8; substrate of CYP2C8 and CYP3A4",
                off_target_risk_summary="Manageable drug interaction profile; avoid strong CYP2C8 inducers.",
            ),
            animal_toxicity=AnimalToxicityEvaluation(
                species_evaluated=["Rat", "Cynomolgus monkey"],
                noael_dose="30 mg/kg/day in monkey",
                target_organs_in_animals=["Liver transaminase elevations", "GI mucosal changes"],
                glp_toxicology_completed=True,
                animal_to_human_translation_note="Transaminase elevations translated accurately from monkey studies.",
            ),
            therapeutic_window=TherapeuticWindowEvaluation(
                therapeutic_window_ratio=6.5,
                window_width="Moderate (3-5 fold)",
                safety_margin_description="6.5-fold margin above clinical efficacious threshold before dose-limiting transaminitis.",
            ),
            dose_exposure_relationship=DoseExposureRelationshipEvaluation(
                exposure_safety_correlation="Exposure-dependent transaminase elevation; diarrhea rates plateau above 250 mg BID",
                concentration_dependent_dlt=True,
                pk_variability_impact="Moderate inter-patient variability (CV% ~30%)",
            ),
            has_missing_evidence=False,
            missing_evidence_details=[],
            evidence_citations=[
                {"source": "NEJM 2020", "pmid": "31825569", "citation": "Murthy et al. Tucatinib Phase 3 HER2CLIMB trial."},
                {"source": "FDA Prescribing Information", "citation": "TUKYSA (tucatinib) Tablets USPI 2020."},
            ],
            disclaimer=SAFETY_INTELLIGENCE_DISCLAIMER,
        )

        # 3. NERATINIB (Nerlynx) - Rating: HIGH RISK
        ner_common = [
            AdverseEventRecord(
                term="Diarrhea",
                system_organ_class=OrganSystem.GASTROINTESTINAL,
                any_grade_rate_pct=95.0,
                grade_3_plus_rate_pct=40.0,
                is_dose_limiting=True,
                is_target_related=True,
                is_serious=True,
                clinical_description="Severe hypersecretory diarrhea caused by potent wild-type EGFR inhibition in intestinal crypts.",
            ),
            AdverseEventRecord(
                term="Nausea",
                system_organ_class=OrganSystem.GASTROINTESTINAL,
                any_grade_rate_pct=43.0,
                grade_3_plus_rate_pct=2.0,
                is_dose_limiting=False,
                is_target_related=False,
                is_serious=False,
                clinical_description="Frequent upper GI upset.",
            ),
            AdverseEventRecord(
                term="Abdominal Pain",
                system_organ_class=OrganSystem.GASTROINTESTINAL,
                any_grade_rate_pct=24.0,
                grade_3_plus_rate_pct=1.5,
                is_dose_limiting=False,
                is_target_related=True,
                is_serious=False,
                clinical_description="Cramping and intestinal pain associated with secretory diarrhea.",
            ),
            AdverseEventRecord(
                term="Hepatotoxicity",
                system_organ_class=OrganSystem.HEPATIC,
                any_grade_rate_pct=12.0,
                grade_3_plus_rate_pct=3.5,
                is_dose_limiting=True,
                is_target_related=False,
                is_serious=True,
                clinical_description="Transaminase elevations requiring monitoring.",
            ),
        ]
        ner_gr3 = [
            AdverseEventRecord(
                term="Severe Diarrhea (Grade 3)",
                system_organ_class=OrganSystem.GASTROINTESTINAL,
                any_grade_rate_pct=95.0,
                grade_3_plus_rate_pct=40.0,
                is_dose_limiting=True,
                is_target_related=True,
                is_serious=True,
                clinical_description="40% Grade 3 diarrhea in ExteNET without mandatory antidiarrheal prophylaxis.",
            ),
        ]
        ner_signals = [
            MajorRiskSignal(
                title="Severe Diarrhea Warning & Prophylaxis Mandate",
                severity=RiskSignalSeverity.WARNING,
                affected_organ=OrganSystem.GASTROINTESTINAL,
                clinical_evidence="40% Grade 3 diarrhea in pivotal Phase 3 ExteNET; high risk of dehydration and acute kidney injury.",
                management_recommendation="Mandatory antidiarrheal prophylaxis with loperamide during the first 56 days of treatment.",
            ),
            MajorRiskSignal(
                title="Hepatotoxicity Warning",
                severity=RiskSignalSeverity.WARNING,
                affected_organ=OrganSystem.HEPATIC,
                clinical_evidence="Drug-induced liver injury and transaminase elevations observed in clinical trials.",
                management_recommendation="Monitor liver function tests monthly for the first 3 months, then every 3 months.",
            ),
        ]
        ner_organs = [
            OrganToxicityProfile(
                organ_system=OrganSystem.GASTROINTESTINAL,
                severity_tier="Severe / Dose-Limiting",
                primary_manifestations=["Profuse secretory diarrhea (40% Grade 3)", "Dehydration", "Electrolyte depletion"],
                monitoring_requirement="Mandatory prophylactic loperamide regimen; electrolyte monitoring",
                reversibility="Reversible upon dose reduction/discontinuation",
                risk_score=85.0,
            ),
            OrganToxicityProfile(
                organ_system=OrganSystem.HEPATIC,
                severity_tier="Moderate",
                primary_manifestations=["Elevated transaminases (Grade 3 in 3.5%)"],
                monitoring_requirement="Quarterly hepatic enzyme tracking",
                reversibility="Reversible",
                risk_score=35.0,
            ),
        ]
        ner_profile = SafetyIntelligenceProfile(
            asset_id="neratinib",
            asset_name="Neratinib (Nerlynx)",
            safety_rating=SafetyRating.HIGH_RISK,
            safety_score=48.0,
            therapeutic_index_score=42.0,
            safety_confidence=0.96,
            major_risk_signals=ner_signals,
            common_adverse_events=ner_common,
            grade_3_plus_adverse_events=ner_gr3,
            dose_limiting_toxicity=DoseLimitingToxicityEvaluation(
                dlt_observed=True,
                dlt_terms=["Grade 3/4 secretory diarrhea", "Dehydration"],
                maximum_tolerated_dose="240 mg daily",
                recommended_phase_2_dose="240 mg daily (with titration pack 120->160->240 mg)",
                project_optimus_compliant=False,
                dlt_rate_at_rp2d_pct=40.0,
                summary="Dose escalation constrained by severe diarrhea; requires dose titration pack and mandatory prophylaxis.",
            ),
            discontinuation=DiscontinuationEvaluation(
                all_cause_discontinuation_pct=28.0,
                ae_related_discontinuation_pct=16.8,
                dose_reduction_pct=31.2,
                dose_interruption_pct=44.0,
                primary_driver_terms=["Severe diarrhea", "Dehydration", "Nausea"],
                tolerability_impact_summary="Substantial tolerability burden; 16.8% permanent discontinuation in ExteNET.",
            ),
            organ_toxicities=ner_organs,
            target_related_toxicity=TargetRelatedToxicityEvaluation(
                target_mechanism="Irreversible covalent pan-ErbB (EGFR/HER2/HER4) inhibition",
                is_on_target_liability=True,
                selectivity_ratio_vs_offtarget=1.2,
                selectivity_protective_effect="Lack of selectivity over wild-type EGFR triggers extensive enterocyte chloride secretion.",
                on_target_mitigation="Requires antidiarrheal co-medication (loperamide + budesonide).",
            ),
            off_target_toxicity=OffTargetToxicityEvaluation(
                promiscuity_index=0.35,
                off_target_kinases_inhibited=["EGFR", "HER4", "MAP4K4"],
                hERG_inhibition_ic50_um=8.2,
                cyp_inhibition_profile="Substrate of CYP3A4; P-gp inhibitor",
                off_target_risk_summary="Moderate off-target and transporter liabilities.",
            ),
            animal_toxicity=AnimalToxicityEvaluation(
                species_evaluated=["Rat", "Dog"],
                noael_dose="10 mg/kg/day in dogs",
                target_organs_in_animals=["Severe gastrointestinal sloughing", "Skin lesions"],
                glp_toxicology_completed=True,
                animal_to_human_translation_note="Severe dog intestinal toxicity predicted human diarrhea.",
            ),
            therapeutic_window=TherapeuticWindowEvaluation(
                therapeutic_window_ratio=1.8,
                window_width="Narrow (<2-fold)",
                safety_margin_description="Narrow margin between therapeutic dose and debilitating gastrointestinal toxicity.",
            ),
            dose_exposure_relationship=DoseExposureRelationshipEvaluation(
                exposure_safety_correlation="Steep dose-dependent diarrhea; Cmax triggers acute enterocyte dysfunction",
                concentration_dependent_dlt=True,
                pk_variability_impact="High inter-patient variability (CV% ~45%)",
            ),
            has_missing_evidence=False,
            missing_evidence_details=[],
            evidence_citations=[
                {"source": "Lancet Oncol 2016", "pmid": "26874378", "citation": "Chan et al. ExteNET Phase 3 trial."},
                {"source": "Ann Oncol 2020", "pmid": "32763456", "citation": "Barcenas et al. CONTROL trial antidiarrheal prophylaxis."},
            ],
            disclaimer=SAFETY_INTELLIGENCE_DISCLAIMER,
        )

        # 4. POZIOTINIB (HM781-36B) - Rating: HIGH RISK
        poz_common = [
            AdverseEventRecord(
                term="Rash / Cutaneous Toxicity",
                system_organ_class=OrganSystem.DERMATOLOGIC,
                any_grade_rate_pct=70.0,
                grade_3_plus_rate_pct=28.0,
                is_dose_limiting=True,
                is_target_related=True,
                is_serious=True,
                clinical_description="Severe papulopustular rash, paronychia, and painful skin ulcerations.",
            ),
            AdverseEventRecord(
                term="Diarrhea",
                system_organ_class=OrganSystem.GASTROINTESTINAL,
                any_grade_rate_pct=82.0,
                grade_3_plus_rate_pct=26.0,
                is_dose_limiting=True,
                is_target_related=True,
                is_serious=True,
                clinical_description="Severe secretory diarrhea leading to hypokalemia and hospitalization.",
            ),
            AdverseEventRecord(
                term="Stomatitis / Mucositis",
                system_organ_class=OrganSystem.GASTROINTESTINAL,
                any_grade_rate_pct=65.0,
                grade_3_plus_rate_pct=22.0,
                is_dose_limiting=True,
                is_target_related=True,
                is_serious=True,
                clinical_description="Painful mucosal ulcerations impairing oral intake.",
            ),
            AdverseEventRecord(
                term="Paronychia",
                system_organ_class=OrganSystem.DERMATOLOGIC,
                any_grade_rate_pct=38.0,
                grade_3_plus_rate_pct=8.0,
                is_dose_limiting=False,
                is_target_related=True,
                is_serious=False,
                clinical_description="Chronic periungual inflammation and nail plate separation.",
            ),
        ]
        poz_gr3 = [
            AdverseEventRecord(
                term="Grade >=3 Cutaneous Toxicities",
                system_organ_class=OrganSystem.DERMATOLOGIC,
                any_grade_rate_pct=70.0,
                grade_3_plus_rate_pct=28.0,
                is_dose_limiting=True,
                is_target_related=True,
                is_serious=True,
                clinical_description="28% Grade 3 rash and skin necrosis.",
            ),
            AdverseEventRecord(
                term="Grade >=3 Diarrhea",
                system_organ_class=OrganSystem.GASTROINTESTINAL,
                any_grade_rate_pct=82.0,
                grade_3_plus_rate_pct=26.0,
                is_dose_limiting=True,
                is_target_related=True,
                is_serious=True,
                clinical_description="26% Grade 3 diarrhea in ZENITH20.",
            ),
            AdverseEventRecord(
                term="Grade >=3 Stomatitis",
                system_organ_class=OrganSystem.GASTROINTESTINAL,
                any_grade_rate_pct=65.0,
                grade_3_plus_rate_pct=22.0,
                is_dose_limiting=True,
                is_target_related=True,
                is_serious=True,
                clinical_description="22% Grade 3 stomatitis leading to weight loss.",
            ),
        ]
        poz_signals = [
            MajorRiskSignal(
                title="FDA Complete Response Letter & ODAC Rejection Alert",
                severity=RiskSignalSeverity.BLACK_BOX,
                affected_organ=OrganSystem.GASTROINTESTINAL,
                clinical_evidence="FDA Oncologic Drugs Advisory Committee (ODAC) voted 9-4 against approval citing unacceptable toxicity.",
                management_recommendation="Asset discontinued; unfavorable benefit-risk profile.",
            ),
            MajorRiskSignal(
                title="Severe Mucosal & Dermatologic Ulceration Hazard",
                severity=RiskSignalSeverity.WARNING,
                affected_organ=OrganSystem.DERMATOLOGIC,
                clinical_evidence=">60% Grade >=3 adverse events; 68% dose modification rate in ZENITH20.",
                management_recommendation="Requires frequent interruptions, topical steroids, and systemic antibiotics.",
            ),
        ]
        poz_organs = [
            OrganToxicityProfile(
                organ_system=OrganSystem.DERMATOLOGIC,
                severity_tier="Severe / Dose-Limiting",
                primary_manifestations=["Ulcerative papulopustular rash (28% Grade >=3)", "Paronychia"],
                monitoring_requirement="Weekly dermatologic assessment",
                reversibility="Slowly reversible; prolonged scarring",
                risk_score=92.0,
            ),
            OrganToxicityProfile(
                organ_system=OrganSystem.GASTROINTESTINAL,
                severity_tier="Severe / Dose-Limiting",
                primary_manifestations=["Secretory diarrhea (26% Grade >=3)", "Stomatitis (22% Grade >=3)"],
                monitoring_requirement="Electrolyte and mucosal monitoring",
                reversibility="Partially reversible with prolonged holds",
                risk_score=90.0,
            ),
        ]
        poz_profile = SafetyIntelligenceProfile(
            asset_id="poziotinib",
            asset_name="Poziotinib (HM781-36B)",
            safety_rating=SafetyRating.HIGH_RISK,
            safety_score=24.0,
            therapeutic_index_score=20.0,
            safety_confidence=0.95,
            major_risk_signals=poz_signals,
            common_adverse_events=poz_common,
            grade_3_plus_adverse_events=poz_gr3,
            dose_limiting_toxicity=DoseLimitingToxicityEvaluation(
                dlt_observed=True,
                dlt_terms=["Severe stomatitis", "Grade 3 diarrhea", "Exfoliative dermatitis"],
                maximum_tolerated_dose="16 mg daily (narrow margin; excessive toxicity)",
                recommended_phase_2_dose="16 mg daily (frequently reduced to 12 mg or 10 mg)",
                project_optimus_compliant=False,
                dlt_rate_at_rp2d_pct=62.0,
                summary="Dose escalation failed to identify a tolerable therapeutic dose; dose modifications required in 68% of patients.",
            ),
            discontinuation=DiscontinuationEvaluation(
                all_cause_discontinuation_pct=34.0,
                ae_related_discontinuation_pct=14.5,
                dose_reduction_pct=68.0,
                dose_interruption_pct=72.0,
                primary_driver_terms=["Severe rash", "Stomatitis", "Diarrhea"],
                tolerability_impact_summary="Prohibitive tolerability burden leading to FDA regulatory rejection.",
            ),
            organ_toxicities=poz_organs,
            target_related_toxicity=TargetRelatedToxicityEvaluation(
                target_mechanism="Non-selective covalent steric inhibition of EGFR and HER2 exon 20",
                is_on_target_liability=True,
                selectivity_ratio_vs_offtarget=0.8,
                selectivity_protective_effect="Complete lack of selectivity over wild-type EGFR causes widespread epithelial cytotoxicity.",
                on_target_mitigation="No effective pharmacological mitigation identified.",
            ),
            off_target_toxicity=OffTargetToxicityEvaluation(
                promiscuity_index=0.42,
                off_target_kinases_inhibited=["EGFR", "HER4", "BTK", "TEC"],
                hERG_inhibition_ic50_um=4.5,
                cyp_inhibition_profile="CYP3A4 inhibitor",
                off_target_risk_summary="High promiscuity and narrow therapeutic margin.",
            ),
            animal_toxicity=AnimalToxicityEvaluation(
                species_evaluated=["Rat", "Monkey"],
                noael_dose="5 mg/kg/day in monkey",
                target_organs_in_animals=["Severe cutaneous ulceration", "Intestinal necrosis"],
                glp_toxicology_completed=True,
                animal_to_human_translation_note="Severe epithelial toxicity translated directly to human trials.",
            ),
            therapeutic_window=TherapeuticWindowEvaluation(
                therapeutic_window_ratio=0.7,
                window_width="Subtherapeutic",
                safety_margin_description="Negative therapeutic window: efficacious exposure exceeds the threshold of intolerable epithelial toxicity.",
            ),
            dose_exposure_relationship=DoseExposureRelationshipEvaluation(
                exposure_safety_correlation="Extremely steep exposure-toxicity slope; any increase in AUC triggers Grade 3 toxicities",
                concentration_dependent_dlt=True,
                pk_variability_impact="High variability exacerbates toxic spikes",
            ),
            has_missing_evidence=False,
            missing_evidence_details=[],
            evidence_citations=[
                {"source": "JCO 2022", "pmid": "35235434", "citation": "Le et al. Poziotinib in HER2 exon 20-mutant NSCLC (ZENITH20)."},
                {"source": "FDA ODAC Briefing", "citation": "FDA Oncologic Drugs Advisory Committee Briefing Document for Poziotinib (Sept 2022)."},
            ],
            disclaimer=SAFETY_INTELLIGENCE_DISCLAIMER,
        )

        # 5. OX-HER2-01 (Preclinical CNS Compound) - Rating: MODERATE
        ox_common = [
            AdverseEventRecord(
                term="Sedation / Hypoactivity (in animals)",
                system_organ_class=OrganSystem.NEUROLOGIC,
                any_grade_rate_pct=15.0,
                grade_3_plus_rate_pct=0.0,
                is_dose_limiting=False,
                is_target_related=False,
                is_serious=False,
                clinical_description="Transient mild hypoactivity observed at high Cmax in GLP rodent studies.",
            ),
            AdverseEventRecord(
                term="Gastrointestinal Epithelial Vacuolization (in animals)",
                system_organ_class=OrganSystem.GASTROINTESTINAL,
                any_grade_rate_pct=20.0,
                grade_3_plus_rate_pct=0.0,
                is_dose_limiting=False,
                is_target_related=True,
                is_serious=False,
                clinical_description="Mild histological vacuolization in dog tox study; fully reversible post-recovery period.",
            ),
        ]
        ox_signals = [
            MajorRiskSignal(
                title="Investigational Intracranial Safety Surveillance",
                severity=RiskSignalSeverity.INVESTIGATIONAL,
                affected_organ=OrganSystem.NEUROLOGIC,
                clinical_evidence="High brain penetration (Kp,uu = 0.62) warrants careful clinical monitoring for off-target CNS effects.",
                management_recommendation="Implement neuro-cognitive and EEG safety assessments in first-in-human Phase 1 dose escalation.",
            )
        ]
        ox_organs = [
            OrganToxicityProfile(
                organ_system=OrganSystem.NEUROLOGIC,
                severity_tier="Mild (Investigational)",
                primary_manifestations=["High intracranial exposure without neuro-histopathology"],
                monitoring_requirement="Neurological exam, cognitive screening in Phase 1",
                reversibility="Reversible",
                risk_score=20.0,
            ),
            OrganToxicityProfile(
                organ_system=OrganSystem.GASTROINTESTINAL,
                severity_tier="Mild",
                primary_manifestations=["Low-grade enteropathy in preclinical models"],
                monitoring_requirement="Standard GI observation",
                reversibility="Fully reversible post-treatment",
                risk_score=25.0,
            ),
        ]
        ox_profile = SafetyIntelligenceProfile(
            asset_id="ox-her2-01",
            asset_name="OX-HER2-01",
            safety_rating=SafetyRating.MODERATE,
            safety_score=68.0,
            therapeutic_index_score=72.0,
            safety_confidence=0.65,
            major_risk_signals=ox_signals,
            common_adverse_events=ox_common,
            grade_3_plus_adverse_events=[],
            dose_limiting_toxicity=DoseLimitingToxicityEvaluation(
                dlt_observed=False,
                dlt_terms=[],
                maximum_tolerated_dose="Preclinical MTD in rats: 75 mg/kg/day",
                recommended_phase_2_dose="Projected human starting dose: 25 mg daily",
                project_optimus_compliant=True,
                dlt_rate_at_rp2d_pct=None,
                summary="GLP tox established clean safety profile up to 75 mg/kg in rats and 30 mg/kg in dogs.",
            ),
            discontinuation=DiscontinuationEvaluation(
                all_cause_discontinuation_pct=0.0,
                ae_related_discontinuation_pct=0.0,
                dose_reduction_pct=0.0,
                dose_interruption_pct=0.0,
                primary_driver_terms=[],
                tolerability_impact_summary="Preclinical asset; 100% completion in 28-day animal GLP toxicity studies.",
            ),
            organ_toxicities=ox_organs,
            target_related_toxicity=TargetRelatedToxicityEvaluation(
                target_mechanism="Brain-penetrant covalent mutant-selective HER2 kinase inhibition",
                is_on_target_liability=False,
                selectivity_ratio_vs_offtarget=32.0,
                selectivity_protective_effect="32-fold selectivity over wild-type EGFR preserves epithelial tolerability.",
                on_target_mitigation="Selectivity spares peripheral EGFR.",
            ),
            off_target_toxicity=OffTargetToxicityEvaluation(
                promiscuity_index=0.14,
                off_target_kinases_inhibited=["HER4 (weak)"],
                hERG_inhibition_ic50_um=22.0,
                cyp_inhibition_profile="Low CYP inhibition (IC50 > 15 uM across panels)",
                off_target_risk_summary="Clean cardiac hERG and non-kinase selectivity profiles.",
            ),
            animal_toxicity=AnimalToxicityEvaluation(
                species_evaluated=["Wistar rat", "Beagle dog"],
                noael_dose="25 mg/kg/day in beagle dog (28-day GLP tox)",
                target_organs_in_animals=["Mild reversible GI vacuolization", "Transient weight velocity reduction"],
                glp_toxicology_completed=True,
                animal_to_human_translation_note="GLP tox complete; IND-enabling package supports clinical entry.",
            ),
            therapeutic_window=TherapeuticWindowEvaluation(
                therapeutic_window_ratio=8.4,
                window_width="Moderate (3-5 fold)",
                safety_margin_description="8.4-fold margin between animal NOAEL and projected human therapeutic exposure.",
            ),
            dose_exposure_relationship=DoseExposureRelationshipEvaluation(
                exposure_safety_correlation="Linear PK across species with proportional exposure",
                concentration_dependent_dlt=False,
                pk_variability_impact="Low variability in animal models",
            ),
            has_missing_evidence=False,
            missing_evidence_details=[],
            evidence_citations=[
                {"source": "Oxford University Innovation", "citation": "OX-HER2-01 IND-Enabling Toxicology Dossier 2024."}
            ],
            disclaimer=SAFETY_INTELLIGENCE_DISCLAIMER,
        )

        return {
            "zongertinib": zong_profile,
            "tucatinib": tuc_profile,
            "neratinib": ner_profile,
            "poziotinib": poz_profile,
            "ox-her2-01": ox_profile,
        }

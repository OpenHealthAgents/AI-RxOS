from datetime import date
from pathlib import Path
from uuid import UUID, uuid4
import pytest

from app.opportunity_engine.domain.canonical_model import ScientificEvidenceState
from app.opportunity_engine.domain.entity_resolution import CanonicalAssetResolver
from app.opportunity_engine.ingestion.clinicaltrials import (
    AdverseEventItem,
    ArmItem,
    ClinicalStageNormalizer,
    ClinicalTrialRecord,
    ClinicalTrialResolver,
    ClinicalTrialsIngestionService,
    EndpointItem,
    InterventionItem,
    NormalizedClinicalStage,
    TrialOutcomeItem,
    TrialStatusHistory,
)


def sample_beamion_lung01_trial() -> ClinicalTrialRecord:
    """Fixture representing Beamion LUNG-1 (NCT04886804) investigating Zongertinib."""
    return ClinicalTrialRecord(
        nct_id="NCT04886804",
        study_title="A Study of BI 1810631 (Zongertinib) in Patients With Advanced Solid Tumors With HER2 Aberrations (Beamion LUNG-1)",
        official_title="A Phase Ia/Ib Open-label, Dose-escalation and Expansion Trial of Oral BI 1810631 Monotherapy in Patients With Advanced Solid Tumors With HER2 Aberrations",
        sponsor="Boehringer Ingelheim",
        collaborators=["National Cancer Institute", "MD Anderson Cancer Center"],
        phase_raw="Phase 1/Phase 2",
        status="ACTIVE_NOT_RECRUITING",
        enrollment=132,
        interventions=[
            InterventionItem(
                intervention_type="DRUG",
                name="BI 1810631 (Zongertinib)",
                description="Oral selective HER2 tyrosine kinase inhibitor administered once or twice daily.",
            ),
        ],
        arms=[
            ArmItem(
                arm_label="Dose Escalation - Phase 1a",
                arm_type="EXPERIMENTAL",
                intervention_names=["BI 1810631 (Zongertinib)"],
            ),
            ArmItem(
                arm_label="Expansion Cohort 1 - Pretreated HER2 TKD Mutated NSCLC",
                arm_type="EXPERIMENTAL",
                intervention_names=["BI 1810631 (Zongertinib)"],
            ),
        ],
        conditions=[
            "Non-Small Cell Lung Cancer",
            "Advanced Solid Tumors Harboring HER2 Alterations",
            "Metastatic Breast Cancer",
        ],
        biomarkers=[
            "HER2 Exon 20 insertion mutation",
            "ERBB2 L755S point mutation",
            "HER2 amplification",
        ],
        population="Adults >= 18 years with histologically confirmed advanced solid tumors harboring documented HER2 mutations or gene alterations who have progressed on standard therapy.",
        eligibility={
            "gender": "ALL",
            "minimum_age": "18 Years",
            "maximum_age": None,
            "healthy_volunteers": False,
            "criteria": "Documented activating HER2 alteration, ECOG PS 0-1, adequate organ and bone marrow function.",
        },
        endpoints=[
            EndpointItem(
                endpoint_title="Maximum Tolerated Dose (MTD) and Recommended Phase 2 Dose (RP2D)",
                endpoint_type="PRIMARY",
                time_frame="Cycle 1 (first 21 days)",
                description="Incidence of dose-limiting toxicities (DLTs).",
            ),
            EndpointItem(
                endpoint_title="Objective Response Rate (ORR)",
                endpoint_type="SECONDARY",
                time_frame="Up to approximately 24 months",
                description="Assessed per RECIST v1.1 by independent central review.",
            ),
        ],
        outcomes=[
            TrialOutcomeItem(
                endpoint_name="Objective Response Rate (ORR)",
                metric="ORR",
                value=73.8,
                unit="%",
                confidence_interval="95% CI: 61.2 - 84.0%",
            ),
            TrialOutcomeItem(
                endpoint_name="Median Progression-Free Survival (mPFS)",
                metric="mPFS",
                value=12.4,
                unit="months",
                confidence_interval="95% CI: 9.8 - 15.2 months",
            ),
            TrialOutcomeItem(
                endpoint_name="Intracranial Objective Response Rate",
                metric="CNS_ORR",
                value=41.2,
                unit="%",
                confidence_interval="95% CI: 26.5 - 58.1%",
            ),
        ],
        results={
            "summary": "Confirmed ORR of 73.8% in pretreated HER2 TKD mutation-positive NSCLC with robust intracranial efficacy and manageable safety.",
            "posted_date": "2024-05-10",
        },
        adverse_events=[
            AdverseEventItem(
                term="Diarrhea",
                grade="Grade 3+",
                affected_count=5,
                total_evaluated=132,
                frequency_pct=3.79,
                is_serious=False,
            ),
            AdverseEventItem(
                term="Rash",
                grade="Grade 3+",
                affected_count=2,
                total_evaluated=132,
                frequency_pct=1.52,
                is_serious=False,
            ),
            AdverseEventItem(
                term="ALT Elevation",
                grade="Grade 3+",
                affected_count=4,
                total_evaluated=132,
                frequency_pct=3.03,
                is_serious=False,
            ),
        ],
        termination_reason=None,
        withdrawal_reason=None,
        publication_links=[
            "https://pubmed.ncbi.nlm.nih.gov/38718468/",
            "https://doi.org/10.1038/s43018-024-00778-5",
        ],
        start_date=date(2021, 5, 12),
        primary_completion_date=date(2024, 12, 1),
    )


def test_trial_record_captures_all_twenty_attributes() -> None:
    """
    Verifies that ClinicalTrialRecord faithfully captures all 20 specified attributes:
    1. NCT ID
    2. study title
    3. sponsor
    4. collaborators
    5. phase
    6. status
    7. enrollment
    8. intervention
    9. arm
    10. condition
    11. biomarker
    12. population
    13. eligibility
    14. endpoint
    15. outcome
    16. results
    17. adverse events
    18. termination
    19. withdrawal
    20. publication links
    """
    trial = sample_beamion_lung01_trial()

    # 1. NCT ID
    assert trial.nct_id == "NCT04886804"
    # 2. study title
    assert "BI 1810631" in trial.study_title
    # 3. sponsor
    assert trial.sponsor == "Boehringer Ingelheim"
    # 4. collaborators
    assert "MD Anderson Cancer Center" in trial.collaborators
    # 5. phase
    assert trial.phase_raw == "Phase 1/Phase 2"
    # 6. status
    assert trial.status == "ACTIVE_NOT_RECRUITING"
    # 7. enrollment
    assert trial.enrollment == 132
    # 8. intervention
    assert len(trial.interventions) >= 1
    assert "Zongertinib" in trial.interventions[0].name
    # 9. arm
    assert len(trial.arms) == 2
    assert trial.arms[0].arm_label.startswith("Dose Escalation")
    # 10. condition
    assert "Non-Small Cell Lung Cancer" in trial.conditions
    # 11. biomarker
    assert any("Exon 20" in b for b in trial.biomarkers)
    # 12. population
    assert "HER2 mutations" in trial.population
    # 13. eligibility
    assert trial.eligibility["gender"] == "ALL"
    assert trial.eligibility["minimum_age"] == "18 Years"
    # 14. endpoint
    assert len(trial.endpoints) == 2
    assert trial.endpoints[0].endpoint_type == "PRIMARY"
    # 15. outcome
    assert len(trial.outcomes) == 3
    assert trial.outcomes[0].metric == "ORR"
    assert trial.outcomes[0].value == 73.8
    # 16. results
    assert trial.results is not None
    assert "Confirmed ORR of 73.8%" in trial.results["summary"]
    # 17. adverse events
    assert len(trial.adverse_events) == 3
    assert trial.adverse_events[0].term == "Diarrhea"
    assert trial.adverse_events[0].frequency_pct == pytest.approx(3.79, rel=1e-2)
    # 18. termination
    assert trial.termination_reason is None
    # 19. withdrawal
    assert trial.withdrawal_reason is None
    # 20. publication links
    assert len(trial.publication_links) == 2
    assert "38718468" in trial.publication_links[0]

    # Content hash integrity
    assert len(trial.content_hash) == 64


def test_stage_normalizer_all_twelve_stages() -> None:
    """
    Verifies deterministic normalization across all 12 canonical stages:
    - Preclinical
    - IND-enabling
    - Phase I
    - Phase Ib
    - Phase II
    - Phase II/III
    - Phase III
    - Regulatory review
    - Approved
    - Withdrawn
    - Terminated
    - Discontinued
    """
    # 1. Preclinical
    assert ClinicalStageNormalizer.normalize("Early Discovery / Preclinical", "NOT_YET_RECRUITING") == NormalizedClinicalStage.PRECLINICAL
    assert ClinicalStageNormalizer.normalize("Pre-clinical Model Validation", "ACTIVE") == NormalizedClinicalStage.PRECLINICAL

    # 2. IND-enabling
    assert ClinicalStageNormalizer.normalize("IND Enabling GLP Toxicology", "NOT_YET_RECRUITING") == NormalizedClinicalStage.IND_ENABLING
    assert ClinicalStageNormalizer.normalize("IND Submission Preparation", "PLANNED") == NormalizedClinicalStage.IND_ENABLING

    # 3. Phase I
    assert ClinicalStageNormalizer.normalize("Phase 1", "RECRUITING") == NormalizedClinicalStage.PHASE_I
    assert ClinicalStageNormalizer.normalize("Phase 1 Early", "ACTIVE_NOT_RECRUITING") == NormalizedClinicalStage.PHASE_I

    # 4. Phase Ib
    assert ClinicalStageNormalizer.normalize("Phase 1b", "RECRUITING") == NormalizedClinicalStage.PHASE_IB
    assert ClinicalStageNormalizer.normalize("Phase 1b Expansion", "ACTIVE_NOT_RECRUITING") == NormalizedClinicalStage.PHASE_IB

    # 5. Phase II
    assert ClinicalStageNormalizer.normalize("Phase 2", "RECRUITING") == NormalizedClinicalStage.PHASE_II
    assert ClinicalStageNormalizer.normalize("Phase 2a", "ACTIVE_NOT_RECRUITING") == NormalizedClinicalStage.PHASE_II
    assert ClinicalStageNormalizer.normalize("Phase 2b", "COMPLETED") == NormalizedClinicalStage.PHASE_II

    # 6. Phase II/III
    assert ClinicalStageNormalizer.normalize("Phase 2/Phase 3", "RECRUITING") == NormalizedClinicalStage.PHASE_II_III
    assert ClinicalStageNormalizer.normalize("Phase 2b/3 Pivotal", "ACTIVE") == NormalizedClinicalStage.PHASE_II_III

    # 7. Phase III
    assert ClinicalStageNormalizer.normalize("Phase 3", "RECRUITING") == NormalizedClinicalStage.PHASE_III
    assert ClinicalStageNormalizer.normalize("Phase 3 Confirmatory", "COMPLETED") == NormalizedClinicalStage.PHASE_III

    # 8. Regulatory review
    assert ClinicalStageNormalizer.normalize("Phase 3", "NDA Filed / Under Review") == NormalizedClinicalStage.REGULATORY_REVIEW
    assert ClinicalStageNormalizer.normalize("Registration Filing", "BLA Submitted") == NormalizedClinicalStage.REGULATORY_REVIEW

    # 9. Approved
    assert ClinicalStageNormalizer.normalize("Phase 3", "Approved for Marketing") == NormalizedClinicalStage.APPROVED
    assert ClinicalStageNormalizer.normalize("Phase 4", "FDA Approved") == NormalizedClinicalStage.APPROVED

    # 10. Withdrawn
    assert ClinicalStageNormalizer.normalize("Phase 2", "Withdrawn", why_stopped="Commercial decision prior to enrollment") == NormalizedClinicalStage.WITHDRAWN

    # 11. Terminated
    assert ClinicalStageNormalizer.normalize("Phase 3", "Terminated", why_stopped="Lack of efficacy at interim analysis") == NormalizedClinicalStage.TERMINATED

    # 12. Discontinued
    assert ClinicalStageNormalizer.normalize("Phase 1", "Suspended") == NormalizedClinicalStage.DISCONTINUED
    assert ClinicalStageNormalizer.normalize("Phase 2", "Discontinued by Sponsor") == NormalizedClinicalStage.DISCONTINUED


def test_stage_normalizer_status_precedence_and_edge_cases() -> None:
    """
    Verifies that terminal / interrupted statuses properly take precedence over raw phase strings.
    For example: A Phase 3 trial that was terminated for futility must normalize to 'Terminated',
    not 'Phase III'.
    """
    # Terminated overrides Phase 3
    stage_terminated = ClinicalStageNormalizer.normalize(
        phase_raw="Phase 3",
        status="TERMINATED",
        why_stopped="Futility boundary crossed at planned interim analysis",
    )
    assert stage_terminated == NormalizedClinicalStage.TERMINATED

    # Withdrawn overrides Phase 1/Phase 2
    stage_withdrawn = ClinicalStageNormalizer.normalize(
        phase_raw="Phase 1/Phase 2",
        status="WITHDRAWN",
        why_stopped="Study closed before first subject enrolled due to portfolio realignment",
    )
    assert stage_withdrawn == NormalizedClinicalStage.WITHDRAWN

    # Approved overrides Phase 4
    stage_approved = ClinicalStageNormalizer.normalize(
        phase_raw="Phase 4",
        status="APPROVED",
    )
    assert stage_approved == NormalizedClinicalStage.APPROVED

    # Phase 1/Phase 2 raw maps to Phase II
    stage_p1_p2 = ClinicalStageNormalizer.normalize(
        phase_raw="Phase 1/Phase 2",
        status="RECRUITING",
    )
    assert stage_p1_p2 == NormalizedClinicalStage.PHASE_II


def test_trial_status_tracking_over_time_and_temporal_cutoff() -> None:
    """
    Verifies tracking of trial status transitions over time and querying historical
    status at an exact cutoff date with strict zero-leakage guarantee.
    """
    service = ClinicalTrialsIngestionService()

    base_trial = sample_beamion_lung01_trial()

    # Step 1: Trial initiated in Phase 1 as RECRUITING on 2021-05-15
    base_trial.phase_raw = "Phase 1"
    base_trial.status = "RECRUITING"
    service.ingest_trial(base_trial, as_of_date=date(2021, 5, 15))

    # Step 2: Trial transitions to Phase 1b expansion on 2022-03-01
    base_trial.phase_raw = "Phase 1b"
    base_trial.status = "ACTIVE_NOT_RECRUITING"
    service.ingest_trial(base_trial, as_of_date=date(2022, 3, 1))

    # Step 3: Expansion cohort added (Phase 2), enrollment increases to 132 on 2023-04-10
    base_trial.phase_raw = "Phase 2"
    base_trial.status = "RECRUITING"
    base_trial.enrollment = 132
    service.ingest_trial(base_trial, as_of_date=date(2023, 4, 10))

    # Step 4: Primary results reported on 2024-05-08
    base_trial.status = "ACTIVE_NOT_RECRUITING"
    service.ingest_trial(base_trial, as_of_date=date(2024, 5, 8))

    # Check status history records
    history = service.history_by_nct["NCT04886804"]
    assert len(history) == 4

    # Verify temporal cutoff replays
    # Query BEFORE trial initiation (2020-01-01) -> Should return None
    status_2020 = service.get_trial_status_at_cutoff("NCT04886804", date(2020, 1, 1))
    assert status_2020 is None

    # Query during Phase 1 (2021-08-01) -> Should be Phase 1 / RECRUITING
    status_2021 = service.get_trial_status_at_cutoff("NCT04886804", date(2021, 8, 1))
    assert status_2021 is not None
    assert status_2021.normalized_stage == NormalizedClinicalStage.PHASE_I
    assert status_2021.overall_status == "RECRUITING"

    # Query during Phase 1b (2022-06-01) -> Should be Phase Ib / ACTIVE_NOT_RECRUITING
    status_2022 = service.get_trial_status_at_cutoff("NCT04886804", date(2022, 6, 1))
    assert status_2022 is not None
    assert status_2022.normalized_stage == NormalizedClinicalStage.PHASE_IB
    assert status_2022.overall_status == "ACTIVE_NOT_RECRUITING"

    # Query during Phase 2 (2023-08-01) -> Should be Phase II / RECRUITING
    status_2023 = service.get_trial_status_at_cutoff("NCT04886804", date(2023, 8, 1))
    assert status_2023 is not None
    assert status_2023.normalized_stage == NormalizedClinicalStage.PHASE_II
    assert status_2023.enrollment == 132


def test_trial_to_asset_resolution() -> None:
    """
    Verifies trial-to-asset resolution for development codes and trade names:
    - 'BI 1810631 (Zongertinib)' -> Resolves to Zongertinib
    - 'ONT-380 / Tukysa' -> Resolves to Tucatinib
    - 'HKI-272 / Nerlynx' -> Resolves to Neratinib
    """
    resolver = ClinicalTrialResolver()

    # Case 1: Zongertinib via BI code
    trial_zong = sample_beamion_lung01_trial()
    asset_maps_zong = resolver.resolve_trial_to_asset(trial_zong)
    assert len(asset_maps_zong) >= 1
    primary_zong = asset_maps_zong[0]
    assert primary_zong.canonical_name == "Zongertinib"
    assert primary_zong.confidence >= 0.95
    assert primary_zong.is_primary is True

    # Case 2: Tucatinib via development code ONT-380
    trial_tuc = ClinicalTrialRecord(
        nct_id="NCT02614794",
        study_title="HER2CLIMB: A Study of Tucatinib (ONT-380) vs. Placebo in HER2+ Breast Cancer",
        sponsor="Seattle Genetics, Inc.",
        phase_raw="Phase 3",
        status="COMPLETED",
        interventions=[
            InterventionItem(intervention_type="DRUG", name="ONT-380 (Tucatinib)"),
            InterventionItem(intervention_type="DRUG", name="Trastuzumab"),
            InterventionItem(intervention_type="DRUG", name="Capecitabine"),
        ],
    )
    asset_maps_tuc = resolver.resolve_trial_to_asset(trial_tuc)
    assert len(asset_maps_tuc) >= 1
    tuc_match = next((m for m in asset_maps_tuc if m.canonical_name == "Tucatinib"), None)
    assert tuc_match is not None
    assert tuc_match.confidence >= 0.90

    # Case 3: Neratinib via HKI-272
    trial_ner = ClinicalTrialRecord(
        nct_id="NCT01808573",
        study_title="ExteNET: Neratinib (HKI-272) After Trastuzumab in Early HER2-Positive Breast Cancer",
        sponsor="Puma Biotechnology, Inc.",
        phase_raw="Phase 3",
        status="COMPLETED",
        interventions=[
            InterventionItem(intervention_type="DRUG", name="HKI-272 (Neratinib maleate)"),
        ],
    )
    asset_maps_ner = resolver.resolve_trial_to_asset(trial_ner)
    assert len(asset_maps_ner) >= 1
    assert asset_maps_ner[0].canonical_name == "Neratinib"


def test_trial_to_indication_resolution() -> None:
    """
    Verifies trial-to-indication resolution:
    - Extracts Non-Small Cell Lung Cancer & subtype
    - Extracts Metastatic Breast Cancer & subtype
    """
    resolver = ClinicalTrialResolver()
    trial = sample_beamion_lung01_trial()

    indication_maps = resolver.resolve_trial_to_indication(trial)
    assert len(indication_maps) >= 2

    # Verify NSCLC condition mapping
    nsclc_mapping = next((m for m in indication_maps if "Lung" in m.condition_name), None)
    assert nsclc_mapping is not None
    assert nsclc_mapping.cancer_subtype == "HER2-Mutated NSCLC"

    # Verify Breast Cancer condition mapping
    breast_mapping = next((m for m in indication_maps if "Breast" in m.condition_name), None)
    assert breast_mapping is not None
    assert breast_mapping.cancer_subtype == "HER2+ Metastatic Breast Cancer"


def test_trial_to_biomarker_resolution() -> None:
    """
    Verifies trial-to-biomarker resolution:
    - Identifies ERBB2 / HER2 mutations including Exon 20 insertions and L755S
    - Normalizes gene symbols and inclusion status
    """
    resolver = ClinicalTrialResolver()
    trial = sample_beamion_lung01_trial()

    biomarker_maps = resolver.resolve_trial_to_biomarker(trial)
    assert len(biomarker_maps) >= 2

    exon20_map = next((b for b in biomarker_maps if "Exon 20" in b.biomarker_text), None)
    assert exon20_map is not None
    assert exon20_map.gene_symbol == "ERBB2"
    assert exon20_map.inclusion_status == "REQUIRED"

    l755s_map = next((b for b in biomarker_maps if "L755S" in b.biomarker_text), None)
    assert l755s_map is not None
    assert l755s_map.gene_symbol == "ERBB2"


def test_trial_to_company_resolution() -> None:
    """
    Verifies trial-to-company resolution:
    - Identifies lead sponsor (Boehringer Ingelheim)
    - Identifies collaborators (National Cancer Institute, MD Anderson Cancer Center)
    """
    resolver = ClinicalTrialResolver()
    trial = sample_beamion_lung01_trial()

    company_maps = resolver.resolve_trial_to_company(trial)
    assert len(company_maps) >= 3

    sponsor_map = next((c for c in company_maps if c.role == "LEAD_SPONSOR"), None)
    assert sponsor_map is not None
    assert sponsor_map.company_name == "Boehringer Ingelheim"

    collab_names = [c.company_name for c in company_maps if c.role == "COLLABORATOR"]
    assert "National Cancer Institute" in collab_names
    assert "MD Anderson Cancer Center" in collab_names


def test_end_to_end_trial_ingestion_and_resolution() -> None:
    """
    Verifies full end-to-end ingestion cycle via ClinicalTrialsIngestionService:
    - Ingestion stores trial record
    - Automated normalization to Phase II
    - Automated resolution of all 4 entities (asset, indication, biomarker, company)
    - Historical cutoff tracking
    """
    service = ClinicalTrialsIngestionService()
    trial = sample_beamion_lung01_trial()

    ingested = service.ingest_trial(trial, as_of_date=date(2024, 5, 8))

    assert ingested.nct_id == "NCT04886804"
    assert ingested.normalized_stage == NormalizedClinicalStage.PHASE_II

    # Check resolution summary
    resolutions = service.get_resolutions("NCT04886804")
    assert resolutions is not None
    assert len(resolutions.assets) >= 1
    assert resolutions.assets[0].canonical_name == "Zongertinib"
    assert len(resolutions.indications) >= 2
    assert len(resolutions.biomarkers) >= 2
    assert len(resolutions.companies) >= 3


def test_migration_file_exists_and_defines_all_tables() -> None:
    """
    Verifies that services/kg/migrations/017_clinicaltrials_ingestion.sql and
    037_clinicaltrials_production_history.sql exist and define tables and indexes.
    """
    repo_root = Path(__file__).resolve().parents[3]
    migration_path_017 = repo_root / "services" / "kg" / "migrations" / "017_clinicaltrials_ingestion.sql"
    migration_path_037 = repo_root / "services" / "kg" / "migrations" / "037_clinicaltrials_production_history.sql"

    assert migration_path_017.exists(), f"Migration file not found at {migration_path_017}"
    content_017 = migration_path_017.read_text(encoding="utf-8")

    # Verify tables
    assert "CREATE TABLE IF NOT EXISTS clinical_trials_rich" in content_017
    assert "CREATE TABLE IF NOT EXISTS trial_status_history" in content_017
    assert "CREATE TABLE IF NOT EXISTS trial_asset_mappings" in content_017
    assert "CREATE TABLE IF NOT EXISTS trial_indication_mappings" in content_017
    assert "CREATE TABLE IF NOT EXISTS trial_biomarker_mappings" in content_017
    assert "CREATE TABLE IF NOT EXISTS trial_company_mappings" in content_017

    # Verify indexes
    assert "idx_trials_rich_nct" in content_017
    assert "idx_trial_history_nct_date" in content_017
    assert "idx_trial_asset_nct" in content_017

    assert migration_path_037.exists(), f"Migration file not found at {migration_path_037}"
    content_037 = migration_path_037.read_text(encoding="utf-8")
    assert "ALTER TABLE clinical_trials_rich" in content_037
    assert "ALTER TABLE trial_status_history" in content_037
    assert "idx_trial_history_nct_asof" in content_037


def test_batch_trial_ingestion_and_status_history() -> None:
    """
    Verifies batch ingestion of trials and retrieval of full status history.
    """
    service = ClinicalTrialsIngestionService()
    trial1 = sample_beamion_lung01_trial()
    trial2 = ClinicalTrialRecord(
        nct_id="NCT02614794",
        study_title="HER2CLIMB: Tucatinib in HER2+ Breast Cancer",
        sponsor="Seattle Genetics",
        phase_raw="Phase 3",
        status="COMPLETED",
        interventions=[InterventionItem(name="Tucatinib")],
    )

    batch_res = service.batch_ingest_trials([trial1, trial2], as_of_date=date(2024, 1, 15))
    assert len(batch_res) == 2
    assert service.get_trial("NCT04886804") is not None
    assert service.get_trial("NCT02614794") is not None

    # Check status history retrieval
    history = service.get_status_history("NCT04886804")
    assert len(history) == 1
    assert history[0].overall_status == "ACTIVE_NOT_RECRUITING"

    # Check results retrieval
    results_dict = service.get_trial_results("NCT04886804")
    assert results_dict["nct_id"] == "NCT04886804"
    assert len(results_dict["outcomes"]) == 3
    assert len(results_dict["adverse_events"]) == 3
    assert results_dict["results"]["summary"] is not None


def test_clinicaltrials_fastapi_endpoints() -> None:
    """
    Verifies the FastAPI router endpoints for ClinicalTrials.gov ingestion:
    - POST /api/v1/ingest/clinicaltrials/trial
    - POST /api/v1/ingest/clinicaltrials/batch
    - GET /api/v1/ingest/clinicaltrials/{nct_id}
    - GET /api/v1/ingest/clinicaltrials/{nct_id}/history
    - GET /api/v1/ingest/clinicaltrials/{nct_id}/resolutions
    - GET /api/v1/ingest/clinicaltrials/{nct_id}/results
    """
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    trial = sample_beamion_lung01_trial()

    # Ingest trial
    resp_ingest = client.post("/api/v1/ingest/clinicaltrials/trial", json=trial.model_dump(mode="json"))
    assert resp_ingest.status_code == 200
    ingested_data = resp_ingest.json()
    assert ingested_data["nct_id"] == "NCT04886804"
    assert ingested_data["normalized_stage"] == "Phase II"

    # Get trial
    resp_get = client.get("/api/v1/ingest/clinicaltrials/NCT04886804")
    assert resp_get.status_code == 200
    assert resp_get.json()["nct_id"] == "NCT04886804"

    # Get history
    resp_hist = client.get("/api/v1/ingest/clinicaltrials/NCT04886804/history")
    assert resp_hist.status_code == 200
    assert len(resp_hist.json()) >= 1

    # Get history with cutoff
    resp_cutoff = client.get("/api/v1/ingest/clinicaltrials/NCT04886804/history?cutoff_date=2020-01-01")
    assert resp_cutoff.status_code == 200
    assert len(resp_cutoff.json()) == 0

    # Get resolutions
    resp_res = client.get("/api/v1/ingest/clinicaltrials/NCT04886804/resolutions")
    assert resp_res.status_code == 200
    res_data = resp_res.json()
    assert any(a["canonical_name"] == "Zongertinib" for a in res_data["assets"])
    assert any(c["company_name"] == "Boehringer Ingelheim" for c in res_data["companies"])

    # Get results
    resp_results = client.get("/api/v1/ingest/clinicaltrials/NCT04886804/results")
    assert resp_results.status_code == 200
    res_payload = resp_results.json()
    assert len(res_payload["outcomes"]) == 3
    assert len(res_payload["adverse_events"]) == 3

    # Batch endpoint
    trial_copy = sample_beamion_lung01_trial()
    trial_copy.nct_id = "NCT99999999"
    resp_batch = client.post(
        "/api/v1/ingest/clinicaltrials/batch",
        json={"trials": [trial_copy.model_dump(mode="json")]},
    )
    assert resp_batch.status_code == 200
    batch_data = resp_batch.json()
    assert batch_data["total_submitted"] == 1
    assert batch_data["total_ingested"] == 1


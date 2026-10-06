"""Unit and Integration Tests for Canonical Biomedical Domain Model and Entity Resolution."""

from datetime import date, datetime
from uuid import uuid4

import pytest

from app.opportunity_engine.domain.canonical_model import (
    Asset,
    AssetAlias,
    AssetDevelopmentCode,
    AuditEvent,
    AuditEventType,
    BacktestSnapshot,
    Biomarker,
    CancerSubtype,
    ClinicalOutcome,
    Combination,
    CommercialObservation,
    Company,
    CompetitiveAsset,
    Decision,
    Disease,
    Evidence,
    EvidenceObservation,
    EvidencePolarity,
    Gene,
    Indication,
    Institution,
    LicenseEvent,
    MechanismOfAction,
    Modality,
    ModalityCode,
    Mutation,
    Organization,
    Partnership,
    Patent,
    PatientPopulation,
    PreclinicalResult,
    Prediction,
    Protein,
    Publication,
    Recommendation,
    RegulatoryAuthority,
    RegulatoryEvent,
    RegulatoryEventType,
    ResistanceMechanism,
    SafetyObservation,
    CNSObservation,
    Score,
    ScoreComponent,
    Sponsor,
    StrategicAction,
    Study,
    Target,
    Trial,
    User,
)
from app.opportunity_engine.domain.entity_resolution import (
    CanonicalAssetResolver,
)


def test_core_entities_instantiation():
    """Verify that all 43 canonical domain entities instantiate and validate properly."""
    org = Organization(name="Genentech / Roche", slug="roche")
    user = User(organization_id=org.id, email="investigator@roche.com", full_name="Dr. Jane Doe")
    company = Company(name="Boehringer Ingelheim", ticker="PRIVATE", country="Germany")
    institution = Institution(name="MD Anderson Cancer Center", city="Houston", country="USA")
    sponsor = Sponsor(name="Boehringer Ingelheim R&D", company_id=company.id)

    gene = Gene(hgnc_symbol="ERBB2", full_name="erb-b2 receptor tyrosine kinase 2")
    protein = Protein(uniprot_id="P04626", gene_id=gene.id, protein_name="Receptor tyrosine-protein kinase erbB-2")
    target = Target(symbol="HER2", name="Human Epidermal Growth Factor Receptor 2", gene_id=gene.id, protein_id=protein.id)

    disease = Disease(name="Breast Cancer", category="oncology")
    indication = Indication(disease_id=disease.id, name="HER2-mutant metastatic breast cancer", setting="second_line")
    cancer_subtype = CancerSubtype(disease_id=disease.id, name="ER+/HER2-non-amplified", receptor_status="ER+ / HER2-")

    biomarker = Biomarker(name="HER2 Exon 20 insertion", target_id=target.id, biomarker_type="mutation")
    mutation = Mutation(biomarker_id=biomarker.id, gene_id=gene.id, protein_change="A775_G776insYVMA", exon=20)

    modality = Modality(code=ModalityCode.SMALL_MOLECULE, name="Small Molecule Kinase Inhibitor")
    moa = MechanismOfAction(target_id=target.id, name="Mutant-selective covalent HER2 TKI")

    asset = Asset(
        preferred_name="Zongertinib",
        primary_target_symbol=target.symbol,
        owner_company_name=company.name,
        primary_indication_name=indication.name,
    )
    dev_code = AssetDevelopmentCode(asset_id=asset.id, code="BI-1810631", is_primary=True)
    alias = AssetAlias(asset_id=asset.id, alias="BI-0631")
    asset.development_codes.append(dev_code)
    asset.aliases.append(alias)

    trial = Trial(nct_id="NCT04886804", brief_title="Beamion LUNG-1 Phase 1/2 Study", phase="Phase 1/Phase 2", overall_status="Recruiting")
    study = Study(trial_id=trial.id, name="Beamion Dose Escalation", study_type="interventional_trial")
    pub = Publication(pmid="38000001", doi="10.1056/NEJMoa2300001", title="Zongertinib in HER2-mutant non-small cell lung cancer", publication_year=2023)

    evidence = Evidence(
        asset_id=asset.id,
        publication_id=pub.id,
        trial_id=trial.id,
        source_ref="NEJM 2023",
        citation="Doe et al. NEJM 2023",
        publication_year=2023,
        as_of_date=date(2023, 10, 1),
        polarity=EvidencePolarity.SUPPORTING,
        excerpt="Zongertinib demonstrated 73.8% confirmed ORR in pretreated patients.",
    )
    ev_obs = EvidenceObservation(
        evidence_id=evidence.id,
        asset_id=asset.id,
        parameter_name="ORR",
        observed_value="73.8%",
        numeric_value=73.8,
        unit="percentage",
    )

    outcome = ClinicalOutcome(trial_id=trial.id, asset_id=asset.id, endpoint_name="ORR", response_rate=73.8)
    preclinical = PreclinicalResult(asset_id=asset.id, target_id=target.id, ic50_nm=2.4, is_wt_sparing=True)
    safety = SafetyObservation(asset_id=asset.id, adverse_event_name="Diarrhea", grade_3_plus_rate=3.2, dose_limiting_toxicity=False)
    cns = CNSObservation(asset_id=asset.id, brain_to_plasma_ratio=0.45, csf_penetration_verified=True, cns_score=78)

    pop = PatientPopulation(asset_id=asset.id, population_name="HER2 Exon 20 mutant NSCLC", match_score=92.5)
    resist = ResistanceMechanism(asset_id=asset.id, name="ER pathway activation", impact_level="High", mechanism_description="Compensatory ER signaling")
    combo = Combination(primary_asset_id=asset.id, partner_name="+ Fulvestrant", synergy_type="Endocrine synergy", rationale="Prevent ER bypass", clinical_status="Phase 1b")

    patent = Patent(patent_number="US11223344B2", title="Novel aminopyrimidine HER2 inhibitors", expiration_date=date(2041, 6, 15))
    license_event = LicenseEvent(
        asset_id=asset.id,
        licensor_company_id=company.id,
        licensee_company_id=company.id,
        effective_date=date(2022, 1, 1),
    )
    partnership = Partnership(asset_id=asset.id, partner_company_id=company.id, scope="Global development", start_date=date(2022, 1, 1))
    reg_event = RegulatoryEvent(asset_id=asset.id, authority=RegulatoryAuthority.FDA, event_type=RegulatoryEventType.BREAKTHROUGH_THERAPY, event_date=date(2023, 12, 1))
    commercial = CommercialObservation(asset_id=asset.id, estimated_peak_sales_usd=2500000000)
    comp_asset = CompetitiveAsset(target_asset_id=asset.id, competitor_asset_id=uuid4(), differentiating_advantage="Wild-type EGFR sparing")

    decision = Decision(asset_id=asset.id, action=StrategicAction.PURSUE, clinical_justification="Target selectivity validated")
    recommendation = Recommendation(asset_id=asset.id, action=StrategicAction.PURSUE, confidence=88.5, rationale="Favorable therapeutic index", badge_text="High Priority")
    score = Score(asset_id=asset.id, score_type="development_potential", numeric_score=78.4)
    score_comp = ScoreComponent(score_id=score.id, component_name="Target Selectivity", weight=0.35, raw_value=92.0, weighted_value=32.2)
    prediction = Prediction(asset_id=asset.id, transition_stage="phase_ii_to_iii", predicted_probability=0.65)
    backtest = BacktestSnapshot(
        asset_id=asset.id,
        cutoff_date=date(2023, 6, 1),
        predicted_action=StrategicAction.PURSUE,
        predicted_dps=75.0,
        eligible_evidence_count=4,
        suppressed_future_evidence_count=2,
        ground_truth_outcome="Phase 3 trial initiation",
        prediction_accuracy="True Positive",
    )
    audit = AuditEvent(event_type=AuditEventType.ASSET_CREATED, entity_id=asset.id, entity_type="Asset", actor_name="Admin", summary="Asset created")

    assert org.slug == "roche"
    assert user.email == "investigator@roche.com"
    assert asset.preferred_name == "Zongertinib"
    assert asset.development_codes[0].code == "BI-1810631"
    assert evidence.polarity == EvidencePolarity.SUPPORTING
    assert cns.cns_score == 78
    assert decision.action == StrategicAction.PURSUE
    assert backtest.anti_leakage_audit_passed is True


def test_entity_resolution_across_aliases_and_development_codes():
    """Verify that multiple aliases and developmental codes resolve to a single canonical asset."""
    resolver = CanonicalAssetResolver()

    # 1. Register Zongertinib
    zongertinib = Asset(
        preferred_name="Zongertinib",
        primary_target_symbol="HER2",
        owner_company_name="Boehringer Ingelheim",
    )
    zongertinib.development_codes.append(AssetDevelopmentCode(asset_id=zongertinib.id, code="BI-1810631", is_primary=True))
    zongertinib.development_codes.append(AssetDevelopmentCode(asset_id=zongertinib.id, code="BI 1810631"))
    zongertinib.development_codes.append(AssetDevelopmentCode(asset_id=zongertinib.id, code="BI-0631"))
    zongertinib.aliases.append(AssetAlias(asset_id=zongertinib.id, alias="BI1810631"))
    resolver.register_asset(zongertinib)

    # 2. Register Neratinib
    neratinib = Asset(
        preferred_name="Neratinib",
        primary_target_symbol="pan-HER",
        owner_company_name="Puma Biotechnology",
    )
    neratinib.development_codes.append(AssetDevelopmentCode(asset_id=neratinib.id, code="PB272", is_primary=True))
    neratinib.development_codes.append(AssetDevelopmentCode(asset_id=neratinib.id, code="PB-272"))
    neratinib.development_codes.append(AssetDevelopmentCode(asset_id=neratinib.id, code="HKI-272"))
    neratinib.aliases.append(AssetAlias(asset_id=neratinib.id, alias="Nerlynx"))
    resolver.register_asset(neratinib)

    # 3. Test resolution of Zongertinib via diverse code formats
    for query in ["Zongertinib", "zongertinib", "BI-1810631", "BI 1810631", "BI1810631", "BI-0631"]:
        res = resolver.resolve(query)
        assert res.resolved is True
        assert res.match is not None
        assert res.match.asset_id == zongertinib.id
        assert res.match.canonical_name == "Zongertinib"

    # 4. Test resolution of Neratinib via diverse codes and brand names
    for query in ["Neratinib", "PB272", "pb-272", "HKI-272", "Nerlynx"]:
        res = resolver.resolve(query)
        assert res.resolved is True
        assert res.match is not None
        assert res.match.asset_id == neratinib.id
        assert res.match.canonical_name == "Neratinib"


def test_duplicate_prevention_on_ingestion():
    """Verify that ingesting a publication citing a new code attaches it to existing asset without duplicating."""
    resolver = CanonicalAssetResolver()

    # Pre-existing canonical Tucatinib
    tucatinib = Asset(
        preferred_name="Tucatinib",
        primary_target_symbol="HER2",
        owner_company_name="Seagen / Pfizer",
    )
    tucatinib.development_codes.append(AssetDevelopmentCode(asset_id=tucatinib.id, code="ONT-380", is_primary=True))
    resolver.register_asset(tucatinib)

    # Ingest incoming record citing "ONT-380" but introducing novel synonym "ARRY-380"
    asset, is_new, audit = resolver.ingest_or_resolve(
        raw_name="ONT-380",
        development_codes=["ARRY-380"],
        aliases=["Tukysa"],
        source_ref="Journal of Clinical Oncology 2020",
    )

    # Must NOT create a duplicate asset!
    assert is_new is False
    assert asset.id == tucatinib.id
    assert asset.preferred_name == "Tucatinib"
    assert audit.event_type in (AuditEventType.ALIAS_ATTACHED, AuditEventType.DEV_CODE_ATTACHED)

    # Now verify that searching for the newly attached code "ARRY-380" resolves to Tucatinib
    res = resolver.resolve("ARRY-380")
    assert res.resolved is True
    assert res.match is not None
    assert res.match.asset_id == tucatinib.id

    # Verify that searching for "Tukysa" also resolves to Tucatinib
    res2 = resolver.resolve("Tukysa")
    assert res2.resolved is True
    assert res2.match is not None
    assert res2.match.asset_id == tucatinib.id


def test_asset_merging_with_audit_trail():
    """Verify merging two assets re-points all codes and emits a trace."""
    resolver = CanonicalAssetResolver()

    # Asset A: Created early as "HM781-36B"
    asset_a = Asset(
        preferred_name="HM781-36B",
        primary_target_symbol="pan-HER",
        owner_company_name="Hanmi",
    )
    asset_a.development_codes.append(AssetDevelopmentCode(asset_id=asset_a.id, code="HM-781-36B"))
    resolver.register_asset(asset_a)

    # Asset B: Created later as "Poziotinib"
    asset_b = Asset(
        preferred_name="Poziotinib",
        primary_target_symbol="pan-HER",
        owner_company_name="Spectrum",
    )
    asset_b.development_codes.append(AssetDevelopmentCode(asset_id=asset_b.id, code="NOV120101"))
    resolver.register_asset(asset_b)

    # Merge Asset A into canonical Asset B
    merged_target, audit = resolver.merge_assets(
        source_asset_id=asset_a.id,
        target_asset_id=asset_b.id,
        rationale="HM781-36B was licensed to Spectrum and received INN Poziotinib.",
    )

    assert merged_target.id == asset_b.id
    assert audit.event_type == AuditEventType.ASSET_MERGED
    assert audit.entity_id == asset_b.id

    # Querying "HM781-36B" must now resolve to Poziotinib
    res = resolver.resolve("HM781-36B")
    assert res.resolved is True
    assert res.match is not None
    assert res.match.asset_id == asset_b.id
    assert res.match.canonical_name == "Poziotinib"


def test_database_migration_file_exists():
    """Verify that migration 013 exists, is non-empty, and contains core table statements."""
    from pathlib import Path
    migration_file = Path("services/kg/migrations/013_canonical_domain_model.sql")
    assert migration_file.exists()
    content = migration_file.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS canonical.assets" in content
    assert "CREATE TABLE IF NOT EXISTS canonical.asset_development_codes" in content
    assert "CREATE TABLE IF NOT EXISTS canonical.asset_aliases" in content
    assert "CREATE TABLE IF NOT EXISTS canonical.targets" in content
    assert "CREATE TABLE IF NOT EXISTS canonical.decisions" in content
    assert "CREATE TABLE IF NOT EXISTS canonical.audit_events" in content

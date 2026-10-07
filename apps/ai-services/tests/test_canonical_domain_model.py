"""Unit and Integration Tests for Canonical Biomedical Domain Model and Entity Resolution."""

from datetime import date, datetime
from uuid import uuid4

import pytest

from app.opportunity_engine.domain.canonical_model import (
    AdverseEvent,
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
    DevelopmentStage,
    Endpoint,
    Gene,
    Indication,
    Institution,
    Intervention,
    LicenseEvent,
    MechanismOfAction,
    Modality,
    ModalityCode,
    Mutation,
    Organization,
    Partnership,
    Patent,
    PatientPopulation,
    Population,
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
    TrialArm,
    TrialLifecycleStatus,
    TrialPhase,
    TrialStatusHistory,
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


def test_canonical_asset_all_17_required_attributes():
    """Verify canonical Asset directly supports and exposes all 17 required attributes, identity, and relationships."""
    from app.opportunity_engine.domain.canonical_model import (
        AssetIdentity,
        AssetRelationship,
        AssetRelationshipPredicate,
        AliasType,
        DevelopmentStage,
    )

    asset = Asset(
        preferred_name="Zanidatamab",
        development_code="ZW25",
        generic_name="zanidatamab",
        former_names=["ZW25", "ZW-25"],
        aliases=[
            AssetAlias(alias="Jazz-025", alias_type=AliasType.COMPANY_CODE, confidence=0.98),
            AssetAlias(alias="Ziihera", alias_type=AliasType.BRAND_NAME, confidence=1.0),
        ],
        company_codes=["JAZZ-025", "ZW25"],
        target="HER2",
        modality=ModalityCode.ANTIBODY,
        mechanism="Biparatopic HER2-targeting bispecific antibody binding ECD2 and ECD4",
        indication="Biliary Tract Cancer",
        disease="Solid Tumors",
        cancer_subtype="HER2-amplified / IHC 3+",
        biomarker="HER2 overexpression or amplification",
        stage=DevelopmentStage.PHASE_III,
        owner="Jazz Pharmaceuticals",
        developer="Zymeworks / Jazz Pharmaceuticals / BeiGene",
        sponsor="Jazz Pharmaceuticals Ireland Limited",
        originator="Zymeworks Inc.",
    )

    # 1. Assert all 17 canonical fields are present and accurate
    assert asset.development_code == "ZW25"
    assert asset.generic_name == "zanidatamab"
    assert asset.former_names == ["ZW25", "ZW-25"]
    alias_names = {a.alias for a in asset.aliases}
    assert "Jazz-025" in alias_names
    assert "Ziihera" in alias_names
    assert "zanidatamab" in alias_names
    assert asset.company_codes == ["JAZZ-025", "ZW25"]
    assert asset.target == "HER2"
    assert asset.modality == ModalityCode.ANTIBODY
    assert "Biparatopic" in (asset.mechanism or "")
    assert asset.indication == "Biliary Tract Cancer"
    assert asset.disease == "Solid Tumors"
    assert asset.cancer_subtype == "HER2-amplified / IHC 3+"
    assert "HER2" in (asset.biomarker or "")
    assert asset.stage == DevelopmentStage.PHASE_III
    assert asset.owner == "Jazz Pharmaceuticals"
    assert "Zymeworks" in (asset.developer or "")
    assert "Jazz" in (asset.sponsor or "")
    assert asset.originator == "Zymeworks Inc."

    # 2. Test AssetIdentity attachment and cryptographic hash
    identity = AssetIdentity(
        asset_id=asset.id,
        preferred_name=asset.preferred_name,
        generic_name=asset.generic_name,
        development_code=asset.development_code,
        former_names=asset.former_names,
        company_codes=asset.company_codes,
        registry_identifiers={"ChEMBL": "CHEMBL4297890", "CAS": "2088842-68-4"},
    )
    asset.identity = identity
    assert len(identity.resolution_hash) == 64  # SHA-256 hex string
    assert "ZW25" in identity.normalized_tokens

    # 3. Test AssetRelationship construction
    rel_target = AssetRelationship(
        subject_asset_id=asset.id,
        predicate=AssetRelationshipPredicate.TARGETS,
        object_entity_id=uuid4(),
        object_entity_type="target",
        object_entity_name="HER2",
        confidence=1.0,
    )
    rel_originator = AssetRelationship(
        subject_asset_id=asset.id,
        predicate=AssetRelationshipPredicate.ORIGINATED_BY,
        object_entity_id=uuid4(),
        object_entity_type="company",
        object_entity_name="Zymeworks Inc.",
        confidence=1.0,
    )
    asset.relationships.extend([rel_target, rel_originator])
    rel_predicates = {r.predicate for r in asset.relationships}
    assert AssetRelationshipPredicate.TARGETS in rel_predicates
    assert AssetRelationshipPredicate.ORIGINATED_BY in rel_predicates
    assert AssetRelationshipPredicate.OWNED_BY in rel_predicates


def test_multi_name_resolution_and_confidence_calibration():
    """Verify that multiple aliases and developmental codes resolve to a single canonical asset with calibrated confidence."""
    from app.opportunity_engine.domain.canonical_model import (
        AssetIdentity,
        AliasType,
        DevelopmentStage,
    )
    from app.opportunity_engine.domain.entity_resolution import ResolutionMatchType

    resolver = CanonicalAssetResolver()

    # Create canonical Zanidatamab asset
    zanidatamab = Asset(
        preferred_name="Zanidatamab",
        development_code="ZW25",
        generic_name="zanidatamab",
        former_names=["ZW-25"],
        company_codes=["JAZZ-025"],
        target="HER2",
        modality=ModalityCode.ANTIBODY,
        mechanism="Biparatopic HER2 bispecific antibody",
        indication="Biliary tract cancer",
        disease="Biliary tract cancer",
        cancer_subtype="HER2 amplified",
        biomarker="HER2 overexpression",
        stage=DevelopmentStage.PHASE_III,
        owner="Jazz Pharmaceuticals",
        developer="Jazz / Zymeworks",
        sponsor="Jazz Pharmaceuticals",
        originator="Zymeworks",
    )
    zanidatamab.aliases.append(AssetAlias(asset_id=zanidatamab.id, alias="Ziihera", alias_type=AliasType.BRAND_NAME))
    zanidatamab.identity = AssetIdentity(
        asset_id=zanidatamab.id,
        preferred_name=zanidatamab.preferred_name,
        generic_name=zanidatamab.generic_name,
        development_code=zanidatamab.development_code,
        former_names=zanidatamab.former_names,
        company_codes=zanidatamab.company_codes,
        registry_identifiers={"ChEMBL": "CHEMBL4297890"},
    )
    resolver.register_asset(zanidatamab)

    # Test Exact Primary Name
    res1 = resolver.resolve("Zanidatamab")
    assert res1.resolved is True
    assert res1.confidence == 1.0
    assert res1.match_type == ResolutionMatchType.PRIMARY_NAME
    assert res1.match is not None and res1.match.asset_id == zanidatamab.id

    # Test Generic Name
    res2 = resolver.resolve("zanidatamab")
    assert res2.resolved is True
    assert res2.confidence == 1.0
    assert res2.match_type in (ResolutionMatchType.GENERIC_NAME, ResolutionMatchType.PRIMARY_NAME)
    assert res2.match is not None and res2.match.asset_id == zanidatamab.id

    # Test Development Code
    res3 = resolver.resolve("ZW25")
    assert res3.resolved is True
    assert res3.confidence == 1.0
    assert res3.match_type == ResolutionMatchType.DEVELOPMENT_CODE
    assert res3.match is not None and res3.match.asset_id == zanidatamab.id

    # Test Token Match for hyphenated variant ZW-25
    res4 = resolver.resolve("ZW-25")
    assert res4.resolved is True
    assert res4.confidence in (0.95, 0.98, 1.0)
    assert res4.match is not None and res4.match.asset_id == zanidatamab.id

    # Test Company Code
    res5 = resolver.resolve("JAZZ-025")
    assert res5.resolved is True
    assert res5.confidence == 0.98
    assert res5.match_type == ResolutionMatchType.COMPANY_CODE
    assert res5.match is not None and res5.match.asset_id == zanidatamab.id

    # Test Registry ID
    res6 = resolver.resolve("CHEMBL4297890")
    assert res6.resolved is True
    assert res6.confidence == 1.0
    assert res6.match_type == ResolutionMatchType.REGISTRY_ID
    assert res6.match is not None and res6.match.asset_id == zanidatamab.id

    # Test Brand Alias
    res7 = resolver.resolve("Ziihera")
    assert res7.resolved is True
    assert res7.confidence == 0.95
    assert res7.match_type == ResolutionMatchType.ALIAS
    assert res7.match is not None and res7.match.asset_id == zanidatamab.id

    # Test multi-name consolidation: all names must resolve to Zanidatamab
    names = ["Zanidatamab", "ZW25", "ZW-25", "JAZZ-025", "Ziihera", "CHEMBL4297890"]
    consolidated_asset, joint_conf, results = resolver.consolidate_names(names)
    assert consolidated_asset is not None
    assert consolidated_asset.id == zanidatamab.id
    assert joint_conf >= 0.95
    assert len(results) == len(names)


def test_domain_entities_and_relationships_ontology_neutrality():
    """Verify all 14 domain entities instantiate and interlink without being hard-coded to HER2 or ESR1.

    Tests multiple diverse oncogenic axes:
    1. KRAS / MAPK axis (Target: KRAS G12C, Modality: SMALL_MOLECULE, Indication: NSCLC)
    2. EGFR / Exon 20 axis (Target: EGFR, Modality: SMALL_MOLECULE, Indication: NSCLC)
    3. ESR1 / ER axis (Target: ER-alpha, Modality: PROTEIN_DEGRADER/SERD, Indication: Breast Cancer)
    """
    from app.opportunity_engine.domain.canonical_model import (
        Biomarker,
        CancerSubtype,
        Combination,
        Disease,
        DomainRelationship,
        DomainRelationshipPredicate,
        Gene,
        Indication,
        MechanismOfAction,
        Modality,
        ModalityCode,
        Mutation,
        Pathway,
        PatientPopulation,
        Protein,
        ResistanceMechanism,
        Target,
    )

    # 1. Pathway Entity
    mapk_pathway = Pathway(
        name="RTK-RAS-RAF-MEK-ERK Signaling Pathway",
        identifier="KEGG:hsa04010",
        category="signal_transduction",
        description="Downstream mitogen-activated protein kinase cascade governing cellular proliferation.",
    )
    pi3k_pathway = Pathway(
        name="PI3K-AKT-mTOR Signaling Pathway",
        identifier="KEGG:hsa04151",
        category="survival_signaling",
    )
    er_pathway = Pathway(
        name="Estrogen Receptor Transcription Signaling",
        identifier="Reactome:R-HSA-9018519",
        category="nuclear_receptor_signaling",
    )

    # 2. Gene Entity
    kras_gene = Gene(hgnc_symbol="KRAS", full_name="KRAS proto-oncogene, GTPase", chromosome="12p12.1", pathway_ids=[mapk_pathway.id])
    egfr_gene = Gene(hgnc_symbol="EGFR", full_name="epidermal growth factor receptor", chromosome="7p11.2", pathway_ids=[mapk_pathway.id, pi3k_pathway.id])
    esr1_gene = Gene(hgnc_symbol="ESR1", full_name="estrogen receptor 1", chromosome="6q25.1", pathway_ids=[er_pathway.id])

    # 3. Protein Entity
    kras_protein = Protein(uniprot_id="P01116", gene_id=kras_gene.id, protein_name="GTPase KRas", sequence_length=189)
    egfr_protein = Protein(uniprot_id="P00533", gene_id=egfr_gene.id, protein_name="Epidermal growth factor receptor", sequence_length=1210)
    esr1_protein = Protein(uniprot_id="P03372", gene_id=esr1_gene.id, protein_name="Estrogen receptor", sequence_length=595)

    # 4. Target Entity (Diverse target classes: GTPase, Kinase, Nuclear Receptor)
    kras_target = Target(symbol="KRAS", name="K-Ras GTPase", gene_id=kras_gene.id, protein_id=kras_protein.id, pathway_ids=[mapk_pathway.id], target_class="gtpase", validation_level="clinically_validated")
    egfr_target = Target(symbol="EGFR", name="Epidermal Growth Factor Receptor", gene_id=egfr_gene.id, protein_id=egfr_protein.id, pathway_ids=[mapk_pathway.id], target_class="kinase", validation_level="clinically_validated")
    esr1_target = Target(symbol="ESR1", name="Estrogen Receptor Alpha", gene_id=esr1_gene.id, protein_id=esr1_protein.id, pathway_ids=[er_pathway.id], target_class="nuclear_receptor", validation_level="clinically_validated")

    mapk_pathway.target_ids.extend([kras_target.id, egfr_target.id])
    mapk_pathway.gene_ids.extend([kras_gene.id, egfr_gene.id])

    # 5. Disease, Indication, CancerSubtype Entities
    lung_cancer = Disease(name="Non-Small Cell Lung Cancer", category="oncology", doid="DOID:3908")
    breast_cancer = Disease(name="Breast Cancer", category="oncology", doid="DOID:1612")

    kras_nsclc_ind = Indication(disease_id=lung_cancer.id, name="KRAS G12C-mutant locally advanced or metastatic NSCLC", setting="second_line")
    er_breast_ind = Indication(disease_id=breast_cancer.id, name="ER+/HER2- metastatic breast cancer post-CDK4/6 progression", setting="second_line")

    lung_subtype = CancerSubtype(disease_id=lung_cancer.id, indication_id=kras_nsclc_ind.id, name="Adenocarcinoma with KRAS G12C", receptor_status="KRAS G12C+", frequency_percentage=13.0)
    breast_subtype = CancerSubtype(disease_id=breast_cancer.id, indication_id=er_breast_ind.id, name="ER+/HER2- Invasive Ductal Carcinoma", receptor_status="ER+ / PR+ / HER2-", frequency_percentage=65.0)

    # 6. Biomarker & Mutation Entities
    kras_biomarker = Biomarker(name="KRAS G12C Mutation", target_id=kras_target.id, gene_id=kras_gene.id, biomarker_type="mutation", diagnostic_test_available=True, cdx_test_name="therascreen KRAS RGQ PCR Kit")
    esr1_biomarker = Biomarker(name="ESR1 Ligand-Binding Domain Mutation", target_id=esr1_target.id, gene_id=esr1_gene.id, biomarker_type="mutation", diagnostic_test_available=True, cdx_test_name="Guardant360 CDx")

    kras_mutation = Mutation(biomarker_id=kras_biomarker.id, gene_id=kras_gene.id, target_id=kras_target.id, protein_change="G12C", exon=2, functional_consequence="activating")
    esr1_mutation = Mutation(biomarker_id=esr1_biomarker.id, gene_id=esr1_gene.id, target_id=esr1_target.id, protein_change="Y537S", exon=8, functional_consequence="resistance_gatekeeper")

    # 7. Modality & MechanismOfAction Entities
    covalent_small_mol = Modality(code=ModalityCode.SMALL_MOLECULE, name="Covalent Switch-II Pocket Inhibitor")
    protac_modality = Modality(code=ModalityCode.PROTEIN, name="Oral Selective Estrogen Receptor Degrader (SERD)")

    kras_moa = MechanismOfAction(target_id=kras_target.id, pathway_id=mapk_pathway.id, name="GDP-bound inactive state-specific covalent locking", binding_type="irreversible_covalent")
    esr1_moa = MechanismOfAction(target_id=esr1_target.id, pathway_id=er_pathway.id, name="Direct competitive antagonism and proteasomal degradation", binding_type="degrader_protac")

    # 8. PatientPopulation Entities
    kras_pop = PatientPopulation(
        population_name="KRAS G12C+ Advanced NSCLC (Post-Platinum/IO)",
        disease_id=lung_cancer.id,
        indication_id=kras_nsclc_ind.id,
        cancer_subtype_id=lung_subtype.id,
        biomarker_ids=[kras_biomarker.id],
        mutation_ids=[kras_mutation.id],
        prior_lines="2L+",
        cns_metastases_benefit=True,
        match_score=94.0,
    )

    # 9. ResistanceMechanism Entities
    kras_resistance = ResistanceMechanism(
        target_id=kras_target.id,
        gene_id=kras_gene.id,
        pathway_id=mapk_pathway.id,
        name="RTK bypass activation (MET / EGFR feedback amplification)",
        impact_level="High",
        mechanism_type="bypass_pathway",
        mechanism_description="Compensatory upstream RTK signaling re-activating the MAPK cascade despite KRAS G12C inhibition.",
    )

    esr1_resistance = ResistanceMechanism(
        target_id=esr1_target.id,
        gene_id=esr1_gene.id,
        mutation_id=esr1_mutation.id,
        pathway_id=er_pathway.id,
        name="ESR1 Y537S constitutive estrogen-independent transactivation",
        impact_level="High",
        mechanism_type="on_target_mutation",
        mechanism_description="Conformational stabilization of the active helix-12 state conferring resistance to standard aromatase inhibitors.",
    )

    # 10. Combination Entities
    kras_egfr_combo = Combination(
        partner_name="Cetuximab (anti-EGFR mAb)",
        target_ids=[kras_target.id, egfr_target.id],
        pathway_ids=[mapk_pathway.id],
        synergy_type="Vertical pathway feedback blockade",
        rationale="Blocks adaptive EGFR feedback re-activation observed upon KRAS G12C inhibition.",
        clinical_status="Phase 3 (KRYSTAL-10 / CodeBreaK 300)",
        addressed_resistance_mechanism_ids=[kras_resistance.id],
    )

    kras_resistance.counteracting_combination_ids.append(kras_egfr_combo.id)

    # 11. Domain Relationships (Cross-entity semantic graph edges)
    rel_encodes = DomainRelationship(
        source_entity_id=kras_gene.id,
        source_entity_type="Gene",
        predicate=DomainRelationshipPredicate.ENCODES,
        target_entity_id=kras_protein.id,
        target_entity_type="Protein",
    )
    rel_pathway = DomainRelationship(
        source_entity_id=kras_target.id,
        source_entity_type="Target",
        predicate=DomainRelationshipPredicate.PART_OF_PATHWAY,
        target_entity_id=mapk_pathway.id,
        target_entity_type="Pathway",
    )
    rel_mutation = DomainRelationship(
        source_entity_id=kras_gene.id,
        source_entity_type="Gene",
        predicate=DomainRelationshipPredicate.HARBORS_MUTATION,
        target_entity_id=kras_mutation.id,
        target_entity_type="Mutation",
    )
    rel_resistance = DomainRelationship(
        source_entity_id=kras_resistance.id,
        source_entity_type="ResistanceMechanism",
        predicate=DomainRelationshipPredicate.CONFERS_RESISTANCE,
        target_entity_id=kras_target.id,
        target_entity_type="Target",
    )
    rel_combo_overcomes = DomainRelationship(
        source_entity_id=kras_egfr_combo.id,
        source_entity_type="Combination",
        predicate=DomainRelationshipPredicate.OVERCOMES_RESISTANCE,
        target_entity_id=kras_resistance.id,
        target_entity_type="ResistanceMechanism",
    )

    # Verify relationships and properties
    assert mapk_pathway.name.startswith("RTK-RAS")
    assert kras_gene.hgnc_symbol == "KRAS"
    assert kras_target.target_class == "gtpase"
    assert esr1_target.target_class == "nuclear_receptor"
    assert kras_mutation.protein_change == "G12C"
    assert esr1_mutation.protein_change == "Y537S"
    assert kras_pop.prior_lines == "2L+"
    assert kras_egfr_combo.synergy_type == "Vertical pathway feedback blockade"
    assert rel_encodes.predicate == DomainRelationshipPredicate.ENCODES
    assert rel_pathway.predicate == DomainRelationshipPredicate.PART_OF_PATHWAY
    assert rel_mutation.predicate == DomainRelationshipPredicate.HARBORS_MUTATION
    assert rel_combo_overcomes.predicate == DomainRelationshipPredicate.OVERCOMES_RESISTANCE


def test_stakeholder_roles_and_temporal_ownership_tracking():
    """Verify stakeholder entities and temporal ownership tracking across all 7 deal types:

    - acquisition
    - asset transfer
    - license
    - co-development
    - option
    - partnership
    - termination
    """
    from app.opportunity_engine.domain.canonical_model import (
        Acquirer,
        Asset,
        AssetOwnershipTransfer,
        Company,
        DealType,
        Developer,
        Institution,
        Licensee,
        Licensor,
        Owner,
        Partner,
        Sponsor,
    )

    # 1. Stakeholder Entity Instantiations
    zymeworks = Company(name="Zymeworks Inc.", ticker="ZYME", country="Canada")
    jazz = Company(name="Jazz Pharmaceuticals", ticker="JAZZ", country="Ireland")
    beigene = Company(name="BeiGene Ltd.", ticker="BGNE", country="China")
    pfizer = Company(name="Pfizer Inc.", ticker="PFE", country="USA")
    seagen = Company(name="Seagen Inc.", ticker="SGEN", country="USA")
    dana_farber = Institution(name="Dana-Farber Cancer Institute", city="Boston", country="USA")

    developer = Developer(name="Zymeworks Clinical Development Team", company_id=zymeworks.id, role_description="Translational & Phase 1 Development")
    sponsor = Sponsor(name="Jazz Pharmaceuticals Ireland", company_id=jazz.id, sponsor_type="industry")
    owner_orig = Owner(name="Zymeworks Inc.", company_id=zymeworks.id, ownership_type="academic_inventor")
    partner = Partner(name="BeiGene Co-Development", company_id=beigene.id, scope="Asia-Pacific regional development")
    licensor = Licensor(name="Zymeworks IP Holding", company_id=zymeworks.id, jurisdiction="Global")
    licensee = Licensee(name="Jazz Pharma Rights", company_id=jazz.id, territory="US/EU/Japan")
    acquirer = Acquirer(name="Pfizer Global", company_id=pfizer.id, acquisition_date=date(2023, 12, 14))

    assert developer.name.startswith("Zymeworks")
    assert sponsor.sponsor_type == "industry"
    assert owner_orig.ownership_type == "academic_inventor"
    assert partner.scope.startswith("Asia-Pacific")
    assert licensor.jurisdiction == "Global"
    assert licensee.territory == "US/EU/Japan"
    assert acquirer.acquisition_date == date(2023, 12, 14)

    # 2. Asset Creation & Deal Log (Tracking stewardship over time)
    asset = Asset(
        preferred_name="Zanidatamab",
        development_code="ZW25",
        target="HER2",
        owner="Jazz Pharmaceuticals",
        originator="Zymeworks Inc.",
    )

    # Deal 1: Option agreement
    event_option = AssetOwnershipTransfer(
        asset_id=asset.id,
        deal_type=DealType.OPTION,
        effective_date=date(2018, 11, 26),
        end_date=date(2022, 10, 19),
        from_entity_name=zymeworks.name,
        from_entity_id=zymeworks.id,
        to_entity_name=jazz.name,
        to_entity_id=jazz.id,
        scope="Exclusive option to license ex-Asia rights",
        disclosed_upfront_usd=50000000,
        is_active=False,
        termination_reason="Option exercised into exclusive commercial license",
    )

    # Deal 2: Co-development partnership
    event_codev = AssetOwnershipTransfer(
        asset_id=asset.id,
        deal_type=DealType.CO_DEVELOPMENT,
        effective_date=date(2018, 11, 27),
        partner=beigene.name,
        from_entity_name=zymeworks.name,
        to_entity_name=beigene.name,
        territory="Asia-Pacific (ex-Japan)",
        scope="Co-development and commercialization in APAC",
        disclosed_upfront_usd=40000000,
        disclosed_milestones_usd=390000000,
        royalty_rate_pct="tiered up to 20%",
        is_active=True,
    )

    # Deal 3: Exclusive license agreement
    event_license = AssetOwnershipTransfer(
        asset_id=asset.id,
        deal_type=DealType.LICENSE,
        effective_date=date(2022, 10, 19),
        licensor=zymeworks.name,
        licensee=jazz.name,
        from_entity_name=zymeworks.name,
        to_entity_name=jazz.name,
        territory="US, Europe, Japan and Rest of World (ex-APAC)",
        scope="Exclusive commercialization rights",
        disclosed_upfront_usd=50000000,
        disclosed_milestones_usd=1760000000,
        royalty_rate_pct="10% - 20%",
        is_active=True,
    )

    # Deal 4: Research partnership
    event_partnership = AssetOwnershipTransfer(
        asset_id=asset.id,
        deal_type=DealType.PARTNERSHIP,
        effective_date=date(2020, 1, 15),
        partner=dana_farber.name,
        scope="Translational resistance biomarker research alliance",
        is_active=True,
    )

    # Deal 5: Asset transfer (Historical reference: Seagen -> Pfizer acquisition & transfer)
    tucatinib = Asset(
        preferred_name="Tucatinib",
        development_code="ONT-380",
        target="HER2",
        owner="Pfizer Inc.",
        originator="Array BioPharma",
    )

    event_transfer = AssetOwnershipTransfer(
        asset_id=tucatinib.id,
        deal_type=DealType.ASSET_TRANSFER,
        effective_date=date(2014, 6, 9),
        from_entity_name="Array BioPharma",
        to_entity_name="Oncothyreon (Cascadian)",
        scope="Full worldwide rights transferred to Oncothyreon",
        is_active=False,
    )

    event_acq = AssetOwnershipTransfer(
        asset_id=tucatinib.id,
        deal_type=DealType.ACQUISITION,
        effective_date=date(2023, 12, 14),
        acquirer=pfizer.name,
        from_entity_name=seagen.name,
        to_entity_name=pfizer.name,
        scope="Corporate buyout of Seagen Inc. ($43B) transferring full portfolio",
        is_active=True,
    )

    # Deal 6: Termination
    event_termination = AssetOwnershipTransfer(
        asset_id=asset.id,
        deal_type=DealType.TERMINATION,
        effective_date=date(2024, 1, 1),
        from_entity_name="Predecessor Regional Partner",
        to_entity_name=zymeworks.name,
        scope="Handback of regional commercial option",
        is_active=False,
        termination_reason="Strategic pipeline reprioritization",
    )

    asset.ownership_transfers.extend([event_option, event_codev, event_license, event_partnership, event_termination])
    tucatinib.ownership_transfers.extend([event_transfer, event_acq])

    # Assertions
    assert len(asset.ownership_transfers) == 5
    assert len(tucatinib.ownership_transfers) == 2

    # Verify all 7 DealType values are covered
    covered_deals = {transfer.deal_type for transfer in [*asset.ownership_transfers, *tucatinib.ownership_transfers]}
    assert DealType.ACQUISITION in covered_deals
    assert DealType.ASSET_TRANSFER in covered_deals
    assert DealType.LICENSE in covered_deals
    assert DealType.CO_DEVELOPMENT in covered_deals
    assert DealType.OPTION in covered_deals
    assert DealType.PARTNERSHIP in covered_deals
    assert DealType.TERMINATION in covered_deals

    # Chronological sort verification
    chronological = sorted(asset.ownership_transfers, key=lambda t: t.effective_date)
    assert chronological[0].deal_type == DealType.OPTION  # 2018-11-26
    assert chronological[1].deal_type == DealType.CO_DEVELOPMENT  # 2018-11-27
    assert chronological[-1].deal_type == DealType.TERMINATION  # 2024-01-01


def test_clinical_trial_architecture_entities_and_phases():
    """Verifies complete implementation of:
    1. Trial
    2. Study
    3. TrialArm
    4. Intervention
    5. Population
    6. Endpoint
    7. ClinicalOutcome
    8. AdverseEvent
    9. TrialStatusHistory

    And supports all 10 required phases and lifecycle states:
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
    # 1. Verify all 10 phases and statuses exist in enums
    required_stages = [
        "Phase I",
        "Phase Ib",
        "Phase II",
        "Phase II/III",
        "Phase III",
        "Regulatory review",
        "Approved",
        "Withdrawn",
        "Terminated",
        "Discontinued",
    ]
    for stage_str in required_stages:
        assert stage_str in [s.value for s in DevelopmentStage]
        assert stage_str in [s.value for s in TrialLifecycleStatus]

    # Verify TrialPhase values
    assert TrialPhase.PHASE_I.value == "Phase I"
    assert TrialPhase.PHASE_IB.value == "Phase Ib"
    assert TrialPhase.PHASE_II.value == "Phase II"
    assert TrialPhase.PHASE_II_III.value == "Phase II/III"
    assert TrialPhase.PHASE_III.value == "Phase III"

    # 2. Build Asset aggregate
    asset = Asset(
        preferred_name="Tucatinib",
        development_code="ONT-380",
        target="HER2",
        modality="SMALL_MOLECULE",
        current_development_stage=DevelopmentStage.APPROVED,
    )

    # 3. Build Study
    study = Study(
        name="HER2CLIMB Study Protocol",
        study_code="HER2CLIMB",
        study_type="interventional_trial",
        phase="Phase III",
        description="Randomized, double-blind, placebo-controlled trial of tucatinib in HER2+ metastatic breast cancer",
    )

    # 4. Build Trial
    trial = Trial(
        nct_id="NCT02614794",
        brief_title="A Study of Tucatinib vs. Placebo in Combination With Capecitabine & Trastuzumab in Patients With Locally Advanced or Metastatic HER2+ Breast Cancer",
        official_title="HER2CLIMB: A Phase 2/3 Randomized Study of Tucatinib vs Placebo",
        phase=TrialPhase.PHASE_III.value,
        overall_status="Approved",
        normalized_stage=DevelopmentStage.APPROVED,
        enrollment=612,
        start_date=date(2016, 2, 23),
        primary_completion_date=date(2019, 9, 2),
        completion_date=date(2021, 6, 28),
        study_type="interventional",
        allocation="Randomized",
        intervention_model="Parallel Assignment",
        masking="Triple (Participant, Care Provider, Investigator)",
    )
    study.trials.append(trial)

    # 5. Build TrialArm entities
    arm_experimental = TrialArm(
        trial_id=trial.id,
        arm_label="Tucatinib Combination Arm",
        arm_type="experimental",
        description="Tucatinib 300 mg BID + Trastuzumab + Capecitabine",
        cohort_size=410,
        intervention_names=["Tucatinib", "Trastuzumab", "Capecitabine"],
    )
    arm_control = TrialArm(
        trial_id=trial.id,
        arm_label="Placebo Control Arm",
        arm_type="placebo_comparator",
        description="Placebo + Trastuzumab + Capecitabine",
        cohort_size=202,
        intervention_names=["Placebo", "Trastuzumab", "Capecitabine"],
    )
    trial.arms.extend([arm_experimental, arm_control])

    # 6. Build Intervention entities
    int_tucatinib = Intervention(
        trial_id=trial.id,
        arm_id=arm_experimental.id,
        asset_id=asset.id,
        name="Tucatinib",
        intervention_type="drug",
        dosage_form="Tablet",
        dose_regimen="300 mg orally twice daily",
        is_investigational=True,
    )
    int_trastuzumab = Intervention(
        trial_id=trial.id,
        arm_id=arm_experimental.id,
        name="Trastuzumab",
        intervention_type="biological",
        dosage_form="Intravenous infusion",
        dose_regimen="6 mg/kg every 3 weeks after 8 mg/kg loading",
        is_investigational=False,
    )
    trial.interventions.extend([int_tucatinib, int_trastuzumab])

    # 7. Build Population entity
    population = Population(
        trial_id=trial.id,
        asset_id=asset.id,
        population_name="HER2-positive Metastatic Breast Cancer with Brain Metastases",
        condition="HER2+ Breast Neoplasms",
        cancer_subtype="HER2-overexpressing / amplified",
        biomarker_criteria=["HER2 IHC 3+", "HER2 ISH+"],
        prior_lines=">=2 prior anti-HER2 regimens including Trastuzumab, Pertuzumab, and T-DM1",
        line_of_therapy="3L+",
        cns_metastases_allowed=True,
        cns_metastases_benefit=True,
        match_score=96.0,
        inclusion_criteria=["ECOG 0-1", "Treated or active untreated brain metastases allowed"],
    )
    trial.populations.append(population)
    asset.patient_populations.append(population)

    # 8. Build Endpoint entities
    ep_pfs = Endpoint(
        trial_id=trial.id,
        endpoint_title="Progression-Free Survival (PFS) in Overall Population",
        endpoint_type="primary",
        metric="PFS",
        time_frame="Assessed by BICR per RECIST 1.1 up to 24 months",
        is_met=True,
    )
    ep_os = Endpoint(
        trial_id=trial.id,
        endpoint_title="Overall Survival (OS)",
        endpoint_type="secondary",
        metric="OS",
        time_frame="Up to 36 months",
        is_met=True,
    )
    ep_cns_pfs = Endpoint(
        trial_id=trial.id,
        endpoint_title="Progression-Free Survival in Patients With Brain Metastases",
        endpoint_type="secondary",
        metric="CNS-PFS",
        time_frame="Up to 24 months",
        is_met=True,
    )
    trial.endpoints.extend([ep_pfs, ep_os, ep_cns_pfs])

    # 9. Build ClinicalOutcome entities
    outcome_pfs = ClinicalOutcome(
        trial_id=trial.id,
        asset_id=asset.id,
        arm_id=arm_experimental.id,
        endpoint_id=ep_pfs.id,
        endpoint_name="Progression-Free Survival",
        endpoint_type="primary",
        cohort_description="Overall randomized population (N=612)",
        metric="mPFS",
        median_months=7.8,
        hazard_ratio=0.54,
        confidence_interval="95% CI: 0.42-0.71",
        p_value=0.00001,
        sample_size=410,
        is_statistically_significant=True,
        source_citation="Murthy RK, et al. N Engl J Med. 2020;382(7):597-609",
    )
    outcome_orr = ClinicalOutcome(
        trial_id=trial.id,
        asset_id=asset.id,
        arm_id=arm_experimental.id,
        endpoint_name="Objective Response Rate",
        endpoint_type="secondary",
        metric="ORR",
        response_rate=40.6,
        confidence_interval="95% CI: 34.7-46.8",
        sample_size=340,
        is_statistically_significant=True,
        source_citation="Murthy RK, et al. NEJM 2020",
    )
    trial.outcomes.extend([outcome_pfs, outcome_orr])
    asset.outcomes.append(outcome_pfs)

    # 10. Build AdverseEvent entities
    ae_diarrhea = AdverseEvent(
        trial_id=trial.id,
        arm_id=arm_experimental.id,
        asset_id=asset.id,
        term="Diarrhea",
        category="Gastrointestinal",
        grade="Grade 3+",
        affected_count=53,
        total_evaluated=410,
        frequency_pct=12.9,
        is_serious=False,
        dose_limiting=True,
        treatment_emergent=True,
        source_citation="HER2CLIMB Safety Data, NEJM 2020",
    )
    ae_alt = AdverseEvent(
        trial_id=trial.id,
        arm_id=arm_experimental.id,
        asset_id=asset.id,
        term="Alanine aminotransferase increased",
        category="Hepatic",
        grade="Grade 3+",
        affected_count=22,
        total_evaluated=410,
        frequency_pct=5.4,
        is_serious=False,
        dose_limiting=True,
        treatment_emergent=True,
        source_citation="HER2CLIMB Safety Data, NEJM 2020",
    )
    trial.adverse_events.extend([ae_diarrhea, ae_alt])
    asset.adverse_events.append(ae_diarrhea)

    # 11. Build TrialStatusHistory tracking lifecycle over time
    history_phase1 = TrialStatusHistory(
        trial_id=trial.id,
        nct_id=trial.nct_id,
        as_of_date=date(2016, 2, 1),
        overall_status="Recruiting",
        normalized_stage=DevelopmentStage.PHASE_I,
        change_summary="Protocol initiation and Phase I dose escalation opened",
    )
    history_phase1b = TrialStatusHistory(
        trial_id=trial.id,
        nct_id=trial.nct_id,
        as_of_date=date(2016, 11, 1),
        overall_status="Recruiting",
        normalized_stage=DevelopmentStage.PHASE_IB,
        change_summary="Phase 1b expansion cohort opened in combination with capecitabine/trastuzumab",
    )
    history_phase2 = TrialStatusHistory(
        trial_id=trial.id,
        nct_id=trial.nct_id,
        as_of_date=date(2017, 6, 1),
        overall_status="Recruiting",
        normalized_stage=DevelopmentStage.PHASE_II,
        change_summary="Transitioned to randomized Phase 2 cohort",
    )
    history_phase2_3 = TrialStatusHistory(
        trial_id=trial.id,
        nct_id=trial.nct_id,
        as_of_date=date(2018, 3, 1),
        overall_status="Active, not recruiting",
        normalized_stage=DevelopmentStage.PHASE_II_III,
        change_summary="Adaptive sample size expansion to registrational Phase 2/3 design",
    )
    history_phase3 = TrialStatusHistory(
        trial_id=trial.id,
        nct_id=trial.nct_id,
        as_of_date=date(2019, 10, 21),
        overall_status="Active, not recruiting",
        normalized_stage=DevelopmentStage.PHASE_III,
        change_summary="Positive Phase 3 primary PFS endpoint announced; primary completion reached",
    )
    history_reg_review = TrialStatusHistory(
        trial_id=trial.id,
        nct_id=trial.nct_id,
        as_of_date=date(2019, 12, 16),
        overall_status="Regulatory review",
        normalized_stage=DevelopmentStage.REGULATORY_REVIEW,
        change_summary="FDA NDA accepted with Priority Review under Real-Time Oncology Review (RTOR)",
    )
    history_approved = TrialStatusHistory(
        trial_id=trial.id,
        nct_id=trial.nct_id,
        as_of_date=date(2020, 4, 17),
        overall_status="Approved",
        normalized_stage=DevelopmentStage.APPROVED,
        change_summary="FDA approved Tukysa (tucatinib) for metastatic HER2+ breast cancer with brain metastases",
    )
    trial.status_history.extend([
        history_phase1,
        history_phase1b,
        history_phase2,
        history_phase2_3,
        history_phase3,
        history_reg_review,
        history_approved,
    ])

    # Also verify non-approved lifecycle termination/withdrawal/discontinued status histories
    history_withdrawn = TrialStatusHistory(
        nct_id="NCT01234567",
        as_of_date=date(2021, 5, 10),
        overall_status="Withdrawn",
        normalized_stage=DevelopmentStage.WITHDRAWN,
        why_stopped="Sponsor commercial prioritization before patient enrollment",
        change_summary="Study withdrawn prior to participant enrollment",
    )
    history_terminated = TrialStatusHistory(
        nct_id="NCT07654321",
        as_of_date=date(2022, 9, 15),
        overall_status="Terminated",
        normalized_stage=DevelopmentStage.TERMINATED,
        why_stopped="Futility boundary crossed at pre-planned interim analysis",
        change_summary="Trial terminated prematurely due to lack of efficacy",
    )
    history_discontinued = TrialStatusHistory(
        nct_id="NCT09876543",
        as_of_date=date(2023, 1, 20),
        overall_status="Discontinued",
        normalized_stage=DevelopmentStage.DISCONTINUED,
        why_stopped="Strategic discontinuation following corporate restructuring",
        change_summary="Development program discontinued",
    )

    assert history_withdrawn.normalized_stage == DevelopmentStage.WITHDRAWN
    assert history_terminated.normalized_stage == DevelopmentStage.TERMINATED
    assert history_discontinued.normalized_stage == DevelopmentStage.DISCONTINUED

    # 12. Verification Assertions
    assert len(study.trials) == 1
    assert len(trial.arms) == 2
    assert len(trial.interventions) == 2
    assert len(trial.populations) == 1
    assert len(trial.endpoints) == 3
    assert len(trial.outcomes) == 2
    assert len(trial.adverse_events) == 2
    assert len(trial.status_history) == 7

    assert len(asset.outcomes) == 1
    assert len(asset.adverse_events) == 1
    assert len(asset.patient_populations) == 1

    # Check temporal ordering of trial status transitions
    stages_in_order = [h.normalized_stage for h in trial.status_history]
    assert stages_in_order == [
        DevelopmentStage.PHASE_I,
        DevelopmentStage.PHASE_IB,
        DevelopmentStage.PHASE_II,
        DevelopmentStage.PHASE_II_III,
        DevelopmentStage.PHASE_III,
        DevelopmentStage.REGULATORY_REVIEW,
        DevelopmentStage.APPROVED,
    ]


def test_evidence_architecture_canonical_entities():
    """Verify that all 9 Evidence architecture entities instantiate, capture all 16 required attributes,
    and enforce that every observation references its evidence.
    """
    from app.opportunity_engine.evidence.models import ScientificEvidenceState
    from app.opportunity_engine.domain.canonical_model import (
        SourceType,
        ProspectiveOrRetrospective,
        ExtractionMethod,
        RiskOfBias,
        QualityGrade,
        ConfidenceLevel,
        ClaimType,
        EvidenceTemporalScope,
        EvidenceQuality,
        EvidenceConfidence,
        EvidenceCitation,
        EvidenceSource,
        EvidenceExtraction,
        EvidenceObservation,
        EvidenceClaim,
        Evidence,
    )

    asset_id = uuid4()
    ev_id = uuid4()

    # 1. Temporal Scope
    temporal = EvidenceTemporalScope(
        valid_from=date(2023, 10, 20),
        as_of_date=date(2023, 10, 20),
        is_current=True,
        cutoff_compliant=True,
    )
    assert temporal.is_current is True

    # 2. Quality
    quality = EvidenceQuality(
        quality_score=92.5,
        methodological_rigor=95.0,
        risk_of_bias=RiskOfBias.LOW,
        reproducibility_flag=True,
        quality_grade=QualityGrade.GRADE_A_HIGH,
        scoring_breakdown={"peer_review": 1.0, "sample_size": 0.95},
    )
    assert quality.quality_score == 92.5

    # 3. Confidence
    confidence = EvidenceConfidence(
        score=0.94,
        confidence_interval_low=0.88,
        confidence_interval_high=0.98,
        confidence_level=ConfidenceLevel.VERY_HIGH,
        epistemic_uncertainty=0.06,
        aleatoric_uncertainty=0.04,
    )
    assert confidence.score == 0.94

    # 4. Citation
    citation = EvidenceCitation(
        source_id=uuid4(),
        formatted_citation="Jänne PA, et al. N Engl J Med. 2022;387(1):10-20.",
        short_citation="Jänne et al. (2022)",
        doi="10.1056/NEJMoa2206995",
        pmid="35657008",
        nct_id="NCT05054374",
    )
    assert citation.pmid == "35657008"

    # 5. EvidenceSource (capturing all 16 attributes)
    ev_source = EvidenceSource(
        source_type=SourceType.PUBLICATION,
        source_id="PMID:35657008",
        title="Trastuzumab Deruxtecan in HER2-Mutant Non-Small-Cell Lung Cancer",
        authors=["Jänne PA", "Bob T", "Alice C"],
        organization="Dana-Farber Cancer Institute",
        publication_date=date(2022, 1, 20),
        retrieval_date=date(2023, 1, 1),
        study_type="Clinical Trial",
        phase="Phase II",
        species="Human",
        model="Patient Cohort",
        sample_size=91,
        peer_reviewed=True,
        peer_review_status="peer_reviewed",
        prospective_or_retrospective=ProspectiveOrRetrospective.PROSPECTIVE,
        quality=quality,
        confidence=0.94,
        confidence_details=confidence,
        citation=citation,
        temporal_validity=temporal,
        url_reference="https://doi.org/10.1056/NEJMoa2206995",
    )
    assert ev_source.source_type == SourceType.PUBLICATION
    assert ev_source.sample_size == 91
    assert ev_source.peer_reviewed is True
    assert ev_source.peer_review_status == "peer_reviewed"

    # 6. EvidenceExtraction
    extraction = EvidenceExtraction(
        source_id=ev_source.id,
        source_location="Table 2, Page 15",
        extracted_text="Confirmed objective response rate was 55% (95% CI, 44 to 65).",
        extraction_method=ExtractionMethod.LLM_STRUCTURED_EXTRACTION,
        confidence=0.96,
        extracted_date=date(2023, 1, 2),
    )
    assert extraction.source_id == ev_source.id

    # 7. EvidenceObservation (strict evidence reference)
    observation = EvidenceObservation(
        evidence_id=ev_id,
        asset_id=asset_id,
        extraction_id=extraction.id,
        source_id=ev_source.id,
        source_ref="PMID:35657008",
        entity="Trastuzumab Deruxtecan",
        parameter_name="ORR",
        observed_value="55%",
        extracted_text_or_value="55%",
        numeric_value=55.0,
        normalized_value=55.0,
        unit="percentage",
        observation_date=date(2022, 1, 20),
        source_location="Table 2, Page 15",
        confidence=0.95,
        polarity=EvidencePolarity.SUPPORTING,
        observation_state=ScientificEvidenceState.VERIFIED_FACT,
    )
    assert observation.evidence_id == ev_id
    assert observation.numeric_value == 55.0

    # 8. EvidenceClaim
    claim = EvidenceClaim(
        asset_id=asset_id,
        claim_text="T-DXd demonstrates 55% ORR in pretreated HER2-mutant NSCLC",
        claim_type=ClaimType.EFFICACY,
        polarity=EvidencePolarity.SUPPORTING,
        epistemic_status=ScientificEvidenceState.VERIFIED_FACT,
        supporting_observation_ids=[observation.id],
        synthesis_confidence=0.95,
    )
    assert observation.id in claim.supporting_observation_ids

    # 9. Evidence aggregate
    evidence = Evidence(
        id=ev_id,
        asset_id=asset_id,
        source_type=SourceType.PUBLICATION,
        source_id="PMID:35657008",
        title="Trastuzumab Deruxtecan in HER2-Mutant Non-Small-Cell Lung Cancer",
        authors=["Jänne PA", "Bob T"],
        organization="Dana-Farber Cancer Institute",
        publication_date=date(2022, 1, 20),
        retrieval_date=date(2023, 1, 1),
        url_reference="https://doi.org/10.1056/NEJMoa2206995",
        study_type="Clinical Trial",
        phase="Phase II",
        species="Human",
        model="Patient Cohort",
        sample_size=91,
        peer_reviewed=True,
        peer_review_status="peer_reviewed",
        prospective_or_retrospective=ProspectiveOrRetrospective.PROSPECTIVE,
        quality=quality,
        confidence_details=confidence,
        citation=citation,
        temporal_validity=temporal,
        extractions=[extraction],
        observations=[observation],
        claims=[claim],
    )

    assert evidence.id == ev_id
    assert len(evidence.observations) == 1
    assert evidence.observations[0].evidence_id == evidence.id
    assert evidence.sample_size == 91
    assert evidence.peer_review_status == "peer_reviewed"


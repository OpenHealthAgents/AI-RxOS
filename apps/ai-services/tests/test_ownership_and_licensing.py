from datetime import date
from pathlib import Path
from uuid import UUID, uuid4
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.opportunity_engine.licensing import (
    AssetOwnershipProfile,
    DealType,
    LicensingAndIPGuard,
    LicensingStatus,
    MANDATORY_FTO_DISCLAIMER,
    OwnershipAndDealEvent,
    OwnershipAndLicensingService,
    PatentClaimType,
    PatentJurisdiction,
    PatentRecord,
    PatentStatus,
    ProhibitedFTOAssertionError,
    UnverifiedLicensingAssertionError,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def licensing_service() -> OwnershipAndLicensingService:
    return OwnershipAndLicensingService()


def test_ownership_entities_and_all_deal_types_tracked(
    licensing_service: OwnershipAndLicensingService,
) -> None:
    """
    Verifies that the layer tracks:
    - developer, originator, current owner, former owner, academic origin,
      partner, licensee, licensor.
    - deal types: acquisition, asset transfer, licensing announcement,
      co-development, option agreement.
    """
    asset_id = uuid4()
    profile = AssetOwnershipProfile(
        asset_id=asset_id,
        developer="Astra Bio",
        originator="University of Oxford",
        current_owner="Astra Bio",
        former_owners=["University of Oxford", "BioSpinout Ltd"],
        academic_origin="Department of Oncology, University of Oxford",
        licensing_status=LicensingStatus.PARTNERED,
        licensing_status_rationale="Co-development and commercialization partnership active.",
        licensing_status_verified=True,
        licensing_verification_source="SEC Form 8-K Partnership Disclosure 2022",
    )

    all_deal_types = [
        DealType.LICENSING_ANNOUNCEMENT,
        DealType.CO_DEVELOPMENT,
        DealType.OPTION_AGREEMENT,
        DealType.ACQUISITION,
        DealType.ASSET_TRANSFER,
    ]

    for i, deal_type in enumerate(all_deal_types):
        deal = OwnershipAndDealEvent(
            asset_id=asset_id,
            deal_type=deal_type,
            licensor="BioSpinout Ltd" if i == 0 else "Astra Bio",
            licensee="Astra Bio" if i == 0 else "BigPharma Co",
            partner="BigPharma Co" if deal_type == DealType.CO_DEVELOPMENT else None,
            territory="Global",
            effective_date=date(2018 + i, 1, 1),
            disclosed_upfront_usd=10000000 * (i + 1),
            summary=f"Event for {deal_type.value}",
            source_citation=f"Corporate Disclosure {deal_type.value}",
        )
        profile.deal_history.append(deal)

    verified_profile = LicensingAndIPGuard.verify_profile(profile, strict=True)
    assert verified_profile.developer == "Astra Bio"
    assert verified_profile.originator == "University of Oxford"
    assert verified_profile.current_owner == "Astra Bio"
    assert "BioSpinout Ltd" in verified_profile.former_owners
    assert verified_profile.academic_origin == "Department of Oncology, University of Oxford"
    assert len(verified_profile.deal_history) == 5

    deal_types_present = {d.deal_type for d in verified_profile.deal_history}
    assert deal_types_present == set(all_deal_types)


def test_patent_entities_and_all_five_claim_types_supported() -> None:
    """
    Verifies support for:
    - Patent, PatentFamily, Assignee, Inventor, Jurisdiction, FilingDate,
      PriorityDate, ExpirationDate, ClaimType.
    - All 5 claim types:
      1. composition of matter
      2. therapeutic use
      3. formulation
      4. combination
      5. biomarker claims
    """
    asset_id = uuid4()
    patent = PatentRecord(
        asset_id=asset_id,
        family_id="FAM-TEST-001",
        patent_number="US11223344B2",
        title="Novel selective tyrosine kinase inhibitors and methods of use",
        assignee="Genentech, Inc.",
        inventors=["Smith JA", "Doe RC"],
        jurisdiction=PatentJurisdiction.US,
        filing_date=date(2020, 3, 15),
        priority_date=date(2019, 3, 20),
        expiration_date=date(2040, 3, 15),
        grant_date=date(2022, 6, 1),
        status=PatentStatus.GRANTED,
        claim_types=[
            PatentClaimType.COMPOSITION_OF_MATTER,
            PatentClaimType.THERAPEUTIC_USE,
            PatentClaimType.FORMULATION,
            PatentClaimType.COMBINATION,
            PatentClaimType.BIOMARKER_CLAIMS,
        ],
        composition_of_matter_expiry=date(2040, 3, 15),
        source_citation="USPTO Full-Text Database US 11,223,344",
    )

    assert patent.patent_number == "US11223344B2"
    assert patent.assignee == "Genentech, Inc."
    assert "Smith JA" in patent.inventors
    assert patent.jurisdiction == PatentJurisdiction.US
    assert patent.filing_date == date(2020, 3, 15)
    assert patent.priority_date == date(2019, 3, 20)
    assert patent.expiration_date == date(2040, 3, 15)
    assert len(patent.claim_types) == 5
    assert PatentClaimType.COMPOSITION_OF_MATTER in patent.claim_types
    assert PatentClaimType.THERAPEUTIC_USE in patent.claim_types
    assert PatentClaimType.FORMULATION in patent.claim_types
    assert PatentClaimType.COMBINATION in patent.claim_types
    assert PatentClaimType.BIOMARKER_CLAIMS in patent.claim_types


def test_never_state_licensing_available_unless_verified() -> None:
    """
    STRICT POLICY:
    'Never state "licensing available" unless verified.'

    Allowed states:
    - VERIFIED_AVAILABLE
    - POTENTIALLY_AVAILABLE
    - PARTNERED
    - OWNERSHIP_UNCLEAR
    - NO_PUBLIC_LICENSING_SIGNAL
    - UNKNOWN

    Verifies that:
    1. Setting VERIFIED_AVAILABLE without verified evidence raises UnverifiedLicensingAssertionError.
    2. Setting VERIFIED_AVAILABLE with verified public source succeeds.
    3. Non-strict mode safely downgrades to POTENTIALLY_AVAILABLE.
    """
    # 1. Unverified assertion in strict mode MUST raise UnverifiedLicensingAssertionError
    with pytest.raises(UnverifiedLicensingAssertionError) as exc_info:
        LicensingAndIPGuard.validate_licensing_status(
            status=LicensingStatus.VERIFIED_AVAILABLE,
            is_verified=False,
            verification_source=None,
            strict=True,
        )
    assert "Never state 'licensing available'" in str(exc_info.value)

    # 2. Non-strict fallback downgrades to POTENTIALLY_AVAILABLE
    status, verified, _ = LicensingAndIPGuard.validate_licensing_status(
        status=LicensingStatus.VERIFIED_AVAILABLE,
        is_verified=False,
        verification_source=None,
        strict=False,
    )
    assert status == LicensingStatus.POTENTIALLY_AVAILABLE
    assert verified is False

    # 3. Verified assertion with public citation succeeds
    valid_status, valid_verified, source = LicensingAndIPGuard.validate_licensing_status(
        status=LicensingStatus.VERIFIED_AVAILABLE,
        is_verified=True,
        verification_source="University Tech Transfer Portal: Listed for Out-Licensing Q1 2024",
        strict=True,
    )
    assert valid_status == LicensingStatus.VERIFIED_AVAILABLE
    assert valid_verified is True
    assert "Tech Transfer Portal" in source


def test_all_six_standard_licensing_states_supported() -> None:
    """
    Verifies that all 6 standard licensing states are supported:
    VERIFIED_AVAILABLE, POTENTIALLY_AVAILABLE, PARTNERED,
    OWNERSHIP_UNCLEAR, NO_PUBLIC_LICENSING_SIGNAL, UNKNOWN.
    """
    states = [
        LicensingStatus.VERIFIED_AVAILABLE,
        LicensingStatus.POTENTIALLY_AVAILABLE,
        LicensingStatus.PARTNERED,
        LicensingStatus.OWNERSHIP_UNCLEAR,
        LicensingStatus.NO_PUBLIC_LICENSING_SIGNAL,
        LicensingStatus.UNKNOWN,
    ]
    assert len(states) == 6
    assert LicensingStatus("VERIFIED_AVAILABLE") == LicensingStatus.VERIFIED_AVAILABLE
    assert LicensingStatus("NO_PUBLIC_LICENSING_SIGNAL") == LicensingStatus.NO_PUBLIC_LICENSING_SIGNAL


def test_ip_analysis_is_intelligence_never_claim_freedom_to_operate() -> None:
    """
    STRICT LEGAL POLICY:
    - 'IP analysis is intelligence, not legal advice.'
    - 'Never claim freedom to operate.'

    Verifies:
    1. Every profile contains the mandatory legal disclaimer.
    2. Prohibited FTO claims are caught and rejected by LicensingAndIPGuard.
    """
    # 1. Mandatory disclaimer verification
    profile = AssetOwnershipProfile(
        asset_id=uuid4(),
        developer="TestCo",
        originator="TestCo",
        current_owner="TestCo",
        licensing_status=LicensingStatus.NO_PUBLIC_LICENSING_SIGNAL,
    )
    assert profile.fto_disclaimer == MANDATORY_FTO_DISCLAIMER
    assert "not legal advice" in profile.fto_disclaimer
    assert "No Freedom to Operate (FTO) is claimed" in profile.fto_disclaimer

    # 2. Attempting to assert FTO raises ProhibitedFTOAssertionError
    prohibited_claims = [
        "The asset has freedom to operate against competitor patents.",
        "Clear FTO established across US and EU jurisdictions.",
        "Guaranteed FTO based on expiration of composition of matter.",
        "Legal non-infringement opinion obtained confirming market entry.",
    ]

    for claim in prohibited_claims:
        with pytest.raises(ProhibitedFTOAssertionError) as exc_info:
            LicensingAndIPGuard.audit_fto_statements(claim)
        assert "Never claim Freedom to Operate" in str(exc_info.value) or "Prohibited FTO Claim" in str(exc_info.value)


def test_tucatinib_historical_ownership_lineage_and_temporal_cutoff(
    licensing_service: OwnershipAndLicensingService,
) -> None:
    """
    Verifies historical asset ownership reconstruction on Tucatinib (Tukysa):
    - Originator: Array BioPharma
    - 2010 License: Oncothyreon (Cascadian Therapeutics)
    - 2018 Acquisition: Seattle Genetics (Seagen) acquires Cascadian for $614M
    - 2020 Co-development: Merck partners with Seagen for ex-US/EU rights
    - 2023 Acquisition: Pfizer acquires Seagen for $43B

    Temporal verification:
    - As of 2015: Current owner is Cascadian Therapeutics
    - As of 2019: Current owner is Seattle Genetics (Seagen)
    - As of 2024: Current owner is Pfizer Inc.
    """
    tucatinib_id = UUID("11111111-1111-1111-1111-111111111111")

    # 1. Query as of January 1, 2015
    profile_2015 = licensing_service.get_ownership_profile(tucatinib_id, cutoff_date=date(2015, 1, 1))
    assert profile_2015 is not None
    assert profile_2015.current_owner == "Oncothyreon (Cascadian Therapeutics)"
    assert "Pfizer" not in profile_2015.current_owner
    assert "Seagen" not in profile_2015.current_owner
    assert len(profile_2015.deal_history) == 1

    # 2. Query as of January 1, 2019 (After Seagen acquisition, before Pfizer)
    profile_2019 = licensing_service.get_ownership_profile(tucatinib_id, cutoff_date=date(2019, 1, 1))
    assert profile_2019 is not None
    assert profile_2019.current_owner == "Seattle Genetics (Seagen)"
    assert "Pfizer" not in profile_2019.current_owner
    assert len(profile_2019.deal_history) == 2

    # 3. Query current profile (2024 - After Pfizer acquisition)
    profile_current = licensing_service.get_ownership_profile(tucatinib_id)
    assert profile_current is not None
    assert profile_current.current_owner == "Pfizer Inc."
    assert "Seagen Inc." in profile_current.former_owners
    assert profile_current.licensing_status == LicensingStatus.PARTNERED
    assert len(profile_current.deal_history) == 4


def test_zongertinib_proprietary_no_public_signal(
    licensing_service: OwnershipAndLicensingService,
) -> None:
    """
    Verifies Zongertinib:
    - Originator and current owner: Boehringer Ingelheim
    - Licensing status: NO_PUBLIC_LICENSING_SIGNAL
    - Composition of matter patent: US 11,814,374 expiring 2040
    - Biomarker claims patent: US 2024/0108639
    """
    zongertinib_id = UUID("00000000-0000-0000-0000-000000000001")
    profile = licensing_service.get_ownership_profile(zongertinib_id)
    assert profile is not None
    assert profile.developer == "Boehringer Ingelheim"
    assert profile.current_owner == "Boehringer Ingelheim"
    assert profile.licensing_status == LicensingStatus.NO_PUBLIC_LICENSING_SIGNAL

    # Check composition of matter patent
    com_patent = next(
        p for p in profile.patents if PatentClaimType.COMPOSITION_OF_MATTER in p.claim_types
    )
    assert com_patent.patent_number == "US11814374B2"
    assert com_patent.expiration_date == date(2040, 12, 10)

    # Check biomarker claim patent
    bio_patent = next(
        p for p in profile.patents if PatentClaimType.BIOMARKER_CLAIMS in p.claim_types
    )
    assert "L755S" in bio_patent.title


def test_fastapi_licensing_endpoints(client: TestClient) -> None:
    """
    Verifies FastAPI licensing endpoints:
    - GET /api/v1/licensing/assets/{id}
    - GET /api/v1/licensing/assets/{id}/patents
    - GET /api/v1/licensing/assets/{id}/deals
    - POST /api/v1/licensing/assets/{id}/status (guardrail rejection on unverified available)
    - POST /api/v1/licensing/assets/{id}/status (rejection on FTO claim)
    """
    tucatinib_id = "11111111-1111-1111-1111-111111111111"

    # 1. GET Profile
    resp_profile = client.get(f"/api/v1/licensing/assets/{tucatinib_id}")
    assert resp_profile.status_code == 200
    profile_data = resp_profile.json()
    assert profile_data["current_owner"] == "Pfizer Inc."
    assert profile_data["licensing_status"] == "PARTNERED"
    assert "DISCLAIMER" in profile_data["fto_disclaimer"]

    # 2. GET Patents
    resp_patents = client.get(f"/api/v1/licensing/assets/{tucatinib_id}/patents")
    assert resp_patents.status_code == 200
    patents = resp_patents.json()
    assert len(patents) >= 2
    assert any("COMPOSITION_OF_MATTER" in p["claim_types"] for p in patents)

    # 3. GET Deals
    resp_deals = client.get(f"/api/v1/licensing/assets/{tucatinib_id}/deals")
    assert resp_deals.status_code == 200
    deals = resp_deals.json()
    assert len(deals) >= 4

    # 4. POST unverified VERIFIED_AVAILABLE -> 422 Unprocessable Entity
    resp_unverified = client.post(
        f"/api/v1/licensing/assets/{tucatinib_id}/status",
        json={
            "status": "VERIFIED_AVAILABLE",
            "rationale": "Claimed available on blog post without verification.",
            "is_verified": False,
            "strict": True,
        },
    )
    assert resp_unverified.status_code == 422
    assert "Never state 'licensing available'" in resp_unverified.json()["detail"]

    # 5. POST with prohibited FTO claim -> 400 Bad Request
    resp_fto = client.post(
        f"/api/v1/licensing/assets/{tucatinib_id}/status",
        json={
            "status": "POTENTIALLY_AVAILABLE",
            "rationale": "Asset has clear freedom to operate in the US market.",
            "strict": True,
        },
    )
    assert resp_fto.status_code == 400
    assert "Never claim freedom to operate" in resp_fto.json()["detail"] or "Prohibited FTO Claim" in resp_fto.json()["detail"]


def test_migration_019_exists_and_defines_all_tables() -> None:
    """
    Verifies that services/kg/migrations/019_ownership_and_licensing_intelligence.sql
    exists and defines all required tables, claim types, and licensing states.
    """
    repo_root = Path(__file__).resolve().parents[3]
    migration_path = repo_root / "services" / "kg" / "migrations" / "019_ownership_and_licensing_intelligence.sql"

    assert migration_path.exists(), f"Migration file not found at {migration_path}"
    content = migration_path.read_text(encoding="utf-8")

    # Tables
    assert "CREATE TABLE IF NOT EXISTS asset_ownership_profiles" in content
    assert "CREATE TABLE IF NOT EXISTS ownership_and_deal_events" in content
    assert "CREATE TABLE IF NOT EXISTS patent_families_rich" in content
    assert "CREATE TABLE IF NOT EXISTS patents_rich" in content

    # Licensing states
    assert "'VERIFIED_AVAILABLE'" in content
    assert "'POTENTIALLY_AVAILABLE'" in content
    assert "'PARTNERED'" in content
    assert "'OWNERSHIP_UNCLEAR'" in content
    assert "'NO_PUBLIC_LICENSING_SIGNAL'" in content
    assert "'UNKNOWN'" in content

    # Claim types
    assert "'COMPOSITION_OF_MATTER'" in content
    assert "'THERAPEUTIC_USE'" in content
    assert "'FORMULATION'" in content
    assert "'COMBINATION'" in content
    assert "'BIOMARKER_CLAIMS'" in content

    # Deal types
    assert "'ACQUISITION'" in content
    assert "'ASSET_TRANSFER'" in content
    assert "'LICENSING_ANNOUNCEMENT'" in content
    assert "'CO_DEVELOPMENT'" in content
    assert "'OPTION_AGREEMENT'" in content


def test_patent_intelligence_endpoints_and_queries(client: TestClient) -> None:
    """
    Verifies patent intelligence capture, classification, and zero-FTO enforcement:
    - Captures patent, patent family, assignee, inventor, jurisdiction, priority, filing, expiration, claim types.
    - Classifies composition of matter, therapeutic use, combination, formulation, biomarker.
    - Queries by patent number, family ID, and claim type.
    - Rejects FTO claims with 400 Bad Request.
    """
    asset_id = "00000000-0000-0000-0000-000000000001"  # Zongertinib

    # 1. Ingest new patent via POST /api/v1/licensing/patents
    patent_payload = {
        "asset_id": asset_id,
        "family_id": "FAM-ZONG-003",
        "patent_number": "US12345678B2",
        "title": "Novel formulation and combination therapies comprising selective HER2 inhibitors",
        "assignee": "Boehringer Ingelheim",
        "inventors": ["Wilding B", "Neumüller R", "Kopp H"],
        "jurisdiction": "US",
        "filing_date": "2024-01-10",
        "priority_date": "2023-01-12",
        "expiration_date": "2044-01-10",
        "status": "GRANTED",
        "claim_types": [
            "COMPOSITION_OF_MATTER",
            "THERAPEUTIC_USE",
            "COMBINATION",
            "FORMULATION",
            "BIOMARKER_CLAIMS",
        ],
        "source_citation": "USPTO Patent Grant US 12,345,678",
    }
    resp_post = client.post("/api/v1/licensing/patents", json=patent_payload)
    assert resp_post.status_code == 201
    created_patent = resp_post.json()
    assert created_patent["patent_number"] == "US12345678B2"
    assert created_patent["family_id"] == "FAM-ZONG-003"
    assert len(created_patent["claim_types"]) == 5

    # 2. Get patent by patent number: GET /api/v1/licensing/patents/{number}
    resp_get = client.get("/api/v1/licensing/patents/US12345678B2")
    assert resp_get.status_code == 200
    p_data = resp_get.json()
    assert p_data["assignee"] == "Boehringer Ingelheim"
    assert p_data["jurisdiction"] == "US"
    assert p_data["filing_date"] == "2024-01-10"
    assert p_data["priority_date"] == "2023-01-12"
    assert p_data["expiration_date"] == "2044-01-10"
    assert "COMPOSITION_OF_MATTER" in p_data["claim_types"]
    assert "THERAPEUTIC_USE" in p_data["claim_types"]
    assert "COMBINATION" in p_data["claim_types"]
    assert "FORMULATION" in p_data["claim_types"]
    assert "BIOMARKER_CLAIMS" in p_data["claim_types"]

    # 3. Query patents by family: GET /api/v1/licensing/patents/family/{family_id}
    resp_fam = client.get("/api/v1/licensing/patents/family/FAM-ZONG-003")
    assert resp_fam.status_code == 200
    fam_patents = resp_fam.json()
    assert len(fam_patents) >= 1
    assert fam_patents[0]["patent_number"] == "US12345678B2"

    # 4. Query patents by claim type: GET /api/v1/licensing/patents/claim-type/{type}
    resp_com = client.get("/api/v1/licensing/patents/claim-type/COMPOSITION_OF_MATTER")
    assert resp_com.status_code == 200
    com_patents = resp_com.json()
    assert len(com_patents) >= 2
    assert any(p["patent_number"] == "US12345678B2" for p in com_patents)

    resp_form = client.get("/api/v1/licensing/patents/claim-type/FORMULATION")
    assert resp_form.status_code == 200
    form_patents = resp_form.json()
    assert any(p["patent_number"] == "US12345678B2" for p in form_patents)

    # 5. Batch ingestion: POST /api/v1/licensing/patents/batch
    batch_payload = {
        "patents": [
            {
                "asset_id": asset_id,
                "family_id": "FAM-ZONG-004",
                "patent_number": "EP9988776A1",
                "title": "Therapeutic use of HER2 inhibitors in NSCLC",
                "assignee": "Boehringer Ingelheim",
                "inventors": ["Wilding B"],
                "jurisdiction": "EP",
                "filing_date": "2024-02-01",
                "priority_date": "2023-02-01",
                "expiration_date": "2044-02-01",
                "status": "PENDING",
                "claim_types": ["THERAPEUTIC_USE"],
                "source_citation": "EPO Publication EP 9988776",
            }
        ]
    }
    resp_batch = client.post("/api/v1/licensing/patents/batch", json=batch_payload)
    assert resp_batch.status_code == 200
    assert resp_batch.json()["total_ingested"] == 1

    # 6. Strict Prohibition: Patent asserting FTO in title/claims must be rejected!
    illegal_fto_patent = dict(patent_payload)
    illegal_fto_patent["patent_number"] = "US99999999B2"
    illegal_fto_patent["title"] = "Compound granting confirmed freedom to operate against target patents"
    resp_fto = client.post("/api/v1/licensing/patents", json=illegal_fto_patent)
    assert resp_fto.status_code == 400
    assert "Never claim Freedom to Operate" in resp_fto.json()["detail"] or "Prohibited FTO Claim" in resp_fto.json()["detail"]


def test_public_company_events_all_seven_types_supported() -> None:
    """
    Verifies that all 7 public company events are captured and supported:
    1. funding
    2. acquisition
    3. licensing
    4. partnership
    5. asset transfer
    6. co-development
    7. option
    Also verifies string normalization and funding round/investor metadata.
    """
    asset_id = uuid4()
    events = [
        ("funding", DealType.FUNDING),
        ("acquisition", DealType.ACQUISITION),
        ("licensing", DealType.LICENSING),
        ("partnership", DealType.PARTNERSHIP),
        ("asset transfer", DealType.ASSET_TRANSFER),
        ("co-development", DealType.CO_DEVELOPMENT),
        ("option", DealType.OPTION),
    ]

    for raw_type, expected_enum in events:
        deal = OwnershipAndDealEvent(
            asset_id=asset_id,
            deal_type=raw_type,  # Normalized via field_validator
            effective_date=date(2022, 1, 1),
            summary=f"Event for {raw_type}",
            source_citation=f"Public Filing {raw_type}",
            funding_round="Series B" if expected_enum == DealType.FUNDING else None,
            investors=["Flagship Pioneering", "ARCH Venture Partners"] if expected_enum == DealType.FUNDING else [],
            disclosed_upfront_usd=50000000 if expected_enum == DealType.FUNDING else 10000000,
        )
        assert deal.deal_type == expected_enum
        if expected_enum == DealType.FUNDING:
            assert deal.funding_round == "Series B"
            assert len(deal.investors) == 2
            assert deal.disclosed_upfront_usd == 50000000


def test_resolve_ownership_changes_over_time_temporal_simulation(
    licensing_service: OwnershipAndLicensingService,
) -> None:
    """
    Verifies full temporal resolution of ownership changes over time across:
    funding -> option -> licensing -> partnership -> acquisition -> asset transfer (reversion).
    Guarantees historical reconstruction without future information leakage.
    """
    asset_id = uuid4()
    originator = "GeneTech Bio"
    profile = AssetOwnershipProfile(
        asset_id=asset_id,
        developer=originator,
        originator=originator,
        current_owner=originator,
        former_owners=[],
        licensing_status=LicensingStatus.NO_PUBLIC_SIGNAL,
        licensing_status_rationale="Initial proprietary internal development.",
        licensing_status_verified=True,
    )
    licensing_service.register_profile(profile)

    # 1. 2018-03-15: FUNDING (Series A $35M)
    deal_funding = OwnershipAndDealEvent(
        asset_id=asset_id,
        deal_type=DealType.FUNDING,
        effective_date=date(2018, 3, 15),
        funding_round="Series A",
        investors=["Flagship Pioneering"],
        disclosed_upfront_usd=35000000,
        summary="GeneTech Bio secures $35M Series A financing.",
        source_citation="SEC Form D 2018",
    )
    # 2. 2019-01-10: OPTION
    deal_option = OwnershipAndDealEvent(
        asset_id=asset_id,
        deal_type=DealType.OPTION,
        licensor=originator,
        licensee="PharmaOne Corp",
        partner="PharmaOne Corp",
        effective_date=date(2019, 1, 10),
        disclosed_upfront_usd=5000000,
        summary="PharmaOne options exclusive rights to lead oncology program.",
        source_citation="PharmaOne Press Release Jan 2019",
    )
    # 3. 2020-04-01: LICENSING (Option exercised, exclusive global license)
    deal_licensing = OwnershipAndDealEvent(
        asset_id=asset_id,
        deal_type=DealType.LICENSING,
        licensor=originator,
        licensee="PharmaOne Corp",
        effective_date=date(2020, 4, 1),
        disclosed_upfront_usd=40000000,
        disclosed_milestones_usd=200000000,
        summary="PharmaOne exercises exclusive worldwide license for lead program.",
        source_citation="SEC Form 8-K License Disclosure April 2020",
    )
    # 4. 2021-09-01: PARTNERSHIP (Asia-Pacific commercialization partnership)
    deal_partnership = OwnershipAndDealEvent(
        asset_id=asset_id,
        deal_type=DealType.PARTNERSHIP,
        licensor="PharmaOne Corp",
        licensee="AsiaPharma Inc",
        partner="AsiaPharma Inc",
        territory="Asia-Pacific",
        effective_date=date(2021, 9, 1),
        disclosed_upfront_usd=15000000,
        summary="PharmaOne and AsiaPharma form strategic partnership for regional development.",
        source_citation="AsiaPharma Corporate Disclosure Sept 2021",
    )
    # 5. 2022-11-15: ACQUISITION
    deal_acquisition = OwnershipAndDealEvent(
        asset_id=asset_id,
        deal_type=DealType.ACQUISITION,
        licensor="PharmaOne Corp",
        licensee="MegaNovartis",
        effective_date=date(2022, 11, 15),
        disclosed_upfront_usd=1200000000,
        summary="MegaNovartis completes acquisition of PharmaOne Corp for $1.2B.",
        source_citation="MegaNovartis SEC 8-K Merger Completion Nov 2022",
    )
    # 6. 2023-08-01: ASSET_TRANSFER (Rights revert to originator)
    deal_reversion = OwnershipAndDealEvent(
        asset_id=asset_id,
        deal_type=DealType.ASSET_TRANSFER,
        licensor="MegaNovartis",
        licensee=originator,
        effective_date=date(2023, 8, 1),
        summary="Rights revert back to GeneTech Bio following strategic portfolio reprioritization.",
        source_citation="GeneTech Bio Press Release Aug 2023",
    )

    licensing_service.batch_record_deal_events([
        deal_funding,
        deal_option,
        deal_licensing,
        deal_partnership,
        deal_acquisition,
        deal_reversion,
    ])

    # Temporal Query 1: As of 2018-05-01 (After Funding, before Option)
    p_2018 = licensing_service.get_ownership_profile(asset_id, cutoff_date=date(2018, 5, 1))
    assert p_2018 is not None
    assert p_2018.current_owner == originator
    assert p_2018.former_owners == []
    assert len(p_2018.deal_history) == 1
    assert p_2018.deal_history[0].deal_type == DealType.FUNDING

    # Temporal Query 2: As of 2019-05-01 (After Option, before Licensing)
    p_2019 = licensing_service.get_ownership_profile(asset_id, cutoff_date=date(2019, 5, 1))
    assert p_2019 is not None
    assert p_2019.current_owner == originator
    assert p_2019.partner == "PharmaOne Corp"
    assert p_2019.licensing_status == LicensingStatus.PARTNERED
    assert len(p_2019.deal_history) == 2

    # Temporal Query 3: As of 2020-05-01 (After Licensing, before Partnership)
    p_2020 = licensing_service.get_ownership_profile(asset_id, cutoff_date=date(2020, 5, 1))
    assert p_2020 is not None
    assert p_2020.current_owner == "PharmaOne Corp"
    assert originator in p_2020.former_owners
    assert p_2020.licensing_status == LicensingStatus.PARTNERED
    assert len(p_2020.deal_history) == 3

    # Temporal Query 4: As of 2021-10-01 (After Partnership, before Acquisition)
    p_2021 = licensing_service.get_ownership_profile(asset_id, cutoff_date=date(2021, 10, 1))
    assert p_2021 is not None
    assert p_2021.current_owner == "PharmaOne Corp"
    assert p_2021.partner == "AsiaPharma Inc"
    assert p_2021.licensing_status == LicensingStatus.PARTNERED
    assert "MegaNovartis" not in p_2021.current_owner  # Zero future information leakage!

    # Temporal Query 5: As of 2022-12-01 (After MegaNovartis Acquisition, before Reversion)
    p_2022 = licensing_service.get_ownership_profile(asset_id, cutoff_date=date(2022, 12, 1))
    assert p_2022 is not None
    assert p_2022.current_owner == "MegaNovartis"
    assert "PharmaOne Corp" in p_2022.former_owners
    assert len(p_2022.deal_history) == 5

    # Temporal Query 6: As of 2023-09-01 (After Reversion to Originator)
    p_2023 = licensing_service.get_ownership_profile(asset_id, cutoff_date=date(2023, 9, 1))
    assert p_2023 is not None
    assert p_2023.current_owner == originator
    assert "MegaNovartis" in p_2023.former_owners
    assert p_2023.partner is None
    assert p_2023.licensing_status == LicensingStatus.POTENTIALLY_AVAILABLE
    assert len(p_2023.deal_history) == 6


def test_all_six_licensing_statuses_strictly_supported() -> None:
    """
    Verifies that all 6 required licensing statuses are strictly supported:
    - VERIFIED_AVAILABLE
    - POTENTIALLY_AVAILABLE
    - PARTNERED
    - OWNERSHIP_UNCLEAR
    - NO_PUBLIC_SIGNAL
    - UNKNOWN
    """
    statuses = [
        LicensingStatus.VERIFIED_AVAILABLE,
        LicensingStatus.POTENTIALLY_AVAILABLE,
        LicensingStatus.PARTNERED,
        LicensingStatus.OWNERSHIP_UNCLEAR,
        LicensingStatus.NO_PUBLIC_SIGNAL,
        LicensingStatus.UNKNOWN,
    ]
    assert len(statuses) == 6

    # Normalization from string
    assert LicensingStatus("VERIFIED_AVAILABLE") == LicensingStatus.VERIFIED_AVAILABLE
    assert LicensingStatus("POTENTIALLY_AVAILABLE") == LicensingStatus.POTENTIALLY_AVAILABLE
    assert LicensingStatus("PARTNERED") == LicensingStatus.PARTNERED
    assert LicensingStatus("OWNERSHIP_UNCLEAR") == LicensingStatus.OWNERSHIP_UNCLEAR
    assert LicensingStatus("NO_PUBLIC_SIGNAL") == LicensingStatus.NO_PUBLIC_SIGNAL
    assert LicensingStatus("UNKNOWN") == LicensingStatus.UNKNOWN

    # Backward-compatible alias
    assert LicensingStatus.NO_PUBLIC_LICENSING_SIGNAL.value == "NO_PUBLIC_LICENSING_SIGNAL"


def test_public_company_events_api_endpoints(client: TestClient) -> None:
    """
    Verifies FastAPI public company event ingestion and query endpoints:
    - POST /api/v1/licensing/deals
    - POST /api/v1/licensing/deals/batch
    - GET /api/v1/licensing/deals
    - GET /api/v1/licensing/deals/by-type/{deal_type}
    """
    asset_id = "00000000-0000-0000-0000-000000000001"  # Zongertinib

    # 1. Ingest Funding Deal
    funding_payload = {
        "asset_id": asset_id,
        "deal_type": "FUNDING",
        "effective_date": "2024-03-01",
        "funding_round": "Series C",
        "investors": ["Third Rock Ventures", "ARCH Venture Partners"],
        "disclosed_upfront_usd": 75000000,
        "summary": "Biotech closes $75M Series C crossover round.",
        "source_citation": "SEC Form D Filing March 2024",
    }
    resp_deal = client.post("/api/v1/licensing/deals", json=funding_payload)
    assert resp_deal.status_code == 201
    created = resp_deal.json()
    assert created["deal_type"] == "FUNDING"
    assert created["funding_round"] == "Series C"
    assert created["disclosed_upfront_usd"] == 75000000

    # 2. Batch Ingest Deals
    batch_payload = {
        "deals": [
            {
                "asset_id": asset_id,
                "deal_type": "PARTNERSHIP",
                "partner": "GlobalBio Co.",
                "effective_date": "2024-04-15",
                "summary": "Strategic research alliance for combination studies.",
                "source_citation": "Joint Press Release April 2024",
            },
            {
                "asset_id": asset_id,
                "deal_type": "OPTION",
                "licensee": "MajorPharma Inc.",
                "effective_date": "2024-05-20",
                "disclosed_upfront_usd": 15000000,
                "summary": "Option granted for ex-US commercial rights.",
                "source_citation": "SEC Form 8-K May 2024",
            },
        ]
    }
    resp_batch = client.post("/api/v1/licensing/deals/batch", json=batch_payload)
    assert resp_batch.status_code == 200
    assert resp_batch.json()["total_ingested"] == 2

    # 3. Query Deals by Type: GET /api/v1/licensing/deals/by-type/FUNDING
    resp_funding = client.get("/api/v1/licensing/deals/by-type/FUNDING")
    assert resp_funding.status_code == 200
    funding_deals = resp_funding.json()
    assert len(funding_deals) >= 1
    assert any(d["funding_round"] == "Series C" for d in funding_deals)

    # 4. Query Deals by Type with temporal cutoff: GET /api/v1/licensing/deals/by-type/OPTION
    resp_option = client.get("/api/v1/licensing/deals/by-type/OPTION?cutoff_date=2024-05-01")
    assert resp_option.status_code == 200
    # The May 20, 2024 option deal is excluded by the May 1 cutoff
    assert not any(d["summary"] == "Option granted for ex-US commercial rights." for d in resp_option.json())


def test_migration_038_public_company_events_and_ownership_exists() -> None:
    """
    Verifies that services/kg/migrations/038_public_company_events_and_ownership.sql
    exists and defines constraints for all 7 event types and 6 licensing states.
    """
    repo_root = Path(__file__).resolve().parents[3]
    migration_path = repo_root / "services" / "kg" / "migrations" / "038_public_company_events_and_ownership.sql"

    assert migration_path.exists(), f"Migration file not found at {migration_path}"
    content = migration_path.read_text(encoding="utf-8")

    # 7 public company events
    assert "'FUNDING'" in content
    assert "'ACQUISITION'" in content
    assert "'LICENSING'" in content
    assert "'PARTNERSHIP'" in content
    assert "'ASSET_TRANSFER'" in content
    assert "'CO_DEVELOPMENT'" in content
    assert "'OPTION'" in content

    # 6 licensing statuses
    assert "'VERIFIED_AVAILABLE'" in content
    assert "'POTENTIALLY_AVAILABLE'" in content
    assert "'PARTNERED'" in content
    assert "'OWNERSHIP_UNCLEAR'" in content
    assert "'NO_PUBLIC_SIGNAL'" in content
    assert "'UNKNOWN'" in content



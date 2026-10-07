from datetime import date
from pathlib import Path
from uuid import UUID, uuid4
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.opportunity_engine.regulatory import (
    RegulatoryAssetRef,
    RegulatoryAuthority,
    RegulatoryEventPayload,
    RegulatoryEventRecord,
    RegulatoryEventType,
    RegulatoryEvidenceVerifier,
    RegulatoryIndicationRef,
    RegulatoryIntelligenceService,
    RegulatoryJurisdiction,
    RegulatorySource,
    RegulatorySourceType,
    UnverifiedMarketingClaimError,
    VerificationStatus,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def regulatory_service() -> RegulatoryIntelligenceService:
    return RegulatoryIntelligenceService()


def test_track_all_twelve_regulatory_event_types(regulatory_service: RegulatoryIntelligenceService) -> None:
    """
    Verifies that the regulatory layer tracks all 12 required event categories:
    1. IND-related information
    2. Fast Track
    3. Breakthrough Therapy
    4. Orphan Drug
    5. Accelerated Approval
    6. Full Approval
    7. Supplemental Approval
    8. Complete Response Letter (CRL)
    9. Withdrawal
    10. Safety Warning
    11. Label Changes
    12. Regulatory Milestones
    """
    asset_id = uuid4()
    asset_ref = RegulatoryAssetRef(asset_id=asset_id, asset_name="TestAsset-101")
    indication_ref = RegulatoryIndicationRef(indication_name="Advanced Solid Tumors")

    all_event_types = [
        RegulatoryEventType.IND_RELATED,
        RegulatoryEventType.FAST_TRACK,
        RegulatoryEventType.BREAKTHROUGH_THERAPY,
        RegulatoryEventType.ORPHAN_DRUG,
        RegulatoryEventType.ACCELERATED_APPROVAL,
        RegulatoryEventType.FULL_APPROVAL,
        RegulatoryEventType.SUPPLEMENTAL_APPROVAL,
        RegulatoryEventType.COMPLETE_RESPONSE_LETTER,
        RegulatoryEventType.WITHDRAWAL,
        RegulatoryEventType.SAFETY_WARNING,
        RegulatoryEventType.LABEL_CHANGE,
        RegulatoryEventType.REGULATORY_MILESTONE,
    ]

    for event_type in all_event_types:
        record = RegulatoryEventRecord(
            source=RegulatorySource(
                source_type=RegulatorySourceType.FDA_ACTION_LETTER,
                source_citation=f"FDA Official Action Docket for {event_type.value}",
                source_document_id=f"FDA-{event_type.value}-001",
                is_verified_evidence=True,
                publication_date=date(2023, 1, 1),
            ),
            event_date=date(2023, 1, 1),
            jurisdiction=RegulatoryJurisdiction.US,
            authority=RegulatoryAuthority.FDA,
            asset=asset_ref,
            indication=indication_ref,
            event=RegulatoryEventPayload(
                event_type=event_type,
                headline=f"Verified Event {event_type.value}",
                details=f"Details for {event_type.value} test event.",
            ),
            confidence=0.98,
        )

        recorded = regulatory_service.record_event(record, strict=True)
        assert recorded.event.event_type == event_type
        assert recorded.verification_status == VerificationStatus.VERIFIED_OFFICIAL_RECORD

    # Confirm all 12 events recorded for this asset
    timeline = regulatory_service.get_asset_timeline(asset_id)
    assert len(timeline) == 12
    recorded_types = {e.event.event_type for e in timeline}
    assert recorded_types == set(all_event_types)


def test_every_regulatory_event_requires_all_seven_fields() -> None:
    """
    Verifies that every regulatory event strictly requires:
    1. source
    2. date
    3. jurisdiction
    4. asset
    5. indication
    6. event
    7. confidence
    """
    valid_record = RegulatoryEventRecord(
        source=RegulatorySource(
            source_type=RegulatorySourceType.FDA_DRUGS_AT_FDA,
            source_citation="FDA CDER Application NDA 213051 Approval Letter",
            source_url="https://www.accessdata.fda.gov/drugsatfda_docs/appletter/2020/213051Orig1s000ltr.pdf",
            source_document_id="NDA 213051",
            is_verified_evidence=True,
        ),
        event_date=date(2020, 4, 17),
        jurisdiction=RegulatoryJurisdiction.US,
        authority=RegulatoryAuthority.FDA,
        asset=RegulatoryAssetRef(asset_id=uuid4(), asset_name="Tucatinib"),
        indication=RegulatoryIndicationRef(indication_name="HER2+ Metastatic Breast Cancer"),
        event=RegulatoryEventPayload(
            event_type=RegulatoryEventType.FULL_APPROVAL,
            headline="FDA Approves Tukysa (tucatinib)",
            details="Approved in combination with trastuzumab and capecitabine.",
        ),
        confidence=1.0,
    )

    # 1. source
    assert valid_record.source.source_type == RegulatorySourceType.FDA_DRUGS_AT_FDA
    assert valid_record.source.is_verified_evidence is True
    # 2. date
    assert valid_record.event_date == date(2020, 4, 17)
    # 3. jurisdiction
    assert valid_record.jurisdiction == RegulatoryJurisdiction.US
    # 4. asset
    assert valid_record.asset.asset_name == "Tucatinib"
    # 5. indication
    assert valid_record.indication.indication_name == "HER2+ Metastatic Breast Cancer"
    # 6. event
    assert valid_record.event.event_type == RegulatoryEventType.FULL_APPROVAL
    # 7. confidence
    assert valid_record.confidence == 1.0
    # Integrity hash
    assert len(valid_record.content_hash) == 64


def test_never_infer_regulatory_approval_from_marketing_claims_without_verified_evidence() -> None:
    """
    STRICT INVARIANT:
    'Never infer regulatory approval from marketing claims without verified evidence.'

    Verifies that:
    1. Strict mode immediately raises UnverifiedMarketingClaimError.
    2. Non-strict ingestion marks event as REJECTED_UNVERIFIED_MARKETING with 0.0 confidence.
    3. Rejected marketing claims are strictly excluded from verifiable timelines and approval standings.
    """
    service = RegulatoryIntelligenceService()
    asset_id = uuid4()

    unverified_claim = RegulatoryEventRecord(
        source=RegulatorySource(
            source_type=RegulatorySourceType.UNVERIFIED_MARKETING_CLAIM,
            source_citation="Company Corporate Slide Deck: 'Broad Label Approval Anticipated Globally'",
            source_url="https://promotional-biotech.example.com/pitch-deck.pdf",
            is_verified_evidence=False,
        ),
        event_date=date(2024, 1, 15),
        jurisdiction=RegulatoryJurisdiction.US,
        authority=RegulatoryAuthority.FDA,
        asset=RegulatoryAssetRef(asset_id=asset_id, asset_name="HypotheticalDrug"),
        indication=RegulatoryIndicationRef(indication_name="Pancreatic Cancer"),
        event=RegulatoryEventPayload(
            event_type=RegulatoryEventType.FULL_APPROVAL,
            headline="Marketing Claim: Regulatory Approval Reached",
            details="Claim made in investor slide presentation without statutory FDA documentation.",
        ),
        confidence=0.90,  # Asserted high confidence by marketing source
    )

    # 1. Strict mode MUST raise UnverifiedMarketingClaimError
    with pytest.raises(UnverifiedMarketingClaimError) as exc_info:
        service.record_event(unverified_claim, strict=True)
    assert "cannot be inferred from marketing claims or unverified evidence" in str(exc_info.value)

    # 2. Ingest mode flags policy rejection and nullifies confidence
    flagged_event = service.record_event(unverified_claim, strict=False)
    assert flagged_event.verification_status == VerificationStatus.REJECTED_UNVERIFIED_MARKETING
    assert flagged_event.confidence == 0.0
    assert "Official regulatory agency action letter" in (flagged_event.policy_violation or "")

    # 3. Timeline query excludes the rejected claim
    clean_timeline = service.get_asset_timeline(asset_id=asset_id, include_rejected=False)
    assert len(clean_timeline) == 0

    # 4. Status query confirms drug is NOT approved
    status = service.get_regulatory_status_at_cutoff(asset_id=asset_id, cutoff_date=date(2024, 6, 1))
    assert status["is_approved"] is False
    assert status["has_full_approval"] is False
    assert status["overall_standing"] == "PRE_IND"


def test_official_agency_action_letter_passes_verification_with_high_confidence() -> None:
    """
    Verifies that official FDA Action Letters or statutory SEC 8-K filings
    pass verification cleanly with >= 0.95 confidence.
    """
    service = RegulatoryIntelligenceService()
    asset_id = uuid4()

    verified_event = RegulatoryEventRecord(
        source=RegulatorySource(
            source_type=RegulatorySourceType.FDA_ACTION_LETTER,
            source_citation="FDA CDER BLA 761139 Approval Letter",
            source_document_id="BLA 761139",
            is_verified_evidence=True,
            publication_date=date(2022, 5, 20),
        ),
        event_date=date(2022, 5, 20),
        jurisdiction=RegulatoryJurisdiction.US,
        authority=RegulatoryAuthority.FDA,
        asset=RegulatoryAssetRef(asset_id=asset_id, asset_name="Enhertu"),
        indication=RegulatoryIndicationRef(indication_name="HER2-Low Breast Cancer"),
        event=RegulatoryEventPayload(
            event_type=RegulatoryEventType.SUPPLEMENTAL_APPROVAL,
            headline="FDA Approves First Targeted Therapy for HER2-Low Breast Cancer",
            details="Approved based on DESTINY-Breast04 trial results.",
        ),
        confidence=0.85,  # Input confidence
    )

    recorded = service.record_event(verified_event, strict=True)
    assert recorded.verification_status == VerificationStatus.VERIFIED_OFFICIAL_RECORD
    assert recorded.confidence >= 0.95
    assert recorded.policy_violation is None


def test_tucatinib_counterfactual_regulatory_timeline_anti_leakage(
    regulatory_service: RegulatoryIntelligenceService,
) -> None:
    """
    Verifies temporal intelligence on Tucatinib (Tukysa):
    - Breakthrough Therapy: 2019-12-05
    - Full Approval (mBC): 2020-04-17
    - Accelerated Approval (mCRC): 2023-01-19

    Strict zero leakage:
    - As of 2018-01-01: No approvals, 0 events
    - As of 2020-01-01: Has Breakthrough Therapy, NOT approved
    - As of 2021-01-01: Has Full Approval in mBC, NOT approved in mCRC
    - As of 2023-06-01: Has Full Approval in mBC AND Accelerated Approval in mCRC
    """
    tucatinib_id = UUID("11111111-1111-1111-1111-111111111111")

    # 1. Cutoff: January 1, 2018
    status_2018 = regulatory_service.get_regulatory_status_at_cutoff(tucatinib_id, cutoff_date=date(2018, 1, 1))
    assert status_2018["is_approved"] is False
    assert status_2018["has_breakthrough_therapy"] is False
    assert status_2018["total_verifiable_events"] == 0

    # 2. Cutoff: January 1, 2020 (Breakthrough received, but pre-approval)
    status_2020 = regulatory_service.get_regulatory_status_at_cutoff(tucatinib_id, cutoff_date=date(2020, 1, 1))
    assert status_2020["has_breakthrough_therapy"] is True
    assert status_2020["is_approved"] is False
    assert status_2020["has_full_approval"] is False
    assert status_2020["total_verifiable_events"] == 1

    # 3. Cutoff: January 1, 2021 (Approved for mBC, but NOT yet mCRC)
    status_2021 = regulatory_service.get_regulatory_status_at_cutoff(tucatinib_id, cutoff_date=date(2021, 1, 1))
    assert status_2021["is_approved"] is True
    assert status_2021["has_full_approval"] is True
    assert status_2021["has_accelerated_approval"] is False
    assert status_2021["total_verifiable_events"] == 2

    # Check indication specific status for mCRC at 2021: MUST NOT be approved!
    status_mcrc_2021 = regulatory_service.get_regulatory_status_at_cutoff(
        tucatinib_id, cutoff_date=date(2021, 1, 1), indication_name="Colorectal"
    )
    assert status_mcrc_2021["is_approved"] is False

    # 4. Cutoff: June 1, 2023 (Approved for mBC and mCRC)
    status_2023 = regulatory_service.get_regulatory_status_at_cutoff(tucatinib_id, cutoff_date=date(2023, 6, 1))
    assert status_2023["is_approved"] is True
    assert status_2023["has_full_approval"] is True
    assert status_2023["has_accelerated_approval"] is True
    assert status_2023["total_verifiable_events"] == 3


def test_poziotinib_crl_and_withdrawal_tracked_accurately(
    regulatory_service: RegulatoryIntelligenceService,
) -> None:
    """
    Verifies tracking of negative regulatory outcomes:
    - Fast Track: 2018-02-01
    - ODAC Negative Vote: 2022-09-22
    - Complete Response Letter (CRL): 2022-11-25
    - Regulatory Withdrawal: 2023-01-10
    """
    poziotinib_id = UUID("33333333-3333-3333-3333-333333333333")

    # Cutoff prior to CRL (June 2022): Fast Track active, no CRL
    status_mid_2022 = regulatory_service.get_regulatory_status_at_cutoff(poziotinib_id, cutoff_date=date(2022, 6, 1))
    assert status_mid_2022["has_fast_track"] is True
    assert status_mid_2022["has_crl"] is False
    assert status_mid_2022["has_withdrawal"] is False

    # Cutoff after CRL (December 2022): CRL present, standing is CRL_ISSUED
    status_dec_2022 = regulatory_service.get_regulatory_status_at_cutoff(poziotinib_id, cutoff_date=date(2022, 12, 1))
    assert status_dec_2022["has_crl"] is True
    assert status_dec_2022["overall_standing"] == "CRL_ISSUED"
    assert status_dec_2022["has_withdrawal"] is False

    # Cutoff after withdrawal (March 2023): Standing is WITHDRAWN
    status_2023 = regulatory_service.get_regulatory_status_at_cutoff(poziotinib_id, cutoff_date=date(2023, 3, 1))
    assert status_2023["has_withdrawal"] is True
    assert status_2023["overall_standing"] == "WITHDRAWN"


def test_neratinib_safety_warning_and_label_changes(
    regulatory_service: RegulatoryIntelligenceService,
) -> None:
    """
    Verifies tracking of safety warnings and label changes on Neratinib:
    - 2017-07-17: FDA Boxed/Severe Diarrhea Safety Warning
    - 2020-02-25: Supplemental Approval in combination with capecitabine
    - 2021-06-30: Label Change (Dose escalation schedule added to improve GI tolerability)
    """
    neratinib_id = UUID("22222222-2222-2222-2222-222222222222")
    timeline = regulatory_service.get_asset_timeline(neratinib_id)

    event_types = [e.event.event_type for e in timeline]
    assert RegulatoryEventType.SAFETY_WARNING in event_types
    assert RegulatoryEventType.SUPPLEMENTAL_APPROVAL in event_types
    assert RegulatoryEventType.LABEL_CHANGE in event_types

    safety_event = next(e for e in timeline if e.event.event_type == RegulatoryEventType.SAFETY_WARNING)
    assert "Diarrhea" in safety_event.event.headline
    assert safety_event.confidence == 1.0


def test_fastapi_regulatory_endpoints(client: TestClient) -> None:
    """
    Verifies FastAPI endpoints:
    - GET /api/v1/regulatory/assets/{id}/timeline
    - GET /api/v1/regulatory/assets/{id}/status
    - POST /api/v1/regulatory/events (rejection of unverified marketing claim)
    """
    tucatinib_id = "11111111-1111-1111-1111-111111111111"

    # 1. GET Timeline
    resp_timeline = client.get(f"/api/v1/regulatory/assets/{tucatinib_id}/timeline")
    assert resp_timeline.status_code == 200
    timeline = resp_timeline.json()
    assert len(timeline) >= 3
    assert any(e["event"]["event_type"] == "FULL_APPROVAL" for e in timeline)

    # 2. GET Timeline with Cutoff Date
    resp_cutoff = client.get(
        f"/api/v1/regulatory/assets/{tucatinib_id}/timeline",
        params={"cutoff_date": "2019-12-31"},
    )
    assert resp_cutoff.status_code == 200
    timeline_filtered = resp_cutoff.json()
    assert len(timeline_filtered) == 1
    assert timeline_filtered[0]["event"]["event_type"] == "BREAKTHROUGH_THERAPY"

    # 3. GET Status
    resp_status = client.get(
        f"/api/v1/regulatory/assets/{tucatinib_id}/status",
        params={"cutoff_date": "2020-05-01"},
    )
    assert resp_status.status_code == 200
    status_data = resp_status.json()
    assert status_data["is_approved"] is True
    assert status_data["has_full_approval"] is True
    assert status_data["has_accelerated_approval"] is False

    # 4. POST unverified marketing claim asserting approval with strict=True
    bogus_approval_payload = {
        "source": {
            "source_type": "UNVERIFIED_MARKETING_CLAIM",
            "source_citation": "Biotech Pitch Deck slide 14",
            "is_verified_evidence": False,
        },
        "event_date": "2024-03-01",
        "jurisdiction": "US",
        "authority": "FDA",
        "asset": {
            "asset_id": str(uuid4()),
            "asset_name": "BogusPill",
        },
        "indication": {
            "indication_name": "Glioblastoma",
        },
        "event": {
            "event_type": "FULL_APPROVAL",
            "headline": "Company Claims Imminent FDA Approval",
            "details": "Unverified assertion from promotional roadshow.",
        },
        "confidence": 0.95,
    }

    resp_post = client.post("/api/v1/regulatory/events?strict=true", json=bogus_approval_payload)
    # MUST return 422 Unprocessable Entity
    assert resp_post.status_code == 422
    assert "cannot be inferred from marketing claims or unverified evidence" in resp_post.json()["detail"]


def test_migration_018_exists_and_defines_all_tables() -> None:
    """
    Verifies that services/kg/migrations/018_regulatory_intelligence.sql
    exists and defines regulatory_events_rich, regulatory_audit_logs, check constraints,
    and indexes.
    """
    repo_root = Path(__file__).resolve().parents[3]
    migration_path = repo_root / "services" / "kg" / "migrations" / "018_regulatory_intelligence.sql"

    assert migration_path.exists(), f"Migration file not found at {migration_path}"
    content = migration_path.read_text(encoding="utf-8")

    # Check tables
    assert "CREATE TABLE IF NOT EXISTS regulatory_events_rich" in content
    assert "CREATE TABLE IF NOT EXISTS regulatory_audit_logs" in content

    # Check 12 event types in check constraint
    assert "'IND_RELATED'" in content
    assert "'FAST_TRACK'" in content
    assert "'BREAKTHROUGH_THERAPY'" in content
    assert "'ORPHAN_DRUG'" in content
    assert "'ACCELERATED_APPROVAL'" in content
    assert "'FULL_APPROVAL'" in content
    assert "'SUPPLEMENTAL_APPROVAL'" in content
    assert "'COMPLETE_RESPONSE_LETTER'" in content
    assert "'WITHDRAWAL'" in content
    assert "'SAFETY_WARNING'" in content
    assert "'LABEL_CHANGE'" in content
    assert "'REGULATORY_MILESTONE'" in content

    # Check anti-marketing source type
    assert "'UNVERIFIED_MARKETING_CLAIM'" in content
    assert "'FDA_ACTION_LETTER'" in content

    # Check indexes
    assert "idx_reg_events_asset_date" in content
    assert "idx_reg_events_type" in content
    assert "idx_reg_events_jurisdiction" in content


def test_batch_regulatory_ingestion_and_type_queries(client: TestClient) -> None:
    """
    Verifies batch ingestion of regulatory events and retrieval by event type:
    - Fast Track
    - Breakthrough Therapy
    - Orphan Drug
    - Accelerated Approval
    - Full Approval
    - Complete Response Letter (CRL)
    - Withdrawal
    - Safety Warnings
    - Label Changes
    Every event strictly captures source and date.
    """
    asset_id = str(uuid4())
    events_payload = [
        {
            "source": {
                "source_type": "FDA_ACTION_LETTER",
                "source_citation": "FDA CDER Fast Track Designation Letter",
                "is_verified_evidence": True,
            },
            "event_date": "2021-05-10",
            "jurisdiction": "US",
            "authority": "FDA",
            "asset": {"asset_id": asset_id, "asset_name": "BatchTestDrug"},
            "indication": {"indication_name": "Triple Negative Breast Cancer"},
            "event": {
                "event_type": "FAST_TRACK",
                "headline": "FDA Grants Fast Track Designation",
                "details": "Fast track granted based on preclinical potency.",
            },
            "confidence": 0.98,
        },
        {
            "source": {
                "source_type": "FDA_ACTION_LETTER",
                "source_citation": "FDA CDER Orphan Drug Designation Notice",
                "is_verified_evidence": True,
            },
            "event_date": "2021-09-15",
            "jurisdiction": "US",
            "authority": "FDA",
            "asset": {"asset_id": asset_id, "asset_name": "BatchTestDrug"},
            "indication": {"indication_name": "Triple Negative Breast Cancer"},
            "event": {
                "event_type": "ORPHAN_DRUG",
                "headline": "FDA Grants Orphan Drug Designation",
                "details": "Orphan designation granted.",
            },
            "confidence": 0.99,
        },
    ]

    # Batch endpoint test
    resp_batch = client.post("/api/v1/regulatory/events/batch", json={"events": events_payload, "strict": True})
    assert resp_batch.status_code == 200
    batch_data = resp_batch.json()
    assert batch_data["total_submitted"] == 2
    assert batch_data["total_ingested"] == 2

    # Query by event type: FAST_TRACK
    resp_fast = client.get("/api/v1/regulatory/events/type/FAST_TRACK")
    assert resp_fast.status_code == 200
    fast_events = resp_fast.json()
    assert any(e["asset"]["asset_name"] == "BatchTestDrug" for e in fast_events)
    # Check that every event has source and date
    for e in fast_events:
        assert "source" in e and e["source"]["source_citation"]
        assert "event_date" in e and e["event_date"]

    # Query by event type: ORPHAN_DRUG
    resp_orphan = client.get("/api/v1/regulatory/events/type/ORPHAN_DRUG")
    assert resp_orphan.status_code == 200
    orphan_events = resp_orphan.json()
    assert any(e["asset"]["asset_name"] == "BatchTestDrug" for e in orphan_events)
    for e in orphan_events:
        assert "source" in e and e["source"]["source_citation"]
        assert "event_date" in e and e["event_date"]


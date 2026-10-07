from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from .models import (
    RegulatoryAssetRef,
    RegulatoryAuthority,
    RegulatoryEventPayload,
    RegulatoryEventRecord,
    RegulatoryEventType,
    RegulatoryIndicationRef,
    RegulatoryJurisdiction,
    RegulatorySource,
    RegulatorySourceType,
    VerificationStatus,
)
from .verifier import RegulatoryEvidenceVerifier

logger = logging.getLogger(__name__)


class RegulatoryIntelligenceService:
    """
    Production-grade Regulatory Intelligence Layer:
    - Tracks IND-related, Fast Track, Breakthrough, Orphan, Accelerated Approval,
      Full Approval, Supplemental Approval, CRL, Withdrawal, Safety Warnings,
      Label Changes, and Regulatory Milestones.
    - Guarantees the 7 required fields: source, date, jurisdiction, asset, indication, event, confidence.
    - Strictly prevents inferring regulatory approval from marketing claims.
    - Integrates with temporal intelligence for zero-leakage historical counterfactual backtesting.
    """

    def __init__(self) -> None:
        self._events_by_id: Dict[UUID, RegulatoryEventRecord] = {}
        self._events_by_asset: Dict[UUID, List[RegulatoryEventRecord]] = {}
        self._audit_log: List[Dict[str, Any]] = []
        self._load_reference_fixtures()

    def record_event(
        self,
        event: RegulatoryEventRecord,
        strict: bool = False,
    ) -> RegulatoryEventRecord:
        """
        Records and verifies a regulatory event.
        Enforces strict provenance validation.
        """
        is_valid, verified_event = RegulatoryEvidenceVerifier.verify(event, strict=strict)

        self._audit_log.append({
            "id": uuid4(),
            "event_id": verified_event.id,
            "asset_id": verified_event.asset.asset_id,
            "event_type": verified_event.event.event_type.value,
            "policy_check_passed": is_valid,
            "violation_reason": verified_event.policy_violation,
            "source_type": verified_event.source.source_type.value,
        })

        self._events_by_id[verified_event.id] = verified_event
        self._events_by_asset.setdefault(verified_event.asset.asset_id, []).append(verified_event)
        return verified_event

    def batch_record_events(
        self,
        events: List[RegulatoryEventRecord],
        strict: bool = False,
    ) -> List[RegulatoryEventRecord]:
        """Batch records and validates multiple regulatory events."""
        return [self.record_event(e, strict=strict) for e in events]

    def get_event(self, event_id: UUID) -> Optional[RegulatoryEventRecord]:
        """Retrieves a single regulatory event by UUID."""
        return self._events_by_id.get(event_id)

    def get_events_by_type(
        self,
        event_type: RegulatoryEventType,
        cutoff_date: Optional[date] = None,
    ) -> List[RegulatoryEventRecord]:
        """Retrieves all events matching a given RegulatoryEventType, optionally capped at cutoff_date."""
        matches = [e for e in self._events_by_id.values() if e.event.event_type == event_type]
        if cutoff_date:
            matches = [e for e in matches if e.event_date <= cutoff_date]
        return sorted(matches, key=lambda e: e.event_date)

    def get_asset_timeline(
        self,
        asset_id: UUID,
        cutoff_date: Optional[date] = None,
        include_rejected: bool = False,
    ) -> List[RegulatoryEventRecord]:
        """
        Retrieves the complete regulatory timeline for an asset.
        If cutoff_date is provided, enforces temporal intelligence by suppressing
        any events dated strictly after the cutoff.
        """
        events = self._events_by_asset.get(asset_id, [])

        # Temporal filter: prevent future leakage
        if cutoff_date is not None:
            events = [e for e in events if e.event_date <= cutoff_date]

        # Filter out rejected marketing claims unless explicitly requested for audit
        if not include_rejected:
            events = [e for e in events if e.verification_status != VerificationStatus.REJECTED_UNVERIFIED_MARKETING]

        # Chronological ordering
        return sorted(events, key=lambda e: e.event_date)

    def get_regulatory_status_at_cutoff(
        self,
        asset_id: UUID,
        cutoff_date: date,
        indication_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Synthesizes the verifiable regulatory standing of an asset as of a specific cutoff date.
        """
        timeline = self.get_asset_timeline(asset_id=asset_id, cutoff_date=cutoff_date)
        if indication_name:
            timeline = [
                e for e in timeline
                if indication_name.lower() in e.indication.indication_name.lower()
            ]

        has_ind_cleared = any(e.event.event_type == RegulatoryEventType.IND_RELATED for e in timeline)
        has_fast_track = any(e.event.event_type == RegulatoryEventType.FAST_TRACK for e in timeline)
        has_breakthrough = any(e.event.event_type == RegulatoryEventType.BREAKTHROUGH_THERAPY for e in timeline)
        has_orphan_drug = any(e.event.event_type == RegulatoryEventType.ORPHAN_DRUG for e in timeline)
        has_accelerated_approval = any(e.event.event_type == RegulatoryEventType.ACCELERATED_APPROVAL for e in timeline)
        has_full_approval = any(e.event.event_type == RegulatoryEventType.FULL_APPROVAL for e in timeline)
        has_supplemental_approval = any(e.event.event_type == RegulatoryEventType.SUPPLEMENTAL_APPROVAL for e in timeline)
        has_crl = any(e.event.event_type == RegulatoryEventType.COMPLETE_RESPONSE_LETTER for e in timeline)
        has_withdrawal = any(e.event.event_type == RegulatoryEventType.WITHDRAWAL for e in timeline)
        safety_warnings = [e for e in timeline if e.event.event_type == RegulatoryEventType.SAFETY_WARNING]
        label_changes = [e for e in timeline if e.event.event_type == RegulatoryEventType.LABEL_CHANGE]

        overall_standing = "PRE_IND"
        if has_withdrawal:
            overall_standing = "WITHDRAWN"
        elif has_full_approval or has_accelerated_approval or has_supplemental_approval:
            overall_standing = "APPROVED"
        elif has_crl:
            overall_standing = "CRL_ISSUED"
        elif has_ind_cleared or has_fast_track or has_breakthrough:
            overall_standing = "INVESTIGATIONAL_IND_ACTIVE"

        return {
            "asset_id": asset_id,
            "cutoff_date": cutoff_date,
            "overall_standing": overall_standing,
            "is_approved": has_full_approval or has_accelerated_approval or has_supplemental_approval,
            "has_accelerated_approval": has_accelerated_approval,
            "has_full_approval": has_full_approval,
            "has_supplemental_approval": has_supplemental_approval,
            "has_breakthrough_therapy": has_breakthrough,
            "has_fast_track": has_fast_track,
            "has_orphan_drug": has_orphan_drug,
            "has_crl": has_crl,
            "has_withdrawal": has_withdrawal,
            "safety_warnings_count": len(safety_warnings),
            "label_changes_count": len(label_changes),
            "total_verifiable_events": len(timeline),
        }

    def _load_reference_fixtures(self) -> None:
        """Loads canonical ground-truth regulatory events for known assets."""
        # 1. Tucatinib (Tukysa) Canonical Events
        tucatinib_id = UUID("11111111-1111-1111-1111-111111111111")
        tucatinib_ref = RegulatoryAssetRef(asset_id=tucatinib_id, asset_name="Tucatinib")
        mBC_ref = RegulatoryIndicationRef(indication_name="HER2+ Metastatic Breast Cancer", cancer_subtype="HER2+ mBC Brain Mets")
        mCRC_ref = RegulatoryIndicationRef(indication_name="HER2-Positive Colorectal Cancer", cancer_subtype="RAS WT / HER2+")

        # Tucatinib Breakthrough Therapy (2019)
        self.record_event(
            RegulatoryEventRecord(
                source=RegulatorySource(
                    source_type=RegulatorySourceType.SEC_8K_FILING,
                    source_citation="Seattle Genetics SEC Form 8-K Regulatory Filing, Accession 0001060397-19-000078",
                    source_document_id="SEC:0001060397-19-000078",
                    is_verified_evidence=True,
                    publication_date=date(2019, 12, 5),
                ),
                event_date=date(2019, 12, 5),
                jurisdiction=RegulatoryJurisdiction.US,
                authority=RegulatoryAuthority.FDA,
                asset=tucatinib_ref,
                indication=mBC_ref,
                event=RegulatoryEventPayload(
                    event_type=RegulatoryEventType.BREAKTHROUGH_THERAPY,
                    headline="FDA Grants Breakthrough Therapy Designation for Tucatinib in HER2+ Breast Cancer",
                    details="Designation granted for tucatinib in combination with trastuzumab and capecitabine for patients with locally advanced or metastatic HER2-positive breast cancer, including those with brain metastases.",
                ),
                confidence=0.98,
            )
        )

        # Tucatinib Full Approval (2020-04-17)
        self.record_event(
            RegulatoryEventRecord(
                source=RegulatorySource(
                    source_type=RegulatorySourceType.FDA_DRUGS_AT_FDA,
                    source_citation="FDA CDER Application NDA 213051 Approval Letter and Summary Review",
                    source_url="https://www.accessdata.fda.gov/drugsatfda_docs/appletter/2020/213051Orig1s000ltr.pdf",
                    source_document_id="NDA 213051/Orig-1",
                    is_verified_evidence=True,
                    publication_date=date(2020, 4, 17),
                ),
                event_date=date(2020, 4, 17),
                jurisdiction=RegulatoryJurisdiction.US,
                authority=RegulatoryAuthority.FDA,
                asset=tucatinib_ref,
                indication=mBC_ref,
                event=RegulatoryEventPayload(
                    event_type=RegulatoryEventType.FULL_APPROVAL,
                    headline="FDA Approves Tukysa (tucatinib) for Advanced Unresectable or Metastatic HER2+ Breast Cancer",
                    details="Full approval granted under Project Orbis in combination with trastuzumab and capecitabine based on overall survival advantage demonstrated in the pivotal HER2CLIMB trial.",
                ),
                confidence=1.0,
            )
        )

        # Tucatinib Accelerated Approval / Supplemental (2023-01-19)
        self.record_event(
            RegulatoryEventRecord(
                source=RegulatorySource(
                    source_type=RegulatorySourceType.FDA_DRUGS_AT_FDA,
                    source_citation="FDA CDER Supplemental NDA 213051/S-005 Accelerated Approval Letter",
                    source_url="https://www.accessdata.fda.gov/drugsatfda_docs/appletter/2023/213051Orig1s005ltr.pdf",
                    source_document_id="NDA 213051/S-005",
                    is_verified_evidence=True,
                    publication_date=date(2023, 1, 19),
                ),
                event_date=date(2023, 1, 19),
                jurisdiction=RegulatoryJurisdiction.US,
                authority=RegulatoryAuthority.FDA,
                asset=tucatinib_ref,
                indication=mCRC_ref,
                event=RegulatoryEventPayload(
                    event_type=RegulatoryEventType.ACCELERATED_APPROVAL,
                    headline="FDA Grants Accelerated Approval for Tukysa in HER2-Positive Metastatic Colorectal Cancer",
                    details="Accelerated approval in combination with trastuzumab for adult patients with RAS wild-type HER2-positive mCRC based on objective response rate in the MOUNTAINEER trial.",
                ),
                confidence=1.0,
            )
        )

        # 2. Poziotinib Canonical Events
        poziotinib_id = UUID("33333333-3333-3333-3333-333333333333")
        poziotinib_ref = RegulatoryAssetRef(asset_id=poziotinib_id, asset_name="Poziotinib")
        nsclc_ref = RegulatoryIndicationRef(indication_name="Non-Small Cell Lung Cancer", cancer_subtype="HER2 Exon 20 Insertion NSCLC")

        # Poziotinib Fast Track (2018-02-01)
        self.record_event(
            RegulatoryEventRecord(
                source=RegulatorySource(
                    source_type=RegulatorySourceType.SPONSOR_REGULATORY_DISCLOSURE,
                    source_citation="Spectrum Pharmaceuticals Press Release and SEC 8-K: FDA Grants Fast Track Designation",
                    source_document_id="SEC:0001193125-18-028491",
                    is_verified_evidence=True,
                    publication_date=date(2018, 2, 1),
                ),
                event_date=date(2018, 2, 1),
                jurisdiction=RegulatoryJurisdiction.US,
                authority=RegulatoryAuthority.FDA,
                asset=poziotinib_ref,
                indication=nsclc_ref,
                event=RegulatoryEventPayload(
                    event_type=RegulatoryEventType.FAST_TRACK,
                    headline="FDA Grants Fast Track Designation for Poziotinib in HER2 Exon 20 Insertion NSCLC",
                    details="Fast Track granted for previously treated patients with HER2 exon 20 insertion mutant non-small cell lung cancer.",
                ),
                confidence=0.95,
            )
        )

        # Poziotinib Advisory Committee (2022-09-22)
        self.record_event(
            RegulatoryEventRecord(
                source=RegulatorySource(
                    source_type=RegulatorySourceType.FEDERAL_REGISTER,
                    source_citation="FDA Oncologic Drugs Advisory Committee (ODAC) Meeting Briefing Document and Vote",
                    source_url="https://www.fda.gov/advisory-committees/oncologic-drugs-advisory-committee",
                    source_document_id="FDA-2022-N-1563",
                    is_verified_evidence=True,
                    publication_date=date(2022, 9, 22),
                ),
                event_date=date(2022, 9, 22),
                jurisdiction=RegulatoryJurisdiction.US,
                authority=RegulatoryAuthority.FDA,
                asset=poziotinib_ref,
                indication=nsclc_ref,
                event=RegulatoryEventPayload(
                    event_type=RegulatoryEventType.REGULATORY_MILESTONE,
                    headline="FDA ODAC Votes Against Poziotinib Benefit-Risk Profile",
                    details="ODAC panel voted 9 to 4 that the benefits of poziotinib do not outweigh its risks for HER2 exon 20 insertion NSCLC due to severe EGFR-mediated toxicity and marginal response durability.",
                    milestone_type="ADCOM_VOTE",
                ),
                confidence=0.99,
            )
        )

        # Poziotinib Complete Response Letter (2022-11-25)
        self.record_event(
            RegulatoryEventRecord(
                source=RegulatorySource(
                    source_type=RegulatorySourceType.SEC_8K_FILING,
                    source_citation="Spectrum Pharmaceuticals SEC Form 8-K Regulatory Action Announcement",
                    source_document_id="SEC:0001193125-22-293814",
                    is_verified_evidence=True,
                    publication_date=date(2022, 11, 25),
                ),
                event_date=date(2022, 11, 25),
                jurisdiction=RegulatoryJurisdiction.US,
                authority=RegulatoryAuthority.FDA,
                asset=poziotinib_ref,
                indication=nsclc_ref,
                event=RegulatoryEventPayload(
                    event_type=RegulatoryEventType.COMPLETE_RESPONSE_LETTER,
                    headline="FDA Issues Complete Response Letter (CRL) for Poziotinib NDA",
                    details="FDA determined that the NDA cannot be approved in its present form, citing insufficient efficacy durability, safety profile concerns, and requirement for an additional randomized confirmatory trial.",
                ),
                confidence=1.0,
            )
        )

        # Poziotinib Application Withdrawal (2023-01-10)
        self.record_event(
            RegulatoryEventRecord(
                source=RegulatorySource(
                    source_type=RegulatorySourceType.SPONSOR_REGULATORY_DISCLOSURE,
                    source_citation="Spectrum Pharmaceuticals Corporate Filing: Discontinuation and Program De-prioritization",
                    source_document_id="SEC:0001193125-23-005112",
                    is_verified_evidence=True,
                    publication_date=date(2023, 1, 10),
                ),
                event_date=date(2023, 1, 10),
                jurisdiction=RegulatoryJurisdiction.US,
                authority=RegulatoryAuthority.FDA,
                asset=poziotinib_ref,
                indication=nsclc_ref,
                event=RegulatoryEventPayload(
                    event_type=RegulatoryEventType.WITHDRAWAL,
                    headline="Sponsor Formally Withdraws Poziotinib Regulatory Submissions",
                    details="Following the CRL, sponsor discontinued regulatory pursuits for poziotinib in HER2 exon 20 insertion NSCLC to focus resources on other pipeline assets.",
                ),
                confidence=0.98,
            )
        )

        # 3. Neratinib (Nerlynx) Canonical Events
        neratinib_id = UUID("22222222-2222-2222-2222-222222222222")
        neratinib_ref = RegulatoryAssetRef(asset_id=neratinib_id, asset_name="Neratinib")
        early_bc_ref = RegulatoryIndicationRef(indication_name="Early-Stage HER2+ Breast Cancer", cancer_subtype="Adjuvant HER2+ BC")

        # Neratinib Full Approval (2017-07-17)
        self.record_event(
            RegulatoryEventRecord(
                source=RegulatorySource(
                    source_type=RegulatorySourceType.FDA_DRUGS_AT_FDA,
                    source_citation="FDA CDER Application NDA 16-193 Approval Letter and Dossier",
                    source_document_id="NDA 016193/Orig-1",
                    is_verified_evidence=True,
                    publication_date=date(2017, 7, 17),
                ),
                event_date=date(2017, 7, 17),
                jurisdiction=RegulatoryJurisdiction.US,
                authority=RegulatoryAuthority.FDA,
                asset=neratinib_ref,
                indication=early_bc_ref,
                event=RegulatoryEventPayload(
                    event_type=RegulatoryEventType.FULL_APPROVAL,
                    headline="FDA Approves Nerlynx (neratinib) for Extended Adjuvant Treatment of HER2+ Early Breast Cancer",
                    details="Approved for adult patients with early-stage HER2-overexpressed/amplified breast cancer, to follow adjuvant trastuzumab-based therapy based on the ExteNET trial.",
                ),
                confidence=1.0,
            )
        )

        # Neratinib Safety Warning (Boxed / Severe Diarrhea Warning) (2017-07-17)
        self.record_event(
            RegulatoryEventRecord(
                source=RegulatorySource(
                    source_type=RegulatorySourceType.FDA_ACTION_LETTER,
                    source_citation="FDA Approved Product Labeling NDA 016193, Warnings and Precautions Section 5.1",
                    source_document_id="NDA 016193-LABEL-1",
                    is_verified_evidence=True,
                    publication_date=date(2017, 7, 17),
                ),
                event_date=date(2017, 7, 17),
                jurisdiction=RegulatoryJurisdiction.US,
                authority=RegulatoryAuthority.FDA,
                asset=neratinib_ref,
                indication=early_bc_ref,
                event=RegulatoryEventPayload(
                    event_type=RegulatoryEventType.SAFETY_WARNING,
                    headline="FDA Mandates Severe Diarrhea Warning and Mandatory Loperamide Prophylaxis",
                    details="Prescribing information includes prominent warning for severe diarrhea (Grade 3 in 40% without prophylaxis). Mandatory antidiarrheal prophylaxis with loperamide required during first 56 days of treatment.",
                ),
                confidence=1.0,
            )
        )

        # Neratinib Supplemental Approval (2020-02-25)
        self.record_event(
            RegulatoryEventRecord(
                source=RegulatorySource(
                    source_type=RegulatorySourceType.FDA_DRUGS_AT_FDA,
                    source_citation="FDA Supplemental Approval Letter NDA 016193/S-004",
                    source_document_id="NDA 016193/S-004",
                    is_verified_evidence=True,
                    publication_date=date(2020, 2, 25),
                ),
                event_date=date(2020, 2, 25),
                jurisdiction=RegulatoryJurisdiction.US,
                authority=RegulatoryAuthority.FDA,
                asset=neratinib_ref,
                indication=mBC_ref,
                event=RegulatoryEventPayload(
                    event_type=RegulatoryEventType.SUPPLEMENTAL_APPROVAL,
                    headline="FDA Approves Nerlynx in Combination with Capecitabine for HER2+ Metastatic Breast Cancer",
                    details="Supplemental approval for patients with advanced or metastatic HER2-positive breast cancer who have received two or more prior anti-HER2 based regimens, based on the NALA trial.",
                ),
                confidence=1.0,
            )
        )

        # Neratinib Label Change / Expansion (2021-06-30)
        self.record_event(
            RegulatoryEventRecord(
                source=RegulatorySource(
                    source_type=RegulatorySourceType.FDA_DRUGS_AT_FDA,
                    source_citation="FDA Label Revision NDA 016193 Dose Escalation Labeling Update",
                    source_document_id="NDA 016193/S-008",
                    is_verified_evidence=True,
                    publication_date=date(2021, 6, 30),
                ),
                event_date=date(2021, 6, 30),
                jurisdiction=RegulatoryJurisdiction.US,
                authority=RegulatoryAuthority.FDA,
                asset=neratinib_ref,
                indication=early_bc_ref,
                event=RegulatoryEventPayload(
                    event_type=RegulatoryEventType.LABEL_CHANGE,
                    headline="FDA Approves Dose Escalation Strategy in Nerlynx Prescribing Information",
                    details="Label updated to incorporate alternative 2-week dose escalation schedule to improve gastrointestinal tolerability based on the CONTROL trial.",
                ),
                confidence=0.98,
            )
        )

        # 4. Zongertinib Canonical Events
        zongertinib_id = UUID("00000000-0000-0000-0000-000000000001")
        zongertinib_ref = RegulatoryAssetRef(asset_id=zongertinib_id, asset_name="Zongertinib")

        # Zongertinib IND Cleared (2021-04-15)
        self.record_event(
            RegulatoryEventRecord(
                source=RegulatorySource(
                    source_type=RegulatorySourceType.SPONSOR_REGULATORY_DISCLOSURE,
                    source_citation="Boehringer Ingelheim Clinical Development Regulatory Notice, IND 154210",
                    source_document_id="IND 154210",
                    is_verified_evidence=True,
                    publication_date=date(2021, 4, 15),
                ),
                event_date=date(2021, 4, 15),
                jurisdiction=RegulatoryJurisdiction.US,
                authority=RegulatoryAuthority.FDA,
                asset=zongertinib_ref,
                indication=nsclc_ref,
                event=RegulatoryEventPayload(
                    event_type=RegulatoryEventType.IND_RELATED,
                    headline="FDA Clears IND for Oral HER2 TKI BI 1810631 (Zongertinib)",
                    details="IND 154210 cleared to evaluate oral selective HER2 tyrosine kinase inhibitor in patients with advanced solid tumors harboring HER2 alterations.",
                ),
                confidence=0.98,
            )
        )

        # Zongertinib Fast Track (2023-08-25)
        self.record_event(
            RegulatoryEventRecord(
                source=RegulatorySource(
                    source_type=RegulatorySourceType.SPONSOR_REGULATORY_DISCLOSURE,
                    source_citation="Boehringer Ingelheim Official Regulatory Announcement",
                    source_document_id="BI-PR-20230825",
                    is_verified_evidence=True,
                    publication_date=date(2023, 8, 25),
                ),
                event_date=date(2023, 8, 25),
                jurisdiction=RegulatoryJurisdiction.US,
                authority=RegulatoryAuthority.FDA,
                asset=zongertinib_ref,
                indication=nsclc_ref,
                event=RegulatoryEventPayload(
                    event_type=RegulatoryEventType.FAST_TRACK,
                    headline="FDA Grants Fast Track Designation for Zongertinib in HER2-Mutated NSCLC",
                    details="Fast Track designation granted for the treatment of adult patients with advanced or metastatic NSCLC whose tumors have activating HER2 mutations.",
                ),
                confidence=0.97,
            )
        )

        # Zongertinib Breakthrough Therapy (2024-04-18)
        self.record_event(
            RegulatoryEventRecord(
                source=RegulatorySource(
                    source_type=RegulatorySourceType.SPONSOR_REGULATORY_DISCLOSURE,
                    source_citation="Boehringer Ingelheim Regulatory Notice: FDA Grants Breakthrough Therapy Designation",
                    source_document_id="BI-PR-20240418",
                    is_verified_evidence=True,
                    publication_date=date(2024, 4, 18),
                ),
                event_date=date(2024, 4, 18),
                jurisdiction=RegulatoryJurisdiction.US,
                authority=RegulatoryAuthority.FDA,
                asset=zongertinib_ref,
                indication=nsclc_ref,
                event=RegulatoryEventPayload(
                    event_type=RegulatoryEventType.BREAKTHROUGH_THERAPY,
                    headline="FDA Grants Breakthrough Therapy Designation for Zongertinib in Previously Treated HER2-Mutant NSCLC",
                    details="Breakthrough Therapy granted based on confirmed objective response rates and intracranial durability from the Beamion LUNG-1 trial.",
                ),
                confidence=0.98,
            )
        )

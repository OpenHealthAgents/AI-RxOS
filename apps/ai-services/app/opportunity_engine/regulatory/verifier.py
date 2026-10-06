from __future__ import annotations

import logging
from typing import Tuple

from .models import (
    RegulatoryEventRecord,
    RegulatoryEventType,
    RegulatorySourceType,
    UnverifiedMarketingClaimError,
    VerificationStatus,
)

logger = logging.getLogger(__name__)


class RegulatoryEvidenceVerifier:
    """
    Enforces the fundamental architectural invariant:
    'Never infer regulatory approval from marketing claims without verified evidence.'

    Validates provenance, agency authority correspondence, statutory SEC 8-K filings,
    and flags uncorroborated commercial claims.
    """

    APPROVAL_EVENT_TYPES = {
        RegulatoryEventType.FULL_APPROVAL,
        RegulatoryEventType.ACCELERATED_APPROVAL,
        RegulatoryEventType.SUPPLEMENTAL_APPROVAL,
    }

    OFFICIAL_VERIFIED_SOURCES = {
        RegulatorySourceType.FDA_DRUGS_AT_FDA,
        RegulatorySourceType.FDA_ACTION_LETTER,
        RegulatorySourceType.FDA_ORANGE_BOOK,
        RegulatorySourceType.EMA_EPAR,
        RegulatorySourceType.PMDA_NOTICE,
        RegulatorySourceType.NMPA_NOTICE,
        RegulatorySourceType.SEC_8K_FILING,
        RegulatorySourceType.FEDERAL_REGISTER,
        RegulatorySourceType.SPONSOR_REGULATORY_DISCLOSURE,
    }

    UNVERIFIED_SOURCES = {
        RegulatorySourceType.UNVERIFIED_MARKETING_CLAIM,
    }

    @classmethod
    def verify(
        cls,
        event: RegulatoryEventRecord,
        strict: bool = False,
    ) -> Tuple[bool, RegulatoryEventRecord]:
        """
        Evaluates a regulatory event against evidence verification policies.

        Returns (is_valid, validated_event).
        If strict=True and an unverified approval claim is detected, raises UnverifiedMarketingClaimError.
        """
        is_approval = event.event.event_type in cls.APPROVAL_EVENT_TYPES
        source = event.source

        # Case 1: Unverified marketing claim attempting to assert regulatory approval
        if is_approval and (source.source_type in cls.UNVERIFIED_SOURCES or not source.is_verified_evidence):
            violation_msg = (
                f"Regulatory approval ({event.event.event_type.value}) for {event.asset.asset_name} "
                f"cannot be inferred from marketing claims or unverified evidence ({source.source_citation}). "
                "Official regulatory agency action letter, registry listing, or statutory SEC 8-K filing is strictly required."
            )
            logger.warning("Regulatory Verification Rejection: %s", violation_msg)

            if strict:
                raise UnverifiedMarketingClaimError(violation_msg)

            # Downgrade and flag policy violation
            event.verification_status = VerificationStatus.REJECTED_UNVERIFIED_MARKETING
            event.confidence = 0.0
            event.policy_violation = violation_msg
            return False, event

        # Case 2: Marketing claim attempting to assert designations (Breakthrough, Fast Track, Orphan)
        if event.event.event_type in (
            RegulatoryEventType.BREAKTHROUGH_THERAPY,
            RegulatoryEventType.FAST_TRACK,
            RegulatoryEventType.ORPHAN_DRUG,
        ) and source.source_type in cls.UNVERIFIED_SOURCES:
            violation_msg = (
                f"Regulatory designation ({event.event.event_type.value}) requires agency confirmation "
                "or formal sponsor disclosure. Unverified marketing claim flagged."
            )
            event.verification_status = VerificationStatus.PROVISIONAL_PENDING_CONFIRMATION
            event.confidence = min(event.confidence, 0.25)
            event.policy_violation = violation_msg
            return True, event

        # Case 3: Official verified regulatory source
        if source.source_type in cls.OFFICIAL_VERIFIED_SOURCES and source.is_verified_evidence:
            event.verification_status = VerificationStatus.VERIFIED_OFFICIAL_RECORD
            event.policy_violation = None
            if event.confidence < 0.90:
                event.confidence = 0.98
            return True, event

        # Case 4: Other provisional or non-statutory records
        event.verification_status = VerificationStatus.PROVISIONAL_PENDING_CONFIRMATION
        return True, event

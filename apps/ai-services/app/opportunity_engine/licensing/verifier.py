from __future__ import annotations

import logging
import re
from typing import Tuple

from .models import (
    AssetOwnershipProfile,
    LicensingStatus,
    MANDATORY_FTO_DISCLAIMER,
    ProhibitedFTOAssertionError,
    UnverifiedLicensingAssertionError,
)

logger = logging.getLogger(__name__)


class LicensingAndIPGuard:
    """
    Enforces strict architectural rules for ownership and IP intelligence:
    1. Never state 'licensing available' unless verified by public primary evidence.
    2. IP analysis is competitive intelligence, not legal advice.
    3. Never claim freedom to operate (FTO).
    """

    FTO_PROHIBITED_PATTERNS = [
        re.compile(r"\b(?:has\s+.*)?freedom\s+to\s+operate\b", re.I),
        re.compile(r"\b(?:guaranteed|clear|unencumbered|confirmed|established)\s+fto\b", re.I),
        re.compile(r"\b(?:no\s+infringement(?:\s+risk)?|clear\s+of\s+(?:third[- ]party\s+)?patents)\b", re.I),
        re.compile(r"\blegal\s+non[- ]infringement(?:\s+opinion)?\b", re.I),
    ]

    @classmethod
    def validate_licensing_status(
        cls,
        status: LicensingStatus,
        is_verified: bool,
        verification_source: str | None,
        strict: bool = True,
    ) -> Tuple[LicensingStatus, bool, str]:
        """
        Guarantees that VERIFIED_AVAILABLE is only accepted when accompanied by
        verified public documentation.
        """
        if status == LicensingStatus.VERIFIED_AVAILABLE:
            if not is_verified or not verification_source or not verification_source.strip():
                violation_msg = (
                    "Policy Invariant Violation: Never state 'licensing available' (VERIFIED_AVAILABLE) "
                    "without verified public partnering documentation, formal SEC disclosure, or official institutional listing."
                )
                logger.warning("Licensing Verification Rejection: %s", violation_msg)
                if strict:
                    raise UnverifiedLicensingAssertionError(violation_msg)
                # Fallback to POTENTIALLY_AVAILABLE
                return LicensingStatus.POTENTIALLY_AVAILABLE, False, "Downgraded from VERIFIED_AVAILABLE: unverified claim"

        return status, is_verified, verification_source or ""

    @classmethod
    def audit_fto_statements(cls, text: str) -> None:
        """
        Scans textual analysis to ensure no claims of Freedom to Operate (FTO)
        or legal non-infringement are ever made.
        """
        if not text:
            return

        for pattern in cls.FTO_PROHIBITED_PATTERNS:
            match = pattern.search(text)
            if match:
                violation = (
                    f"Prohibited FTO Claim Detected: '{match.group(0)}'. "
                    "System policy strictly forbids claiming Freedom to Operate (FTO). "
                    "IP analysis is competitive and scientific decision intelligence, not legal advice."
                )
                logger.error("FTO Guardrail Triggered: %s", violation)
                raise ProhibitedFTOAssertionError(violation)

    @classmethod
    def verify_profile(
        cls,
        profile: AssetOwnershipProfile,
        strict: bool = True,
    ) -> AssetOwnershipProfile:
        """
        Audits full ownership profile for licensing state integrity, FTO violations,
        and ensures mandatory disclaimer is present.
        """
        # 1. Audit licensing status
        status, verified, source = cls.validate_licensing_status(
            status=profile.licensing_status,
            is_verified=profile.licensing_status_verified,
            verification_source=profile.licensing_verification_source,
            strict=strict,
        )
        profile.licensing_status = status
        profile.licensing_status_verified = verified
        profile.licensing_verification_source = source

        # 2. Check rationale for illegal FTO claims
        cls.audit_fto_statements(profile.licensing_status_rationale)

        # 3. Ensure mandatory disclaimer is attached
        profile.fto_disclaimer = MANDATORY_FTO_DISCLAIMER
        return profile

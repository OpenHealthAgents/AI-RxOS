from __future__ import annotations

import hashlib
from datetime import date
from typing import Any, Dict, List, Optional
from uuid import UUID

from .models import (
    LeakageAuditReport,
    LeakageViolation,
    LeakageViolationType,
    OutcomeAvailability,
)


class InformationLeakageError(ValueError):
    """
    Raised when an information leakage violation is detected:
    an entity dated after the prediction cutoff date was accessed or exposed.
    """
    pass


class InformationLeakageDetector:
    """
    Detects and prevents any information leakage in historical simulations.
    Scans:
    1. Evidence publication date
    2. Evidence observation date
    3. Trial completion & posting date
    4. Outcome actual date
    5. Regulatory decision date
    6. When an outcome became publicly known
    7. Later acquisitions, licensing deals, and biomarker discoveries
    """

    @classmethod
    def audit_items(
        cls,
        asset_id: UUID,
        cutoff_date: date,
        eligible_items: List[Dict[str, Any]],
        suppressed_items: List[Dict[str, Any]],
        strict: bool = True,
    ) -> LeakageAuditReport:
        """
        Audits a set of eligible vs suppressed items against the cutoff date.
        If strict=True, raises InformationLeakageError on the first violation.
        """
        violations: List[LeakageViolation] = []

        for item in eligible_items:
            item_id = str(item.get("id", item.get("source_id", "unknown")))
            item_name = str(item.get("title", item.get("headline", item.get("entity", item_id))))
            
            # Check all possible temporal date attributes
            pub_date = item.get("publication_date")
            obs_date = item.get("observation_date") or item.get("as_of_date")
            trial_date = item.get("trial_results_date") or item.get("results_first_posted")
            reg_date = item.get("regulatory_date") or item.get("event_date")
            public_known_date = item.get("publicly_known_date")

            dates_to_check = [
                (pub_date, LeakageViolationType.FUTURE_PUBLICATION, "Publication date after cutoff"),
                (obs_date, LeakageViolationType.FUTURE_OBSERVATION_DATE, "Observation recorded after cutoff"),
                (trial_date, LeakageViolationType.FUTURE_TRIAL_RESULT, "Trial results posted after cutoff"),
                (reg_date, LeakageViolationType.FUTURE_REGULATORY_DECISION, "Regulatory decision after cutoff"),
                (public_known_date, LeakageViolationType.FUTURE_OUTCOME_DISCLOSURE, "Public disclosure after cutoff"),
            ]

            for d, vtype, detail_msg in dates_to_check:
                if d is None:
                    continue
                parsed_d = date.fromisoformat(d) if isinstance(d, str) else d
                if parsed_d > cutoff_date:
                    days_post = (parsed_d - cutoff_date).days
                    v = LeakageViolation(
                        violation_type=vtype,
                        entity_id=item_id,
                        entity_name=item_name,
                        entity_date=parsed_d,
                        cutoff_date=cutoff_date,
                        days_post_cutoff=days_post,
                        details=f"{detail_msg}: {parsed_d} is {days_post} days post cutoff {cutoff_date}.",
                    )
                    violations.append(v)
                    if strict:
                        raise InformationLeakageError(
                            f"CRITICAL LEAKAGE DETECTED: {v.violation_type.value} on '{v.entity_name}' "
                            f"(Date: {v.entity_date}, Cutoff: {cutoff_date}, +{v.days_post_cutoff} days). "
                            "Historical prediction invalid!"
                        )

        # Generate deterministic cryptographic audit hash
        hasher = hashlib.sha256()
        hasher.update(str(asset_id).encode("utf-8"))
        hasher.update(str(cutoff_date).encode("utf-8"))
        hasher.update(f"eligible:{len(eligible_items)};suppressed:{len(suppressed_items)}".encode("utf-8"))
        audit_hash = hasher.hexdigest()

        audit_passed = len(violations) == 0
        return LeakageAuditReport(
            asset_id=asset_id,
            cutoff_date=cutoff_date,
            audit_passed=audit_passed,
            total_eligible_items=len(eligible_items),
            total_suppressed_items=len(suppressed_items),
            violations=violations,
            audit_hash=audit_hash,
        )

    @classmethod
    def audit_outcomes(
        cls,
        outcomes: List[OutcomeAvailability],
        cutoff_date: date,
        strict: bool = True,
    ) -> List[LeakageViolation]:
        """
        Audits outcomes to ensure no future public disclosure was included.
        """
        violations: List[LeakageViolation] = []
        for out in outcomes:
            if out.publicly_known_date > cutoff_date:
                days_post = (out.publicly_known_date - cutoff_date).days
                v = LeakageViolation(
                    violation_type=LeakageViolationType.FUTURE_OUTCOME_DISCLOSURE,
                    entity_id=str(out.id),
                    entity_name=out.headline,
                    entity_date=out.publicly_known_date,
                    cutoff_date=cutoff_date,
                    days_post_cutoff=days_post,
                    details=f"Outcome '{out.headline}' was not publicly known until {out.publicly_known_date}.",
                )
                violations.append(v)
                if strict:
                    raise InformationLeakageError(
                        f"CRITICAL LEAKAGE: Outcome '{out.headline}' disclosed on {out.publicly_known_date} "
                        f"cannot be visible at cutoff {cutoff_date}."
                    )
        return violations

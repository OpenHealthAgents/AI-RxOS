from __future__ import annotations

import re
from typing import Optional
from .models import NormalizedClinicalStage


class ClinicalStageNormalizer:
    """
    Normalizes raw ClinicalTrials.gov phase and status strings into the canonical
    12 development stages:
    Preclinical, IND-enabling, Phase I, Phase Ib, Phase II, Phase II/III, Phase III,
    Regulatory review, Approved, Withdrawn, Terminated, Discontinued.
    """

    @classmethod
    def normalize(
        cls,
        phase_raw: str,
        status: str,
        why_stopped: Optional[str] = None,
        is_fda_approved: bool = False,
    ) -> NormalizedClinicalStage:
        clean_status = (status or "").strip().upper()
        clean_phase = (phase_raw or "").strip().lower()

        # 1. Terminal / Interrupted statuses take precedence
        if "WITHDRAWN" in clean_status:
            return NormalizedClinicalStage.WITHDRAWN

        if "TERMINATED" in clean_status:
            return NormalizedClinicalStage.TERMINATED

        if any(term in clean_status for term in ("SUSPENDED", "DISCONTINUED", "TEMPORARILY_NOT_AVAILABLE")):
            return NormalizedClinicalStage.DISCONTINUED

        if is_fda_approved or "APPROVED" in clean_status:
            return NormalizedClinicalStage.APPROVED

        if any(term in clean_status for term in ("NDA", "BLA", "REGULATORY", "FILED")):
            return NormalizedClinicalStage.REGULATORY_REVIEW

        # 2. Phase / Stage based normalization
        if re.search(r"\b(regulatory\s*review|registration|nda|bla|filing|prv)\b", clean_phase):
            return NormalizedClinicalStage.REGULATORY_REVIEW

        if re.search(r"\b(phase\s*4|post[- ]marketing)\b", clean_phase):
            return NormalizedClinicalStage.APPROVED

        if re.search(r"\b(phase\s*1b|phase\s*ib|1b|ib)\b", clean_phase):
            return NormalizedClinicalStage.PHASE_IB

        if re.search(r"\b(phase\s*(?:2/3|ii/iii|2/phase\s*3|ii/phase\s*iii|2b/3))\b", clean_phase):
            return NormalizedClinicalStage.PHASE_II_III

        if re.search(r"\b(phase\s*(?:1/2|i/ii|1/phase\s*2|i/phase\s*ii|1a/1b|ia/ib))\b", clean_phase):
            return NormalizedClinicalStage.PHASE_II

        if re.search(r"\b(phase\s*3|phase\s*iii|p3)\b", clean_phase):
            return NormalizedClinicalStage.PHASE_III

        if re.search(r"\b(phase\s*2|phase\s*ii|p2)\b", clean_phase):
            return NormalizedClinicalStage.PHASE_II

        if re.search(r"\b(phase\s*1|phase\s*i|early\s*phase\s*1|p1)\b", clean_phase):
            return NormalizedClinicalStage.PHASE_I

        if re.search(r"\b(ind[- ]enabling|glp\s*toxicology|pre[- ]ind|ind\s*submission|\bind\b)\b", clean_phase):
            return NormalizedClinicalStage.IND_ENABLING

        if re.search(r"\b(pre[- ]?clinical|discovery|in\s*vitro|animal|validation)\b", clean_phase):
            return NormalizedClinicalStage.PRECLINICAL

        # Default fallback if phase is "NA" or "Not Applicable"
        if clean_status in ("COMPLETED", "ACTIVE_NOT_RECRUITING", "RECRUITING"):
            return NormalizedClinicalStage.PHASE_II

        return NormalizedClinicalStage.PRECLINICAL

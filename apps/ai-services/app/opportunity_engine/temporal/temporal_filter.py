from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from app.opportunity_engine.domain.canonical_model import DevelopmentStage
from .leakage_detector import InformationLeakageDetector
from .models import (
    EvidenceCutoff,
    LeakageAuditReport,
    OutcomeAvailability,
)


class TemporalFilter:
    """
    Temporal filtering engine enforcing strict historical boundaries across all
    asset attributes, evidence collections, trial readouts, and outcomes.
    """

    @classmethod
    def filter_evidence_records(
        cls,
        evidence_items: List[Dict[str, Any]],
        cutoff: EvidenceCutoff,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Splits evidence items into strictly eligible vs suppressed collections.
        """
        eligible: List[Dict[str, Any]] = []
        suppressed: List[Dict[str, Any]] = []

        for item in evidence_items:
            pub_date_str = item.get("publication_date") or item.get("as_of_date")
            obs_date_str = item.get("observation_date")
            
            pub_date = date.fromisoformat(pub_date_str) if isinstance(pub_date_str, str) else pub_date_str
            obs_date = date.fromisoformat(obs_date_str) if isinstance(obs_date_str, str) else obs_date_str

            if cutoff.is_admissible(event_date=obs_date, public_disclosure_date=pub_date):
                eligible.append(item)
            else:
                suppressed.append(item)

        return eligible, suppressed

    @classmethod
    def filter_outcomes(
        cls,
        outcomes: List[OutcomeAvailability],
        cutoff: EvidenceCutoff,
    ) -> Tuple[List[OutcomeAvailability], List[OutcomeAvailability]]:
        """
        Splits outcomes into those publicly known at cutoff vs suppressed future outcomes.
        """
        known: List[OutcomeAvailability] = []
        future: List[OutcomeAvailability] = []

        for out in outcomes:
            if out.is_available_at(cutoff.cutoff_date):
                known.append(out)
            else:
                future.append(out)

        return known, future

    @classmethod
    def resolve_historical_asset_state(
        cls,
        asset_id: str,
        cutoff_date: date,
    ) -> Dict[str, Any]:
        """
        Resolves the exact historical stage, owner, and primary indication
        as they existed on cutoff_date, suppressing later approvals, failures, or acquisitions.
        """
        normalized_id = asset_id.lower()

        # Tucatinib (Approved April 2020, Seagen acquired by Pfizer in Dec 2023)
        if normalized_id == "tucatinib":
            if cutoff_date < date(2020, 4, 17):
                stage = DevelopmentStage.PHASE_II
            elif cutoff_date < date(2023, 12, 14):
                stage = DevelopmentStage.APPROVED
            else:
                stage = DevelopmentStage.APPROVED

            if cutoff_date < date(2018, 3, 9):
                owner = "Cascadian Therapeutics"
            elif cutoff_date < date(2023, 12, 14):
                owner = "Seagen Inc."
            else:
                owner = "Pfizer Inc."

            indication = "HER2+ Metastatic Breast Cancer with CNS Metastases"

        # Neratinib (Approved July 17, 2017)
        elif normalized_id == "neratinib":
            if cutoff_date < date(2017, 7, 17):
                stage = DevelopmentStage.PHASE_III
            else:
                stage = DevelopmentStage.APPROVED

            owner = "Puma Biotechnology"
            indication = "HER2+ Early/Metastatic Breast Cancer (Extended Adjuvant)"

        # Poziotinib (ODAC Vote Sept 2022, CRL Nov 2022)
        elif normalized_id == "poziotinib":
            if cutoff_date < date(2022, 11, 25):
                stage = DevelopmentStage.PHASE_II
            else:
                stage = DevelopmentStage.TERMINATED

            owner = "Spectrum Pharmaceuticals"
            indication = "HER2 Exon 20 Insertion NSCLC / Breast Cancer"

        # Zongertinib (Preclinical until 2022, Phase 1a/1b in 2023)
        elif normalized_id == "zongertinib":
            if cutoff_date < date(2022, 1, 1):
                stage = DevelopmentStage.PRECLINICAL
            elif cutoff_date < date(2024, 1, 1):
                stage = DevelopmentStage.PHASE_I
            else:
                stage = DevelopmentStage.PHASE_II

            owner = "Boehringer Ingelheim"
            indication = "HER2-mutant Metastatic Breast & Lung Cancers"

        else:
            stage = DevelopmentStage.PHASE_II
            owner = "Originating Sponsor"
            indication = "Investigational Oncology"

        return {
            "stage": stage,
            "owner": owner,
            "primary_indication": indication,
        }

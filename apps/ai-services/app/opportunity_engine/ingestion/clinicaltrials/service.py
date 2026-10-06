from __future__ import annotations

import time
from datetime import date
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from .models import (
    ClinicalTrialRecord,
    NormalizedClinicalStage,
    TrialResolutionSummary,
    TrialStatusHistory,
)
from .normalizer import ClinicalStageNormalizer
from .resolution import ClinicalTrialResolver


class ClinicalTrialsIngestionService:
    """
    Production-quality ClinicalTrials.gov ingestion service providing:
    - Capture of all 20 structural trial attributes
    - Canonical 12-stage normalization
    - Temporal status history tracking
    - Trial-to-asset, indication, biomarker, and company resolution
    - Idempotent upserts and deduplication
    """

    def __init__(self, resolver: Optional[ClinicalTrialResolver] = None) -> None:
        self.resolver = resolver or ClinicalTrialResolver()
        self.trials_by_nct: Dict[str, ClinicalTrialRecord] = {}
        self.resolutions_by_nct: Dict[str, TrialResolutionSummary] = {}
        self.history_by_nct: Dict[str, List[TrialStatusHistory]] = {}

    def ingest_trial(
        self,
        trial: ClinicalTrialRecord,
        as_of_date: Optional[date] = None,
        why_stopped: Optional[str] = None,
    ) -> ClinicalTrialRecord:
        """
        Ingests or updates a clinical trial record, normalizes stage,
        records status history transition, and resolves canonical entities.
        """
        nct_id = trial.nct_id.strip().upper()
        current_date = as_of_date or date.today()

        # 1. Normalize Clinical Stage
        norm_stage = ClinicalStageNormalizer.normalize(
            phase_raw=trial.phase_raw,
            status=trial.status,
            why_stopped=trial.termination_reason or trial.withdrawal_reason or why_stopped,
        )
        trial.normalized_stage = norm_stage

        # 2. Track Status Changes Over Time
        history_list = self.history_by_nct.setdefault(nct_id, [])
        is_new_status = not history_list or history_list[-1].overall_status != trial.status or history_list[-1].normalized_stage != norm_stage

        if is_new_status:
            history_item = TrialStatusHistory(
                nct_id=nct_id,
                as_of_date=current_date,
                overall_status=trial.status,
                normalized_stage=norm_stage,
                why_stopped=trial.termination_reason or trial.withdrawal_reason or why_stopped,
                enrollment=trial.enrollment,
                results_posted=trial.results is not None,
                change_summary=f"Status transitioned to {trial.status} ({norm_stage.value})",
            )
            history_list.append(history_item)
            trial.status_history = list(history_list)

        # 3. Store Trial Record
        self.trials_by_nct[nct_id] = trial

        # 4. Resolve Canonical Mappings
        resolutions = self.resolver.resolve_all(trial)
        self.resolutions_by_nct[nct_id] = resolutions

        return trial

    def get_trial(self, nct_id: str) -> Optional[ClinicalTrialRecord]:
        return self.trials_by_nct.get(nct_id.strip().upper())

    def get_resolutions(self, nct_id: str) -> Optional[TrialResolutionSummary]:
        return self.resolutions_by_nct.get(nct_id.strip().upper())

    def get_trial_status_at_cutoff(
        self,
        nct_id: str,
        cutoff_date: date,
    ) -> Optional[TrialStatusHistory]:
        """
        Reconstructs the trial's exact status and normalized stage as it existed
        on cutoff_date, enforcing zero information leakage.
        """
        history_list = self.history_by_nct.get(nct_id.strip().upper(), [])
        eligible_history = [h for h in history_list if h.as_of_date <= cutoff_date]
        if not eligible_history:
            return None
        return eligible_history[-1]

from __future__ import annotations

import re
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from app.opportunity_engine.domain.entity_resolution import CanonicalAssetResolver
from .models import (
    ClinicalTrialRecord,
    TrialAssetMapping,
    TrialBiomarkerMapping,
    TrialCompanyMapping,
    TrialIndicationMapping,
    TrialResolutionSummary,
)


class ClinicalTrialResolver:
    """
    Multi-faceted resolution engine connecting raw ClinicalTrials.gov records to:
    1. Canonical Asset
    2. Canonical Indication
    3. Canonical Biomarker
    4. Canonical Company / Sponsor
    """

    def __init__(self, asset_resolver: Optional[CanonicalAssetResolver] = None) -> None:
        self.asset_resolver = asset_resolver or CanonicalAssetResolver()
        self._bootstrap_resolvers()

    def resolve_all(self, trial: ClinicalTrialRecord) -> TrialResolutionSummary:
        """Runs all 4 resolutions over the trial record."""
        return TrialResolutionSummary(
            nct_id=trial.nct_id,
            assets=self.resolve_trial_to_asset(trial),
            indications=self.resolve_trial_to_indication(trial),
            biomarkers=self.resolve_trial_to_biomarker(trial),
            companies=self.resolve_trial_to_company(trial),
        )

    def resolve_trial_to_asset(self, trial: ClinicalTrialRecord) -> List[TrialAssetMapping]:
        """Resolves trial interventions and titles to canonical drug assets."""
        mappings: List[TrialAssetMapping] = []
        seen_assets = set()

        candidates_to_check = [trial.study_title, trial.official_title or ""]
        for intv in trial.interventions:
            candidates_to_check.append(intv.name)
            if intv.description:
                candidates_to_check.append(intv.description)

        for text in candidates_to_check:
            if not text:
                continue
            # Look for drug names or codes
            for token in re.findall(r"\b([A-Z]{2,4}[- ]?\d{4,7}|[A-Za-z]{5,20})\b", text):
                res = self.asset_resolver.resolve(token)
                if res.resolved and res.match and res.match.asset_id not in seen_assets:
                    seen_assets.add(res.match.asset_id)
                    mappings.append(
                        TrialAssetMapping(
                            nct_id=trial.nct_id,
                            asset_id=res.match.asset_id,
                            canonical_name=res.match.canonical_name,
                            intervention_name=token,
                            is_primary=True,
                            confidence=res.match.confidence,
                        )
                    )

        return mappings

    def resolve_trial_to_indication(self, trial: ClinicalTrialRecord) -> List[TrialIndicationMapping]:
        """Maps conditions to normalized disease & cancer subtypes."""
        mappings: List[TrialIndicationMapping] = []
        seen = set()

        has_her2 = (
            "HER2" in trial.study_title.upper()
            or "ERBB2" in trial.study_title.upper()
            or any("HER2" in b.upper() or "ERBB2" in b.upper() for b in trial.biomarkers)
        )

        for cond in trial.conditions:
            clean = cond.strip()
            if not clean or clean.lower() in seen:
                continue
            seen.add(clean.lower())

            # Determine cancer subtype
            subtype = None
            if re.search(r"\b(her2[- ]mutant|her2\s+mutated|exon\s+20)\b", clean, re.I):
                subtype = "HER2-Mutant"
            elif re.search(r"\b(her2[- ]positive|her2\+)\b", clean, re.I):
                subtype = "HER2-Positive"
            elif "lung" in clean.lower() or "nsclc" in clean.lower():
                subtype = "HER2-Mutated NSCLC" if has_her2 else "NSCLC"
            elif "breast" in clean.lower():
                subtype = "HER2+ Metastatic Breast Cancer" if has_her2 else "Breast Cancer"

            mappings.append(
                TrialIndicationMapping(
                    nct_id=trial.nct_id,
                    indication_id=uuid4(),
                    condition_name=clean,
                    cancer_subtype=subtype,
                    confidence=0.95,
                )
            )

        return mappings

    def resolve_trial_to_biomarker(self, trial: ClinicalTrialRecord) -> List[TrialBiomarkerMapping]:
        """Resolves inclusion/stratification biomarkers from criteria and biomarkers array."""
        mappings: List[TrialBiomarkerMapping] = []
        seen = set()

        # Combine biomarkers array and conditions
        all_biomarker_texts = list(trial.biomarkers)
        elig_vals = [str(v) for v in trial.eligibility.values() if v is not None] if isinstance(trial.eligibility, dict) else []
        full_text = " ".join([trial.study_title] + trial.conditions + elig_vals)

        # Find mutation signatures
        for match in re.finditer(r"\b(L755S|V777L|exon\s+20\s+insertion|Y772_A775dup|ERBB2\s+mutation|HER2[- ]mutant|ER[- ]positive)\b", full_text, re.I):
            all_biomarker_texts.append(match.group(0))

        for bio in all_biomarker_texts:
            norm = bio.strip().upper()
            if not norm or norm in seen:
                continue
            seen.add(norm)

            gene = "ERBB2" if "HER2" in norm or "L755" in norm or "V777" in norm or "EXON" in norm else "ESR1" if "ER" in norm else None
            mappings.append(
                TrialBiomarkerMapping(
                    nct_id=trial.nct_id,
                    biomarker_id=uuid4(),
                    biomarker_text=bio.strip(),
                    gene_symbol=gene,
                    inclusion_status="REQUIRED",
                )
            )

        return mappings

    def resolve_trial_to_company(self, trial: ClinicalTrialRecord) -> List[TrialCompanyMapping]:
        """Resolves sponsor and collaborators to canonical pharmaceutical/biotech companies."""
        mappings: List[TrialCompanyMapping] = []
        seen = set()

        if trial.sponsor:
            s_name = trial.sponsor.strip()
            seen.add(s_name.lower())
            mappings.append(
                TrialCompanyMapping(
                    nct_id=trial.nct_id,
                    company_id=uuid4(),
                    company_name=s_name,
                    role="LEAD_SPONSOR",
                )
            )

        for collab in trial.collaborators:
            c_name = collab.strip()
            if c_name and c_name.lower() not in seen:
                seen.add(c_name.lower())
                mappings.append(
                    TrialCompanyMapping(
                        nct_id=trial.nct_id,
                        company_id=uuid4(),
                        company_name=c_name,
                        role="COLLABORATOR",
                    )
                )

        return mappings

    def _bootstrap_resolvers(self) -> None:
        """Pre-registers oncology benchmark assets into the asset resolver."""
        from app.opportunity_engine.domain.canonical_model import Asset, AssetAlias, AssetDevelopmentCode
        benchmarks = [
            ("Zongertinib", UUID("33333333-3333-3333-3333-333333333333"), ["BI-1810631", "BI-0631", "BI 1810631"]),
            ("Tucatinib", UUID("44444444-4444-4444-4444-444444444444"), ["ONT-380", "Tukysa", "Irbinitinib"]),
            ("Neratinib", UUID("55555555-5555-5555-5555-555555555555"), ["PB272", "HKI-272", "Nerlynx"]),
            ("Poziotinib", UUID("66666666-6666-6666-6666-666666666666"), ["NOV120101", "HM781-36B"]),
        ]
        for name, aid, codes in benchmarks:
            if not self.asset_resolver.get_asset(aid):
                asset = Asset(
                    id=aid,
                    preferred_name=name,
                    canonical_slug=name.lower(),
                    development_codes=[AssetDevelopmentCode(asset_id=aid, code=c) for c in codes],
                    aliases=[AssetAlias(asset_id=aid, alias=c) for c in codes] + [AssetAlias(asset_id=aid, alias=name)],
                )
                self.asset_resolver.register_asset(asset)

from __future__ import annotations

from typing import Dict, List
from app.opportunity_engine.data.fixtures import get_fixture_asset
from app.opportunity_engine.domain.schemas import (
    AssetComparisonResult,
    AssetIntelligence,
)


class OpportunityComparisonEngine:
    """
    Head-to-head multi-asset comparative decision intelligence engine.
    Computes comparative deltas, strategic trade-offs, and competitive positioning.
    """

    @classmethod
    def compare_assets(
        cls,
        asset_ids: List[str],
        target: str = "HER2",
        indication: str = "Breast Cancer",
        setting: str = "Metastatic",
    ) -> AssetComparisonResult:
        assets: List[AssetIntelligence] = []
        for aid in asset_ids:
            found = get_fixture_asset(aid)
            if found:
                assets.append(found)

        if not assets:
            raise ValueError("No valid assets provided for comparison.")

        # Default head-to-head differentiators
        differentiators = [
            "Mutant-selectivity: Zongertinib selectively spares wild-type EGFR, substantially reducing dermatologic and GI toxicity.",
            "CNS Intracranial activity: Zongertinib demonstrates robust blood-brain barrier penetration (brain-to-plasma 0.3-0.5), whereas Neratinib has limited penetration.",
            "Therapeutic Index: Zongertinib provides a wide therapeutic window, while Neratinib is limited by high rates of Grade 3 diarrhea (up to 40% without intensive prophylaxis).",
            "Target Population: Zongertinib focuses on HER2-mutant non-amplified metastatic disease post-CDK4/6; Neratinib is established in HER2-amplified extended adjuvant settings.",
        ]

        advantages: Dict[str, List[str]] = {}
        for a in assets:
            if a.id == "zongertinib":
                advantages[a.id] = [
                    "High mutant selectivity sparing wild-type EGFR and HER4",
                    "Favorable GI tolerability profile with low diarrhea rates",
                    "Blood-brain barrier penetration with intracranial antitumor activity",
                    "Robust activity against resistant mutations (L755S, V777L, exon 20 insertions)",
                    "Strong patent exclusivity extending into the late 2030s",
                ]
            elif a.id == "neratinib":
                advantages[a.id] = [
                    "Full FDA and EMA marketing approval",
                    "Established Phase III efficacy benchmarks (ExteNET, NALA)",
                    "Broad pan-HER irreversible inhibitory mechanism",
                    "Approved combination regimens with capecitabine",
                ]
            elif a.id == "tucatinib":
                advantages[a.id] = [
                    "Proven overall survival advantage in active brain metastases (HER2CLIMB)",
                    "High HER2 selectivity with EGFR-sparing profile",
                    "Established commercial standard-of-care position",
                ]
            elif a.id == "poziotinib":
                advantages[a.id] = [
                    "Historical precedent for exon 20 binding",
                ]
            else:
                advantages[a.id] = [
                    f"Development potential score: {a.recommendation.development_potential_score}%",
                    f"Strategic action: {a.recommendation.action.value}",
                ]

        rec_summary: Dict[str, str] = {
            a.id: f"{a.recommendation.badge_text}: {a.recommendation.rationale}"
            for a in assets
        }

        comparison_summary = (
            f"Head-to-head comparison for {target} {indication} ({setting}). "
            f"Zongertinib represents a High-Priority PURSUE asset due to mutant-sparing selectivity and CNS activity, "
            f"whereas Neratinib serves as an established benchmark relegated to NICHE USE due to GI toxicity."
        )

        return AssetComparisonResult(
            target=target,
            indication=indication,
            setting=setting,
            assets=assets,
            comparison_summary=comparison_summary,
            key_differentiators=differentiators,
            head_to_head_advantages=advantages,
            recommendation_summary=rec_summary,
        )

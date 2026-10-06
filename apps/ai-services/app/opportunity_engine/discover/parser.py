from __future__ import annotations

import re
from typing import List, Optional

from .models import StructuredDiscoverFilters


class NaturalLanguageQueryParser:
    """
    Parses natural language opportunity discovery queries into structured
    14-dimensional search filters.
    """

    TARGET_PATTERNS = {
        r"\b(her2|erbb2|neu)\b": "HER2",
        r"\b(egfr|erbb1)\b": "EGFR",
        r"\b(kras)\b": "KRAS",
        r"\b(trop[- ]?2)\b": "TROP2",
        r"\b(esr1|er\b)\b": "ESR1",
        r"\b(met\b|c[- ]met)\b": "MET",
        r"\b(braf)\b": "BRAF",
        r"\b(pi3k|pik3ca)\b": "PIK3CA",
    }

    DISEASE_PATTERNS = {
        r"\b(breast\s*cancer|mbc|breast\s*neoplasm)\b": "Breast Cancer",
        r"\b(nsclc|non[- ]small\s*cell\s*lung\s*cancer|lung\s*cancer)\b": "Non-Small Cell Lung Cancer",
        r"\b(colorectal\s*cancer|crc|colon\s*cancer)\b": "Colorectal Cancer",
        r"\b(glioblastoma|gbm|brain\s*tumor)\b": "Glioblastoma",
        r"\b(oncology|solid\s*tumor[s]?|cancer)\b": "Oncology",
    }

    STAGE_PATTERNS = {
        r"\b(early[- ]stage|early\s*development)\b": ["PRECLINICAL", "PHASE_I", "PHASE_II"],
        r"\b(preclinical|discovery|ind[- ]enabling)\b": ["PRECLINICAL"],
        r"\b(phase\s*1b?|phase\s*i[b]?)\b": ["PHASE_I", "PHASE_IB"],
        r"\b(phase\s*2[ab]?|phase\s*ii[ab]?)\b": ["PHASE_II"],
        r"\b(phase\s*3|phase\s*iii|pivotal|late[- ]stage)\b": ["PHASE_III"],
        r"\b(approved|marketed)\b": ["APPROVED"],
    }

    MODALITY_PATTERNS = {
        r"\b(small\s*molecule|tki|kinase\s*inhibitor|inhibitor[s]?)\b": "SMALL_MOLECULE_TKI",
        r"\b(antibody|mab|monoclonal)\b": "ANTIBODY",
        r"\b(adc|antibody[- ]drug\s*conjugate)\b": "ANTIBODY_DRUG_CONJUGATE",
        r"\b(degrader|protac)\b": "TARGETED_DEGRADER",
    }

    MUTATION_PATTERNS = {
        r"\b(l755s)\b": "L755S",
        r"\b(v777l)\b": "V777L",
        r"\b(exon\s*20\s*(?:insertion)?|y772_a775dup)\b": "Exon 20 insertion",
        r"\b(c805s)\b": "C805S",
        r"\b(t790m)\b": "T790M",
    }

    @classmethod
    def parse(cls, query: str) -> StructuredDiscoverFilters:
        q_lower = query.strip().lower()
        filters = StructuredDiscoverFilters()

        # 1. Target
        for pattern, target in cls.TARGET_PATTERNS.items():
            if re.search(pattern, q_lower):
                filters.target = target
                break

        # 2. Disease
        for pattern, disease in cls.DISEASE_PATTERNS.items():
            if re.search(pattern, q_lower):
                filters.disease = disease
                break

        # 3. Indication
        if re.search(r"\b(her2[- ]mutant\s*(?:mbc|breast)?)\b", q_lower):
            filters.indication = "HER2-mutant metastatic breast cancer"
        elif re.search(r"\b(exon\s*20\s*nsclc)\b", q_lower):
            filters.indication = "HER2 Exon 20 insertion NSCLC"
        elif filters.disease:
            filters.indication = f"{filters.target or ''} {filters.disease}".strip()

        # 4. Stage
        for pattern, stages in cls.STAGE_PATTERNS.items():
            if re.search(pattern, q_lower):
                filters.stage = stages
                break

        # 5. Modality
        for pattern, modality in cls.MODALITY_PATTERNS.items():
            if re.search(pattern, q_lower):
                filters.modality = modality
                break

        # 6. Biomarker
        if re.search(r"\b(mutant|mutation[s]?)\b", q_lower):
            filters.biomarker = "Activating HER2 kinase mutation"
        elif re.search(r"\b(amplified|amplification|overexpression)\b", q_lower):
            filters.biomarker = "HER2 Amplification / IHC 3+"

        # 7. Mutation
        for pattern, mutation in cls.MUTATION_PATTERNS.items():
            if re.search(pattern, q_lower):
                filters.mutation = mutation
                break

        # 8. CNS Requirement
        if re.search(r"\b(cns|brain|brain\s*penetration|intracranial|blood[- ]brain)\b", q_lower):
            filters.cns_requirement = True

        # 9. Clinical Evidence
        if re.search(r"\b(clinical\s*evidence|clinical\s*data|in\s*patients|trial\s*evidence|phase\s*[123])\b", q_lower):
            filters.clinical_evidence = True

        # 10. Safety / Therapeutic Index
        if re.search(r"\b(selective|sparing|wt[- ]sparing|therapeutic\s*index|tolerable|low\s*toxicity|diarrhea)\b", q_lower):
            filters.safety = "High selectivity / wild-type sparing"

        # 11. Competition
        if re.search(r"\b(limited\s*competition|low\s*competition|uncongested|differentiated|first[- ]in[- ]class)\b", q_lower):
            filters.competition = "Limited competition / Differentiated niche"

        # 12. Ownership
        if re.search(r"\b(academic|university|academic\s*origin|spinout|institution)\b", q_lower):
            filters.ownership = "Academic / Translational origin"

        # 13. Licensing
        if re.search(r"\b(licensing|available\s*for\s*licensing|partnering|unpartnered|out[- ]license)\b", q_lower):
            filters.licensing = "POTENTIALLY_AVAILABLE"

        # 14. Commercial Opportunity
        if re.search(r"\b(translational\s*potential|commercial\s*potential|market\s*potential|opportunity)\b", q_lower):
            filters.commercial_opportunity = "High commercial / translational potential"

        return filters

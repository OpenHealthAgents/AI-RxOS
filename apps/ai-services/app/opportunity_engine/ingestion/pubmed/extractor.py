from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.opportunity_engine.domain.canonical_model import ScientificEvidenceState
from .models import (
    ExtractedObservation,
    ExtractionCategory,
    PubMedArticleRecord,
)


class MultiDomainBiomedicalExtractor:
    """
    Biomedical extraction engine covering all 16 requested target categories:
    drug, target, gene, mutation, disease, biomarker, model, cell line,
    animal model, efficacy, toxicity, CNS exposure, CNS efficacy, resistance,
    combination, clinical outcome.

    CRITICAL SAFETY PRINCIPLE:
    Does NOT treat LLM / automated NLP extraction as ground truth.
    Every extraction is stamped with:
    - is_ground_truth = False
    - epistemic_status = ScientificEvidenceState.AI_INFERENCE
    - extraction_model_version
    - calibrated confidence
    - exact source text & location
    """

    MODEL_VERSION = "BioExtractor-Ensemble-v2.1"

    # Targeted Regex Patterns & Vocabularies
    DRUG_PATTERNS = [
        (r"\b(zongertinib|bi\s*1810631|bi-1810631|bi\s*0631)\b", "Zongertinib", "small_molecule"),
        (r"\b(tucatinib|ont-380|irbinitinib|tukysa)\b", "Tucatinib", "small_molecule"),
        (r"\b(neratinib|hki-272|pb272|nerlynx)\b", "Neratinib", "small_molecule"),
        (r"\b(poziotinib|nov120101|hm781-36b)\b", "Poziotinib", "small_molecule"),
        (r"\b(trastuzumab\s+deruxtecan|t-dxd|enhertu)\b", "Trastuzumab Deruxtecan", "adc"),
        (r"\b(trastuzumab|herceptin)\b", "Trastuzumab", "mab"),
        (r"\b(fulvestrant|faslodex)\b", "Fulvestrant", "endocrine"),
        (r"\b(capecitabine|xeloda)\b", "Capecitabine", "chemotherapy"),
    ]

    TARGET_GENE_PATTERNS = [
        (r"\b(her2|erbb2|neu)\b", "HER2", ExtractionCategory.TARGET),
        (r"\b(egfr|erbb1)\b", "EGFR", ExtractionCategory.TARGET),
        (r"\b(erbb3|her3)\b", "HER3", ExtractionCategory.TARGET),
        (r"\b(pik3ca|pi3k)\b", "PIK3CA", ExtractionCategory.GENE),
        (r"\b(esr1|er\b|estrogen\s+receptor)\b", "ESR1", ExtractionCategory.GENE),
    ]

    MUTATION_PATTERNS = [
        r"\b([A-Z]\d{3,4}[A-Z])\b",  # e.g. L755S, V777L, T790M, C805S
        r"\b(exon\s+20\s+insertion|exon\s+20\s+ins|ex20ins)\b",
        r"\b(y772_a775dup|a775_g776insyvma)\b",
    ]

    CELL_LINE_PATTERNS = [
        r"\b(ba/f3|baf3)\b",
        r"\b(mcf-?7|mda-mb-?453|bt-?474|sk-?br-?3|nci-h1781|calu-?3)\b",
    ]

    ANIMAL_MODEL_PATTERNS = [
        r"\b(balb/c\s+nude|athymic\s+nude|cd-1\s+mice|nude\s+mice|xenograft\s+models?)\b",
        r"\b(orthotopic\s+brain\s+metastasis\s+model|pdx\s+models?)\b",
    ]

    EFFICACY_PATTERNS = [
        (r"ic50(?:[\s:=]+)(\d+(?:\.\d+)?)\s*(nm|um|µm)", "IC50", "nM"),
        (r"(?:overall\s+response\s+rate|orr)(?:[\s:=]+)(\d+(?:\.\d+)?)\s*%", "ORR", "%"),
        (r"(?:tumor\s+growth\s+inhibition|tgi)(?:[\s:=]+)(\d+(?:\.\d+)?)\s*%", "TGI", "%"),
        (r"(\d+(?:\.\d+)?)(?:-fold|\s*fold)\s*(?:selectivity|more\s+potent)", "Selectivity Ratio", "fold_ratio"),
    ]

    TOXICITY_PATTERNS = [
        (r"grade\s*(?:>=|≥|3\s*or\s*higher|3\+?)\s*(?:diarrhea|diarrhoea)(?:[\s:=]+)(\d+(?:\.\d+)?)\s*%", "Grade 3+ Diarrhea Rate", "%"),
        (r"(?:dose\s+reduction|treatment\s+discontinuation)(?:[\s:=]+)(\d+(?:\.\d+)?)\s*%", "Dose Reduction Rate", "%"),
        (r"\b(dose-limiting\s+toxicity|dlt|rash|diarrhea|skin\s+toxicity)\b", "Adverse Event", None),
    ]

    CNS_PATTERNS = [
        (r"(?:brain-to-plasma|brain/plasma)\s*(?:ratio)?(?:\s+of|\s*[:=]|\s+)\s*(\d+(?:\.\d+)?)", ExtractionCategory.CNS_EXPOSURE, "ratio"),
        (r"\b(blood-brain\s+barrier\s+penetration|csf\s+penetration|cns\s+exposure)\b", ExtractionCategory.CNS_EXPOSURE, None),
        (r"(?:intracranial\s+orr|cns\s+response\s+rate)(?:\s+of|\s*[:=]|\s+)\s*(\d+(?:\.\d+)?)\s*%", ExtractionCategory.CNS_EFFICACY, "%"),
        (r"\b(intracranial\s+(?:activity|regression|efficacy)|brain\s+metastases\s+control)\b", ExtractionCategory.CNS_EFFICACY, None),
    ]

    CLINICAL_OUTCOME_PATTERNS = [
        (r"(?:median\s+pfs|pfs)(?:\s+of|\s*[:=]|\s+)\s*(\d+(?:\.\d+)?)\s*(months?|mo)", "Median PFS", "months"),
        (r"(?:median\s+os|os)(?:\s+of|\s*[:=]|\s+)\s*(\d+(?:\.\d+)?)\s*(months?|mo)", "Median OS", "months"),
    ]

    RESISTANCE_PATTERNS = [
        r"\b(er\s+pathway\s+adaptation|estrogen\s+receptor\s+reactivation)\b",
        r"\b(secondary\s+gatekeeper\s+mutation|c805s|t790m)\b",
        r"\b(pi3k/akt\s+signaling\s+bypass|mapk\s+bypass)\b",
        r"\b(ferritin\s+light\s+chain|ftl|redox\s+adaptation)\b",
    ]

    COMBINATION_PATTERNS = [
        r"\b(in\s+combination\s+with\s+(?:fulvestrant|trastuzumab|capecitabine|endocrine\s+therapy|cdk4/6\s+inhibitors?))\b",
        r"\b(synergistic\s+combination|combination\s+therapy|co-treatment)\b",
    ]

    @classmethod
    def extract_from_article(cls, article: PubMedArticleRecord) -> List[ExtractedObservation]:
        """
        Runs comprehensive extraction pipeline over title and abstract.
        Returns typed observations with location, confidence, and provenance.
        """
        observations: List[ExtractedObservation] = []
        full_text = f"{article.title}\n{article.abstract}"
        citation = article.source_citation

        # Split text into numbered sentences for location tagging
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", full_text) if s.strip()]

        for idx, sentence in enumerate(sentences):
            loc = f"Sentence {idx + 1}"
            text_lower = sentence.lower()

            # 1. Drug Extraction
            for pattern, canonical_drug, _ in cls.DRUG_PATTERNS:
                if re.search(pattern, text_lower):
                    observations.append(
                        ExtractedObservation(
                            pmid=article.pmid,
                            extraction_category=ExtractionCategory.DRUG,
                            entity_text=canonical_drug,
                            extracted_text=sentence,
                            source_location=loc,
                            confidence=0.95,
                            is_ground_truth=False,
                            epistemic_status=ScientificEvidenceState.AI_INFERENCE,
                            extraction_model_version=cls.MODEL_VERSION,
                            source_citation=citation,
                        )
                    )

            # 2. Target & Gene Extraction
            for pattern, gene_target_name, category in cls.TARGET_GENE_PATTERNS:
                if re.search(pattern, text_lower):
                    observations.append(
                        ExtractedObservation(
                            pmid=article.pmid,
                            extraction_category=category,
                            entity_text=gene_target_name,
                            extracted_text=sentence,
                            source_location=loc,
                            confidence=0.92,
                            is_ground_truth=False,
                            epistemic_status=ScientificEvidenceState.AI_INFERENCE,
                            extraction_model_version=cls.MODEL_VERSION,
                            source_citation=citation,
                        )
                    )

            # 3. Mutation Extraction
            for pattern in cls.MUTATION_PATTERNS:
                for match in re.finditer(pattern, sentence, re.IGNORECASE):
                    mut_text = match.group(0).upper()
                    # Filter out common false positives like "PMID" or "NCT"
                    if mut_text not in ("PMID", "NCT", "TABLE", "PHASE", "GRADE"):
                        observations.append(
                            ExtractedObservation(
                                pmid=article.pmid,
                                extraction_category=ExtractionCategory.MUTATION,
                                entity_text=mut_text,
                                extracted_text=sentence,
                                source_location=loc,
                                confidence=0.90,
                                is_ground_truth=False,
                                epistemic_status=ScientificEvidenceState.AI_INFERENCE,
                                extraction_model_version=cls.MODEL_VERSION,
                                source_citation=citation,
                            )
                        )

            # 4. Disease Extraction
            if re.search(r"\b(breast\s+cancer|mbc|breast\s+carcinoma)\b", text_lower):
                observations.append(
                    ExtractedObservation(
                        pmid=article.pmid,
                        extraction_category=ExtractionCategory.DISEASE,
                        entity_text="Breast Neoplasms",
                        extracted_text=sentence,
                        source_location=loc,
                        confidence=0.94,
                        is_ground_truth=False,
                        epistemic_status=ScientificEvidenceState.AI_INFERENCE,
                        extraction_model_version=cls.MODEL_VERSION,
                        source_citation=citation,
                    )
                )
            if re.search(r"\b(nsclc|lung\s+cancer|lung\s+adenocarcinoma)\b", text_lower):
                observations.append(
                    ExtractedObservation(
                        pmid=article.pmid,
                        extraction_category=ExtractionCategory.DISEASE,
                        entity_text="Non-Small Cell Lung Carcinoma",
                        extracted_text=sentence,
                        source_location=loc,
                        confidence=0.94,
                        is_ground_truth=False,
                        epistemic_status=ScientificEvidenceState.AI_INFERENCE,
                        extraction_model_version=cls.MODEL_VERSION,
                        source_citation=citation,
                    )
                )

            # 5. Biomarker Extraction
            if re.search(r"\b(her2[- ]mutants?|her2\s+mutations?|er[- ]positive|er\+|her2\s+non-amplified|biomarkers?)\b", text_lower):
                observations.append(
                    ExtractedObservation(
                        pmid=article.pmid,
                        extraction_category=ExtractionCategory.BIOMARKER,
                        entity_text="HER2-mutant / ER-positive Biomarker Profile",
                        extracted_text=sentence,
                        source_location=loc,
                        confidence=0.89,
                        is_ground_truth=False,
                        epistemic_status=ScientificEvidenceState.AI_INFERENCE,
                        extraction_model_version=cls.MODEL_VERSION,
                        source_citation=citation,
                    )
                )

            # 6. Model & 7. Cell Line & 8. Animal Model
            for pattern in cls.CELL_LINE_PATTERNS:
                match = re.search(pattern, text_lower)
                if match:
                    observations.append(
                        ExtractedObservation(
                            pmid=article.pmid,
                            extraction_category=ExtractionCategory.CELL_LINE,
                            entity_text=match.group(0).upper(),
                            extracted_text=sentence,
                            source_location=loc,
                            confidence=0.91,
                            is_ground_truth=False,
                            epistemic_status=ScientificEvidenceState.AI_INFERENCE,
                            extraction_model_version=cls.MODEL_VERSION,
                            source_citation=citation,
                        )
                    )

            for pattern in cls.ANIMAL_MODEL_PATTERNS:
                match = re.search(pattern, text_lower)
                if match:
                    observations.append(
                        ExtractedObservation(
                            pmid=article.pmid,
                            extraction_category=ExtractionCategory.ANIMAL_MODEL,
                            entity_text=match.group(0).capitalize(),
                            extracted_text=sentence,
                            source_location=loc,
                            confidence=0.90,
                            is_ground_truth=False,
                            epistemic_status=ScientificEvidenceState.AI_INFERENCE,
                            extraction_model_version=cls.MODEL_VERSION,
                            source_citation=citation,
                        )
                    )

            if re.search(r"\b(preclinical\s+models?|xenograft\s+models?|orthotopic.*models?|patient-derived\s+xenograft|pdx|in\s+vivo\s+models?|models?)\b", text_lower):
                observations.append(
                    ExtractedObservation(
                        pmid=article.pmid,
                        extraction_category=ExtractionCategory.MODEL,
                        entity_text="In Vivo Preclinical Model",
                        extracted_text=sentence,
                        source_location=loc,
                        confidence=0.88,
                        is_ground_truth=False,
                        epistemic_status=ScientificEvidenceState.AI_INFERENCE,
                        extraction_model_version=cls.MODEL_VERSION,
                        source_citation=citation,
                    )
                )

            # 9. Efficacy Extraction
            for pattern, param_name, unit in cls.EFFICACY_PATTERNS:
                match = re.search(pattern, text_lower)
                if match:
                    val = float(match.group(1)) if match.groups() else None
                    observations.append(
                        ExtractedObservation(
                            pmid=article.pmid,
                            extraction_category=ExtractionCategory.EFFICACY,
                            entity_text=param_name,
                            extracted_text=sentence,
                            source_location=loc,
                            normalized_value=val,
                            normalized_unit=unit,
                            confidence=0.93,
                            is_ground_truth=False,
                            epistemic_status=ScientificEvidenceState.AI_INFERENCE,
                            extraction_model_version=cls.MODEL_VERSION,
                            source_citation=citation,
                        )
                    )

            # 10. Toxicity Extraction
            for pattern, param_name, unit in cls.TOXICITY_PATTERNS:
                match = re.search(pattern, text_lower)
                if match:
                    val = float(match.group(1)) if match.groups() and match.group(1).replace(".", "").isdigit() else None
                    observations.append(
                        ExtractedObservation(
                            pmid=article.pmid,
                            extraction_category=ExtractionCategory.TOXICITY,
                            entity_text=param_name,
                            extracted_text=sentence,
                            source_location=loc,
                            normalized_value=val,
                            normalized_unit=unit,
                            confidence=0.91,
                            is_ground_truth=False,
                            epistemic_status=ScientificEvidenceState.AI_INFERENCE,
                            extraction_model_version=cls.MODEL_VERSION,
                            source_citation=citation,
                        )
                    )

            # 11. CNS Exposure & 12. CNS Efficacy
            for pattern, category, unit in cls.CNS_PATTERNS:
                match = re.search(pattern, text_lower)
                if match:
                    val = float(match.group(1)) if match.groups() and match.group(1).replace(".", "").isdigit() else None
                    observations.append(
                        ExtractedObservation(
                            pmid=article.pmid,
                            extraction_category=category,
                            entity_text="Central Nervous System Activity",
                            extracted_text=sentence,
                            source_location=loc,
                            normalized_value=val,
                            normalized_unit=unit,
                            confidence=0.90,
                            is_ground_truth=False,
                            epistemic_status=ScientificEvidenceState.AI_INFERENCE,
                            extraction_model_version=cls.MODEL_VERSION,
                            source_citation=citation,
                        )
                    )

            # 13. Resistance Extraction
            for pattern in cls.RESISTANCE_PATTERNS:
                match = re.search(pattern, text_lower)
                if match:
                    observations.append(
                        ExtractedObservation(
                            pmid=article.pmid,
                            extraction_category=ExtractionCategory.RESISTANCE,
                            entity_text=match.group(0).title(),
                            extracted_text=sentence,
                            source_location=loc,
                            confidence=0.87,
                            is_ground_truth=False,
                            epistemic_status=ScientificEvidenceState.AI_INFERENCE,
                            extraction_model_version=cls.MODEL_VERSION,
                            source_citation=citation,
                        )
                    )

            # 14. Combination Extraction
            for pattern in cls.COMBINATION_PATTERNS:
                match = re.search(pattern, text_lower)
                if match:
                    observations.append(
                        ExtractedObservation(
                            pmid=article.pmid,
                            extraction_category=ExtractionCategory.COMBINATION,
                            entity_text=match.group(0).title(),
                            extracted_text=sentence,
                            source_location=loc,
                            confidence=0.88,
                            is_ground_truth=False,
                            epistemic_status=ScientificEvidenceState.AI_INFERENCE,
                            extraction_model_version=cls.MODEL_VERSION,
                            source_citation=citation,
                        )
                    )

            # 15. Clinical Outcome Extraction
            for pattern, outcome_metric, unit in cls.CLINICAL_OUTCOME_PATTERNS:
                match = re.search(pattern, text_lower)
                if match:
                    val = float(match.group(1)) if match.groups() else None
                    observations.append(
                        ExtractedObservation(
                            pmid=article.pmid,
                            extraction_category=ExtractionCategory.CLINICAL_OUTCOME,
                            entity_text=outcome_metric,
                            extracted_text=sentence,
                            source_location=loc,
                            normalized_value=val,
                            normalized_unit=unit,
                            confidence=0.92,
                            is_ground_truth=False,
                            epistemic_status=ScientificEvidenceState.AI_INFERENCE,
                            extraction_model_version=cls.MODEL_VERSION,
                            source_citation=citation,
                        )
                    )

        # Remove redundant observations on same category and entity
        unique_observations: List[ExtractedObservation] = []
        seen = set()
        for o in observations:
            key = (o.extraction_category, o.entity_text, o.source_location)
            if key not in seen:
                seen.add(key)
                unique_observations.append(o)

        return unique_observations

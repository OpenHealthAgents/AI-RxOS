"""
Natural Language Query Parser and Constraint Compiler.

Converts free-form natural language queries into structured constraints:
- Targets (e.g. HER2, EGFR, KRAS, ESR1)
- Diseases / Indications (e.g. NSCLC, Breast Cancer, CRC)
- Developmental Stages (e.g. Phase 2, Preclinical, Approved)
- Modalities (e.g. TKI, small molecule, ADC, antibody)
- Biomarkers & Mutations (e.g. L755S, Exon 20 insertion, HER2+)
- Clinical Evidence & CNS Activity (e.g. CNS-active, brain metastases)
- Ownership & Licensing (e.g. available for out-licensing, Boehringer, Pfizer)
- Trial phases, Publication journals, and strategic actions.

STRICT INVARIANT:
"Never use LLM output as the final database query without validation."
All constraints pass through whitelist schema enforcement and validation.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    ALLOWED_CONSTRAINT_FIELDS,
    OperatorType,
    ParsedSearchQuery,
    SearchMode,
    SearchTargetType,
    StructuredConstraint,
)


class NaturalLanguageSearchParser:
    """
    Robust rule- and entity-driven natural language query parser.
    Converts unstructured physician/BD queries into validated structured search constraints.
    """

    TARGET_REGEXES = {
        r"\b(her2|erbb2|neu)\b": "HER2",
        r"\b(egfr|erbb1)\b": "EGFR",
        r"\b(kras|k-ras)\b": "KRAS",
        r"\b(trop[- ]?2)\b": "TROP2",
        r"\b(esr1|er\b)\b": "ESR1",
        r"\b(met|c[- ]met)\b": "MET",
        r"\b(braf)\b": "BRAF",
        r"\b(pi3k|pik3ca)\b": "PIK3CA",
        r"\b(cdk4|cdk6|cdk4/6)\b": "CDK4/6",
        r"\b(alk)\b": "ALK",
    }

    DISEASE_REGEXES = {
        r"\b(nsclc|non[- ]small\s*cell\s*lung\s*cancer|lung\s*cancer)\b": "Non-Small Cell Lung Cancer",
        r"\b(breast\s*cancer|mbc|breast\s*carcinoma)\b": "Breast Cancer",
        r"\b(colorectal\s*cancer|crc|colon\s*cancer)\b": "Colorectal Cancer",
        r"\b(glioblastoma|gbm|brain\s*cancer)\b": "Glioblastoma",
        r"\b(gastric\s*cancer|stomach\s*cancer)\b": "Gastric Cancer",
        r"\b(ovarian\s*cancer)\b": "Ovarian Cancer",
    }

    STAGE_REGEXES = {
        r"\b(preclinical|discovery|ind[- ]enabling)\b": ("Preclinical", OperatorType.EQUALS),
        r"\b(phase\s*1b?|phase\s*i[b]?)\b": ("Phase I", OperatorType.EQUALS),
        r"\b(phase\s*2[ab]?|phase\s*ii[ab]?)\b": ("Phase II", OperatorType.EQUALS),
        r"\b(phase\s*3|phase\s*iii|pivotal)\b": ("Phase III", OperatorType.EQUALS),
        r"\b(approved|commercial|marketed)\b": ("Approved", OperatorType.EQUALS),
    }

    MODALITY_REGEXES = {
        r"\b(small\s*molecule[s]?|tki[s]?|kinase\s*inhibitor[s]?|inhibitor[s]?)\b": "SMALL_MOLECULE_TKI",
        r"\b(antibody|monoclonal|mab[s]?|antibodies)\b": "ANTIBODY",
        r"\b(adc[s]?|antibody[- ]drug\s*conjugate[s]?)\b": "ADC",
        r"\b(protac[s]?|degrader[s]?|targeted\s*degrader[s]?)\b": "TARGETED_DEGRADER",
        r"\b(cell\s*therapy|car[- ]t)\b": "CELL_THERAPY",
    }


    MUTATION_REGEXES = {
        r"\b(l755s)\b": "L755S",
        r"\b(v777l)\b": "V777L",
        r"\b(exon\s*20\s*(?:insertion)?|y772_a775dup)\b": "Exon 20 insertion",
        r"\b(c805s)\b": "C805S",
        r"\b(t790m)\b": "T790M",
        r"\b(g12c)\b": "G12C",
        r"\b(g12d)\b": "G12D",
    }

    COMPANY_REGEXES = {
        r"\b(boehringer(?:\s*ingelheim)?)\b": "Boehringer Ingelheim",
        r"\b(pfizer)\b": "Pfizer",
        r"\b(hanmi(?:\s*pharmaceutical)?)\b": "Hanmi Pharmaceutical",
        r"\b(spectrum(?:\s*pharmaceuticals)?)\b": "Spectrum Pharmaceuticals",
        r"\b(seagen|seattle\s*genetics)\b": "Seagen",
        r"\b(novartis)\b": "Novartis",
        r"\b(roche|genentech)\b": "Roche",
        r"\b(astrazeneca)\b": "AstraZeneca",
    }

    LICENSING_REGEXES = {
        r"\b(available|out[- ]licensing|licenseable|unpartnered|licensing\s*opportunity)\b": "POTENTIALLY_AVAILABLE",
        r"\b(partnered|in[- ]licensed|commercialized)\b": "PARTNERED",
    }

    @classmethod
    def infer_target_type(cls, query: str, default: SearchTargetType = SearchTargetType.ASSET) -> SearchTargetType:
        """Determines the primary target entity being searched if not explicitly stated."""
        q = query.lower()
        if re.search(r"\b(trial[s]?|study|studies|nct\d+)\b", q):
            return SearchTargetType.TRIAL
        if re.search(r"\b(paper[s]?|publication[s]?|pubmed|pmid|article[s]?|literature)\b", q):
            return SearchTargetType.PUBLICATION
        if re.search(r"\b(company|companies|sponsor[s]?|biotech|pharma)\b", q):
            return SearchTargetType.COMPANY
        if re.search(r"\b(biomarker[s]?|ctdna|ihc|fish)\b", q) and not re.search(r"\b(asset|drug|compound|molecule)\b", q):
            return SearchTargetType.BIOMARKER
        if re.search(r"\b(target[s]?|kinase[s]?|receptor[s]?)\b", q) and not re.search(r"\b(drug|asset|treatment|inhibitor)\b", q):
            return SearchTargetType.TARGET
        if re.search(r"\b(opportunity|opportunities|deal[s]?|partnering)\b", q):
            return SearchTargetType.OPPORTUNITY
        if re.search(r"\b(indication[s]?|disease[s]?)\b", q) and not re.search(r"\b(asset|drug|inhibitor)\b", q):
            return SearchTargetType.INDICATION
        return default

    @classmethod
    def parse(
        cls,
        query: str,
        target_type: Optional[SearchTargetType] = None,
        mode: SearchMode = SearchMode.HYBRID,
    ) -> ParsedSearchQuery:
        """
        Parses raw natural language text into a validated ParsedSearchQuery.
        """
        resolved_target = target_type or cls.infer_target_type(query)
        q_clean = query.strip()
        q_lower = q_clean.lower()

        constraints: List[StructuredConstraint] = []
        extracted_entities: Dict[str, List[str]] = {}
        validation_errors: List[str] = []

        # 1. Target Extraction
        for pat, tgt_name in cls.TARGET_REGEXES.items():
            m = re.search(pat, q_lower)
            if m:
                extracted_entities.setdefault("targets", []).append(tgt_name)
                try:
                    constraints.append(
                        StructuredConstraint(
                            field="target",
                            operator=OperatorType.EQUALS,
                            value=tgt_name,
                            confidence=0.98,
                            source_span=m.group(0),
                        )
                    )
                except Exception as e:
                    validation_errors.append(f"Target constraint error: {str(e)}")
                break

        # 2. Disease / Indication Extraction
        for pat, dis_name in cls.DISEASE_REGEXES.items():
            m = re.search(pat, q_lower)
            if m:
                extracted_entities.setdefault("diseases", []).append(dis_name)
                try:
                    constraints.append(
                        StructuredConstraint(
                            field="disease",
                            operator=OperatorType.CONTAINS,
                            value=dis_name,
                            confidence=0.95,
                            source_span=m.group(0),
                        )
                    )
                except Exception as e:
                    validation_errors.append(f"Disease constraint error: {str(e)}")
                break

        # 3. Stage Extraction
        for pat, (stage_val, op) in cls.STAGE_REGEXES.items():
            m = re.search(pat, q_lower)
            if m:
                extracted_entities.setdefault("stages", []).append(stage_val)
                try:
                    constraints.append(
                        StructuredConstraint(
                            field="stage",
                            operator=op,
                            value=stage_val,
                            confidence=0.95,
                            source_span=m.group(0),
                        )
                    )
                except Exception as e:
                    validation_errors.append(f"Stage constraint error: {str(e)}")
                break

        # 4. Modality Extraction
        for pat, mod_val in cls.MODALITY_REGEXES.items():
            m = re.search(pat, q_lower)
            if m:
                extracted_entities.setdefault("modalities", []).append(mod_val)
                try:
                    constraints.append(
                        StructuredConstraint(
                            field="modality",
                            operator=OperatorType.EQUALS,
                            value=mod_val,
                            confidence=0.95,
                            source_span=m.group(0),
                        )
                    )
                except Exception as e:
                    validation_errors.append(f"Modality constraint error: {str(e)}")
                break

        # 5. Mutation Extraction
        for pat, mut_val in cls.MUTATION_REGEXES.items():
            m = re.search(pat, q_lower)
            if m:
                extracted_entities.setdefault("mutations", []).append(mut_val)
                try:
                    constraints.append(
                        StructuredConstraint(
                            field="mutation",
                            operator=OperatorType.CONTAINS,
                            value=mut_val,
                            confidence=0.95,
                            source_span=m.group(0),
                        )
                    )
                except Exception as e:
                    validation_errors.append(f"Mutation constraint error: {str(e)}")
                break

        # 6. CNS Activity / Brain Penetration
        if re.search(r"\b(cns[- ]active|brain\s*penetr(?:ant|ating|ation)|brain\s*met(?:astases)?)\b", q_lower):
            extracted_entities.setdefault("cns", []).append("cns_active")
            try:
                constraints.append(
                    StructuredConstraint(
                        field="cns_active",
                        operator=OperatorType.BOOLEAN_IS,
                        value=True,
                        confidence=0.99,
                        source_span="cns_active",
                    )
                )
            except Exception as e:
                validation_errors.append(f"CNS constraint error: {str(e)}")

        # 7. Clinical Evidence Requirement
        if re.search(r"\b(clinical\s*evidence|clinical\s*data|human\s*trials?|in\s*clinic)\b", q_lower):
            try:
                constraints.append(
                    StructuredConstraint(
                        field="clinical_evidence",
                        operator=OperatorType.BOOLEAN_IS,
                        value=True,
                        confidence=0.90,
                        source_span="clinical_evidence",
                    )
                )
            except Exception as e:
                validation_errors.append(f"Clinical evidence error: {str(e)}")

        # 8. Company Extraction
        for pat, comp_name in cls.COMPANY_REGEXES.items():
            m = re.search(pat, q_lower)
            if m:
                extracted_entities.setdefault("companies", []).append(comp_name)
                try:
                    constraints.append(
                        StructuredConstraint(
                            field="company",
                            operator=OperatorType.CONTAINS,
                            value=comp_name,
                            confidence=0.95,
                            source_span=m.group(0),
                        )
                    )
                except Exception as e:
                    validation_errors.append(f"Company constraint error: {str(e)}")
                break

        # 9. Licensing Status Extraction
        for pat, lic_val in cls.LICENSING_REGEXES.items():
            m = re.search(pat, q_lower)
            if m:
                extracted_entities.setdefault("licensing", []).append(lic_val)
                try:
                    constraints.append(
                        StructuredConstraint(
                            field="licensing_status",
                            operator=OperatorType.EQUALS,
                            value=lic_val,
                            confidence=0.90,
                            source_span=m.group(0),
                        )
                    )
                except Exception as e:
                    validation_errors.append(f"Licensing constraint error: {str(e)}")
                break

        # Semantic intent remainder
        semantic_intent = q_clean

        return ParsedSearchQuery(
            raw_query=q_clean,
            target_type=resolved_target,
            search_mode=mode,
            semantic_intent=semantic_intent,
            structured_constraints=constraints,
            extracted_entities=extracted_entities,
            is_validated=len(validation_errors) == 0,
            validation_errors=validation_errors,
        )

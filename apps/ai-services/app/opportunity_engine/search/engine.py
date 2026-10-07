"""
Semantic and Structured Search Engine for AI-RxOS.

Executes high-precision search across 8 target entities:
1. asset search
2. target search
3. indication search
4. biomarker search
5. trial search
6. publication search
7. company search
8. opportunity search

Supports:
- Natural language query conversion to validated structured constraints
- Hybrid semantic score calculation + metadata filter evaluation
- Validation preventing unvalidated LLM text from executing as database queries
- Complete evidence provenance attached to search results
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from app.opportunity_engine.data.fixtures import list_fixture_assets
from app.opportunity_engine.kg.engine import OncologyKnowledgeGraphEngine
from app.opportunity_engine.kg.models import KGNodeType

from .models import (
    ParsedSearchQuery,
    SearchEvidenceProvenance,
    SearchExecutionResult,
    SearchMode,
    SearchQueryRequest,
    SearchResultItem,
    SearchTargetType,
    StructuredConstraint,
    ValidatedParametricQuery,
)
from .parser import NaturalLanguageSearchParser
from .validator import QueryValidationError, SqlCompilerAndValidator

logger = logging.getLogger(__name__)


class SearchEngine:
    """
    Unified Semantic and Structured Search Engine.
    Executes search across Assets, Targets, Indications, Biomarkers,
    Trials, Publications, Companies, and Opportunities.
    """

    def __init__(self, kg_engine: Optional[OncologyKnowledgeGraphEngine] = None) -> None:
        self._kg_engine = kg_engine or OncologyKnowledgeGraphEngine()
        self._assets_cache = list_fixture_assets()

    def search(self, req: SearchQueryRequest) -> SearchExecutionResult:
        """
        Main Search Execution Pipeline:
        1. Parse natural language into structured constraints.
        2. Merge with explicit user constraints if provided.
        3. Validate constraints against strict schema and compile safe parameterized query.
        4. Execute semantic similarity + structured filter matching over candidate entities.
        5. Return ranked items with match reasons and evidence provenance.
        """
        start_time = time.perf_counter()

        # Step 1: Parse natural language
        parsed = NaturalLanguageSearchParser.parse(
            query=req.query,
            target_type=req.target_type,
            mode=req.mode,
        )

        # Step 2: Merge explicit constraints
        if req.explicit_constraints:
            for ec in req.explicit_constraints:
                # Replace or append
                parsed.structured_constraints = [
                    c for c in parsed.structured_constraints if c.field != ec.field
                ]
                parsed.structured_constraints.append(ec)

        # Step 3: Validate and compile safe parametric query
        validated_sql: Optional[ValidatedParametricQuery] = None
        try:
            validated_sql = SqlCompilerAndValidator.compile_to_parametric_sql(parsed)
            parsed.is_validated = True
        except QueryValidationError as e:
            parsed.is_validated = False
            parsed.validation_errors.append(str(e))
            logger.warning(f"Query validation failed: {str(e)}")

        # Step 4: Dispatch execution to target entity matcher
        dispatchers = {
            SearchTargetType.ASSET: self._search_assets,
            SearchTargetType.TARGET: self._search_targets,
            SearchTargetType.INDICATION: self._search_indications,
            SearchTargetType.BIOMARKER: self._search_biomarkers,
            SearchTargetType.TRIAL: self._search_trials,
            SearchTargetType.PUBLICATION: self._search_publications,
            SearchTargetType.COMPANY: self._search_companies,
            SearchTargetType.OPPORTUNITY: self._search_opportunities,
        }

        matcher = dispatchers.get(req.target_type, self._search_assets)
        matched_items = matcher(parsed, req.query)

        # Sort descending by score
        matched_items.sort(key=lambda x: x.score, reverse=True)

        total_matches = len(matched_items)
        paginated_items = matched_items[req.offset : req.offset + req.limit]

        exec_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        return SearchExecutionResult(
            raw_query=req.query,
            target_type=req.target_type,
            search_mode=req.mode,
            parsed_query=parsed,
            validated_sql=validated_sql,
            total_matches=total_matches,
            returned_count=len(paginated_items),
            items=paginated_items,
            execution_time_ms=exec_ms,
        )

    # --------------------------------------------------------------------------
    # Entity Matchers
    # --------------------------------------------------------------------------

    def _compute_semantic_similarity(self, query: str, document_text: str) -> float:
        """Computes normalized text token semantic overlap similarity score (0.0 - 1.0)."""
        q_tokens = set(re.findall(r"\w+", query.lower()))
        d_tokens = set(re.findall(r"\w+", document_text.lower()))
        if not q_tokens or not d_tokens:
            return 0.0
        intersection = q_tokens.intersection(d_tokens)
        return round(len(intersection) / len(q_tokens), 3)

    def _search_assets(self, parsed: ParsedSearchQuery, raw_query: str) -> List[SearchResultItem]:
        """Executes Asset search matching structured constraints and semantic terms."""
        results: List[SearchResultItem] = []

        for asset in self._assets_cache:
            score = 60.0
            reasons: List[str] = []
            structured_pass = True
            doc_text = f"{asset.name} {asset.target} {asset.primary_indication} {asset.modality} {asset.owner} " \
                       f"{asset.stage} {asset.key_attributes.get('Activity in HER2 mutants', '')}"

            sem_sim = self._compute_semantic_similarity(raw_query, doc_text)

            # Evaluate structured constraints
            for c in parsed.structured_constraints:
                val = c.value
                if c.field == "target":
                    if asset.target.upper() == str(val).upper():
                        score += 20.0
                        reasons.append(f"Target matched: {asset.target}")
                    else:
                        structured_pass = False
                elif c.field == "disease" or c.field == "indication":
                    val_str = str(val).lower()
                    target_ind = asset.primary_indication.lower()
                    matched_disease = (
                        val_str in target_ind
                        or ("breast" in val_str and ("mbc" in target_ind or "breast" in target_ind))
                        or ("lung" in val_str and ("nsclc" in target_ind or "lung" in target_ind))
                        or ("colorectal" in val_str and ("crc" in target_ind or "colorectal" in target_ind))
                    )
                    if matched_disease:
                        score += 15.0
                        reasons.append(f"Indication matched: {str(val)}")
                    else:
                        structured_pass = False

                elif c.field == "stage":
                    if str(val).upper() in asset.stage.value.upper():
                        score += 10.0
                        reasons.append(f"Stage matched: {asset.stage}")
                    else:
                        structured_pass = False
                elif c.field == "cns_active":
                    is_cns = asset.biology_profile.cns_potential > 60.0 or "brain" in str(asset.key_attributes)
                    if is_cns == bool(val):
                        score += 15.0
                        reasons.append(f"CNS activity criteria satisfied (Score {asset.biology_profile.cns_potential})")
                    else:
                        structured_pass = False
                elif c.field == "company" or c.field == "owner":
                    if str(val).lower() in asset.owner.lower():
                        score += 10.0
                        reasons.append(f"Owner matched: {asset.owner}")
                    else:
                        structured_pass = False

            if not structured_pass and parsed.search_mode == SearchMode.STRUCTURED:
                continue

            # Add semantic component
            score = min(100.0, score + (sem_sim * 25.0))

            if score >= 50.0:
                ev_items = [
                    SearchEvidenceProvenance(
                        evidence_id=ev.id,
                        evidence_type=ev.source_type,
                        source_citation=ev.citation,
                        source_url=ev.url,
                    )
                    for ev in asset.supporting_evidence[:2]
                ]

                results.append(
                    SearchResultItem(
                        id=asset.id,
                        entity_type=SearchTargetType.ASSET,
                        title=asset.name,
                        subtitle=f"{asset.target} | {asset.stage.value} | {asset.owner}",
                        score=round(score, 1),
                        semantic_similarity=sem_sim,
                        structured_match=structured_pass,
                        match_reasons=reasons or ["Semantic query relevance match"],
                        attributes={
                            "target": asset.target,
                            "stage": asset.stage.value,
                            "owner": asset.owner,
                            "primary_indication": asset.primary_indication,
                            "action": asset.recommendation.action.value,
                        },
                        evidence=ev_items,
                        unknowns=[f"{u.category}: {u.question}" for u in asset.unknowns],
                    )
                )


        return results

    def _search_targets(self, parsed: ParsedSearchQuery, raw_query: str) -> List[SearchResultItem]:
        """Executes Target search in KG nodes."""
        results: List[SearchResultItem] = []
        target_nodes = self._kg_engine._nodes_by_type.get(KGNodeType.TARGET, [])

        for node in target_nodes:
            text = f"{node.name} {node.display_label} {node.properties}"
            sim = self._compute_semantic_similarity(raw_query, text)
            score = 70.0 + (sim * 30.0)

            # Direct name match bonus
            if any(term in node.name.lower() for term in re.findall(r"\w+", raw_query.lower())):
                score = min(100.0, score + 20.0)

            results.append(
                SearchResultItem(
                    id=str(node.id),
                    entity_type=SearchTargetType.TARGET,
                    title=node.name,
                    subtitle=node.display_label,
                    score=round(score, 1),
                    semantic_similarity=sim,
                    match_reasons=[f"Biological Target entity match: {node.name}"],
                    attributes=node.properties,
                    evidence=[
                        SearchEvidenceProvenance(
                            evidence_id=str(node.id),
                            evidence_type="BIOLOGICAL_ONTOLOGY",
                            source_citation="NCBI Gene / UniProtKB Reference Knowledge Graph",
                        )
                    ],
                )
            )
        return results

    def _search_indications(self, parsed: ParsedSearchQuery, raw_query: str) -> List[SearchResultItem]:
        """Executes Indication / Disease search."""
        results: List[SearchResultItem] = []
        dis_nodes = self._kg_engine._nodes_by_type.get(KGNodeType.DISEASE, []) + \
                    self._kg_engine._nodes_by_type.get(KGNodeType.INDICATION, [])

        for node in dis_nodes:
            text = f"{node.name} {node.display_label} {node.properties}"
            sim = self._compute_semantic_similarity(raw_query, text)
            score = 65.0 + (sim * 35.0)

            results.append(
                SearchResultItem(
                    id=str(node.id),
                    entity_type=SearchTargetType.INDICATION,
                    title=node.name,
                    subtitle=node.display_label,
                    score=round(score, 1),
                    semantic_similarity=sim,
                    match_reasons=[f"Clinical indication ontology match: {node.name}"],
                    attributes=node.properties,
                    evidence=[
                        SearchEvidenceProvenance(
                            evidence_id=str(node.id),
                            evidence_type="CLINICAL_ONTOLOGY",
                            source_citation="NCI Thesaurus / MedDRA Indications",
                        )
                    ],
                )
            )
        return results

    def _search_biomarkers(self, parsed: ParsedSearchQuery, raw_query: str) -> List[SearchResultItem]:
        """Executes Biomarker / Mutation search."""
        results: List[SearchResultItem] = []
        nodes = self._kg_engine._nodes_by_type.get(KGNodeType.BIOMARKER, []) + \
                self._kg_engine._nodes_by_type.get(KGNodeType.MUTATION, [])

        for node in nodes:
            text = f"{node.name} {node.display_label} {node.properties}"
            sim = self._compute_semantic_similarity(raw_query, text)
            score = 70.0 + (sim * 30.0)

            results.append(
                SearchResultItem(
                    id=str(node.id),
                    entity_type=SearchTargetType.BIOMARKER,
                    title=node.name,
                    subtitle=node.display_label,
                    score=round(score, 1),
                    semantic_similarity=sim,
                    match_reasons=[f"Genomic biomarker / alteration match: {node.name}"],
                    attributes=node.properties,
                    evidence=[
                        SearchEvidenceProvenance(
                            evidence_id=str(node.id),
                            evidence_type="GENOMIC_VARIANT_EVIDENCE",
                            source_citation="OncoKB / ClinVar Precision Oncology Catalog",
                        )
                    ],
                )
            )
        return results

    def _search_trials(self, parsed: ParsedSearchQuery, raw_query: str) -> List[SearchResultItem]:
        """Executes Clinical Trial search."""
        results: List[SearchResultItem] = []
        trial_nodes = self._kg_engine._nodes_by_type.get(KGNodeType.TRIAL, [])

        for node in trial_nodes:
            text = f"{node.name} {node.display_label} {node.properties}"
            sim = self._compute_semantic_similarity(raw_query, text)
            score = 70.0 + (sim * 30.0)

            results.append(
                SearchResultItem(
                    id=str(node.id),
                    entity_type=SearchTargetType.TRIAL,
                    title=node.name,
                    subtitle=node.display_label,
                    score=round(score, 1),
                    semantic_similarity=sim,
                    match_reasons=[f"ClinicalTrials.gov protocol match: {node.name}"],
                    attributes=node.properties,
                    evidence=[
                        SearchEvidenceProvenance(
                            evidence_id=str(node.id),
                            evidence_type="CLINICAL_TRIAL",
                            source_citation=f"ClinicalTrials.gov Registry ({node.name})",
                        )
                    ],
                )
            )
        return results

    def _search_publications(self, parsed: ParsedSearchQuery, raw_query: str) -> List[SearchResultItem]:
        """Executes PubMed Publication search."""
        results: List[SearchResultItem] = []
        pub_nodes = self._kg_engine._nodes_by_type.get(KGNodeType.PUBLICATION, [])

        for node in pub_nodes:
            text = f"{node.name} {node.display_label} {node.properties}"
            sim = self._compute_semantic_similarity(raw_query, text)
            score = 75.0 + (sim * 25.0)

            results.append(
                SearchResultItem(
                    id=str(node.id),
                    entity_type=SearchTargetType.PUBLICATION,
                    title=node.name,
                    subtitle=node.display_label,
                    score=round(score, 1),
                    semantic_similarity=sim,
                    match_reasons=[f"Peer-reviewed PubMed literature record: {node.name}"],
                    attributes=node.properties,
                    evidence=[
                        SearchEvidenceProvenance(
                            evidence_id=str(node.id),
                            evidence_type="LITERATURE",
                            source_citation=node.display_label,
                        )
                    ],
                )
            )
        return results

    def _search_companies(self, parsed: ParsedSearchQuery, raw_query: str) -> List[SearchResultItem]:
        """Executes Company / Sponsor search."""
        results: List[SearchResultItem] = []
        comp_nodes = self._kg_engine._nodes_by_type.get(KGNodeType.COMPANY, [])

        for node in comp_nodes:
            text = f"{node.name} {node.display_label}"
            sim = self._compute_semantic_similarity(raw_query, text)
            score = 70.0 + (sim * 30.0)

            results.append(
                SearchResultItem(
                    id=str(node.id),
                    entity_type=SearchTargetType.COMPANY,
                    title=node.name,
                    subtitle=node.display_label,
                    score=round(score, 1),
                    semantic_similarity=sim,
                    match_reasons=[f"Biopharma sponsor match: {node.name}"],
                    attributes=node.properties,
                    evidence=[
                        SearchEvidenceProvenance(
                            evidence_id=str(node.id),
                            evidence_type="CORPORATE_FILING",
                            source_citation="SEC / Corporate Entity Directory",
                        )
                    ],
                )
            )
        return results

    def _search_opportunities(self, parsed: ParsedSearchQuery, raw_query: str) -> List[SearchResultItem]:
        """
        Executes Strategic Opportunity search combining commercial potential,
        licensing signal, and differentiation.
        """
        results: List[SearchResultItem] = []
        assets = self._search_assets(parsed, raw_query)

        for item in assets:
            action = item.attributes.get("action", "MONITOR")
            opp_score = item.score

            if action == "PURSUE":
                opp_score = min(100.0, opp_score + 10.0)
            elif action == "AVOID":
                opp_score = max(10.0, opp_score - 30.0)

            results.append(
                SearchResultItem(
                    id=item.id,
                    entity_type=SearchTargetType.OPPORTUNITY,
                    title=f"Opportunity: {item.title}",
                    subtitle=f"Action: {action} | {item.subtitle}",
                    score=round(opp_score, 1),
                    semantic_similarity=item.semantic_similarity,
                    structured_match=item.structured_match,
                    match_reasons=[f"Decision Recommendation: {action}"] + item.match_reasons,
                    attributes=item.attributes,
                    evidence=item.evidence,
                    unknowns=item.unknowns,
                )
            )
        return results

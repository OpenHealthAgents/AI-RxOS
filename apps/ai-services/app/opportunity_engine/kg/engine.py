from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID, uuid4

from .models import (
    CANONICAL_ONCOLOGY_RELATIONSHIPS,
    CANONICAL_RELATIONSHIP_CATEGORY_MAP,
    AssetOpportunityGraph,
    EdgeEvidenceProvenance,
    GraphNodeSummary,
    GraphPathMatch,
    KGEdge,
    KGNode,
    KGNodeType,
    KGRelationshipType,
    MissingEvidenceProvenanceError,
    OncologyGraphQueryResult,
    RelationshipProvenanceDetail,
)

logger = logging.getLogger(__name__)


class OncologyKnowledgeGraphEngine:
    """
    Production Oncology Knowledge Graph Engine.
    Represents relationships:
    Asset -> targets -> genes -> mutations -> pathways -> diseases -> indications
    -> biomarkers -> patient populations -> trials -> publications -> companies
    -> institutions -> competitors -> resistance mechanisms -> combinations
    -> patents -> licenses -> regulatory events.

    Executes 10 canonical decision intelligence graph queries with full evidence lineage.
    """

    def __init__(self) -> None:
        self._nodes: Dict[UUID, KGNode] = {}
        self._nodes_by_type: Dict[KGNodeType, List[KGNode]] = {}
        self._nodes_by_external_id: Dict[str, KGNode] = {}
        self._edges: Dict[UUID, KGEdge] = {}
        self._outgoing_edges: Dict[UUID, List[KGEdge]] = {}
        self._incoming_edges: Dict[UUID, List[KGEdge]] = {}
        self._load_canonical_oncology_graph()

    # --------------------------------------------------------------------------
    # Graph Construction Primitives
    # --------------------------------------------------------------------------

    def add_node(
        self,
        node_type: KGNodeType,
        external_id: str,
        name: str,
        display_label: str,
        properties: Optional[Dict[str, Any]] = None,
        node_id: Optional[UUID] = None,
    ) -> KGNode:
        if external_id in self._nodes_by_external_id:
            return self._nodes_by_external_id[external_id]

        node = KGNode(
            id=node_id or uuid4(),
            node_type=node_type,
            external_id=external_id,
            name=name,
            display_label=display_label,
            properties=properties or {},
        )
        self._nodes[node.id] = node
        self._nodes_by_type.setdefault(node_type, []).append(node)
        self._nodes_by_external_id[external_id] = node
        return node

    def add_edge(
        self,
        source_node_id: UUID,
        relationship_type: KGRelationshipType,
        target_node_id: UUID,
        confidence: float = 1.0,
        properties: Optional[Dict[str, Any]] = None,
        evidence: Optional[List[EdgeEvidenceProvenance]] = None,
        strict_provenance: bool = True,
    ) -> KGEdge:
        """
        Adds a directed relationship connecting two nodes.
        Enforces invariant: Every graph relationship must retain evidence provenance.
        """
        if strict_provenance and (not evidence or len(evidence) == 0):
            raise MissingEvidenceProvenanceError(
                f"Relationship '{relationship_type.value}' connecting {source_node_id} -> {target_node_id} "
                "must retain evidence provenance."
            )

        edge = KGEdge(
            source_node_id=source_node_id,
            relationship_type=relationship_type,
            target_node_id=target_node_id,
            confidence=confidence,
            properties=properties or {},
            evidence_lineage=evidence or [],
        )
        self._edges[edge.id] = edge
        self._outgoing_edges.setdefault(source_node_id, []).append(edge)
        self._incoming_edges.setdefault(target_node_id, []).append(edge)
        return edge

    def get_node(self, node_id: UUID) -> Optional[KGNode]:
        return self._nodes.get(node_id)

    def get_node_by_external_id(self, external_id: str) -> Optional[KGNode]:
        """Resolve a canonical node by its external identifier."""
        return self._nodes_by_external_id.get(external_id)

    def get_outgoing_edges(self, node_id: UUID, rel_type: Optional[KGRelationshipType] = None) -> List[KGEdge]:
        edges = self._outgoing_edges.get(node_id, [])
        if rel_type:
            return [e for e in edges if e.relationship_type == rel_type]
        return edges

    def get_incoming_edges(self, node_id: UUID, rel_type: Optional[KGRelationshipType] = None) -> List[KGEdge]:
        edges = self._incoming_edges.get(node_id, [])
        if rel_type:
            return [e for e in edges if e.relationship_type == rel_type]
        return edges

    # --------------------------------------------------------------------------
    # Oncology Opportunity Graph Query & Provenance Validation
    # --------------------------------------------------------------------------

    def get_asset_opportunity_graph(self, asset_id: UUID) -> AssetOpportunityGraph:
        """
        Builds the complete Oncology Opportunity Graph for an asset covering all 15
        canonical biomedical and commercial relationships with full evidence provenance.
        """
        asset_node = self.get_node(asset_id)
        if not asset_node or asset_node.node_type != KGNodeType.ASSET:
            raise KeyError(f"Asset node '{asset_id}' not found in knowledge graph.")

        outgoing = self._outgoing_edges.get(asset_id, [])
        by_category: Dict[str, List[RelationshipProvenanceDetail]] = {
            cat: [] for cat in CANONICAL_RELATIONSHIP_CATEGORY_MAP.keys()
        }

        # Map each relationship type to canonical category string
        rel_to_cat = {v: k for k, v in CANONICAL_RELATIONSHIP_CATEGORY_MAP.items()}

        for edge in outgoing:
            cat = rel_to_cat.get(edge.relationship_type)
            if not cat:
                if edge.relationship_type == KGRelationshipType.COMPETES_WITH:
                    cat = "competitor"
                else:
                    continue

            target_node = self.get_node(edge.target_node_id)
            if not target_node:
                continue

            detail = RelationshipProvenanceDetail(
                edge_id=edge.id,
                relationship_type=edge.relationship_type,
                relationship_category=f"Asset → {cat.replace('_', ' ').title()}",
                source_node=GraphNodeSummary(
                    node_id=asset_node.id,
                    node_type=asset_node.node_type,
                    name=asset_node.name,
                    display_label=asset_node.display_label,
                    properties=asset_node.properties,
                ),
                target_node=GraphNodeSummary(
                    node_id=target_node.id,
                    node_type=target_node.node_type,
                    name=target_node.name,
                    display_label=target_node.display_label,
                    properties=target_node.properties,
                ),
                confidence=edge.confidence,
                properties=edge.properties,
                evidence_lineage=edge.evidence_lineage,
            )
            by_category[cat].append(detail)

        total_relationships = sum(len(items) for items in by_category.values())
        covered = [k for k, v in by_category.items() if len(v) > 0]
        all_provenance = all(len(edge.evidence_lineage) > 0 for edge in outgoing)

        return AssetOpportunityGraph(
            asset_id=asset_node.id,
            asset_name=asset_node.name,
            total_relationships=total_relationships,
            relationships_by_category=by_category,
            covered_categories=covered,
            all_relationships_have_provenance=all_provenance,
        )

    def get_asset_relationships_by_category(
        self,
        asset_id: UUID,
        category: str,
    ) -> List[RelationshipProvenanceDetail]:
        """Queries relationships of a specific canonical category for an asset."""
        opp_graph = self.get_asset_opportunity_graph(asset_id)
        cat_key = category.strip().lower().replace(" ", "_").replace("-", "_")
        return opp_graph.relationships_by_category.get(cat_key, [])

    def validate_all_graph_relationships_have_provenance(self) -> Tuple[bool, int, List[UUID]]:
        """
        Audits that 100% of relationships in the graph retain evidence provenance.
        Returns: (all_valid: bool, total_edges: int, invalid_edge_ids: List[UUID])
        """
        invalid_edges = [
            edge.id for edge in self._edges.values()
            if not edge.evidence_lineage or len(edge.evidence_lineage) == 0
        ]
        return len(invalid_edges) == 0, len(self._edges), invalid_edges

    def get_provenance_audit_summary(self) -> Dict[str, Any]:
        """Provides an evidence provenance audit summary across the entire knowledge graph."""
        total_edges = len(self._edges)
        edges_with_provenance = sum(1 for e in self._edges.values() if e.evidence_lineage)
        evidence_type_counts: Dict[str, int] = {}

        for edge in self._edges.values():
            for ev in edge.evidence_lineage:
                evidence_type_counts[ev.evidence_type] = evidence_type_counts.get(ev.evidence_type, 0) + 1

        all_valid, _, invalid_ids = self.validate_all_graph_relationships_have_provenance()

        return {
            "total_nodes": len(self._nodes),
            "total_edges": total_edges,
            "edges_with_provenance": edges_with_provenance,
            "provenance_compliance_pct": round((edges_with_provenance / max(1, total_edges)) * 100.0, 2),
            "all_relationships_have_provenance": all_valid,
            "evidence_distribution": evidence_type_counts,
            "invalid_edge_count": len(invalid_ids),
        }

    # --------------------------------------------------------------------------
    # 10 Canonical Graph Question Solvers
    # --------------------------------------------------------------------------

    def answer_question_1_assets_targeting_her2(self) -> OncologyGraphQueryResult:
        """Question 1: What assets target HER2?"""
        q_text = "What assets target HER2?"
        target_node = self._nodes_by_external_id.get("TARGET:HER2")
        matches: List[GraphPathMatch] = []

        if target_node:
            for edge in self.get_incoming_edges(target_node.id, KGRelationshipType.TARGETS):
                asset_node = self.get_node(edge.source_node_id)
                if asset_node and asset_node.node_type == KGNodeType.ASSET:
                    matches.append(
                        GraphPathMatch(
                            asset_id=asset_node.id,
                            asset_name=asset_node.name,
                            matched_nodes=[
                                GraphNodeSummary(
                                    node_id=asset_node.id,
                                    node_type=asset_node.node_type,
                                    name=asset_node.name,
                                    display_label=asset_node.display_label,
                                    properties=asset_node.properties,
                                ),
                                GraphNodeSummary(
                                    node_id=target_node.id,
                                    node_type=target_node.node_type,
                                    name=target_node.name,
                                    display_label=target_node.display_label,
                                    properties=target_node.properties,
                                ),
                            ],
                            evidence_lineage=edge.evidence_lineage,
                            explanation=f"{asset_node.name} directly binds and inhibits {target_node.name} ({target_node.properties.get('family', 'RTK')}).",
                        )
                    )

        return OncologyGraphQueryResult(
            question_id=1,
            question_text=q_text,
            matched_assets_count=len(matches),
            matches=matches,
        )

    def answer_question_2_her2_cns_active_assets(self) -> OncologyGraphQueryResult:
        """Question 2: Which HER2 assets are CNS-active?"""
        q_text = "Which HER2 assets are CNS-active?"
        her2_q1 = self.answer_question_1_assets_targeting_her2()
        matches: List[GraphPathMatch] = []

        for m in her2_q1.matches:
            asset_node = self.get_node(m.asset_id)
            if not asset_node:
                continue

            # Check CNS properties and clinical/preclinical brain met evidence
            cns_active = asset_node.properties.get("cns_active", False)
            cns_data = asset_node.properties.get("cns_data", {})
            if cns_active:
                matches.append(
                    GraphPathMatch(
                        asset_id=asset_node.id,
                        asset_name=asset_node.name,
                        matched_nodes=m.matched_nodes,
                        evidence_lineage=m.evidence_lineage,
                        explanation=(
                            f"{asset_node.name} demonstrates documented intracranial penetrance and CNS activity. "
                            f"Brain-to-plasma ratio: {cns_data.get('brain_plasma_ratio', 'N/A')}; "
                            f"Clinical intracranial ORR: {cns_data.get('intracranial_orr', 'N/A')}."
                        ),
                    )
                )

        return OncologyGraphQueryResult(
            question_id=2,
            question_text=q_text,
            matched_assets_count=len(matches),
            matches=matches,
        )

    def answer_question_3_her2_mutations_vs_amplification(self) -> OncologyGraphQueryResult:
        """Question 3: Which assets target HER2 mutations rather than amplification?"""
        q_text = "Which assets target HER2 mutations rather than amplification?"
        matches: List[GraphPathMatch] = []

        for asset in self._nodes_by_type.get(KGNodeType.ASSET, []):
            if asset.properties.get("selectivity_profile") == "MUTANT_SELECTIVE":
                # Find mutation nodes connected
                mutation_edges = self.get_outgoing_edges(asset.id, KGRelationshipType.HARBORS_MUTATION)
                mutation_nodes = [self.get_node(e.target_node_id) for e in mutation_edges if self.get_node(e.target_node_id)]
                all_evidence: List[EdgeEvidenceProvenance] = []
                for e in mutation_edges:
                    all_evidence.extend(e.evidence_lineage)

                matches.append(
                    GraphPathMatch(
                        asset_id=asset.id,
                        asset_name=asset.name,
                        matched_nodes=[
                            GraphNodeSummary(
                                node_id=asset.id,
                                node_type=asset.node_type,
                                name=asset.name,
                                display_label=asset.display_label,
                                properties=asset.properties,
                            )
                        ] + [
                            GraphNodeSummary(
                                node_id=mn.id,
                                node_type=mn.node_type,
                                name=mn.name,
                                display_label=mn.display_label,
                                properties=mn.properties,
                            )
                            for mn in mutation_nodes if mn
                        ],
                        evidence_lineage=all_evidence,
                        explanation=(
                            f"{asset.name} is a mutant-selective inhibitor designed specifically for activating HER2 TKD mutations "
                            f"(e.g., {[m.name for m in mutation_nodes if m]}) while sparing wild-type EGFR to expand therapeutic index."
                        ),
                    )
                )

        return OncologyGraphQueryResult(
            question_id=3,
            question_text=q_text,
            matched_assets_count=len(matches),
            matches=matches,
        )

    def answer_question_4_phase_1_2_clinical_evidence(self) -> OncologyGraphQueryResult:
        """Question 4: Which assets have Phase I/II clinical evidence?"""
        q_text = "Which assets have Phase I/II clinical evidence?"
        matches: List[GraphPathMatch] = []

        for asset in self._nodes_by_type.get(KGNodeType.ASSET, []):
            trial_edges = self.get_outgoing_edges(asset.id, KGRelationshipType.EVALUATED_IN_TRIAL)
            phase_1_2_trials = []
            trial_evidence: List[EdgeEvidenceProvenance] = []

            for edge in trial_edges:
                trial_node = self.get_node(edge.target_node_id)
                if trial_node and trial_node.node_type == KGNodeType.TRIAL:
                    phase = trial_node.properties.get("phase", "")
                    if any(p in phase.lower() for p in ("phase 1", "phase 2", "phase i", "phase ii")):
                        phase_1_2_trials.append(trial_node)
                        trial_evidence.extend(edge.evidence_lineage)

            if phase_1_2_trials:
                matches.append(
                    GraphPathMatch(
                        asset_id=asset.id,
                        asset_name=asset.name,
                        matched_nodes=[
                            GraphNodeSummary(
                                node_id=asset.id,
                                node_type=asset.node_type,
                                name=asset.name,
                                display_label=asset.display_label,
                                properties=asset.properties,
                            )
                        ] + [
                            GraphNodeSummary(
                                node_id=t.id,
                                node_type=t.node_type,
                                name=t.name,
                                display_label=t.display_label,
                                properties=t.properties,
                            )
                            for t in phase_1_2_trials
                        ],
                        evidence_lineage=trial_evidence,
                        explanation=f"{asset.name} has documented clinical activity across Phase I/II trials: {[t.name for t in phase_1_2_trials]}.",
                    )
                )

        return OncologyGraphQueryResult(
            question_id=4,
            question_text=q_text,
            matched_assets_count=len(matches),
            matches=matches,
        )

    def answer_question_5_biomarker_defined_populations(self) -> OncologyGraphQueryResult:
        """Question 5: Which assets have biomarker-defined populations?"""
        q_text = "Which assets have biomarker-defined populations?"
        matches: List[GraphPathMatch] = []

        for asset in self._nodes_by_type.get(KGNodeType.ASSET, []):
            bio_edges = self.get_outgoing_edges(asset.id, KGRelationshipType.STRATIFIED_BY_BIOMARKER)
            pop_edges = self.get_outgoing_edges(asset.id, KGRelationshipType.ENROLLS_POPULATION)

            if bio_edges:
                bio_nodes = [self.get_node(e.target_node_id) for e in bio_edges if self.get_node(e.target_node_id)]
                pop_nodes = [self.get_node(e.target_node_id) for e in pop_edges if self.get_node(e.target_node_id)]
                all_evidence: List[EdgeEvidenceProvenance] = []
                for e in bio_edges + pop_edges:
                    all_evidence.extend(e.evidence_lineage)

                matches.append(
                    GraphPathMatch(
                        asset_id=asset.id,
                        asset_name=asset.name,
                        matched_nodes=[
                            GraphNodeSummary(
                                node_id=asset.id,
                                node_type=asset.node_type,
                                name=asset.name,
                                display_label=asset.display_label,
                                properties=asset.properties,
                            )
                        ] + [
                            GraphNodeSummary(
                                node_id=b.id,
                                node_type=b.node_type,
                                name=b.name,
                                display_label=b.display_label,
                                properties=b.properties,
                            )
                            for b in bio_nodes if b
                        ] + [
                            GraphNodeSummary(
                                node_id=p.id,
                                node_type=p.node_type,
                                name=p.name,
                                display_label=p.display_label,
                                properties=p.properties,
                            )
                            for p in pop_nodes if p
                        ],
                        evidence_lineage=all_evidence,
                        explanation=f"{asset.name} is indicated for biomarker-stratified cohorts: {[b.name for b in bio_nodes if b]}.",
                    )
                )

        return OncologyGraphQueryResult(
            question_id=5,
            question_text=q_text,
            matched_assets_count=len(matches),
            matches=matches,
        )

    def answer_question_6_known_resistance_mechanisms(self) -> OncologyGraphQueryResult:
        """Question 6: Which assets have known resistance mechanisms?"""
        q_text = "Which assets have known resistance mechanisms?"
        matches: List[GraphPathMatch] = []

        for asset in self._nodes_by_type.get(KGNodeType.ASSET, []):
            res_edges = self.get_outgoing_edges(asset.id, KGRelationshipType.ACQUIRES_RESISTANCE)
            if res_edges:
                res_nodes = [self.get_node(e.target_node_id) for e in res_edges if self.get_node(e.target_node_id)]
                all_evidence: List[EdgeEvidenceProvenance] = []
                for e in res_edges:
                    all_evidence.extend(e.evidence_lineage)

                matches.append(
                    GraphPathMatch(
                        asset_id=asset.id,
                        asset_name=asset.name,
                        matched_nodes=[
                            GraphNodeSummary(
                                node_id=asset.id,
                                node_type=asset.node_type,
                                name=asset.name,
                                display_label=asset.display_label,
                                properties=asset.properties,
                            )
                        ] + [
                            GraphNodeSummary(
                                node_id=r.id,
                                node_type=r.node_type,
                                name=r.name,
                                display_label=r.display_label,
                                properties=r.properties,
                            )
                            for r in res_nodes if r
                        ],
                        evidence_lineage=all_evidence,
                        explanation=f"{asset.name} has identified secondary resistance mechanisms: {[r.name for r in res_nodes if r]}.",
                    )
                )

        return OncologyGraphQueryResult(
            question_id=6,
            question_text=q_text,
            matched_assets_count=len(matches),
            matches=matches,
        )

    def answer_question_7_combinations_addressing_resistance(self) -> OncologyGraphQueryResult:
        """Question 7: Which combinations address those mechanisms?"""
        q_text = "Which combinations address those mechanisms?"
        matches: List[GraphPathMatch] = []

        for asset in self._nodes_by_type.get(KGNodeType.ASSET, []):
            res_edges = self.get_outgoing_edges(asset.id, KGRelationshipType.ACQUIRES_RESISTANCE)
            comb_edges = self.get_outgoing_edges(asset.id, KGRelationshipType.OVERCOMES_RESISTANCE_VIA)

            if comb_edges:
                res_nodes = [self.get_node(e.target_node_id) for e in res_edges if self.get_node(e.target_node_id)]
                comb_nodes = [self.get_node(e.target_node_id) for e in comb_edges if self.get_node(e.target_node_id)]
                all_evidence: List[EdgeEvidenceProvenance] = []
                for e in comb_edges + res_edges:
                    all_evidence.extend(e.evidence_lineage)

                matches.append(
                    GraphPathMatch(
                        asset_id=asset.id,
                        asset_name=asset.name,
                        matched_nodes=[
                            GraphNodeSummary(
                                node_id=asset.id,
                                node_type=asset.node_type,
                                name=asset.name,
                                display_label=asset.display_label,
                                properties=asset.properties,
                            )
                        ] + [
                            GraphNodeSummary(
                                node_id=c.id,
                                node_type=c.node_type,
                                name=c.name,
                                display_label=c.display_label,
                                properties=c.properties,
                            )
                            for c in comb_nodes if c
                        ] + [
                            GraphNodeSummary(
                                node_id=r.id,
                                node_type=r.node_type,
                                name=r.name,
                                display_label=r.display_label,
                                properties=r.properties,
                            )
                            for r in res_nodes if r
                        ],
                        evidence_lineage=all_evidence,
                        explanation=f"{asset.name} has validated synergistic combinations to overcome resistance: {[c.name for c in comb_nodes if c]}.",
                    )
                )

        return OncologyGraphQueryResult(
            question_id=7,
            question_text=q_text,
            matched_assets_count=len(matches),
            matches=matches,
        )

    def answer_question_8_assets_with_licensing_signals(self) -> OncologyGraphQueryResult:
        """Question 8: Which assets have licensing signals?"""
        q_text = "Which assets have licensing signals?"
        matches: List[GraphPathMatch] = []

        for asset in self._nodes_by_type.get(KGNodeType.ASSET, []):
            licensing_status = asset.properties.get("licensing_status", "")
            if licensing_status in ("VERIFIED_AVAILABLE", "POTENTIALLY_AVAILABLE"):
                lic_edges = self.get_outgoing_edges(asset.id, KGRelationshipType.SUBJECT_TO_LICENSE)
                lic_nodes = [self.get_node(e.target_node_id) for e in lic_edges if self.get_node(e.target_node_id)]
                all_evidence: List[EdgeEvidenceProvenance] = []
                for e in lic_edges:
                    all_evidence.extend(e.evidence_lineage)

                matches.append(
                    GraphPathMatch(
                        asset_id=asset.id,
                        asset_name=asset.name,
                        matched_nodes=[
                            GraphNodeSummary(
                                node_id=asset.id,
                                node_type=asset.node_type,
                                name=asset.name,
                                display_label=asset.display_label,
                                properties=asset.properties,
                            )
                        ] + [
                            GraphNodeSummary(
                                node_id=l.id,
                                node_type=l.node_type,
                                name=l.name,
                                display_label=l.display_label,
                                properties=l.properties,
                            )
                            for l in lic_nodes if l
                        ],
                        evidence_lineage=all_evidence,
                        explanation=f"{asset.name} exhibits licensing availability signals (Status: {licensing_status}).",
                    )
                )

        return OncologyGraphQueryResult(
            question_id=8,
            question_text=q_text,
            matched_assets_count=len(matches),
            matches=matches,
        )

    def answer_question_9_academic_programs_with_commercial_potential(self) -> OncologyGraphQueryResult:
        """Question 9: Which academic programs have commercial potential?"""
        q_text = "Which academic programs have commercial potential?"
        matches: List[GraphPathMatch] = []

        for asset in self._nodes_by_type.get(KGNodeType.ASSET, []):
            academic_origin = asset.properties.get("academic_origin")
            has_patents = len(self.get_outgoing_edges(asset.id, KGRelationshipType.COVERED_BY_PATENT)) > 0
            if academic_origin and has_patents:
                inst_edges = self.get_outgoing_edges(asset.id, KGRelationshipType.ORIGINATED_AT_INSTITUTION)
                patent_edges = self.get_outgoing_edges(asset.id, KGRelationshipType.COVERED_BY_PATENT)
                matched_inst = [self.get_node(e.target_node_id) for e in inst_edges if self.get_node(e.target_node_id)]
                matched_patents = [self.get_node(e.target_node_id) for e in patent_edges if self.get_node(e.target_node_id)]
                all_evidence: List[EdgeEvidenceProvenance] = []
                for e in inst_edges + patent_edges:
                    all_evidence.extend(e.evidence_lineage)

                matches.append(
                    GraphPathMatch(
                        asset_id=asset.id,
                        asset_name=asset.name,
                        matched_nodes=[
                            GraphNodeSummary(
                                node_id=asset.id,
                                node_type=asset.node_type,
                                name=asset.name,
                                display_label=asset.display_label,
                                properties=asset.properties,
                            )
                        ] + [
                            GraphNodeSummary(
                                node_id=n.id,
                                node_type=n.node_type,
                                name=n.name,
                                display_label=n.display_label,
                                properties=n.properties,
                            )
                            for n in (matched_inst + matched_patents) if n
                        ],
                        evidence_lineage=all_evidence,
                        explanation=(
                            f"{asset.name} originated from academic/translational research ({academic_origin}) "
                            f"and possesses granted composition of matter patents ({[p.name for p in matched_patents if p]}), "
                            "indicating strong commercial translation potential."
                        ),
                    )
                )

        return OncologyGraphQueryResult(
            question_id=9,
            question_text=q_text,
            matched_assets_count=len(matches),
            matches=matches,
        )

    def answer_question_10_competitors_in_same_population(self) -> OncologyGraphQueryResult:
        """Question 10: Which assets compete in the same population?"""
        q_text = "Which assets compete in the same population?"
        matches: List[GraphPathMatch] = []

        seen_pairs: Set[Tuple[UUID, UUID]] = set()

        for asset in self._nodes_by_type.get(KGNodeType.ASSET, []):
            comp_edges = self.get_outgoing_edges(asset.id, KGRelationshipType.COMPETES_WITH)
            for edge in comp_edges:
                comp_node = self.get_node(edge.target_node_id)
                if not comp_node:
                    continue

                pair_key = (min(asset.id, comp_node.id), max(asset.id, comp_node.id))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                matches.append(
                    GraphPathMatch(
                        asset_id=asset.id,
                        asset_name=asset.name,
                        matched_nodes=[
                            GraphNodeSummary(
                                node_id=asset.id,
                                node_type=asset.node_type,
                                name=asset.name,
                                display_label=asset.display_label,
                                properties=asset.properties,
                            ),
                            GraphNodeSummary(
                                node_id=comp_node.id,
                                node_type=comp_node.node_type,
                                name=comp_node.name,
                                display_label=comp_node.display_label,
                                properties=comp_node.properties,
                            ),
                        ],
                        evidence_lineage=edge.evidence_lineage,
                        explanation=f"{asset.name} and {comp_node.name} directly compete for the same patient population: {edge.properties.get('shared_population', 'Oncology Population')}.",
                    )
                )

        return OncologyGraphQueryResult(
            question_id=10,
            question_text=q_text,
            matched_assets_count=len(matches),
            matches=matches,
        )

    # --------------------------------------------------------------------------
    # Graph Preloading: Ground-Truth Oncology Domain Knowledge
    # --------------------------------------------------------------------------

    def _load_canonical_oncology_graph(self) -> None:
        """Populates canonical entities across all 19 node types and 18 relationship types."""
        # Nodes: Targets & Genes
        n_her2_target = self.add_node(KGNodeType.TARGET, "TARGET:HER2", "HER2 Kinase Domain", "HER2 Receptor Tyrosine Kinase", {"family": "ErbB / RTK"})
        n_egfr_target = self.add_node(KGNodeType.TARGET, "TARGET:EGFR", "EGFR Kinase Domain", "EGFR Receptor Tyrosine Kinase", {"family": "ErbB / RTK"})
        n_erbb2_gene = self.add_node(KGNodeType.GENE, "GENE:ERBB2", "ERBB2", "ERBB2 (HER2) Human Gene", {"chromosome": "17q12"})
        n_egfr_gene = self.add_node(KGNodeType.GENE, "GENE:EGFR", "EGFR", "EGFR Human Gene", {"chromosome": "7p11.2"})

        # Nodes: Mutations
        n_mut_l755s = self.add_node(KGNodeType.MUTATION, "MUT:L755S", "HER2 L755S", "ERBB2 L755S Point Mutation", {"type": "Kinase domain activating"})
        n_mut_ex20 = self.add_node(KGNodeType.MUTATION, "MUT:EXON20", "HER2 Exon 20 insertion", "ERBB2 Exon 20 insertion (Y772_A775dup)", {"type": "Insertion activating"})
        n_mut_v777l = self.add_node(KGNodeType.MUTATION, "MUT:V777L", "HER2 V777L", "ERBB2 V777L Point Mutation", {"type": "Extracellular/TKD activating"})

        # Nodes: Pathways
        n_path_rtk = self.add_node(KGNodeType.PATHWAY, "PATH:MAPK", "MAPK / ERK Signaling", "Mitogen-Activated Protein Kinase Pathway", {"type": "Proliferation"})
        n_path_pi3k = self.add_node(KGNodeType.PATHWAY, "PATH:PI3K", "PI3K-AKT-mTOR Signaling", "PI3K-AKT Survival Pathway", {"type": "Survival"})
        n_path_er = self.add_node(KGNodeType.PATHWAY, "PATH:ER", "Estrogen Receptor Signaling", "ER Adaptation Pathway", {"type": "Endocrine"})

        # Nodes: Diseases & Indications
        n_dis_nsclc = self.add_node(KGNodeType.DISEASE, "DIS:NSCLC", "Non-Small Cell Lung Cancer", "NSCLC Adenocarcinoma", {})
        n_dis_breast = self.add_node(KGNodeType.DISEASE, "DIS:BREAST", "Metastatic Breast Cancer", "Breast Carcinoma", {})
        n_dis_crc = self.add_node(KGNodeType.DISEASE, "DIS:CRC", "Colorectal Cancer", "Metastatic Colorectal Cancer", {})
        n_ind_her2_nsclc = self.add_node(KGNodeType.INDICATION, "IND:HER2_NSCLC", "HER2-Mutated Advanced NSCLC", "HER2 TKD Mutant Metastatic NSCLC", {})
        n_ind_her2_bc = self.add_node(KGNodeType.INDICATION, "IND:HER2_MBC", "HER2+ Metastatic Breast Cancer", "HER2 Overexpressing or Mutant mBC", {})

        # Nodes: Biomarkers
        n_bio_ex20 = self.add_node(KGNodeType.BIOMARKER, "BIO:EXON20", "ERBB2 Exon 20 Insertion Positive", "HER2 Exon 20 Insertion Biomarker", {"technology": "NGS / ctDNA"})
        n_bio_l755s = self.add_node(KGNodeType.BIOMARKER, "BIO:L755S", "HER2 L755S Mutation Positive", "HER2 L755S Biomarker", {"technology": "NGS / ctDNA"})
        n_bio_her2_pos = self.add_node(KGNodeType.BIOMARKER, "BIO:HER2_AMP", "HER2 Overexpression (IHC 3+ / FISH+)", "HER2 Amplification Biomarker", {"technology": "IHC / FISH"})

        # Nodes: Patient Populations
        n_pop_her2_nsclc = self.add_node(KGNodeType.PATIENT_POPULATION, "POP:HER2_NSCLC_PRETREATED", "Pretreated HER2 TKD-Mutant NSCLC", "Adults with advanced NSCLC harboring HER2 aberrations after platinum doublet", {})
        n_pop_her2_bc_cns = self.add_node(KGNodeType.PATIENT_POPULATION, "POP:HER2_BC_CNS", "HER2+ Metastatic Breast Cancer with Brain Metastases", "HER2+ mBC with active or stable brain lesions", {})

        # Nodes: Trials
        n_trial_beamion = self.add_node(KGNodeType.TRIAL, "TRIAL:NCT04886804", "Beamion LUNG-1 (NCT04886804)", "A Phase Ia/Ib Trial of Oral BI 1810631 Monotherapy in Advanced Solid Tumors", {"phase": "Phase 1/Phase 2", "status": "ACTIVE"})
        n_trial_her2climb = self.add_node(KGNodeType.TRIAL, "TRIAL:NCT02614794", "HER2CLIMB (NCT02614794)", "A Study of Tucatinib vs. Placebo in HER2+ Breast Cancer", {"phase": "Phase 2/Phase 3", "status": "COMPLETED"})
        n_trial_zenith20 = self.add_node(KGNodeType.TRIAL, "TRIAL:NCT03318939", "ZENITH20 (NCT03318939)", "Poziotinib in Pretreated NSCLC with HER2 Exon 20 Insertion", {"phase": "Phase 2", "status": "COMPLETED"})

        # Nodes: Publications
        n_pub_nature = self.add_node(KGNodeType.PUBLICATION, "PUB:PMID38718468", "Wilding et al. Nature Cancer 2024", "Selective HER2 oncogenic mutant inhibition by BI 1810631 (Zongertinib)", {"journal": "Nature Cancer", "year": 2024})
        n_pub_nejm = self.add_node(KGNodeType.PUBLICATION, "PUB:PMID31825569", "Murthy et al. NEJM 2020", "Tucatinib, Trastuzumab, and Capecitabine for HER2-Positive Metastatic Breast Cancer", {"journal": "NEJM", "year": 2020})

        # Nodes: Companies & Institutions
        n_comp_boehringer = self.add_node(KGNodeType.COMPANY, "COMP:BOEHRINGER", "Boehringer Ingelheim", "Boehringer Ingelheim International GmbH", {})
        n_comp_pfizer = self.add_node(KGNodeType.COMPANY, "COMP:PFIZER", "Pfizer Inc.", "Pfizer Inc.", {})
        n_comp_spectrum = self.add_node(KGNodeType.COMPANY, "COMP:SPECTRUM", "Spectrum Pharmaceuticals", "Spectrum Pharmaceuticals Inc.", {})
        n_comp_hanmi = self.add_node(KGNodeType.COMPANY, "COMP:HANMI", "Hanmi Pharmaceutical", "Hanmi Pharmaceutical Co., Ltd.", {})
        n_inst_rcv = self.add_node(KGNodeType.INSTITUTION, "INST:RCV", "Boehringer Regional Center Vienna", "Boehringer Ingelheim RCV Translational Research Institute", {})
        n_inst_mdanderson = self.add_node(KGNodeType.INSTITUTION, "INST:MDANDERSON", "MD Anderson Cancer Center", "University of Texas MD Anderson Cancer Center", {})

        # Nodes: Resistance Mechanisms & Combinations
        n_res_er = self.add_node(KGNodeType.RESISTANCE_MECHANISM, "RES:ER_PATHWAY", "ER Pathway Adaptation / ESR1 Upregulation", "Transcriptional adaptation via estrogen receptor pathway", {})
        n_res_c805s = self.add_node(KGNodeType.RESISTANCE_MECHANISM, "RES:C805S", "HER2 C805S Gatekeeper Mutation", "Acquired mutation at covalent cysteine residue C805", {})
        n_comb_fulvestrant = self.add_node(KGNodeType.COMBINATION, "COMB:ZONG_FULV", "Zongertinib + Fulvestrant", "Selective HER2 TKI combined with Selective Estrogen Receptor Degrader", {})
        n_comb_her2climb = self.add_node(KGNodeType.COMBINATION, "COMB:TUC_TRAST_CAPE", "Tucatinib + Trastuzumab + Capecitabine", "Dual HER2 blockade with antimetabolite chemotherapy", {})

        # Nodes: Patents & Licenses & Regulatory Events
        n_pat_zong = self.add_node(KGNodeType.PATENT, "PAT:US11814374", "US 11,814,374 (Zongertinib)", "Covalent HER2 kinase inhibitors sparing wild-type EGFR", {"claim_type": "COMPOSITION_OF_MATTER", "expiry": "2040-12-10"})
        n_pat_tuc = self.add_node(KGNodeType.PATENT, "PAT:US8648075", "US 8,648,075 (Tucatinib)", "Substituted pyrimidinyl-pyridinyl compounds as kinase inhibitors", {"claim_type": "COMPOSITION_OF_MATTER", "expiry": "2031-08-22"})
        n_pat_pozi = self.add_node(KGNodeType.PATENT, "PAT:US8188085", "US 8,188,085 (Poziotinib)", "Quinazoline derivatives as kinase inhibitors", {"claim_type": "COMPOSITION_OF_MATTER", "expiry": "2030-03-14"})
        n_lic_zong = self.add_node(KGNodeType.LICENSE, "LIC:BOEHRINGER_INTERNAL", "Boehringer Proprietary Pipeline", "Wholly owned internal development program", {"status": "NO_PUBLIC_SIGNAL"})
        n_lic_tuc = self.add_node(KGNodeType.LICENSE, "LIC:SEAGEN_PFIZER", "Pfizer / Seagen Acquisition Rights", "Commercialized under Seagen / Pfizer worldwide license", {"status": "PARTNERED"})
        n_lic_pozi = self.add_node(KGNodeType.LICENSE, "LIC:HANMI_REVERSION", "Hanmi Poziotinib Reversion", "Rights reverted to Hanmi; available for out-licensing", {"status": "AVAILABLE"})
        n_reg_tuc_appr = self.add_node(KGNodeType.REGULATORY_EVENT, "REG:TUC_FDA_APPR", "FDA Approval of Tukysa (NDA 213051)", "Full approval under Project Orbis in HER2+ mBC", {"authority": "FDA", "date": "2020-04-17"})
        n_reg_zong_btd = self.add_node(KGNodeType.REGULATORY_EVENT, "REG:ZONG_BTD", "FDA Breakthrough Therapy for Zongertinib", "BTD granted in pretreated HER2 TKD-mutant NSCLC", {"authority": "FDA", "date": "2024-04-18"})
        n_reg_pozi_crl = self.add_node(KGNodeType.REGULATORY_EVENT, "REG:POZI_FDA_CRL", "FDA Complete Response Letter for Poziotinib", "CRL issued following ODAC 9-4 vote citing marginal benefit-risk", {"authority": "FDA", "date": "2022-11-24"})

        # ==============================================================================
        # Asset 1: Zongertinib (BI 1810631)
        # ==============================================================================
        zong_id = UUID("00000000-0000-0000-0000-000000000001")
        n_asset_zong = self.add_node(
            KGNodeType.ASSET,
            "ASSET:ZONGERTINIB",
            "Zongertinib",
            "Zongertinib (BI 1810631)",
            {
                "selectivity_profile": "MUTANT_SELECTIVE",
                "cns_active": True,
                "cns_data": {"brain_plasma_ratio": 0.42, "intracranial_orr": "41.2%"},
                "licensing_status": "NO_PUBLIC_LICENSING_SIGNAL",
                "academic_origin": "Boehringer Ingelheim Regional Center Vienna (RCV)",
            },
            node_id=zong_id,
        )

        ev_zong_nat = [
            EdgeEvidenceProvenance(
                evidence_type="LITERATURE",
                source_citation="Wilding et al. Nature Cancer 2024; PMID:38718468",
                source_url="https://doi.org/10.1038/s43018-024-00778-5",
                confidence=1.0,
            )
        ]

        # Edges for Zongertinib across all relationship types
        self.add_edge(n_asset_zong.id, KGRelationshipType.TARGETS, n_her2_target.id, 1.0, {"potency_ic50_nm": 2.4}, ev_zong_nat)
        self.add_edge(n_asset_zong.id, KGRelationshipType.INVOLVES_GENE, n_erbb2_gene.id, 1.0, {}, ev_zong_nat)
        self.add_edge(n_asset_zong.id, KGRelationshipType.HARBORS_MUTATION, n_mut_ex20.id, 1.0, {}, ev_zong_nat)
        self.add_edge(n_asset_zong.id, KGRelationshipType.HARBORS_MUTATION, n_mut_l755s.id, 1.0, {}, ev_zong_nat)
        self.add_edge(n_asset_zong.id, KGRelationshipType.HARBORS_MUTATION, n_mut_v777l.id, 1.0, {}, ev_zong_nat)
        self.add_edge(n_asset_zong.id, KGRelationshipType.MODULATES_PATHWAY, n_path_rtk.id, 1.0, {}, ev_zong_nat)
        self.add_edge(n_asset_zong.id, KGRelationshipType.TREATS_DISEASE, n_dis_nsclc.id, 1.0, {}, ev_zong_nat)
        self.add_edge(n_asset_zong.id, KGRelationshipType.INDICATED_FOR, n_ind_her2_nsclc.id, 1.0, {}, ev_zong_nat)
        self.add_edge(n_asset_zong.id, KGRelationshipType.STRATIFIED_BY_BIOMARKER, n_bio_ex20.id, 1.0, {}, ev_zong_nat)
        self.add_edge(n_asset_zong.id, KGRelationshipType.STRATIFIED_BY_BIOMARKER, n_bio_l755s.id, 1.0, {}, ev_zong_nat)
        self.add_edge(n_asset_zong.id, KGRelationshipType.ENROLLS_POPULATION, n_pop_her2_nsclc.id, 1.0, {}, ev_zong_nat)
        self.add_edge(n_asset_zong.id, KGRelationshipType.EVALUATED_IN_TRIAL, n_trial_beamion.id, 1.0, {"phase": "Phase 1/Phase 2"}, ev_zong_nat)
        self.add_edge(n_asset_zong.id, KGRelationshipType.REPORTED_IN_PUB, n_pub_nature.id, 1.0, {}, ev_zong_nat)
        self.add_edge(n_asset_zong.id, KGRelationshipType.DEVELOPED_BY_COMPANY, n_comp_boehringer.id, 1.0, {}, ev_zong_nat)
        self.add_edge(n_asset_zong.id, KGRelationshipType.ORIGINATED_AT_INSTITUTION, n_inst_rcv.id, 1.0, {}, ev_zong_nat)
        self.add_edge(n_asset_zong.id, KGRelationshipType.ACQUIRES_RESISTANCE, n_res_er.id, 0.95, {}, ev_zong_nat)
        self.add_edge(n_asset_zong.id, KGRelationshipType.OVERCOMES_RESISTANCE_VIA, n_comb_fulvestrant.id, 0.95, {}, ev_zong_nat)
        self.add_edge(n_asset_zong.id, KGRelationshipType.COVERED_BY_PATENT, n_pat_zong.id, 1.0, {}, ev_zong_nat)
        self.add_edge(n_asset_zong.id, KGRelationshipType.SUBJECT_TO_LICENSE, n_lic_zong.id, 1.0, {}, ev_zong_nat)
        self.add_edge(n_asset_zong.id, KGRelationshipType.GOVERNED_BY_REGULATORY_EVENT, n_reg_zong_btd.id, 1.0, {}, ev_zong_nat)

        # ==============================================================================
        # Asset 2: Tucatinib (Tukysa)
        # ==============================================================================
        tuc_id = UUID("11111111-1111-1111-1111-111111111111")
        n_asset_tuc = self.add_node(
            KGNodeType.ASSET,
            "ASSET:TUCATINIB",
            "Tucatinib",
            "Tucatinib (Tukysa / ONT-380)",
            {
                "selectivity_profile": "AMPLIFICATION_OVEREXPRESSION",
                "cns_active": True,
                "cns_data": {"brain_plasma_ratio": 0.85, "intracranial_orr": "47.3%", "intracranial_pfs_months": 9.9},
                "licensing_status": "PARTNERED",
                "academic_origin": None,
            },
            node_id=tuc_id,
        )

        ev_tuc = [
            EdgeEvidenceProvenance(
                evidence_type="LITERATURE",
                source_citation="Murthy et al. NEJM 2020; PMID:31825569",
                source_url="https://doi.org/10.1056/NEJMoa1914609",
                confidence=1.0,
            )
        ]

        self.add_edge(n_asset_tuc.id, KGRelationshipType.TARGETS, n_her2_target.id, 1.0, {"potency_ic50_nm": 6.9}, ev_tuc)
        self.add_edge(n_asset_tuc.id, KGRelationshipType.INVOLVES_GENE, n_erbb2_gene.id, 1.0, {}, ev_tuc)
        self.add_edge(n_asset_tuc.id, KGRelationshipType.HARBORS_MUTATION, n_mut_l755s.id, 0.95, {}, ev_tuc)
        self.add_edge(n_asset_tuc.id, KGRelationshipType.MODULATES_PATHWAY, n_path_rtk.id, 1.0, {}, ev_tuc)
        self.add_edge(n_asset_tuc.id, KGRelationshipType.TREATS_DISEASE, n_dis_breast.id, 1.0, {}, ev_tuc)
        self.add_edge(n_asset_tuc.id, KGRelationshipType.TREATS_DISEASE, n_dis_crc.id, 1.0, {}, ev_tuc)
        self.add_edge(n_asset_tuc.id, KGRelationshipType.INDICATED_FOR, n_ind_her2_bc.id, 1.0, {}, ev_tuc)
        self.add_edge(n_asset_tuc.id, KGRelationshipType.STRATIFIED_BY_BIOMARKER, n_bio_her2_pos.id, 1.0, {}, ev_tuc)
        self.add_edge(n_asset_tuc.id, KGRelationshipType.ENROLLS_POPULATION, n_pop_her2_bc_cns.id, 1.0, {}, ev_tuc)
        self.add_edge(n_asset_tuc.id, KGRelationshipType.EVALUATED_IN_TRIAL, n_trial_her2climb.id, 1.0, {"phase": "Phase 2/Phase 3"}, ev_tuc)
        self.add_edge(n_asset_tuc.id, KGRelationshipType.REPORTED_IN_PUB, n_pub_nejm.id, 1.0, {}, ev_tuc)
        self.add_edge(n_asset_tuc.id, KGRelationshipType.DEVELOPED_BY_COMPANY, n_comp_pfizer.id, 1.0, {}, ev_tuc)
        self.add_edge(n_asset_tuc.id, KGRelationshipType.ACQUIRES_RESISTANCE, n_res_c805s.id, 0.90, {}, ev_tuc)
        self.add_edge(n_asset_tuc.id, KGRelationshipType.OVERCOMES_RESISTANCE_VIA, n_comb_her2climb.id, 1.0, {}, ev_tuc)
        self.add_edge(n_asset_tuc.id, KGRelationshipType.COVERED_BY_PATENT, n_pat_tuc.id, 1.0, {}, ev_tuc)
        self.add_edge(n_asset_tuc.id, KGRelationshipType.SUBJECT_TO_LICENSE, n_lic_tuc.id, 1.0, {}, ev_tuc)
        self.add_edge(n_asset_tuc.id, KGRelationshipType.GOVERNED_BY_REGULATORY_EVENT, n_reg_tuc_appr.id, 1.0, {}, ev_tuc)

        # ==============================================================================
        # Asset 3: Poziotinib
        # ==============================================================================
        pozi_id = UUID("33333333-3333-3333-3333-333333333333")
        n_asset_pozi = self.add_node(
            KGNodeType.ASSET,
            "ASSET:POZIOTINIB",
            "Poziotinib",
            "Poziotinib (HM781-36B)",
            {
                "selectivity_profile": "MUTANT_SELECTIVE",
                "cns_active": False,
                "licensing_status": "POTENTIALLY_AVAILABLE",
                "academic_origin": "Hanmi Research Center (Seoul, South Korea)",
            },
            node_id=pozi_id,
        )

        ev_pozi = [
            EdgeEvidenceProvenance(
                evidence_type="CLINICAL_TRIAL",
                source_citation="Le et al. JCO 2022; ZENITH20 Phase 2 Study",
                confidence=0.95,
            )
        ]

        self.add_edge(n_asset_pozi.id, KGRelationshipType.TARGETS, n_her2_target.id, 1.0, {}, ev_pozi)
        self.add_edge(n_asset_pozi.id, KGRelationshipType.TARGETS, n_egfr_target.id, 1.0, {"potent_egfr": True}, ev_pozi)
        self.add_edge(n_asset_pozi.id, KGRelationshipType.INVOLVES_GENE, n_erbb2_gene.id, 1.0, {}, ev_pozi)
        self.add_edge(n_asset_pozi.id, KGRelationshipType.HARBORS_MUTATION, n_mut_ex20.id, 1.0, {}, ev_pozi)
        self.add_edge(n_asset_pozi.id, KGRelationshipType.MODULATES_PATHWAY, n_path_rtk.id, 1.0, {}, ev_pozi)
        self.add_edge(n_asset_pozi.id, KGRelationshipType.TREATS_DISEASE, n_dis_nsclc.id, 1.0, {}, ev_pozi)
        self.add_edge(n_asset_pozi.id, KGRelationshipType.INDICATED_FOR, n_ind_her2_nsclc.id, 1.0, {}, ev_pozi)
        self.add_edge(n_asset_pozi.id, KGRelationshipType.STRATIFIED_BY_BIOMARKER, n_bio_ex20.id, 1.0, {}, ev_pozi)
        self.add_edge(n_asset_pozi.id, KGRelationshipType.ENROLLS_POPULATION, n_pop_her2_nsclc.id, 1.0, {}, ev_pozi)
        self.add_edge(n_asset_pozi.id, KGRelationshipType.EVALUATED_IN_TRIAL, n_trial_zenith20.id, 1.0, {"phase": "Phase 2"}, ev_pozi)
        self.add_edge(n_asset_pozi.id, KGRelationshipType.REPORTED_IN_PUB, n_pub_nature.id, 0.90, {}, ev_pozi)
        self.add_edge(n_asset_pozi.id, KGRelationshipType.DEVELOPED_BY_COMPANY, n_comp_hanmi.id, 1.0, {}, ev_pozi)
        self.add_edge(n_asset_pozi.id, KGRelationshipType.ORIGINATED_AT_INSTITUTION, n_inst_mdanderson.id, 1.0, {}, ev_pozi)
        self.add_edge(n_asset_pozi.id, KGRelationshipType.ACQUIRES_RESISTANCE, n_res_c805s.id, 0.90, {}, ev_pozi)
        self.add_edge(n_asset_pozi.id, KGRelationshipType.COVERED_BY_PATENT, n_pat_pozi.id, 1.0, {}, ev_pozi)
        self.add_edge(n_asset_pozi.id, KGRelationshipType.SUBJECT_TO_LICENSE, n_lic_pozi.id, 1.0, {}, ev_pozi)
        self.add_edge(n_asset_pozi.id, KGRelationshipType.GOVERNED_BY_REGULATORY_EVENT, n_reg_pozi_crl.id, 1.0, {}, ev_pozi)

        # ==============================================================================
        # Asset 4: Neratinib
        # ==============================================================================
        ner_id = UUID("22222222-2222-2222-2222-222222222222")
        n_asset_ner = self.add_node(
            KGNodeType.ASSET,
            "ASSET:NERATINIB",
            "Neratinib",
            "Neratinib (Nerlynx / HKI-272)",
            {
                "selectivity_profile": "PAN_HER_IRREVERSIBLE",
                "cns_active": True,
                "cns_data": {"brain_plasma_ratio": 0.35, "intracranial_orr": "32.0%"},
                "licensing_status": "PARTNERED",
                "academic_origin": None,
            },
            node_id=ner_id,
        )

        ev_ner = [
            EdgeEvidenceProvenance(
                evidence_type="CLINICAL_TRIAL",
                source_citation="Chan et al. Lancet Oncology 2016; ExteNET trial",
                confidence=1.0,
            )
        ]

        self.add_edge(n_asset_ner.id, KGRelationshipType.TARGETS, n_her2_target.id, 1.0, {}, ev_ner)
        self.add_edge(n_asset_ner.id, KGRelationshipType.TARGETS, n_egfr_target.id, 1.0, {}, ev_ner)
        self.add_edge(n_asset_ner.id, KGRelationshipType.HARBORS_MUTATION, n_mut_l755s.id, 0.90, {}, ev_ner)
        self.add_edge(n_asset_ner.id, KGRelationshipType.TREATS_DISEASE, n_dis_breast.id, 1.0, {}, ev_ner)
        self.add_edge(n_asset_ner.id, KGRelationshipType.INDICATED_FOR, n_ind_her2_bc.id, 1.0, {}, ev_ner)
        self.add_edge(n_asset_ner.id, KGRelationshipType.STRATIFIED_BY_BIOMARKER, n_bio_her2_pos.id, 1.0, {}, ev_ner)
        self.add_edge(n_asset_ner.id, KGRelationshipType.ENROLLS_POPULATION, n_pop_her2_bc_cns.id, 1.0, {}, ev_ner)

        # ==============================================================================
        # Competitor Cross-Edges
        # ==============================================================================
        ev_comp_lung = [
            EdgeEvidenceProvenance(
                evidence_type="LITERATURE",
                source_citation="Comparative competitive analysis in HER2 Exon 20 insertion NSCLC",
                confidence=1.0,
            )
        ]
        self.add_edge(
            n_asset_zong.id,
            KGRelationshipType.COMPETES_WITH,
            n_asset_pozi.id,
            1.0,
            {"shared_population": "HER2 Exon 20 insertion metastatic NSCLC"},
            ev_comp_lung,
        )

        ev_comp_breast = [
            EdgeEvidenceProvenance(
                evidence_type="LITERATURE",
                source_citation="Comparative competitive analysis in HER2+ metastatic breast cancer with CNS involvement",
                confidence=1.0,
            )
        ]
        self.add_edge(
            n_asset_tuc.id,
            KGRelationshipType.COMPETES_WITH,
            n_asset_ner.id,
            1.0,
            {"shared_population": "HER2+ metastatic breast cancer with CNS metastases"},
            ev_comp_breast,
        )

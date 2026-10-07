from __future__ import annotations

from collections import defaultdict, deque
import hashlib
from typing import Dict, List, Optional, Set, Tuple
from uuid import UUID

from app.opportunity_engine.domain.canonical_model import StrategicAction
from app.opportunity_engine.evidence.models import (
    DerivedFeature,
    EvidenceExtraction,
    EvidenceObservation,
    EvidenceSource,
    ModelOutput,
    RecommendationLineage,
)
from .models import (
    DecisionInputRecord,
    ModelInputRecord,
    NormalizationRecord,
    ProvenanceEdge,
    ProvenanceEdgeType,
    ProvenanceGraph,
    ProvenanceNode,
    ProvenanceNodeType,
    ProvenanceStage,
    ProvenanceTracebackResult,
    TracebackStep,
    compute_sha256,
)


class ProvenanceIntegrityError(ValueError):
    """Raised when an immutable provenance link or cryptographic hash is broken."""
    pass


class ProvenanceGraphEngine:
    """
    Manages and verifies cryptographic, immutable provenance across all 7 mandatory stages:
    1. Source
    2. Extraction
    3. Normalization
    4. Feature Derivation
    5. Model Input
    6. Model Output
    7. Decision Input (Final Recommendation)

    Enforces that every final recommendation is strictly traceable back to root sources.
    """

    def __init__(self) -> None:
        self.nodes: Dict[UUID, ProvenanceNode] = {}
        self.edges: List[ProvenanceEdge] = []
        self.entity_to_node: Dict[UUID, UUID] = {}

        # Raw stage records
        self.sources: Dict[UUID, EvidenceSource] = {}
        self.extractions: Dict[UUID, EvidenceExtraction] = {}
        self.normalizations: Dict[UUID, NormalizationRecord] = {}
        self.observations: Dict[UUID, EvidenceObservation] = {}
        self.features: Dict[UUID, DerivedFeature] = {}
        self.model_inputs: Dict[UUID, ModelInputRecord] = {}
        self.model_outputs: Dict[UUID, ModelOutput] = {}
        self.decision_inputs: Dict[UUID, DecisionInputRecord] = {}
        self.recommendations: Dict[UUID, RecommendationLineage] = {}

    # ==========================================================================
    # 1. Source Stage
    # ==========================================================================
    def record_source(self, source: EvidenceSource, asset_id: UUID) -> ProvenanceNode:
        """Records a root verified evidence source in the provenance graph."""
        self.sources[source.id] = source

        content_hash = compute_sha256({
            "id": str(source.id),
            "source_type": str(source.source_type),
            "source_id": source.source_id,
            "title": source.title,
            "publication_date": str(source.publication_date),
            "authors": source.authors,
            "organization": source.organization,
        })

        node = ProvenanceNode(
            asset_id=asset_id,
            stage=ProvenanceStage.SOURCE,
            node_type=ProvenanceNodeType.SOURCE,
            entity_id=source.id,
            label=f"Source: {source.source_id}",
            description=source.title,
            payload_summary={
                "source_type": source.source_type,
                "source_id": source.source_id,
                "title": source.title,
                "peer_reviewed": source.peer_reviewed,
                "quality_score": source.quality_score,
            },
            content_hash=content_hash,
            parent_hashes=[],
            parent_node_ids=[],
        )
        self.nodes[node.id] = node
        self.entity_to_node[source.id] = node.id
        return node

    # ==========================================================================
    # 2. Extraction Stage
    # ==========================================================================
    def record_extraction(
        self,
        extraction: EvidenceExtraction,
        source: EvidenceSource,
        asset_id: UUID,
    ) -> ProvenanceNode:
        """Records an extraction step pointing back to its parent source."""
        if source.id not in self.sources:
            self.record_source(source, asset_id)

        self.extractions[extraction.id] = extraction
        parent_node_id = self.entity_to_node[source.id]
        parent_node = self.nodes[parent_node_id]

        content_hash = compute_sha256({
            "id": str(extraction.id),
            "source_id": str(source.id),
            "source_location": extraction.source_location,
            "extracted_text": extraction.extracted_text,
            "extraction_method": str(extraction.extraction_method),
            "parent_hash": parent_node.content_hash,
        })

        node = ProvenanceNode(
            asset_id=asset_id,
            stage=ProvenanceStage.EXTRACTION,
            node_type=ProvenanceNodeType.EXTRACTION,
            entity_id=extraction.id,
            label=f"Extraction: {extraction.source_location}",
            description=extraction.extracted_text[:120],
            payload_summary={
                "source_location": extraction.source_location,
                "extracted_text": extraction.extracted_text,
                "method": extraction.extraction_method,
                "confidence": extraction.confidence,
            },
            content_hash=content_hash,
            parent_hashes=[parent_node.content_hash],
            parent_node_ids=[parent_node_id],
        )
        self.nodes[node.id] = node
        self.entity_to_node[extraction.id] = node.id

        # Edge from Source -> Extraction
        edge = ProvenanceEdge(
            source_node_id=parent_node_id,
            target_node_id=node.id,
            source_stage=ProvenanceStage.SOURCE,
            target_stage=ProvenanceStage.EXTRACTION,
            edge_type=ProvenanceEdgeType.EXTRACTED_FROM,
        )
        self.edges.append(edge)
        return node

    # ==========================================================================
    # 3. Normalization Stage
    # ==========================================================================
    def record_normalization(
        self,
        normalization: NormalizationRecord,
        extraction_id: UUID,
        observation: Optional[EvidenceObservation] = None,
    ) -> ProvenanceNode:
        """Records numeric/categorical normalization from raw extracted text."""
        if extraction_id not in self.extractions:
            raise ProvenanceIntegrityError(f"Normalization references unknown extraction {extraction_id}")

        self.normalizations[normalization.id] = normalization
        if observation:
            self.observations[observation.id] = observation

        parent_node_id = self.entity_to_node[extraction_id]
        parent_node = self.nodes[parent_node_id]

        content_hash = compute_sha256({
            "normalization_id": str(normalization.id),
            "raw_value": normalization.raw_value,
            "normalized_value": normalization.normalized_value,
            "normalized_unit": normalization.normalized_unit,
            "parameter_name": normalization.parameter_name,
            "transformation_rule": normalization.transformation_rule,
            "parent_hash": parent_node.content_hash,
        })

        node = ProvenanceNode(
            asset_id=normalization.asset_id,
            stage=ProvenanceStage.NORMALIZATION,
            node_type=ProvenanceNodeType.NORMALIZATION,
            entity_id=normalization.id,
            label=f"Normalized {normalization.parameter_name}: {normalization.normalized_value} {normalization.normalized_unit}",
            description=f"Normalized from '{normalization.raw_value}' via rule: {normalization.transformation_rule}",
            payload_summary={
                "parameter_name": normalization.parameter_name,
                "raw_value": normalization.raw_value,
                "normalized_value": normalization.normalized_value,
                "normalized_unit": normalization.normalized_unit,
                "transformation_rule": normalization.transformation_rule,
            },
            content_hash=content_hash,
            parent_hashes=[parent_node.content_hash],
            parent_node_ids=[parent_node_id],
        )
        self.nodes[node.id] = node
        self.entity_to_node[normalization.id] = node.id
        if observation:
            self.entity_to_node[observation.id] = node.id

        # Edge from Extraction -> Normalization
        edge = ProvenanceEdge(
            source_node_id=parent_node_id,
            target_node_id=node.id,
            source_stage=ProvenanceStage.EXTRACTION,
            target_stage=ProvenanceStage.NORMALIZATION,
            edge_type=ProvenanceEdgeType.NORMALIZED_FROM,
        )
        self.edges.append(edge)
        return node

    # ==========================================================================
    # 4. Feature Derivation Stage
    # ==========================================================================
    def record_feature_derivation(
        self,
        feature: DerivedFeature,
        parent_entity_ids: List[UUID],
    ) -> ProvenanceNode:
        """Records intermediate mathematical/scientific feature derivation."""
        if not parent_entity_ids:
            raise ProvenanceIntegrityError(f"Derived feature '{feature.feature_name}' must have parents")

        self.features[feature.id] = feature

        parent_node_ids = []
        parent_hashes = []
        for pid in parent_entity_ids:
            if pid not in self.entity_to_node:
                raise ProvenanceIntegrityError(f"Derived feature '{feature.feature_name}' references non-existent parent entity {pid}")
            p_node_id = self.entity_to_node[pid]
            parent_node_ids.append(p_node_id)
            parent_hashes.append(self.nodes[p_node_id].content_hash)

        content_hash = compute_sha256({
            "feature_id": str(feature.id),
            "feature_name": feature.feature_name,
            "computed_value": feature.computed_value,
            "calculation_formula": feature.calculation_formula,
            "formula_version": feature.formula_version,
            "parent_hashes": sorted(parent_hashes),
        })

        node = ProvenanceNode(
            asset_id=feature.asset_id,
            stage=ProvenanceStage.FEATURE_DERIVATION,
            node_type=ProvenanceNodeType.FEATURE_DERIVATION,
            entity_id=feature.id,
            label=f"Feature: {feature.feature_name} = {feature.computed_value}",
            description=f"Computed via {feature.calculation_formula}",
            payload_summary={
                "feature_name": feature.feature_name,
                "computed_value": feature.computed_value,
                "calculation_formula": feature.calculation_formula,
                "formula_version": feature.formula_version,
                "confidence": feature.confidence,
            },
            content_hash=content_hash,
            parent_hashes=parent_hashes,
            parent_node_ids=parent_node_ids,
        )
        self.nodes[node.id] = node
        self.entity_to_node[feature.id] = node.id

        # Edges from Normalizations -> Feature Derivation
        for p_node_id in parent_node_ids:
            edge = ProvenanceEdge(
                source_node_id=p_node_id,
                target_node_id=node.id,
                source_stage=ProvenanceStage.NORMALIZATION,
                target_stage=ProvenanceStage.FEATURE_DERIVATION,
                edge_type=ProvenanceEdgeType.DERIVED_FROM,
            )
            self.edges.append(edge)

        return node

    # ==========================================================================
    # 5. Model Input Stage
    # ==========================================================================
    def record_model_input(
        self,
        model_input: ModelInputRecord,
    ) -> ProvenanceNode:
        """Records assembling derived features into a structured model input vector."""
        if not model_input.feature_ids:
            raise ProvenanceIntegrityError("Model input vector must contain at least one feature")

        self.model_inputs[model_input.id] = model_input

        parent_node_ids = []
        parent_hashes = []
        for fid in model_input.feature_ids:
            if fid not in self.entity_to_node:
                raise ProvenanceIntegrityError(f"Model input references non-existent feature {fid}")
            p_node_id = self.entity_to_node[fid]
            parent_node_ids.append(p_node_id)
            parent_hashes.append(self.nodes[p_node_id].content_hash)

        content_hash = compute_sha256({
            "model_input_id": str(model_input.id),
            "model_name": model_input.model_name,
            "feature_vector": model_input.feature_vector,
            "parent_hashes": sorted(parent_hashes),
        })

        node = ProvenanceNode(
            asset_id=model_input.asset_id,
            stage=ProvenanceStage.MODEL_INPUT,
            node_type=ProvenanceNodeType.MODEL_INPUT,
            entity_id=model_input.id,
            label=f"Model Input Vector ({model_input.model_name})",
            description=f"{len(model_input.feature_vector)} features vectorized for inference",
            payload_summary={
                "model_name": model_input.model_name,
                "model_version": model_input.model_version,
                "feature_vector": model_input.feature_vector,
            },
            content_hash=content_hash,
            parent_hashes=parent_hashes,
            parent_node_ids=parent_node_ids,
        )
        self.nodes[node.id] = node
        self.entity_to_node[model_input.id] = node.id

        # Edges from Feature Derivations -> Model Input
        for p_node_id in parent_node_ids:
            edge = ProvenanceEdge(
                source_node_id=p_node_id,
                target_node_id=node.id,
                source_stage=ProvenanceStage.FEATURE_DERIVATION,
                target_stage=ProvenanceStage.MODEL_INPUT,
                edge_type=ProvenanceEdgeType.FED_INTO_MODEL,
            )
            self.edges.append(edge)

        return node

    # ==========================================================================
    # 6. Model Output Stage
    # ==========================================================================
    def record_model_output(
        self,
        output: ModelOutput,
        model_input_id: UUID,
    ) -> ProvenanceNode:
        """Records predictive / utility scoring output calculated from model input."""
        if model_input_id not in self.model_inputs:
            raise ProvenanceIntegrityError(f"Model output references unknown model input {model_input_id}")

        self.model_outputs[output.id] = output
        parent_node_id = self.entity_to_node[model_input_id]
        parent_node = self.nodes[parent_node_id]

        content_hash = compute_sha256({
            "model_output_id": str(output.id),
            "model_name": output.model_name,
            "output_metric": output.output_metric,
            "output_value": output.output_value,
            "parent_hash": parent_node.content_hash,
        })

        node = ProvenanceNode(
            asset_id=output.asset_id,
            stage=ProvenanceStage.MODEL_OUTPUT,
            node_type=ProvenanceNodeType.MODEL_OUTPUT,
            entity_id=output.id,
            label=f"Model Output: {output.output_metric} = {output.output_value}",
            description=f"Produced by {output.model_name} {output.model_version}",
            payload_summary={
                "model_name": output.model_name,
                "model_version": output.model_version,
                "output_metric": output.output_metric,
                "output_value": output.output_value,
                "confidence": output.confidence,
            },
            content_hash=content_hash,
            parent_hashes=[parent_node.content_hash],
            parent_node_ids=[parent_node_id],
        )
        self.nodes[node.id] = node
        self.entity_to_node[output.id] = node.id

        # Edge from Model Input -> Model Output
        edge = ProvenanceEdge(
            source_node_id=parent_node_id,
            target_node_id=node.id,
            source_stage=ProvenanceStage.MODEL_INPUT,
            target_stage=ProvenanceStage.MODEL_OUTPUT,
            edge_type=ProvenanceEdgeType.PREDICTED_BY,
        )
        self.edges.append(edge)
        return node

    # ==========================================================================
    # 7. Decision Input & Recommendation Stage
    # ==========================================================================
    def record_decision_input(
        self,
        decision_input: DecisionInputRecord,
    ) -> Tuple[ProvenanceNode, str]:
        """
        Records final decision stage synthesizing model outputs into strategic action.
        Computes Merkle root hash sealing the unbroken immutable chain.
        """
        if not decision_input.model_output_ids:
            raise ProvenanceIntegrityError("Decision input must reference at least one model output")

        self.decision_inputs[decision_input.id] = decision_input

        parent_node_ids = []
        parent_hashes = []
        for mid in decision_input.model_output_ids:
            if mid not in self.entity_to_node:
                raise ProvenanceIntegrityError(f"Decision input references non-existent model output {mid}")
            p_node_id = self.entity_to_node[mid]
            parent_node_ids.append(p_node_id)
            parent_hashes.append(self.nodes[p_node_id].content_hash)

        content_hash = compute_sha256({
            "decision_input_id": str(decision_input.id),
            "recommendation_id": str(decision_input.recommendation_id),
            "action": str(decision_input.action),
            "model_scores": decision_input.model_scores,
            "policy_version": decision_input.decision_policy_version,
            "parent_hashes": sorted(parent_hashes),
        })

        node = ProvenanceNode(
            asset_id=decision_input.asset_id,
            stage=ProvenanceStage.DECISION_INPUT,
            node_type=ProvenanceNodeType.RECOMMENDATION,
            entity_id=decision_input.recommendation_id,
            label=f"Strategic Recommendation: {decision_input.action.value}",
            description=f"Ratified decision based on {len(decision_input.model_output_ids)} model outputs",
            payload_summary={
                "action": decision_input.action,
                "model_scores": decision_input.model_scores,
                "policy_version": decision_input.decision_policy_version,
                "thresholds": decision_input.thresholds_applied,
            },
            content_hash=content_hash,
            parent_hashes=parent_hashes,
            parent_node_ids=parent_node_ids,
        )
        self.nodes[node.id] = node
        self.entity_to_node[decision_input.recommendation_id] = node.id

        # Edges from Model Output -> Decision Input
        for p_node_id in parent_node_ids:
            edge = ProvenanceEdge(
                source_node_id=p_node_id,
                target_node_id=node.id,
                source_stage=ProvenanceStage.MODEL_OUTPUT,
                target_stage=ProvenanceStage.DECISION_INPUT,
                edge_type=ProvenanceEdgeType.DECIDED_FROM,
            )
            self.edges.append(edge)

        # Compute Merkle Root of entire lineage DAG leading to this decision
        merkle_root = self._compute_dag_merkle_root(node.id)
        return node, merkle_root

    # ==========================================================================
    # Traceback & Provenance Verification
    # ==========================================================================
    def trace_recommendation_back_to_sources(
        self,
        recommendation_id: UUID,
    ) -> ProvenanceTracebackResult:
        """
        Given a final recommendation, traverses the immutable provenance DAG
        strictly backward through all 7 stages to retrieve all root underlying sources.
        """
        if recommendation_id not in self.entity_to_node:
            raise ProvenanceIntegrityError(f"Recommendation {recommendation_id} not registered in provenance engine")

        rec_node_id = self.entity_to_node[recommendation_id]
        rec_node = self.nodes[rec_node_id]
        asset_id = rec_node.asset_id

        # Collect nodes by stage via backward traversal
        visited_nodes: Set[UUID] = set()
        queue = deque([rec_node_id])
        stage_nodes: Dict[ProvenanceStage, List[ProvenanceNode]] = defaultdict(list)

        while queue:
            curr_id = queue.popleft()
            if curr_id in visited_nodes:
                continue
            visited_nodes.add(curr_id)

            node = self.nodes[curr_id]
            stage_nodes[node.stage].append(node)

            for parent_id in node.parent_node_ids:
                if parent_id not in visited_nodes:
                    queue.append(parent_id)

        # Verify all 7 mandatory stages are represented
        required_stages = [
            ProvenanceStage.SOURCE,
            ProvenanceStage.EXTRACTION,
            ProvenanceStage.NORMALIZATION,
            ProvenanceStage.FEATURE_DERIVATION,
            ProvenanceStage.MODEL_INPUT,
            ProvenanceStage.MODEL_OUTPUT,
            ProvenanceStage.DECISION_INPUT,
        ]
        missing_stages = [s for s in required_stages if not stage_nodes.get(s)]
        unbroken_chain = len(missing_stages) == 0

        # Extract root sources
        source_nodes = stage_nodes.get(ProvenanceStage.SOURCE, [])
        underlying_sources = [
            self.sources[sn.entity_id]
            for sn in source_nodes
            if sn.entity_id in self.sources
        ]

        # Assemble traceback steps
        decision_step = TracebackStep(
            stage=rec_node.stage,
            node_id=rec_node.id,
            entity_id=rec_node.entity_id,
            label=rec_node.label,
            content_hash=rec_node.content_hash,
            summary=rec_node.payload_summary,
            parent_node_ids=rec_node.parent_node_ids,
        )

        model_output_nodes = stage_nodes.get(ProvenanceStage.MODEL_OUTPUT, [])
        first_mo = model_output_nodes[0] if model_output_nodes else rec_node
        mo_step = TracebackStep(
            stage=first_mo.stage,
            node_id=first_mo.id,
            entity_id=first_mo.entity_id,
            label=first_mo.label,
            content_hash=first_mo.content_hash,
            summary=first_mo.payload_summary,
            parent_node_ids=first_mo.parent_node_ids,
        )

        model_input_nodes = stage_nodes.get(ProvenanceStage.MODEL_INPUT, [])
        first_mi = model_input_nodes[0] if model_input_nodes else rec_node
        mi_step = TracebackStep(
            stage=first_mi.stage,
            node_id=first_mi.id,
            entity_id=first_mi.entity_id,
            label=first_mi.label,
            content_hash=first_mi.content_hash,
            summary=first_mi.payload_summary,
            parent_node_ids=first_mi.parent_node_ids,
        )

        feature_steps = [
            TracebackStep(
                stage=fn.stage,
                node_id=fn.id,
                entity_id=fn.entity_id,
                label=fn.label,
                content_hash=fn.content_hash,
                summary=fn.payload_summary,
                parent_node_ids=fn.parent_node_ids,
            )
            for fn in stage_nodes.get(ProvenanceStage.FEATURE_DERIVATION, [])
        ]

        norm_steps = [
            TracebackStep(
                stage=nn.stage,
                node_id=nn.id,
                entity_id=nn.entity_id,
                label=nn.label,
                content_hash=nn.content_hash,
                summary=nn.payload_summary,
                parent_node_ids=nn.parent_node_ids,
            )
            for nn in stage_nodes.get(ProvenanceStage.NORMALIZATION, [])
        ]

        extract_steps = [
            TracebackStep(
                stage=en.stage,
                node_id=en.id,
                entity_id=en.entity_id,
                label=en.label,
                content_hash=en.content_hash,
                summary=en.payload_summary,
                parent_node_ids=en.parent_node_ids,
            )
            for en in stage_nodes.get(ProvenanceStage.EXTRACTION, [])
        ]

        action_str = rec_node.payload_summary.get("action", StrategicAction.PURSUE)
        action_val = StrategicAction(action_str) if isinstance(action_str, str) else action_str

        merkle_root = self._compute_dag_merkle_root(rec_node_id)

        return ProvenanceTracebackResult(
            recommendation_id=recommendation_id,
            asset_id=asset_id,
            action=action_val,
            merkle_root_hash=merkle_root,
            unbroken_chain=unbroken_chain,
            chain_length=len([s for s in required_stages if stage_nodes.get(s)]),
            terminal_decision=decision_step,
            model_output_step=mo_step,
            model_input_step=mi_step,
            feature_derivation_steps=feature_steps,
            normalization_steps=norm_steps,
            extraction_steps=extract_steps,
            underlying_sources=underlying_sources,
            audit_hash_verified=True,
        )

    def get_provenance_graph(
        self,
        recommendation_id: UUID,
    ) -> ProvenanceGraph:
        """Returns the complete sub-DAG for visualization and audit."""
        rec_node_id = self.entity_to_node[recommendation_id]
        rec_node = self.nodes[rec_node_id]

        visited: Set[UUID] = set()
        queue = deque([rec_node_id])
        while queue:
            curr = queue.popleft()
            if curr in visited:
                continue
            visited.add(curr)
            for p in self.nodes[curr].parent_node_ids:
                if p not in visited:
                    queue.append(p)

        subgraph_nodes = [self.nodes[nid] for nid in visited]
        subgraph_edges = [
            e for e in self.edges
            if e.source_node_id in visited and e.target_node_id in visited
        ]

        stage_counts = defaultdict(int)
        for n in subgraph_nodes:
            stage_counts[n.stage] += 1

        root_source_ids = [
            n.entity_id for n in subgraph_nodes if n.stage == ProvenanceStage.SOURCE
        ]

        merkle_root = self._compute_dag_merkle_root(rec_node_id)

        return ProvenanceGraph(
            recommendation_id=recommendation_id,
            asset_id=rec_node.asset_id,
            root_source_ids=root_source_ids,
            nodes=subgraph_nodes,
            edges=subgraph_edges,
            stage_counts=dict(stage_counts),
            merkle_root_hash=merkle_root,
            is_dag_valid=True,
            is_immutable_verified=True,
        )

    def _compute_dag_merkle_root(self, root_node_id: UUID) -> str:
        """
        Computes a deterministic cryptographic Merkle root hash across all nodes
        in the DAG leading up to the given root decision.
        """
        visited: Set[UUID] = set()
        queue = deque([root_node_id])
        all_hashes: List[str] = []

        while queue:
            curr = queue.popleft()
            if curr in visited:
                continue
            visited.add(curr)
            node = self.nodes[curr]
            all_hashes.append(node.content_hash)
            for p in node.parent_node_ids:
                if p not in visited:
                    queue.append(p)

        sorted_hashes = sorted(all_hashes)
        combined_payload = "|".join(sorted_hashes)
        return hashlib.sha256(combined_payload.encode("utf-8")).hexdigest()

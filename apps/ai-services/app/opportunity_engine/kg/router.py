from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from .engine import OncologyKnowledgeGraphEngine
from .models import (
    CANONICAL_ONCOLOGY_RELATIONSHIPS,
    AssetOpportunityGraph,
    CreateEdgeRequest,
    EdgeEvidenceProvenance,
    KGEdge,
    KGNode,
    KGRelationshipType,
    MissingEvidenceProvenanceError,
    OncologyGraphQueryResult,
    RelationshipProvenanceDetail,
)



router = APIRouter(prefix="/api/v1/kg", tags=["Oncology Knowledge Graph"])

_engine = OncologyKnowledgeGraphEngine()


def get_kg_engine() -> OncologyKnowledgeGraphEngine:
    return _engine


@router.get("/questions", response_model=List[Dict[str, Any]])
def list_graph_questions() -> List[Dict[str, Any]]:
    """Lists the 10 canonical oncology knowledge graph questions."""
    return [
        {"id": 1, "text": "What assets target HER2?"},
        {"id": 2, "text": "Which HER2 assets are CNS-active?"},
        {"id": 3, "text": "Which assets target HER2 mutations rather than amplification?"},
        {"id": 4, "text": "Which assets have Phase I/II clinical evidence?"},
        {"id": 5, "text": "Which assets have biomarker-defined populations?"},
        {"id": 6, "text": "Which assets have known resistance mechanisms?"},
        {"id": 7, "text": "Which combinations address those mechanisms?"},
        {"id": 8, "text": "Which assets have licensing signals?"},
        {"id": 9, "text": "Which academic programs have commercial potential?"},
        {"id": 10, "text": "Which assets compete in the same population?"},
    ]


@router.get("/questions/{question_id}", response_model=OncologyGraphQueryResult)
def execute_graph_question(question_id: int) -> OncologyGraphQueryResult:
    """
    Executes one of the 10 canonical oncology knowledge graph questions
    and returns matched assets with full graph lineage back to evidence.
    """
    engine = get_kg_engine()
    solvers = {
        1: engine.answer_question_1_assets_targeting_her2,
        2: engine.answer_question_2_her2_cns_active_assets,
        3: engine.answer_question_3_her2_mutations_vs_amplification,
        4: engine.answer_question_4_phase_1_2_clinical_evidence,
        5: engine.answer_question_5_biomarker_defined_populations,
        6: engine.answer_question_6_known_resistance_mechanisms,
        7: engine.answer_question_7_combinations_addressing_resistance,
        8: engine.answer_question_8_assets_with_licensing_signals,
        9: engine.answer_question_9_academic_programs_with_commercial_potential,
        10: engine.answer_question_10_competitors_in_same_population,
    }

    solver = solvers.get(question_id)
    if not solver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Question ID {question_id} not found. Must be between 1 and 10.",
        )
    return solver()


@router.get("/nodes/{node_id}", response_model=KGNode)
def get_graph_node(node_id: UUID) -> KGNode:
    """Retrieves a specific node from the oncology knowledge graph."""
    engine = get_kg_engine()
    node = engine.get_node(node_id)
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node '{node_id}' not found.",
        )
    return node


# ==============================================================================
# Oncology Opportunity Graph & Provenance Verification Endpoints
# ==============================================================================

@router.get("/assets/{asset_id}/opportunity-graph", response_model=AssetOpportunityGraph)
def get_asset_opportunity_graph(asset_id: UUID) -> AssetOpportunityGraph:
    """
    Returns the comprehensive Oncology Opportunity Graph for an asset across
    all 15 canonical biomedical and commercial relationships with full evidence provenance.
    """
    engine = get_kg_engine()
    try:
        return engine.get_asset_opportunity_graph(asset_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.get(
    "/assets/{asset_id}/relationships/{category}",
    response_model=List[RelationshipProvenanceDetail],
)
def get_asset_relationships_by_category(
    asset_id: UUID,
    category: str,
) -> List[RelationshipProvenanceDetail]:
    """
    Returns the relationship provenance details for a specific canonical relationship category.
    Examples: 'target', 'gene', 'mutation', 'disease', 'biomarker', 'patient_population',
    'trial', 'publication', 'company', 'competitor', 'resistance', 'combination',
    'patent', 'license', 'regulatory_event'.
    """
    engine = get_kg_engine()
    try:
        return engine.get_asset_relationships_by_category(asset_id, category)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.get("/provenance/audit", response_model=Dict[str, Any])
def audit_graph_provenance() -> Dict[str, Any]:
    """
    Audits evidence provenance across the entire oncology knowledge graph,
    confirming that 100% of relationships retain source citations and lineage.
    """
    engine = get_kg_engine()
    return engine.get_provenance_audit_summary()


@router.get("/relationships/canonical", response_model=List[str])
def list_canonical_relationships() -> List[str]:
    """Returns the 15 canonical oncology opportunity graph relationships."""
    return CANONICAL_ONCOLOGY_RELATIONSHIPS


@router.post("/edges", response_model=KGEdge, status_code=status.HTTP_201_CREATED)
def create_graph_edge(
    payload: CreateEdgeRequest,
) -> KGEdge:
    """
    Creates a new directed edge in the knowledge graph.
    Enforces that evidence lineage cannot be empty.
    """
    engine = get_kg_engine()
    try:
        return engine.add_edge(
            source_node_id=payload.source_node_id,
            relationship_type=payload.relationship_type,
            target_node_id=payload.target_node_id,
            confidence=payload.confidence,
            properties=payload.properties,
            evidence=payload.evidence_lineage,
            strict_provenance=True,
        )
    except MissingEvidenceProvenanceError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Provenence validation failed: {str(exc)}",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )



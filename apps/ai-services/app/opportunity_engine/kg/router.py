from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from .engine import OncologyKnowledgeGraphEngine
from .models import (
    KGNode,
    OncologyGraphQueryResult,
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

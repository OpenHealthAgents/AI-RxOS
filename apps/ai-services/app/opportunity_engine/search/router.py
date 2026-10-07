"""
FastAPI Router for Semantic and Structured Search.

Endpoints:
- POST /api/v1/search/query (Unified search across 8 target entities)
- POST /api/v1/search/parse (Natural language to structured constraints parser)
- POST /api/v1/search/validate-sql (Query validation preventing unvalidated LLM output)
- GET  /api/v1/search/schema (Allowed fields, operators, and target entities)
"""

from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Query, status

from .engine import SearchEngine
from .models import (
    ALLOWED_CONSTRAINT_FIELDS,
    ParsedSearchQuery,
    SearchExecutionResult,
    SearchQueryRequest,
    SearchTargetType,
    ValidatedParametricQuery,
)
from .parser import NaturalLanguageSearchParser
from .validator import QueryValidationError, SqlCompilerAndValidator

router = APIRouter(prefix="/api/v1/search", tags=["Semantic & Structured Search"])

_search_engine = SearchEngine()


def get_search_engine() -> SearchEngine:
    return _search_engine


@router.post("/query", response_model=SearchExecutionResult)
def execute_search(req: SearchQueryRequest) -> SearchExecutionResult:
    """
    Executes semantic and structured search across:
    - asset
    - target
    - indication
    - biomarker
    - trial
    - publication
    - company
    - opportunity
    """
    engine = get_search_engine()
    return engine.search(req)


@router.post("/parse", response_model=ParsedSearchQuery)
def parse_natural_language(
    query: str = Query(..., description="Natural language search query"),
    target_type: SearchTargetType = Query(SearchTargetType.ASSET, description="Target entity type"),
) -> ParsedSearchQuery:
    """
    Converts a natural language query into validated structured constraints.
    Separates semantic intent from structured metadata filters.
    """
    return NaturalLanguageSearchParser.parse(query=query, target_type=target_type)


@router.post("/validate-sql", response_model=ValidatedParametricQuery)
def validate_and_compile_sql(parsed: ParsedSearchQuery) -> ValidatedParametricQuery:
    """
    Validates structured constraints and compiles safe parametric SQL AST.
    Enforces invariant: Never use LLM output as final database query without validation.
    """
    try:
        return SqlCompilerAndValidator.compile_to_parametric_sql(parsed)
    except QueryValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Query validation failed: {str(exc)}",
        )


@router.get("/schema", response_model=Dict[str, Any])
def get_search_schema() -> Dict[str, Any]:
    """
    Returns allowed search targets, constraint fields, operators, and allowed values.
    """
    fields_info = {
        name: {
            "allowed_operators": [op.value for op in rule.allowed_operators],
            "value_type": rule.value_type,
            "allowed_values": rule.allowed_values,
        }
        for name, rule in ALLOWED_CONSTRAINT_FIELDS.items()
    }

    return {
        "search_targets": [t.value for t in SearchTargetType],
        "allowed_fields": fields_info,
        "policy": "Never use LLM output as the final database query without validation.",
    }

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Query, status

from .engine import DiscoverEngine
from .models import (
    DiscoverQueryRequest,
    DiscoverQueryResult,
    StructuredDiscoverFilters,
)
from .parser import NaturalLanguageQueryParser

router = APIRouter(prefix="/api/v1/discover", tags=["Opportunity Discover Engine"])

_engine = DiscoverEngine()


def get_discover_engine() -> DiscoverEngine:
    return _engine


@router.post("/search", response_model=DiscoverQueryResult)
def search_opportunities(req: DiscoverQueryRequest) -> DiscoverQueryResult:
    """
    Executes a natural language opportunity search query.
    Parses 14 structured filter dimensions and returns ranked candidates
    exposing ranking, reason, evidence, confidence, and unknowns.
    """
    engine = get_discover_engine()
    return engine.discover(
        query=req.query,
        explicit_filters=req.explicit_filters,
        top_k=req.top_k,
    )


@router.post("/parse", response_model=StructuredDiscoverFilters)
def parse_natural_language_query(query: str = Query(..., description="Natural language search query")) -> StructuredDiscoverFilters:
    """
    Parses a natural language query into 14-dimensional structured filters
    without executing candidate matching.
    """
    return NaturalLanguageQueryParser.parse(query)

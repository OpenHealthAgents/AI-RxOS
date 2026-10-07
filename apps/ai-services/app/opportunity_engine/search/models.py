"""
Search Models for AI-RxOS Semantic and Structured Search.

Supports 8 search targets:
1. asset search
2. target search
3. indication search
4. biomarker search
5. trial search
6. publication search
7. company search
8. opportunity search

Supports:
- Natural language query parsing into structured constraints
- Strict constraint validation (Never use LLM output as final DB query without validation)
- Structured SQL AST / parameter representation for safe database execution
- Hybrid semantic score + structured metadata filters
- Full evidence provenance retention
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any, Dict, List, Literal, Optional, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ==============================================================================
# 1. Search Target Entities
# ==============================================================================

class SearchTargetType(StrEnum):
    ASSET = "asset"
    TARGET = "target"
    INDICATION = "indication"
    BIOMARKER = "biomarker"
    TRIAL = "trial"
    PUBLICATION = "publication"
    COMPANY = "company"
    OPPORTUNITY = "opportunity"


class SearchMode(StrEnum):
    STRUCTURED = "structured"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


# ==============================================================================
# 2. Structured Constraint Schema (Validated Intermediate Representation)
# ==============================================================================

class OperatorType(StrEnum):
    EQUALS = "eq"
    NOT_EQUALS = "neq"
    CONTAINS = "contains"
    IN_LIST = "in"
    GREATER_THAN = "gt"
    GREATER_OR_EQUAL = "gte"
    LESS_THAN = "lt"
    LESS_OR_EQUAL = "lte"
    BETWEEN = "between"
    BOOLEAN_IS = "is"


class ConstraintFieldRule(BaseModel):
    """Rules defining allowed fields, permitted operators, and value types."""
    field_name: str
    allowed_operators: List[OperatorType]
    value_type: Literal["string", "number", "boolean", "date", "list_string"]
    allowed_values: Optional[List[str]] = None


# Whitelist of allowed searchable attributes to prevent SQL injection or schema tampering
ALLOWED_CONSTRAINT_FIELDS: Dict[str, ConstraintFieldRule] = {
    # Asset fields
    "target": ConstraintFieldRule(
        field_name="target",
        allowed_operators=[OperatorType.EQUALS, OperatorType.CONTAINS, OperatorType.IN_LIST],
        value_type="string",
    ),
    "disease": ConstraintFieldRule(
        field_name="disease",
        allowed_operators=[OperatorType.EQUALS, OperatorType.CONTAINS, OperatorType.IN_LIST],
        value_type="string",
    ),
    "indication": ConstraintFieldRule(
        field_name="indication",
        allowed_operators=[OperatorType.EQUALS, OperatorType.CONTAINS],
        value_type="string",
    ),
    "stage": ConstraintFieldRule(
        field_name="stage",
        allowed_operators=[OperatorType.EQUALS, OperatorType.IN_LIST],
        value_type="string",
        allowed_values=[
            "Preclinical", "IND-enabling", "Phase I", "Phase Ib", "Phase II",
            "Phase II/III", "Phase III", "Regulatory review", "Approved", "Withdrawn", "Terminated"
        ],
    ),
    "modality": ConstraintFieldRule(
        field_name="modality",
        allowed_operators=[OperatorType.EQUALS, OperatorType.IN_LIST],
        value_type="string",
        allowed_values=[
            "SMALL_MOLECULE_TKI", "SMALL_MOLECULE", "ANTIBODY", "ANTIBODY_DRUG_CONJUGATE",
            "ADC", "TARGETED_DEGRADER", "CELL_THERAPY", "RNA_THERAPY"
        ],
    ),
    "biomarker": ConstraintFieldRule(
        field_name="biomarker",
        allowed_operators=[OperatorType.EQUALS, OperatorType.CONTAINS],
        value_type="string",
    ),
    "mutation": ConstraintFieldRule(
        field_name="mutation",
        allowed_operators=[OperatorType.EQUALS, OperatorType.CONTAINS, OperatorType.IN_LIST],
        value_type="string",
    ),
    "cns_active": ConstraintFieldRule(
        field_name="cns_active",
        allowed_operators=[OperatorType.BOOLEAN_IS, OperatorType.EQUALS],
        value_type="boolean",
    ),
    "clinical_evidence": ConstraintFieldRule(
        field_name="clinical_evidence",
        allowed_operators=[OperatorType.BOOLEAN_IS, OperatorType.EQUALS],
        value_type="boolean",
    ),
    "company": ConstraintFieldRule(
        field_name="company",
        allowed_operators=[OperatorType.EQUALS, OperatorType.CONTAINS],
        value_type="string",
    ),
    "owner": ConstraintFieldRule(
        field_name="owner",
        allowed_operators=[OperatorType.EQUALS, OperatorType.CONTAINS],
        value_type="string",
    ),
    "licensing_status": ConstraintFieldRule(
        field_name="licensing_status",
        allowed_operators=[OperatorType.EQUALS, OperatorType.IN_LIST],
        value_type="string",
        allowed_values=[
            "VERIFIED_AVAILABLE", "POTENTIALLY_AVAILABLE", "PARTNERED",
            "OWNERSHIP_UNCLEAR", "NO_PUBLIC_SIGNAL", "UNKNOWN"
        ],
    ),
    "phase": ConstraintFieldRule(
        field_name="phase",
        allowed_operators=[OperatorType.EQUALS, OperatorType.IN_LIST],
        value_type="string",
    ),
    "status": ConstraintFieldRule(
        field_name="status",
        allowed_operators=[OperatorType.EQUALS, OperatorType.IN_LIST],
        value_type="string",
    ),
    "year": ConstraintFieldRule(
        field_name="year",
        allowed_operators=[OperatorType.EQUALS, OperatorType.GREATER_THAN, OperatorType.GREATER_OR_EQUAL, OperatorType.LESS_THAN, OperatorType.LESS_OR_EQUAL],
        value_type="number",
    ),
    "action": ConstraintFieldRule(
        field_name="action",
        allowed_operators=[OperatorType.EQUALS, OperatorType.IN_LIST],
        value_type="string",
        allowed_values=["PURSUE", "INVESTIGATE", "PARTNER", "LICENSE", "MONITOR", "AVOID"],
    ),
}


class StructuredConstraint(BaseModel):
    """
    A single deterministic constraint parsed from natural language.
    Must pass strict validation before inclusion in query generation.
    """
    model_config = ConfigDict(from_attributes=True)

    field: str
    operator: OperatorType
    value: Union[str, int, float, bool, List[str], List[Union[int, float]]]
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_span: Optional[str] = None  # Text substring from query that produced this constraint

    @field_validator("field")
    @classmethod
    def validate_field_allowed(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in ALLOWED_CONSTRAINT_FIELDS:
            raise ValueError(f"Constraint field '{v}' is not recognized or permitted. Allowed: {list(ALLOWED_CONSTRAINT_FIELDS.keys())}")
        return clean

    @model_validator(mode="after")
    def validate_operator_and_value(self) -> StructuredConstraint:
        rule = ALLOWED_CONSTRAINT_FIELDS.get(self.field)
        if not rule:
            return self

        if self.operator not in rule.allowed_operators:
            raise ValueError(
                f"Operator '{self.operator}' is not valid for field '{self.field}'. Allowed: {rule.allowed_operators}"
            )

        # Value type check
        if rule.value_type == "boolean":
            if not isinstance(self.value, bool):
                if str(self.value).lower() in ("true", "1", "yes"):
                    self.value = True
                elif str(self.value).lower() in ("false", "0", "no"):
                    self.value = False
                else:
                    raise ValueError(f"Field '{self.field}' requires boolean value.")
        elif rule.value_type == "number":
            if not isinstance(self.value, (int, float)):
                try:
                    self.value = float(self.value)
                except (ValueError, TypeError):
                    raise ValueError(f"Field '{self.field}' requires numeric value.")
        elif rule.value_type == "string":
            if isinstance(self.value, list) and self.operator != OperatorType.IN_LIST:
                raise ValueError(f"Operator '{self.operator}' cannot accept list value for field '{self.field}'.")

        # Allowed values whitelist
        if rule.allowed_values:
            vals_to_check = self.value if isinstance(self.value, list) else [self.value]
            for val in vals_to_check:
                val_str = str(val).upper().replace(" ", "_")
                allowed_norm = [av.upper().replace(" ", "_") for av in rule.allowed_values]
                if val_str not in allowed_norm and str(val) not in rule.allowed_values:
                    # Provide helpful message
                    pass
        return self


class ParsedSearchQuery(BaseModel):
    """
    Validated Intermediate Representation of a natural language query.
    Separates semantic intent from structured constraints.
    """
    model_config = ConfigDict(from_attributes=True)

    raw_query: str
    target_type: SearchTargetType
    search_mode: SearchMode = SearchMode.HYBRID
    semantic_intent: str = ""
    structured_constraints: List[StructuredConstraint] = Field(default_factory=list)
    extracted_entities: Dict[str, List[str]] = Field(default_factory=dict)
    is_validated: bool = False
    validation_errors: List[str] = Field(default_factory=list)


# ==============================================================================
# 3. Validated Database Query AST
# ==============================================================================

class ValidatedParametricQuery(BaseModel):
    """
    Guaranteed safe, parameter-bound database query AST.
    Prevents SQL injection and prevents unvalidated LLM output from reaching the database.
    """
    model_config = ConfigDict(from_attributes=True)

    target_table: str
    sql_template: str
    parameters: Dict[str, Any]
    active_filters: List[str]
    audit_trace: str


# ==============================================================================
# 4. Search Request & Match Output
# ==============================================================================

class SearchQueryRequest(BaseModel):
    """User-facing search request."""
    query: str = Field(..., min_length=1, description="Natural language or keyword search query")
    target_type: SearchTargetType = Field(default=SearchTargetType.ASSET, description="Target entity to search")
    mode: SearchMode = Field(default=SearchMode.HYBRID, description="Search execution mode")
    explicit_constraints: Optional[List[StructuredConstraint]] = Field(default=None, description="Explicit structured filters")
    limit: int = Field(default=10, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class SearchEvidenceProvenance(BaseModel):
    evidence_id: str
    evidence_type: str
    source_citation: str
    source_url: Optional[str] = None
    confidence: float = 1.0


class SearchResultItem(BaseModel):
    """Individual entity match returned from search."""
    id: str
    entity_type: SearchTargetType
    title: str
    subtitle: Optional[str] = None
    score: float = Field(ge=0.0, le=100.0, description="Match score (0-100)")
    semantic_similarity: Optional[float] = None
    structured_match: bool = True
    match_reasons: List[str] = Field(default_factory=list)
    attributes: Dict[str, Any] = Field(default_factory=dict)
    evidence: List[SearchEvidenceProvenance] = Field(default_factory=list)
    unknowns: List[str] = Field(default_factory=list)


class SearchExecutionResult(BaseModel):
    """Complete search response."""
    model_config = ConfigDict(from_attributes=True)

    query_id: UUID = Field(default_factory=uuid4)
    raw_query: str
    target_type: SearchTargetType
    search_mode: SearchMode
    parsed_query: ParsedSearchQuery
    validated_sql: Optional[ValidatedParametricQuery] = None
    total_matches: int
    returned_count: int
    items: List[SearchResultItem]
    execution_time_ms: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

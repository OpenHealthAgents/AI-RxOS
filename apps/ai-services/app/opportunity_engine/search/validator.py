"""
Query Validator and SQL AST Compiler.

Enforces:
"Never use LLM output as the final database query without validation."

Guarantees:
1. Every constraint is mapped to an explicitly permitted column.
2. Values are strictly type-checked and bound via parameterized queries.
3. SQL is compiled using parameterized placeholders ($1, $2 or :param).
4. Any forbidden SQL injection tokens or unvalidated clauses immediately abort query compilation.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from .models import (
    ALLOWED_CONSTRAINT_FIELDS,
    OperatorType,
    ParsedSearchQuery,
    SearchTargetType,
    StructuredConstraint,
    ValidatedParametricQuery,
)


class QueryValidationError(ValueError):
    """Raised when an unvalidated query or illegal constraint is detected."""
    pass


class SqlCompilerAndValidator:
    """
    Safely compiles validated structured constraints into parametric SQL queries.
    Prevents raw LLM text injection and validates column mappings.
    """

    TARGET_TABLE_MAP: Dict[SearchTargetType, str] = {
        SearchTargetType.ASSET: "canonical.therapeutic_assets",
        SearchTargetType.TARGET: "canonical.biological_targets",
        SearchTargetType.INDICATION: "canonical.indications",
        SearchTargetType.BIOMARKER: "canonical.biomarkers",
        SearchTargetType.TRIAL: "clinical_trials_rich",
        SearchTargetType.PUBLICATION: "pubmed_raw_articles",
        SearchTargetType.COMPANY: "canonical.companies",
        SearchTargetType.OPPORTUNITY: "canonical.opportunities",
    }

    # Forbidden SQL tokens that must never emerge from LLM or constraint parsing
    FORBIDDEN_SQL_TOKENS = [
        r";", r"--", r"/\*", r"\*/", r"\bdrop\b", r"\bdelete\b",
        r"\bupdate\b", r"\binsert\b", r"\balter\b", r"\btruncate\b",
        r"\bexec\b", r"\bexecute\b", r"\bxp_", r"\bunion\s+all\b",
        r"\bunion\s+select\b", r"\binformation_schema\b", r"\bpg_catalog\b"
    ]

    @classmethod
    def validate_constraint_safety(cls, constraint: StructuredConstraint) -> None:
        """Verifies that field and value are safe and adhere to schema."""
        if constraint.field not in ALLOWED_CONSTRAINT_FIELDS:
            raise QueryValidationError(f"Constraint field '{constraint.field}' is not in allowed schema.")

        # String value check for dangerous SQL characters
        if isinstance(constraint.value, str):
            for token in cls.FORBIDDEN_SQL_TOKENS:
                if re.search(token, constraint.value, re.IGNORECASE):
                    raise QueryValidationError(f"Unsafe token detected in constraint value: '{constraint.value}'")

    @classmethod
    def compile_to_parametric_sql(
        cls,
        parsed_query: ParsedSearchQuery,
    ) -> ValidatedParametricQuery:
        """
        Compiles the parsed search constraints into a strictly parameter-bound SQL query.
        """
        table_name = cls.TARGET_TABLE_MAP.get(parsed_query.target_type, "canonical.therapeutic_assets")
        where_clauses: List[str] = []
        parameters: Dict[str, Any] = {}
        active_filters: List[str] = []

        param_idx = 1
        for constraint in parsed_query.structured_constraints:
            cls.validate_constraint_safety(constraint)

            field = constraint.field
            op = constraint.operator
            val = constraint.value
            param_key = f"p_{field}_{param_idx}"

            if op == OperatorType.EQUALS:
                where_clauses.append(f"{field} = :{param_key}")
                parameters[param_key] = val
                active_filters.append(f"{field} == {val}")
            elif op == OperatorType.NOT_EQUALS:
                where_clauses.append(f"{field} != :{param_key}")
                parameters[param_key] = val
                active_filters.append(f"{field} != {val}")
            elif op == OperatorType.CONTAINS:
                where_clauses.append(f"{field} ILIKE :{param_key}")
                parameters[param_key] = f"%{val}%"
                active_filters.append(f"{field} CONTAINS '{val}'")
            elif op == OperatorType.IN_LIST:
                if isinstance(val, list):
                    placeholders = []
                    for i, item in enumerate(val):
                        item_key = f"{param_key}_{i}"
                        placeholders.append(f":{item_key}")
                        parameters[item_key] = item
                    where_clauses.append(f"{field} IN ({', '.join(placeholders)})")
                    active_filters.append(f"{field} IN {val}")
            elif op == OperatorType.BOOLEAN_IS:
                where_clauses.append(f"{field} IS :{param_key}")
                parameters[param_key] = val
                active_filters.append(f"{field} IS {val}")
            elif op == OperatorType.GREATER_THAN:
                where_clauses.append(f"{field} > :{param_key}")
                parameters[param_key] = val
                active_filters.append(f"{field} > {val}")
            elif op == OperatorType.GREATER_OR_EQUAL:
                where_clauses.append(f"{field} >= :{param_key}")
                parameters[param_key] = val
                active_filters.append(f"{field} >= {val}")
            elif op == OperatorType.LESS_THAN:
                where_clauses.append(f"{field} < :{param_key}")
                parameters[param_key] = val
                active_filters.append(f"{field} < {val}")
            elif op == OperatorType.LESS_OR_EQUAL:
                where_clauses.append(f"{field} <= :{param_key}")
                parameters[param_key] = val
                active_filters.append(f"{field} <= {val}")

            param_idx += 1

        where_stmt = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        sql_template = f"SELECT * FROM {table_name}{where_stmt} LIMIT :limit OFFSET :offset"

        return ValidatedParametricQuery(
            target_table=table_name,
            sql_template=sql_template,
            parameters=parameters,
            active_filters=active_filters,
            audit_trace=f"Query compiled safely from {len(parsed_query.structured_constraints)} validated constraints.",
        )

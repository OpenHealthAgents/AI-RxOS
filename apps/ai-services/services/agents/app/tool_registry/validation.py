from __future__ import annotations

from typing import Any

from app.core.errors import AIPlatformError


class SchemaValidationError(AIPlatformError):
    def __init__(self, message: str) -> None:
        super().__init__(
            message, code="SCHEMA_VALIDATION_ERROR", operation="tool_validation"
        )


def validate_json_schema(
    value: Any,
    schema: dict[str, Any],
    path: str = "$",
    *,
    _root: dict[str, Any] | None = None,
) -> None:
    """Validate the JSON Schema subset used by MCP tool definitions."""
    root = _root or schema
    if "$ref" in schema:
        ref = schema["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/"):
            raise SchemaValidationError(f"{path}: unsupported schema reference")
        target: Any = root
        for part in ref[2:].split("/"):
            target = target[part]
        validate_json_schema(value, target, path, _root=root)
        return

    if "const" in schema and value != schema["const"]:
        raise SchemaValidationError(f"{path}: expected {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise SchemaValidationError(f"{path}: value is not one of the allowed values")
    if "anyOf" in schema and not any(
        _valid(value, option, root, path) for option in schema["anyOf"]
    ):
        raise SchemaValidationError(f"{path}: does not match any allowed schema")
    if (
        "oneOf" in schema
        and sum(_valid(value, option, root, path) for option in schema["oneOf"]) != 1
    ):
        raise SchemaValidationError(f"{path}: does not match exactly one schema")
    if "allOf" in schema:
        for option in schema["allOf"]:
            validate_json_schema(value, option, path, _root=root)

    schema_type = schema.get("type")
    if schema_type == "object":
        if not isinstance(value, dict):
            raise SchemaValidationError(f"{path}: expected object")
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                raise SchemaValidationError(f"{path}.{name}: field is required")
        if schema.get("additionalProperties") is False:
            unknown = set(value) - set(properties)
            if unknown:
                raise SchemaValidationError(
                    f"{path}: unexpected fields {', '.join(sorted(unknown))}"
                )
        for name, child_schema in properties.items():
            if name in value:
                validate_json_schema(
                    value[name], child_schema, f"{path}.{name}", _root=root
                )
    elif schema_type == "array":
        if not isinstance(value, list):
            raise SchemaValidationError(f"{path}: expected array")
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise SchemaValidationError(f"{path}: too few items")
        for index, item in enumerate(value):
            validate_json_schema(
                item, schema.get("items", {}), f"{path}[{index}]", _root=root
            )
    elif schema_type == "string" and not isinstance(value, str):
        raise SchemaValidationError(f"{path}: expected string")
    elif schema_type == "integer" and (
        not isinstance(value, int) or isinstance(value, bool)
    ):
        raise SchemaValidationError(f"{path}: expected integer")
    elif schema_type == "number" and (
        not isinstance(value, (int, float)) or isinstance(value, bool)
    ):
        raise SchemaValidationError(f"{path}: expected number")
    elif schema_type == "boolean" and not isinstance(value, bool):
        raise SchemaValidationError(f"{path}: expected boolean")
    elif schema_type == "null" and value is not None:
        raise SchemaValidationError(f"{path}: expected null")

    if (
        isinstance(value, str)
        and "minLength" in schema
        and len(value) < schema["minLength"]
    ):
        raise SchemaValidationError(f"{path}: string is too short")


def _valid(value: Any, schema: dict[str, Any], root: dict[str, Any], path: str) -> bool:
    try:
        validate_json_schema(value, schema, path, _root=root)
    except SchemaValidationError:
        return False
    return True

from __future__ import annotations

import inspect
import asyncio
from typing import Any

from app.tool_registry.schemas import ToolDefinition, ToolExecutionResult, ToolHandler
from app.tool_registry.validation import SchemaValidationError, validate_json_schema
from app.core.errors import AIPlatformError, TimeoutError as PlatformTimeoutError


class ToolNotFoundError(AIPlatformError):
    def __init__(self, name: str) -> None:
        super().__init__(f"tool not found: {name}", code="TOOL_NOT_FOUND", operation="tool_lookup", details={"tool": name})


class ToolExecutionError(AIPlatformError):
    pass


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        schema: dict[str, Any],
        handler: ToolHandler,
        *,
        output_schema: dict[str, Any] | None = None,
        description: str = "",
        source: str = "local",
        timeout_seconds: float = 30,
    ) -> ToolDefinition:
        if name in self._tools:
            raise ValueError(f"tool already registered: {name}")
        definition = ToolDefinition(
            name=name,
            input_schema=schema,
            output_schema=output_schema,
            handler=handler,
            description=description,
            source=source,
            timeout_seconds=timeout_seconds,
        )
        self._tools[name] = definition
        return definition

    def get(self, name: str) -> ToolDefinition:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolNotFoundError(name) from exc

    def list_tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    async def execute(self, name: str, arguments: dict[str, Any]) -> ToolExecutionResult:
        definition = self.get(name)
        validate_json_schema(arguments, definition.input_schema)
        try:
            if inspect.iscoroutinefunction(definition.handler):
                result = await asyncio.wait_for(
                    definition.handler(arguments), timeout=definition.timeout_seconds
                )
            else:
                result = await asyncio.wait_for(
                    asyncio.to_thread(definition.handler, arguments), timeout=definition.timeout_seconds
                )
                if inspect.isawaitable(result):
                    result = await asyncio.wait_for(result, timeout=definition.timeout_seconds)
        except asyncio.TimeoutError as exc:
            raise PlatformTimeoutError("tool_call", details={"tool": name}) from exc
        except AIPlatformError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ToolExecutionError(f"tool {name} failed: {exc}", code="TOOL_EXECUTION_ERROR", operation="tool_call", retriable=False, details={"tool": name}) from exc
        if definition.output_schema is not None:
            validate_json_schema(result, definition.output_schema, path="$.result")
        return ToolExecutionResult(name=name, result=result, source=definition.source)
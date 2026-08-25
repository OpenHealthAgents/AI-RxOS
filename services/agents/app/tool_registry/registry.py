from __future__ import annotations

import asyncio
import inspect
from typing import Any, Literal, cast

from app.core.errors import AIPlatformError
from app.core.errors import TimeoutError as PlatformTimeoutError
from app.core.security import AuthorizationService, TenantContext
from app.tool_registry.schemas import (
    ToolDefinition,
    ToolExecutionResult,
    ToolHandler,
    current_execution_id,
)
from app.tool_registry.validation import validate_json_schema


class ToolNotFoundError(AIPlatformError):
    def __init__(self, name: str) -> None:
        super().__init__(
            f"tool not found: {name}",
            code="TOOL_NOT_FOUND",
            operation="tool_lookup",
            details={"tool": name},
        )


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
        allowed_agents: set[str] | frozenset[str] | None = None,
        required_permissions: set[str] | frozenset[str] | None = None,
        allowed_organizations: set[str] | frozenset[str] | None = None,
        allowed_workspaces: set[str] | frozenset[str] | None = None,
        retry_mode: str = "non_idempotent",
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
            allowed_agents=frozenset(allowed_agents or ()),
            required_permissions=frozenset(required_permissions or ()),
            allowed_organizations=frozenset(allowed_organizations or ()),
            allowed_workspaces=frozenset(allowed_workspaces or ()),
            retry_mode=cast(
                Literal["idempotent", "non_idempotent", "requires_idempotency_key"],
                retry_mode,
            ),
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

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        agent_name: str | None = None,
        permissions: set[str] | frozenset[str] = frozenset(),
        tenant: TenantContext | None = None,
        execution_key: str | None = None,
        execution_id: str | None = None,
    ) -> ToolExecutionResult:
        definition = self.get(name)
        authorization = AuthorizationService()
        if tenant is None or not authorization.can_execute_tool(
            tenant,
            agent_name,
            definition.allowed_agents,
            definition.required_permissions,
        ):
            raise AIPlatformError(
                f"agent is not authorized for tool {name}",
                code="TOOL_NOT_AUTHORIZED",
                operation="tool_authorization",
                retriable=False,
                details={"tool": name, "agent": agent_name},
            )
        effective_permissions = frozenset(permissions)
        if tenant is not None:
            effective_permissions |= tenant.permissions
        if not definition.required_permissions.issubset(effective_permissions):
            raise AIPlatformError(
                f"missing permissions for tool {name}",
                code="TOOL_NOT_AUTHORIZED",
                operation="tool_authorization",
                retriable=False,
                details={"tool": name},
            )
        if (
            definition.allowed_organizations
            and tenant.organization_id not in definition.allowed_organizations
        ):
            raise AIPlatformError(
                f"tenant is not authorized for tool {name}",
                code="TOOL_NOT_AUTHORIZED",
                operation="tool_authorization",
                retriable=False,
                details={"tool": name},
            )
        if (
            definition.allowed_workspaces
            and tenant.workspace_id not in definition.allowed_workspaces
        ):
            raise AIPlatformError(
                f"workspace is not authorized for tool {name}",
                code="TOOL_NOT_AUTHORIZED",
                operation="tool_authorization",
                retriable=False,
                details={"tool": name},
            )
        if definition.retry_mode == "requires_idempotency_key" and not execution_key:
            raise AIPlatformError(
                f"tool {name} requires an idempotency key",
                code="TOOL_NOT_AUTHORIZED",
                operation="tool_authorization",
                retriable=False,
                details={"tool": name},
            )
        validate_json_schema(arguments, definition.input_schema)
        execution_token = current_execution_id.set(execution_id)
        try:
            if inspect.iscoroutinefunction(definition.handler):
                result = await asyncio.wait_for(
                    definition.handler(arguments), timeout=definition.timeout_seconds
                )
            else:
                result = await asyncio.wait_for(
                    asyncio.to_thread(definition.handler, arguments),
                    timeout=definition.timeout_seconds,
                )
                if inspect.isawaitable(result):
                    result = await asyncio.wait_for(
                        result, timeout=definition.timeout_seconds
                    )
        except asyncio.TimeoutError as exc:
            raise PlatformTimeoutError("tool_call", details={"tool": name}) from exc
        except AIPlatformError:
            raise
        except Exception as exc:
            raise ToolExecutionError(
                f"tool {name} failed: {exc}",
                code="TOOL_EXECUTION_ERROR",
                operation="tool_call",
                retriable=False,
                details={"tool": name},
            ) from exc
        finally:
            current_execution_id.reset(execution_token)
        if definition.output_schema is not None:
            validate_json_schema(result, definition.output_schema, path="$.result")
        return ToolExecutionResult(name=name, result=result, source=definition.source)

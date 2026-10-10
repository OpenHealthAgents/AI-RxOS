from __future__ import annotations

import asyncio
import inspect
from typing import Any, Literal, cast

from app.core.errors import AIPlatformError
from app.core.errors import TimeoutError as PlatformTimeoutError
from app.core.security import AuthorizationService, TenantContext
from app.tool_registry.schemas import (
    ToolDefinition,
    ToolExecutionContext,
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


class ToolExecutor:
    """Reusable tool execution abstraction aligned with the generic Agent Harness pattern.

    This class keeps the execution flow explicit and reusable while preserving the
    stronger production controls already present in the Prompt 9 registry.
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

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
        request_id: str | None = None,
        correlation_id: str | None = None,
        context: ToolExecutionContext | None = None,
    ) -> ToolExecutionResult:
        resolved_context = context or ToolExecutionContext(
            tool_name=name,
            agent_name=agent_name,
            tenant=tenant,
            execution_key=execution_key,
            execution_id=execution_id,
            request_id=request_id,
            correlation_id=correlation_id,
            workspace_id=getattr(tenant, "workspace_id", None),
            project_id=getattr(tenant, "project_id", None),
        )
        effective_agent_name = agent_name or resolved_context.agent_name
        effective_tenant = tenant or resolved_context.tenant
        effective_execution_key = execution_key or resolved_context.execution_key
        effective_execution_id = execution_id or resolved_context.execution_id
        definition = self.registry.get(name)

        authorization = AuthorizationService()
        if effective_tenant is None or not authorization.can_execute_tool(
            effective_tenant,
            effective_agent_name,
            definition.allowed_agents,
            definition.required_permissions,
        ):
            raise AIPlatformError(
                f"agent is not authorized for tool {name}",
                code="TOOL_NOT_AUTHORIZED",
                operation="tool_authorization",
                retriable=False,
                details={"tool": name, "agent": effective_agent_name},
            )

        effective_permissions = frozenset(permissions)
        if effective_tenant is not None:
            effective_permissions |= effective_tenant.permissions
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
            and effective_tenant is not None
            and effective_tenant.organization_id not in definition.allowed_organizations
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
            and effective_tenant is not None
            and effective_tenant.workspace_id not in definition.allowed_workspaces
        ):
            raise AIPlatformError(
                f"workspace is not authorized for tool {name}",
                code="TOOL_NOT_AUTHORIZED",
                operation="tool_authorization",
                retriable=False,
                details={"tool": name},
            )
        if definition.retry_mode == "requires_idempotency_key" and not effective_execution_key:
            raise AIPlatformError(
                f"tool {name} requires an idempotency key",
                code="TOOL_NOT_AUTHORIZED",
                operation="tool_authorization",
                retriable=False,
                details={"tool": name},
            )

        validate_json_schema(arguments, definition.input_schema)
        execution_token = current_execution_id.set(effective_execution_id)
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


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self.executor = ToolExecutor(self)

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
        request_id: str | None = None,
        correlation_id: str | None = None,
        context: ToolExecutionContext | None = None,
    ) -> ToolExecutionResult:
        return await self.executor.execute(
            name,
            arguments,
            agent_name=agent_name,
            permissions=permissions,
            tenant=tenant,
            execution_key=execution_key,
            execution_id=execution_id,
            request_id=request_id,
            correlation_id=correlation_id,
            context=context,
        )

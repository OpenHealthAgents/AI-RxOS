from __future__ import annotations

from typing import Any

_SAFE_KEYS = {
    "type",
    "run_id",
    "job_id",
    "task_id",
    "execution_id",
    "worker_id",
    "request_id",
    "correlation_id",
    "trace_id",
    "node",
    "next_node",
    "attempt",
    "retry_count",
    "retry_mode",
    "name",
    "tool_call_id",
    "model",
    "provider",
    "status",
    "duration_ms",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "stage",
    "error_category",
    "error",
}

_EVENT_TYPES = {
    "run_started",
    "run_error",
    "run_completed",
    "node_started",
    "node_error",
    "node_completed",
    "model_usage",
    "model_output",
    "token",
    "tool_call",
    "tool_result",
    "mcp_tool_chunk",
    "intermediate_step",
    "memory_snapshot",
    "owned",
    "job_queued",
    "job_claimed",
    "job_started",
    "job_retrying",
    "job_recovered",
    "job_completed",
    "job_failed",
    "job_cancelled",
    "job_timeout",
}


def sanitize_exception(exc: BaseException) -> dict[str, str]:
    code = getattr(exc, "code", None)
    if isinstance(code, str):
        category = code.lower()
    elif isinstance(exc, PermissionError):
        category = "authorization"
    elif isinstance(exc, (ValueError, TypeError)):
        category = "validation"
    elif isinstance(exc, TimeoutError):
        category = "timeout"
    else:
        category = "internal"
    return {"error_category": category, "error": "operation failed"}


def redact_mapping(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key in _SAFE_KEYS and _is_safe_value(key, value)
    }


def redact_event(event: dict[str, Any]) -> dict[str, Any]:
    event_type = event.get("type")
    if not isinstance(event_type, str) or event_type not in _EVENT_TYPES:
        return {"type": "agent_event", "status": "accepted"}
    result = redact_mapping(event)
    result["type"] = event_type
    if "error" in event:
        result.update({"error_category": "internal", "error": "operation failed"})
    elif isinstance(event.get("error_category"), str):
        result["error_category"] = event["error_category"]
    if event_type in {"model_output", "token", "tool_result", "mcp_tool_chunk"}:
        result["status"] = "completed"
    if event_type == "intermediate_step":
        result["status"] = "in_progress"
    return result


def sanitize_tool_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return redact_mapping(metadata)


def sanitize_stream_event(event: dict[str, Any]) -> dict[str, Any]:
    return redact_event(event)


def sanitize_task_payload(task: Any) -> dict[str, Any]:
    """Return only operational metadata suitable for Redis task state."""
    return {
        "id": str(getattr(task, "id", "")),
        "job_type": getattr(task, "job_type", "agent.invoke"),
        "agentType": str(getattr(task, "agentType", "")),
        "status": getattr(task, "status", "failed"),
        "progress": {
            "current_step": getattr(getattr(task, "progress", None), "current_step", None),
            "completed_steps": getattr(getattr(task, "progress", None), "completed_steps", 0),
            "total_steps": getattr(getattr(task, "progress", None), "total_steps", None),
            "total_steps_status": getattr(getattr(task, "progress", None), "total_steps_status", "in_progress"),
        },
        "tenant": getattr(task, "tenant", {}),
        "retry_count": getattr(task, "retry_count", 0),
        "created_at": getattr(task, "created_at", None),
        "started_at": getattr(task, "started_at", None),
        "completed_at": getattr(task, "completed_at", None),
        "error": "operation failed" if getattr(task, "error", None) else None,
        "request_id": getattr(task, "request_id", None),
        "correlation_id": getattr(task, "correlation_id", None),
        "retry_allowed": getattr(task, "retry_allowed", True),
    }


def _is_safe_value(key: str, value: Any) -> bool:
    if key in {"type", "node", "next_node", "name", "model", "provider", "status", "stage", "retry_mode", "error_category", "error"}:
        return isinstance(value, str)
    if key in {"run_id", "job_id", "task_id", "execution_id", "worker_id", "request_id", "correlation_id", "trace_id", "tool_call_id"}:
        return isinstance(value, str)
    if key in {"attempt", "retry_count", "input_tokens", "output_tokens", "total_tokens"}:
        return isinstance(value, int) and value >= 0
    if key == "duration_ms":
        return isinstance(value, (int, float)) and value >= 0
    return False

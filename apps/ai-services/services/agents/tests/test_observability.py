from __future__ import annotations

from app.core.observability import CostCalculator, ModelUsage, new_context
from app.security.redaction import redact_event, sanitize_exception


def test_usage_is_best_effort_and_cost_is_optional():
    usage = ModelUsage.from_raw(
        {"usage": {"prompt_tokens": 10, "completion_tokens": 5}}
    )
    assert usage is not None
    assert usage.total_tokens == 15
    assert (
        CostCalculator(
            '{"openai/gpt-test":{"input_per_million":1,"output_per_million":2}}'
        ).estimate("openai", "gpt-test", usage)
        == 0.00002
    )
    assert CostCalculator().estimate("openai", "unknown", usage) is None
    assert ModelUsage.from_raw({"choices": []}) is None


def test_execution_context_uses_opaque_identifiers():
    context = new_context()
    assert len(context.request_id) > 20
    assert len(context.correlation_id) > 20
    assert "prompt" not in context.request_id.lower()


def test_redaction_removes_sensitive_event_payloads():
    event = redact_event(
        {
            "type": "model_output",
            "model": "configured-model",
            "content": "secret model response",
            "prompt": "secret user prompt",
            "tool_args": {"secret": "value"},
            "tool_result": "secret result",
        }
    )

    assert event == {
        "type": "model_output",
        "model": "configured-model",
        "status": "completed",
    }
    assert "secret model response" not in str(event)


def test_exception_sanitization_does_not_expose_message():
    safe = sanitize_exception(RuntimeError("database password=secret"))

    assert safe == {"error_category": "internal", "error": "operation failed"}
    assert "secret" not in str(safe)

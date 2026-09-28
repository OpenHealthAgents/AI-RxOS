from __future__ import annotations

import importlib
import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

otel_propagate: Any = None
otel_trace: Any = None
OtelResource: Any = None
OtelTracerProvider: Any = None
OtelBatchSpanProcessor: Any = None
OtelSpanExporter: Any = None
OtelSpanKind: Any = None

try:
    otel_propagate = importlib.import_module("opentelemetry.propagate")
    otel_trace = importlib.import_module("opentelemetry.trace")
    OtelSpanExporter = importlib.import_module(
        "opentelemetry.exporter.otlp.proto.http.trace_exporter"
    ).OTLPSpanExporter
    OtelResource = importlib.import_module("opentelemetry.sdk.resources").Resource
    OtelTracerProvider = importlib.import_module(
        "opentelemetry.sdk.trace"
    ).TracerProvider
    OtelBatchSpanProcessor = importlib.import_module(
        "opentelemetry.sdk.trace.export"
    ).BatchSpanProcessor
    OtelSpanKind = otel_trace.SpanKind
except ImportError:  # pragma: no cover
    pass

propagate: Any = otel_propagate
trace: Any = otel_trace
Resource: Any = OtelResource
TracerProvider: Any = OtelTracerProvider
BatchSpanProcessor: Any = OtelBatchSpanProcessor
OTLPSpanExporter: Any = OtelSpanExporter
SpanKind: Any = OtelSpanKind


@dataclass(frozen=True)
class ExecutionContext:
    request_id: str
    correlation_id: str
    traceparent: str | None = None


_current: ContextVar[ExecutionContext | None] = ContextVar(
    "agent_execution_context", default=None
)


def new_context(
    request_id: str | None = None, correlation_id: str | None = None
) -> ExecutionContext:
    return ExecutionContext(
        request_id=request_id or str(uuid.uuid4()),
        correlation_id=correlation_id or str(uuid.uuid4()),
    )


def set_context(context: ExecutionContext) -> None:
    _current.set(context)


def get_context() -> ExecutionContext | None:
    return _current.get()


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], int] = {}
        self._histograms: dict[
            tuple[str, tuple[tuple[str, str], ...]], list[float]
        ] = {}

    @staticmethod
    def _key(
        name: str, labels: dict[str, str]
    ) -> tuple[str, tuple[tuple[str, str], ...]]:
        return name, tuple(sorted(labels.items()))

    def inc(self, name: str, **labels: str) -> None:
        key = self._key(name, labels)
        self._counters[key] = self._counters.get(key, 0) + 1

    def observe(self, name: str, value: float, **labels: str) -> None:
        key = self._key(name, labels)
        self._histograms.setdefault(key, []).append(value)

    def render(self) -> str:
        lines: list[str] = []
        for (name, labels), value in sorted(self._counters.items()):
            lines.append(f"{name}{_format_labels(labels)} {value}")
        for (name, labels), values in sorted(self._histograms.items()):
            suffix = _format_labels(labels)
            lines.append(f"{name}_count{suffix} {len(values)}")
            lines.append(f"{name}_sum{suffix} {sum(values)}")
        return "\n".join(lines) + ("\n" if lines else "")


def _format_labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    return "{" + ",".join(f'{key}="{value}"' for key, value in labels) + "}"


@contextmanager
def span(name: str, **attributes: str) -> Iterator[None]:
    if trace is None:
        yield
        return
    tracer = trace.get_tracer("ai-rxos.agents")
    with tracer.start_as_current_span(
        name, kind=SpanKind.INTERNAL, attributes=attributes
    ):
        yield


def inject_trace_context() -> dict[str, str]:
    carrier: dict[str, str] = {}
    if propagate is not None:
        propagate.inject(carrier)
    return carrier


def extract_trace_context(carrier: dict[str, str]) -> None:
    if propagate is not None:
        propagate.extract(carrier)


def configure_tracing(endpoint: str | None = None) -> None:
    if trace is None or TracerProvider is None or not endpoint:
        return
    if trace.get_tracer_provider().__class__.__name__ != "ProxyTracerProvider":
        return
    provider = TracerProvider(
        resource=Resource.create({"service.name": "ai-rxos-agents"})
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)


@dataclass(frozen=True)
class ModelUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @classmethod
    def from_raw(cls, raw: Any) -> ModelUsage | None:
        usage = raw.get("usage") if isinstance(raw, dict) else None
        if not isinstance(usage, dict):
            return None
        input_tokens = usage.get("prompt_tokens", usage.get("input_tokens", 0))
        output_tokens = usage.get("completion_tokens", usage.get("output_tokens", 0))
        if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
            return None
        return cls(max(input_tokens, 0), max(output_tokens, 0))


class CostCalculator:
    def __init__(self, pricing_json: str | None = None) -> None:
        try:
            self.pricing = json.loads(pricing_json) if pricing_json else {}
        except json.JSONDecodeError:
            self.pricing = {}

    def estimate(
        self, provider: str, model: str, usage: ModelUsage | None
    ) -> float | None:
        if usage is None:
            return None
        price = self.pricing.get(f"{provider}/{model}")
        if not isinstance(price, dict):
            return None
        input_rate = price.get("input_per_million")
        output_rate = price.get("output_per_million")
        if not isinstance(input_rate, (int, float)) or not isinstance(
            output_rate, (int, float)
        ):
            return None
        return (
            usage.input_tokens * input_rate + usage.output_tokens * output_rate
        ) / 1_000_000


metrics = MetricsRegistry()
